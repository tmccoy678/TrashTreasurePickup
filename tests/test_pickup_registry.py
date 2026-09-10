#!/usr/bin/env python3

from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pickup_registry.py"
LEGACY_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "treasurepickup_receipt.py"
)
SELECTOR_RE = re.compile(r"^alpha@cp-20260902-125509-[0-9a-f]{8}$")


class PickupRegistryCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.registry = self.workspace / "treasurepickup" / "pickups"
        self.compatibility = (
            self.workspace / "treasurepickup" / "context-resume.json"
        )
        self.handoff = self.workspace / "trashpickup" / "current-context.md"
        self.checkpoint = (
            self.workspace / "trashpickup" / "context-checkpoint.json"
        )
        self.resource = self.workspace / "projects" / "alpha"
        self.handoff.parent.mkdir(parents=True)
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        self.compatibility.parent.mkdir(parents=True)
        self.resource.mkdir(parents=True)
        self.handoff.write_text("# Alpha handoff\n", encoding="utf-8")
        self.checkpoint.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "generated_at": "2026-09-02T12:55:09-05:00",
                    "context_status": "READY",
                    "canonical_handoff": str(self.handoff),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.gitleaks = self.root / "gitleaks"
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)

    def test_standalone_round_trip_without_checkpoint_version(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint.pop("schema_version")
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        completed = json.loads(self.complete_ready(current).stdout)

        self.assertEqual(completed["status"], "READY")
        self.assertFalse(completed["scope"]["phase_authorized"])
        self.assertEqual(
            [item["gate"] for item in completed["transition_evidence"]],
            ["CANONICAL_PAIR_VERIFIED", "LIVE_STATE_VERIFIED"],
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "CONSUMED")

    def test_completion_saves_one_markdown_receipt_with_the_recorded_checks(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)

        completed = json.loads(self.complete_ready(current).stdout)

        markdown_path = Path(completed["markdown_receipt_path"])
        self.assertEqual(markdown_path.parent, self.compatibility.parent / "receipts")
        self.assertEqual(list(markdown_path.parent.iterdir()), [markdown_path])
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("TREASUREPICKUP: DONE", markdown)
        self.assertIn("No authorization for subsequent work", markdown)
        recorded = json.loads(markdown.split("```json\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(recorded, json.loads(Path(completed["receipt_path"]).read_bytes()))
        self.assertFalse(recorded["scope"]["phase_authorized"])
        self.assertEqual(stat.S_IMODE(markdown_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(markdown_path.parent.stat().st_mode), 0o700)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "CONSUMED")

    def test_markdown_save_failure_keeps_the_claim_incomplete(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        markdown_path = self.compatibility.parent / "receipts" / "{}-r{:04d}.md".format(
            current["receipt_id"], current["revision"] + 1
        )
        markdown_path.parent.mkdir(mode=0o700)
        environment = self.fsync_fault_environment(
            "directory-after-link", target=markdown_path.parent, arm_destination=markdown_path
        )

        with mock.patch.dict(os.environ, environment):
            rejected = self.complete_ready(current, expected=3)

        self.assertEqual(rejected.stdout, "")
        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "TRANSACTION_ROLLBACK_FAILED")
        self.assertTrue((self.root / "fsync-fault-fired").is_file())
        self.assertEqual(list(markdown_path.parent.iterdir()), [])
        state = self.inspect(str(package["selector"]))
        self.assertEqual(state["state"], "OPENING")
        self.assertTrue(state["claim_active"])

    def test_aborted_markdown_receipt_does_not_claim_done(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        completed = self.complete_aborted(claimed)

        markdown = Path(completed["markdown_receipt_path"]).read_text(encoding="utf-8")
        self.assertIn("TREASUREPICKUP: ABORTED", markdown)
        self.assertNotIn("TREASUREPICKUP: DONE", markdown)
        recorded = json.loads(markdown.split("```json\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(recorded["drift"], "UNKNOWN")
        self.assertEqual(recorded["status"], "ABORTED")
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW")

    def test_handoff_verifier_reports_only_observed_checks(self) -> None:
        module = self.load_registry_module()
        content = b"# Handoff\n"
        metadata = {"selector": "selected", "handoff_sha256": hashlib.sha256(content).hexdigest()}
        cases = (
            (metadata, "selected", content, "PASS", "NONE", 0),
            (metadata, "selected", content + b"changed", "REVIEW_REQUIRED", "MATERIAL", 1),
            (metadata, "different", content, "REVIEW_REQUIRED", "MATERIAL", 1),
            (metadata, "selected", None, "BLOCKED", "UNKNOWN", 2),
            ({}, "selected", content, "BLOCKED", "UNKNOWN", 2),
            ({"selector": "different"}, "selected", None, "REVIEW_REQUIRED", "MATERIAL", 1),
            ({"selector": [], "handoff_sha256": []}, "selected", content, "BLOCKED", "UNKNOWN", 2),
        )
        for fields, selected, data, status, drift, expected in cases:
            with self.subTest(status=status, drift=drift, selected=selected):
                result, code = module.verify_handoff(fields, selected, data)
                self.assertEqual((result["status"], result["drift"], code), (status, drift, expected))
                self.assertEqual(result["live_state"], "UNKNOWN")
                self.assertFalse(result["phase_authorized"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(
        self,
        *arguments: str,
        expected: int = 0,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                **(extra_env or {}),
            },
        )
        self.assertEqual(completed.returncode, expected, completed.stderr)
        return completed

    def publish(
        self,
        track_id: str = "alpha",
        resource: Path | None = None,
    ) -> dict[str, object]:
        completed = self.publish_result(track_id, resource)
        return json.loads(completed.stdout)

    def publish_result(
        self,
        track_id: str = "alpha",
        resource: Path | None = None,
        *,
        expected: int = 0,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "publish",
            "--registry-root",
            str(self.registry),
            "--track-id",
            track_id,
            "--resource-scope",
            str(resource or self.resource),
            "--handoff",
            str(self.handoff),
            "--checkpoint",
            str(self.checkpoint),
            "--gitleaks-path",
            str(self.gitleaks),
            expected=expected,
            extra_env=extra_env,
        )

    def claim_arguments(self, selector: str | None = None) -> list[str]:
        arguments = [
            "claim",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(self.compatibility),
            "--workspace",
            str(self.workspace),
            "--fresh-task",
            "YES",
            "--freshness-basis",
            "FIRST_SUBSTANTIVE_USER_TURN",
            "--invocation-mode",
            "MANUAL_SKILL_SELECTOR",
            "--model",
            "TEST",
            "--effort",
            "TEST",
            "--skill-file",
            str(SCRIPT.parents[1] / "SKILL.md"),
            "--gitleaks-path",
            str(self.gitleaks),
        ]
        if selector is not None:
            arguments.extend(["--selector", selector])
        return arguments

    def claim(
        self, selector: str | None = None, *, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        return self.run_cli(*self.claim_arguments(selector), expected=expected)

    def test_configured_workspace_and_path_scanner_publish_then_explicit_workspace_claims(self) -> None:
        published = self.run_cli(
            "publish", "--track-id", "alpha", "--resource-scope", str(self.resource),
            "--handoff", str(self.handoff), "--checkpoint", str(self.checkpoint),
            extra_env={"PICKUP_HOME": str(self.workspace), "PATH": str(self.root)},
        )
        selector = json.loads(published.stdout)["selector"]
        arguments = self.claim_arguments(selector)
        for option in ("--registry-root", "--compatibility-output"):
            index = arguments.index(option)
            del arguments[index:index + 2]
        claimed = self.run_cli(*arguments, extra_env={"PICKUP_HOME": str(self.root / "unused")})
        self.assertEqual(json.loads(claimed.stdout)["workspace"], str(self.workspace))
        inspected = self.run_cli("inspect", "--selector", selector, extra_env={"PICKUP_HOME": str(self.workspace)})
        self.assertEqual(json.loads(inspected.stdout)["state"], "CLAIMED")

    def fail_secret_scan(self) -> None:
        self.gitleaks.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)

    def write_valid_legacy_compatibility(self) -> None:
        self.compatibility.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "status": "READY",
                    "drift": "NONE",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.compatibility.chmod(0o600)

    def write_legacy_v3_with_checkpoint_state(
        self, checkpoint_state: str
    ) -> dict[str, object]:
        original = self.checkpoint.read_bytes()
        if checkpoint_state == "missing":
            self.checkpoint.unlink()
        elif checkpoint_state == "nonregular":
            self.checkpoint.unlink()
            self.checkpoint.mkdir()
        elif checkpoint_state == "unsupported":
            self.checkpoint.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "context_status": "HISTORICAL",
                        "generated_at": "historical-value",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            self.fail("unknown legacy checkpoint fixture")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(LEGACY_SCRIPT),
                    "start",
                    "--output",
                    str(self.compatibility),
                    "--workspace",
                    str(self.workspace),
                    "--expected-workspace",
                    str(self.workspace),
                    "--handoff",
                    str(self.handoff),
                    "--checkpoint",
                    str(self.checkpoint),
                    "--skill-file",
                    str(SCRIPT.parents[1] / "SKILL.md"),
                    "--fresh-task",
                    "NO",
                    "--freshness-basis",
                    "PRIOR_TASK_CONTENT",
                    "--invocation-mode",
                    "MANUAL_SKILL_SELECTOR",
                    "--model",
                    "TEST",
                    "--effort",
                    "TEST",
                    "--gitleaks-path",
                    str(self.gitleaks),
                ],
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(self.compatibility.read_text(encoding="utf-8"))
        finally:
            if self.checkpoint.is_dir():
                self.checkpoint.rmdir()
            self.checkpoint.write_bytes(original)

    def mutate_during_secret_scan(self, path: Path, content: str) -> None:
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '%s\\n' {} > {}\nexit 0\n".format(
                shlex.quote(content),
                shlex.quote(str(path)),
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

    def mutate_source_after_repeat_reconciliation_starts(
        self, package_path: Path, content: str
    ) -> dict[str, str]:
        adapter = self.root / "repeat-source-race-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_open = os.open
_handoff = os.environ["PICKUP_REPEAT_HANDOFF"]
_checkpoint = os.environ["PICKUP_REPEAT_CHECKPOINT"]
_package_manifest = os.environ["PICKUP_REPEAT_PACKAGE_MANIFEST"]
_replacement = os.environ["PICKUP_REPEAT_REPLACEMENT"]
_source_opens = {_handoff: 0, _checkpoint: 0}
_mutated = False


def _tracking_open(path, flags, *args, **kwargs):
    global _mutated
    observed = os.fspath(path)
    if kwargs.get("dir_fd") is None and observed in _source_opens:
        _source_opens[observed] += 1
    if (
        not _mutated
        and observed == _package_manifest
        and all(count >= 2 for count in _source_opens.values())
    ):
        Path(_handoff).write_text(_replacement, encoding="utf-8")
        _mutated = True
    return _real_open(path, flags, *args, **kwargs)


os.open = _tracking_open
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_REPEAT_HANDOFF": str(self.handoff),
            "PICKUP_REPEAT_CHECKPOINT": str(self.checkpoint),
            "PICKUP_REPEAT_PACKAGE_MANIFEST": str(package_path / "package.json"),
            "PICKUP_REPEAT_REPLACEMENT": content,
        }

    def load_registry_module(self):
        module_name = "pickup_registry_under_test"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def fsync_fault_environment(
        self,
        boundary: str,
        *,
        target: Path,
        arm_destination: Path | None = None,
    ) -> dict[str, str]:
        adapter = self.root / "fsync-fault-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_fsync = os.fsync
_real_link = os.link
_real_open = os.open
_boundary = os.environ["PICKUP_FSYNC_BOUNDARY"]
_target = Path(os.environ["PICKUP_FSYNC_TARGET"])
_arm_destination = os.environ.get("PICKUP_FSYNC_ARM_DESTINATION")
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_tracked_identity = None
_armed = _boundary != "directory-after-link"
_failed = False


def _identity(descriptor):
    metadata = os.fstat(descriptor)
    return metadata.st_dev, metadata.st_ino


def _tracking_open(path, flags, *args, **kwargs):
    global _tracked_identity
    descriptor = _real_open(path, flags, *args, **kwargs)
    parent_descriptor = kwargs.get("dir_fd")
    if (
        _boundary == "temporary-file"
        and flags & os.O_CREAT
        and parent_descriptor is not None
        and _target.exists()
    ):
        parent = os.fstat(parent_descriptor)
        expected_parent = _target.stat()
        if (parent.st_dev, parent.st_ino) == (
            expected_parent.st_dev,
            expected_parent.st_ino,
        ):
            _tracked_identity = _identity(descriptor)
    return descriptor


def _arming_link(source, destination, *args, **kwargs):
    global _armed
    result = _real_link(source, destination, *args, **kwargs)
    destination_matches = False
    if _arm_destination is not None:
        expected = Path(_arm_destination)
        destination_path = Path(destination)
        if destination_path.is_absolute():
            destination_matches = destination_path == expected
        elif kwargs.get("dst_dir_fd") is not None:
            parent = os.fstat(kwargs["dst_dir_fd"])
            expected_parent = expected.parent.stat()
            destination_matches = (
                destination_path.name == expected.name
                and (parent.st_dev, parent.st_ino)
                == (expected_parent.st_dev, expected_parent.st_ino)
            )
    if (
        _boundary == "directory-after-link"
        and destination_matches
    ):
        _armed = True
    return result


def _faulting_fsync(descriptor):
    global _failed
    if _failed:
        return _real_fsync(descriptor)
    observed = _identity(descriptor)
    matches_temporary = (
        _boundary == "temporary-file" and observed == _tracked_identity
    )
    matches_directory = False
    if _boundary in {"directory", "directory-after-link"} and _armed:
        try:
            metadata = _target.lstat()
            matches_directory = observed == (metadata.st_dev, metadata.st_ino)
        except OSError:
            matches_directory = False
    if matches_temporary or matches_directory:
        _failed = True
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected fsync failure")
    return _real_fsync(descriptor)


os.fsync = _faulting_fsync
os.link = _arming_link
os.open = _tracking_open
""",
            encoding="utf-8",
        )
        marker = self.root / "fsync-fault-fired"
        environment = {
            "PYTHONPATH": str(adapter),
            "PICKUP_FSYNC_BOUNDARY": boundary,
            "PICKUP_FSYNC_TARGET": str(target),
            "PICKUP_FAULT_MARKER": str(marker),
        }
        if arm_destination is not None:
            environment["PICKUP_FSYNC_ARM_DESTINATION"] = str(arm_destination)
        return environment

    def staged_inode_unlink_fault_environment(self, target: Path) -> dict[str, str]:
        adapter = self.root / "unlink-fault-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_open = os.open
_real_unlink = os.unlink
_target = Path(os.environ["PICKUP_FAIL_UNLINK_TARGET"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_tracked = set()
_failed = False


def _tracking_open(path, flags, *args, **kwargs):
    descriptor = _real_open(path, flags, *args, **kwargs)
    parent_descriptor = kwargs.get("dir_fd")
    if flags & os.O_CREAT and parent_descriptor is not None and _target.exists():
        parent = os.fstat(parent_descriptor)
        expected_parent = _target.stat()
        if (parent.st_dev, parent.st_ino) == (
            expected_parent.st_dev,
            expected_parent.st_ino,
        ):
            metadata = os.fstat(descriptor)
            _tracked.add((metadata.st_dev, metadata.st_ino))
    return descriptor


def _faulting_unlink(path, *args, **kwargs):
    global _failed
    try:
        metadata = os.stat(
            path,
            dir_fd=kwargs.get("dir_fd"),
            follow_symlinks=False,
        )
        identity = (metadata.st_dev, metadata.st_ino)
    except OSError:
        identity = None
    if not _failed and identity in _tracked:
        _failed = True
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected unlink failure")
    return _real_unlink(path, *args, **kwargs)


os.open = _tracking_open
os.unlink = _faulting_unlink
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAIL_UNLINK_TARGET": str(target),
            "PICKUP_FAULT_MARKER": str(self.root / "unlink-fault-fired"),
        }

    def cleanup_sync_trace_environment(self, target: Path) -> dict[str, str]:
        adapter = self.root / "cleanup-sync-trace-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_fsync = os.fsync
_real_unlink = os.unlink
_target = Path(os.environ["PICKUP_SYNC_TARGET"])
_target_metadata = _target.stat()
_target_identity = (_target_metadata.st_dev, _target_metadata.st_ino)
_trace = Path(os.environ["PICKUP_SYNC_TRACE"])


def _append(event):
    with _trace.open("a", encoding="utf-8") as stream:
        stream.write(event + "\\n")


def _tracing_unlink(path, *args, **kwargs):
    descriptor = kwargs.get("dir_fd")
    matches = False
    if descriptor is not None:
        metadata = os.fstat(descriptor)
        matches = (metadata.st_dev, metadata.st_ino) == _target_identity
    result = _real_unlink(path, *args, **kwargs)
    if matches and Path(path).name.startswith(".pickup-remove-"):
        _append("UNLINK")
    return result


def _tracing_fsync(descriptor):
    metadata = os.fstat(descriptor)
    result = _real_fsync(descriptor)
    if (metadata.st_dev, metadata.st_ino) == _target_identity:
        _append("SYNC")
    return result


os.unlink = _tracing_unlink
os.fsync = _tracing_fsync
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_SYNC_TARGET": str(target),
            "PICKUP_SYNC_TRACE": str(self.root / "cleanup-sync-trace"),
        }

    def late_mutable_cleanup_fault_environment(self) -> dict[str, str]:
        adapter = self.root / "late-mutable-cleanup-fault-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_unlink = os.unlink
_target = Path(os.environ["PICKUP_FAIL_UNLINK_TARGET"])
_target_identity = (_target.stat().st_dev, _target.stat().st_ino)
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_failed = False


def _faulting_unlink(path, *args, **kwargs):
    global _failed
    descriptor = kwargs.get("dir_fd")
    parent_identity = None
    if descriptor is not None:
        metadata = os.fstat(descriptor)
        parent_identity = (metadata.st_dev, metadata.st_ino)
    if (
        not _failed
        and parent_identity == _target_identity
        and os.fspath(path).startswith(".pickup-remove-")
    ):
        _failed = True
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected late mutable cleanup failure")
    return _real_unlink(path, *args, **kwargs)


os.unlink = _faulting_unlink
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAIL_UNLINK_TARGET": str(self.registry),
            "PICKUP_FAULT_MARKER": str(self.root / "late-mutable-cleanup-fault-fired"),
        }

    def rollback_exchange_sync_trace_environment(self) -> dict[str, str]:
        adapter = self.root / "rollback-exchange-sync-trace-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_fsync = os.fsync
_real_unlink = os.unlink
_target = Path(os.environ["PICKUP_SYNC_TARGET"])
_target_metadata = _target.stat()
_target_identity = (_target_metadata.st_dev, _target_metadata.st_ino)
_trace = Path(os.environ["PICKUP_SYNC_TRACE"])
_failed = False


def _append(event):
    with _trace.open("a", encoding="utf-8") as stream:
        stream.write(event + "\\n")


def _tracing_unlink(path, *args, **kwargs):
    global _failed
    descriptor = kwargs.get("dir_fd")
    matches = False
    if descriptor is not None:
        metadata = os.fstat(descriptor)
        matches = (metadata.st_dev, metadata.st_ino) == _target_identity
    if matches and Path(path).name.startswith(".pickup-remove-"):
        if not _failed:
            _failed = True
            _append("FAULT_UNLINK")
            raise OSError("injected cleanup failure")
        _append("ROLLBACK_UNLINK")
    return _real_unlink(path, *args, **kwargs)


def _tracing_fsync(descriptor):
    metadata = os.fstat(descriptor)
    if _failed and (metadata.st_dev, metadata.st_ino) == _target_identity:
        _append("SYNC")
    return _real_fsync(descriptor)


os.unlink = _tracing_unlink
os.fsync = _tracing_fsync
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_SYNC_TARGET": str(self.registry),
            "PICKUP_SYNC_TRACE": str(self.root / "rollback-exchange-sync-trace"),
        }

    def checkpoint_metadata_read_fault_environment(
        self, checkpoint_path: Path, forged: dict[str, object]
    ) -> dict[str, str]:
        adapter = self.root / "checkpoint-read-fault-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import json
import os
from pathlib import Path

_real_open = os.open
_real_read = os.read
_target = os.path.realpath(os.environ["PICKUP_FAULT_CHECKPOINT"])
_forged_value = json.loads(os.environ["PICKUP_FORGED_CHECKPOINT"])
_forged = (json.dumps(_forged_value) + "\\n").encode()
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_fault_descriptors = {}


class _FaultingOpen:
    def __call__(self, path, flags, *args, **kwargs):
        descriptor = _real_open(path, flags, *args, **kwargs)
        if os.path.realpath(os.fspath(path)) == _target:
            _fault_descriptors[descriptor] = False
        return descriptor


def _faulting_read(descriptor, size):
    if descriptor in _fault_descriptors:
        if not _fault_descriptors[descriptor]:
            _fault_descriptors[descriptor] = True
            _marker.write_text("fault fired\\n", encoding="utf-8")
            return _forged
        del _fault_descriptors[descriptor]
        return b""
    return _real_read(descriptor, size)


os.open = _FaultingOpen()
os.read = _faulting_read
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_CHECKPOINT": str(checkpoint_path),
            "PICKUP_FORGED_CHECKPOINT": json.dumps(forged),
            "PICKUP_FAULT_MARKER": str(self.root / "checkpoint-fault-fired"),
        }

    def mode_replacement_on_open_environment(self, target: Path) -> dict[str, str]:
        adapter = self.root / "mode-replacement-on-open-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_open = os.open
_real_replace = os.replace
_target = Path(os.environ["PICKUP_FAULT_MODE_TARGET"])
_target_text = os.path.abspath(os.fspath(_target))
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _replacing_open(path, flags, *args, **kwargs):
    global _triggered
    path_text = os.path.abspath(os.fspath(path))
    if not _triggered and path_text == _target_text:
        _triggered = True
        replacement = _target.with_name(".mode-replacement")
        replacement.write_bytes(_target.read_bytes())
        replacement.chmod(0o644)
        _real_replace(replacement, _target)
        _marker.write_text("fault fired\\n", encoding="utf-8")
    return _real_open(path, flags, *args, **kwargs)


os.open = _replacing_open
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_MODE_TARGET": str(target),
            "PICKUP_FAULT_MARKER": str(self.root / "mode-fault-fired"),
        }

    def package_rollback_foreign_file_environment(self) -> dict[str, str]:
        adapter = self.root / "package-rollback-foreign-file-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_packages = Path(os.environ["PICKUP_FAULT_PACKAGES_ROOT"])
_triggered = False


class _FaultingLink:
    def __call__(self, source, destination, *args, **kwargs):
        global _triggered
        destination_path = Path(destination)
        installed = [
            path
            for path in _packages.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ] if _packages.exists() else []
        if not _triggered and destination_path.name == "track.json" and installed:
            _triggered = True
            (installed[0] / "foreign.txt").write_text(
                "foreign replacement evidence\\n", encoding="utf-8"
            )
            raise OSError("injected mutable commit failure")
        return _real_link(source, destination, *args, **kwargs)


os.link = _FaultingLink()
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_PACKAGES_ROOT": str(
                self.registry / "tracks" / "alpha" / "packages"
            ),
        }

    def add_foreign_staging_file_during_scan(self) -> None:
        self.gitleaks.write_text(
            """#!/bin/sh
source_path=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--source" ]; then
    source_path=$2
    break
  fi
  shift
done
printf '%s\\n' 'foreign staging evidence' > "$source_path/foreign.txt"
exit 0
""",
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

    def mutable_same_content_replacement_environment(self) -> dict[str, str]:
        adapter = self.root / "mutable-same-content-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_real_replace = os.replace
_target = Path(os.environ["PICKUP_FAULT_CLAIM"])
_triggered = False


class _ReplacingLink:
    def __call__(self, source, destination, *args, **kwargs):
        global _triggered
        result = _real_link(source, destination, *args, **kwargs)
        destination_path = Path(destination)
        if not _triggered and destination_path.name == _target.name:
            _triggered = True
            content = _target.read_bytes()
            replacement = _target.with_name(".foreign-claim.json")
            replacement.write_bytes(content)
            replacement.chmod(0o600)
            _real_replace(replacement, _target)
        return result


os.link = _ReplacingLink()
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_CLAIM": str(
                self.registry / "tracks" / "alpha" / "claim.json"
            ),
        }

    def mutable_staging_replacement_environment(self) -> dict[str, str]:
        adapter = self.root / "mutable-staging-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_real_replace = os.replace
_target = Path(os.environ["PICKUP_FAULT_CLAIM"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _replacing_link(source, destination, *args, **kwargs):
    global _triggered
    destination_path = Path(destination)
    if not _triggered and destination_path.name == _target.name:
        _triggered = True
        source_path = _target.parent / Path(source).name
        replacement = source_path.with_name(".foreign-staging-replacement")
        replacement.write_text("foreign staging replacement\\n", encoding="utf-8")
        replacement.chmod(0o600)
        _real_replace(replacement, source_path)
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected staging replacement")
    return _real_link(source, destination, *args, **kwargs)


os.link = _replacing_link
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_CLAIM": str(
                self.registry / "tracks" / "alpha" / "claim.json"
            ),
            "PICKUP_FAULT_MARKER": str(self.root / "staging-fault-fired"),
        }

    def post_unlink_mutable_addition_environment(self) -> dict[str, str]:
        adapter = self.root / "post-unlink-mutable-addition-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_open = os.open
_real_unlink = os.unlink
_target = Path(os.environ["PICKUP_FAULT_TRACK"])
_target_metadata = _target.stat()
_target_identity = (_target_metadata.st_dev, _target_metadata.st_ino)
_staging_name = None
_triggered = False


def _tracking_open(path, flags, mode=0o777, *args, **kwargs):
    global _staging_name
    descriptor = _real_open(path, flags, mode, *args, **kwargs)
    name = os.fsdecode(path)
    if name.startswith(".track.json-") and name.endswith(".tmp"):
        _staging_name = name
    return descriptor


def _adding_unlink(path, *args, **kwargs):
    global _triggered
    metadata = os.stat(path, dir_fd=kwargs.get("dir_fd"), follow_symlinks=False)
    identity = (metadata.st_dev, metadata.st_ino)
    result = _real_unlink(path, *args, **kwargs)
    if not _triggered and _staging_name is not None and identity == _target_identity:
        _triggered = True
        descriptor = _real_open(
            _staging_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=kwargs.get("dir_fd"),
        )
        try:
            os.write(descriptor, b"foreign post-cleanup addition\\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return result


os.open = _tracking_open
os.unlink = _adding_unlink
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_TRACK": str(
                self.registry / "tracks" / "alpha" / "track.json"
            ),
        }

    def post_unlink_immutable_addition_environment(self) -> dict[str, str]:
        adapter = self.root / "post-unlink-immutable-addition-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import fcntl
import os
from pathlib import Path

_real_open = os.open
_real_unlink = os.unlink
_target_parent = Path(os.environ["PICKUP_FAULT_RECEIPTS"]).resolve()
_staging_name = None
_staging_identity = None
_triggered = False


def _directory_path(descriptor):
    if descriptor is None:
        return None
    raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, b"\\0" * 1024)
    return Path(raw.split(b"\\0", 1)[0].decode("utf-8")).resolve()


def _tracking_open(path, flags, mode=0o777, *args, **kwargs):
    global _staging_identity, _staging_name
    descriptor = _real_open(path, flags, mode, *args, **kwargs)
    name = os.fsdecode(path)
    if (
        name.startswith(".tp-")
        and name.endswith(".tmp")
        and _directory_path(kwargs.get("dir_fd")) == _target_parent
    ):
        metadata = os.fstat(descriptor)
        _staging_name = name
        _staging_identity = (metadata.st_dev, metadata.st_ino)
    return descriptor


def _adding_unlink(path, *args, **kwargs):
    global _triggered
    metadata = os.stat(path, dir_fd=kwargs.get("dir_fd"), follow_symlinks=False)
    identity = (metadata.st_dev, metadata.st_ino)
    result = _real_unlink(path, *args, **kwargs)
    if (
        not _triggered
        and _staging_name is not None
        and identity == _staging_identity
        and _directory_path(kwargs.get("dir_fd")) == _target_parent
    ):
        _triggered = True
        descriptor = _real_open(
            _staging_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=kwargs.get("dir_fd"),
        )
        try:
            os.write(descriptor, b"foreign immutable post-cleanup addition\\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return result


os.open = _tracking_open
os.unlink = _adding_unlink
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_RECEIPTS": str(
                self.registry / "tracks" / "alpha" / "receipts"
            ),
        }

    def foreign_directory_adoption_environment(
        self, parent: Path, name: str
    ) -> dict[str, str]:
        adapter = self.root / "foreign-directory-adoption-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_mkdir = os.mkdir
_target_parent = Path(os.environ["PICKUP_FAULT_DIRECTORY_PARENT"])
_target_name = os.environ["PICKUP_FAULT_DIRECTORY_NAME"]
_triggered = False


def _foreign_mkdir(path, mode=0o777, *args, **kwargs):
    global _triggered
    name = os.fsdecode(path)
    parent_descriptor = kwargs.get("dir_fd")
    matches = False
    if not _triggered and name == _target_name and parent_descriptor is not None:
        try:
            parent = os.fstat(parent_descriptor)
            expected = _target_parent.stat()
            matches = (parent.st_dev, parent.st_ino) == (
                expected.st_dev,
                expected.st_ino,
            )
        except OSError:
            matches = False
    if matches:
        _triggered = True
        _real_mkdir(path, mode, *args, **kwargs)
        marker = _target_parent / _target_name / "foreign-marker"
        marker.write_text("foreign directory addition\\n", encoding="utf-8")
        marker.chmod(0o600)
    return _real_mkdir(path, mode, *args, **kwargs)


os.mkdir = _foreign_mkdir
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_DIRECTORY_PARENT": str(parent),
            "PICKUP_FAULT_DIRECTORY_NAME": name,
        }

    def foreign_registry_entry_during_commit_environment(self) -> dict[str, str]:
        adapter = self.root / "foreign-registry-entry-during-commit-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_track_root = Path(os.environ["PICKUP_FAULT_TRACK_ROOT"])
_triggered = False


def _adding_link(source, destination, *args, **kwargs):
    global _triggered
    result = _real_link(source, destination, *args, **kwargs)
    destination_name = os.fsdecode(destination)
    parent_descriptor = kwargs.get("dst_dir_fd")
    matches = False
    receipts = _track_root / "receipts"
    if (
        not _triggered
        and destination_name.endswith("-r0001.json")
        and parent_descriptor is not None
    ):
        try:
            parent = os.fstat(parent_descriptor)
            expected = receipts.stat()
            matches = (parent.st_dev, parent.st_ino) == (
                expected.st_dev,
                expected.st_ino,
            )
        except OSError:
            matches = False
    if matches:
        _triggered = True
        marker = _track_root / "foreign-during-commit"
        marker.write_text("foreign registry addition\\n", encoding="utf-8")
        marker.chmod(0o600)
    return result


os.link = _adding_link
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_TRACK_ROOT": str(self.registry / "tracks" / "alpha"),
        }

    def prior_mutable_replacement_environment(self) -> dict[str, str]:
        adapter = self.root / "prior-mutable-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_real_replace = os.replace
_claim = Path(os.environ["PICKUP_FAULT_CLAIM"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _replacing_link(source, destination, *args, **kwargs):
    global _triggered
    result = _real_link(source, destination, *args, **kwargs)
    destination_path = Path(destination)
    if not _triggered and destination_path.name == "context-resume.json":
        _triggered = True
        replacement = _claim.with_name(".foreign-prior-claim.json")
        replacement.write_bytes(_claim.read_bytes())
        replacement.chmod(0o600)
        _real_replace(replacement, _claim)
        _marker.write_text("fault fired\\n", encoding="utf-8")
    return result


os.link = _replacing_link
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_CLAIM": str(
                self.registry / "tracks" / "alpha" / "claim.json"
            ),
            "PICKUP_FAULT_MARKER": str(self.root / "prior-mutable-fault-fired"),
        }

    def registry_lock_root_replacement_environment(self) -> dict[str, str]:
        adapter = self.root / "registry-lock-root-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_open = os.open
_target = Path(os.environ["PICKUP_FAULT_REGISTRY_ROOT"])
_target_text = os.path.abspath(os.fspath(_target))
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_target_opens = 0
_triggered = False


def _replacing_open(path, flags, *args, **kwargs):
    global _target_opens, _triggered
    path_text = os.path.abspath(os.fspath(path))
    if path_text == _target_text:
        _target_opens += 1
        if not _triggered and _target_opens == 1:
            _triggered = True
            original = _target.with_name("pickups-owned-original")
            foreign = _target.with_name("pickups-foreign-replacement")
            _target.rename(original)
            foreign.mkdir(mode=0o700)
            _target.symlink_to(foreign, target_is_directory=True)
            _marker.write_text("fault fired\\n", encoding="utf-8")
    return _real_open(path, flags, *args, **kwargs)


os.open = _replacing_open
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_REGISTRY_ROOT": str(self.registry),
            "PICKUP_FAULT_MARKER": str(self.root / "registry-lock-fault-fired"),
        }

    def registry_root_swap_after_flock_environment(self) -> dict[str, str]:
        adapter = self.root / "registry-root-swap-after-flock-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import fcntl
import os
from pathlib import Path

_real_flock = fcntl.flock
_real_lstat = Path.lstat
_target = Path(os.environ["PICKUP_FAULT_REGISTRY_ROOT"])
_original = _target.with_name("pickups-locked-original")
_armed = False
_triggered = False


def _arming_flock(descriptor, operation):
    global _armed
    result = _real_flock(descriptor, operation)
    if operation & fcntl.LOCK_EX:
        _armed = True
    return result


def _swapping_lstat(path):
    global _triggered
    if _armed and not _triggered and os.path.abspath(path) == os.path.abspath(_target):
        metadata = _real_lstat(path)
        _triggered = True
        _target.rename(_original)
        _target.mkdir(mode=0o700)
        return metadata
    return _real_lstat(path)


fcntl.flock = _arming_flock
Path.lstat = _swapping_lstat
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_REGISTRY_ROOT": str(self.registry),
        }

    def directory_open_fault_environment(
        self,
        *,
        parent: Path,
        name_prefix: str,
        marker_name: str,
    ) -> dict[str, str]:
        adapter = self.root / "directory-open-fault-adapter-{}".format(marker_name)
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_open = os.open
_parent = Path(os.environ["PICKUP_FAULT_DIRECTORY_PARENT"])
_name_prefix = os.environ["PICKUP_FAULT_DIRECTORY_PREFIX"]
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _faulting_open(path, flags, *args, **kwargs):
    global _triggered
    descriptor = kwargs.get("dir_fd")
    matches_parent = False
    if descriptor is not None and _parent.exists():
        observed = os.fstat(descriptor)
        expected = _parent.stat()
        matches_parent = (observed.st_dev, observed.st_ino) == (
            expected.st_dev,
            expected.st_ino,
        )
    if (
        not _triggered
        and matches_parent
        and Path(path).name.startswith(_name_prefix)
        and flags & getattr(os, "O_DIRECTORY", 0)
    ):
        _triggered = True
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected directory open failure")
    return _real_open(path, flags, *args, **kwargs)


os.open = _faulting_open
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_DIRECTORY_PARENT": str(parent),
            "PICKUP_FAULT_DIRECTORY_PREFIX": name_prefix,
            "PICKUP_FAULT_MARKER": str(self.root / marker_name),
        }

    def lock_attempt_environment(self, marker: Path) -> dict[str, str]:
        adapter = self.root / "lock-attempt-adapter"
        adapter.mkdir(exist_ok=True)
        (adapter / "sitecustomize.py").write_text(
            """import fcntl
import os
from pathlib import Path

_real_flock = fcntl.flock
_marker = Path(os.environ["PICKUP_LOCK_ATTEMPT_MARKER"])


def _tracking_flock(descriptor, operation):
    if operation & fcntl.LOCK_EX:
        _marker.write_text("lock attempted\\n", encoding="utf-8")
    return _real_flock(descriptor, operation)


fcntl.flock = _tracking_flock
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_LOCK_ATTEMPT_MARKER": str(marker),
        }

    def immutable_same_content_replacement_environment(self) -> dict[str, str]:
        adapter = self.root / "immutable-same-content-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_real_replace = os.replace
_receipts = Path(os.environ["PICKUP_FAULT_RECEIPTS_ROOT"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


class _ReplacingLink:
    def __call__(self, source, destination, *args, **kwargs):
        global _triggered
        destination_path = Path(destination)
        if not _triggered and destination_path.name == "claim.json":
            _triggered = True
            receipts = list(_receipts.glob("*.json"))
            if receipts:
                receipt = receipts[0]
                replacement = receipt.with_name(".foreign-receipt.json")
                replacement.write_bytes(receipt.read_bytes())
                replacement.chmod(0o600)
                _real_replace(replacement, receipt)
                _marker.write_text("fault fired\\n", encoding="utf-8")
            raise OSError("injected mutable commit failure")
        return _real_link(source, destination, *args, **kwargs)


os.link = _ReplacingLink()
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_RECEIPTS_ROOT": str(
                self.registry / "tracks" / "alpha" / "receipts"
            ),
            "PICKUP_FAULT_MARKER": str(self.root / "immutable-fault-fired"),
        }

    def immutable_staging_replacement_environment(self) -> dict[str, str]:
        adapter = self.root / "immutable-staging-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_link = os.link
_real_replace = os.replace
_receipts = Path(os.environ["PICKUP_FAULT_RECEIPTS_ROOT"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _replacing_link(source, destination, *args, **kwargs):
    global _triggered
    destination_path = Path(destination)
    source_path = _receipts / Path(source).name
    source_parent = kwargs.get("src_dir_fd")
    source_parent_identity = None
    if source_parent is not None:
        metadata = os.fstat(source_parent)
        source_parent_identity = (metadata.st_dev, metadata.st_ino)
    receipts_identity = None
    if _receipts.exists():
        receipts_metadata = _receipts.stat()
        receipts_identity = (receipts_metadata.st_dev, receipts_metadata.st_ino)
    if (
        not _triggered
        and destination_path.name.endswith("-r0001.json")
        and source_parent_identity == receipts_identity
    ):
        _triggered = True
        replacement = source_path.with_name(".foreign-immutable-staging")
        replacement.write_text(
            "foreign immutable staging replacement\\n", encoding="utf-8"
        )
        replacement.chmod(0o600)
        _real_replace(replacement, source_path)
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected immutable staging replacement")
    return _real_link(source, destination, *args, **kwargs)


os.link = _replacing_link
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_RECEIPTS_ROOT": str(
                self.registry / "tracks" / "alpha" / "receipts"
            ),
            "PICKUP_FAULT_MARKER": str(self.root / "immutable-staging-fault-fired"),
        }

    def mutable_exchange_race_environment(self, target: Path) -> dict[str, str]:
        adapter = self.root / "mutable-exchange-race-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import ctypes
import os
from pathlib import Path

_real_cdll = ctypes.CDLL
_real_replace = os.replace
_target = Path(os.environ["PICKUP_FAULT_MUTABLE_TARGET"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _inject_replacement():
    global _triggered
    if _triggered:
        return
    _triggered = True
    replacement = _target.with_name(".foreign-mutable-view")
    replacement.write_bytes(_target.read_bytes())
    replacement.chmod(0o644)
    _real_replace(replacement, _target)
    _marker.write_text(str(_target.stat().st_ino), encoding="utf-8")


def _faulting_replace(source, destination, *args, **kwargs):
    if Path(destination) == _target:
        _inject_replacement()
    return _real_replace(source, destination, *args, **kwargs)


class _FunctionProxy:
    def __init__(self, function, name):
        object.__setattr__(self, "_function", function)
        object.__setattr__(self, "_name", name)

    def __getattr__(self, name):
        return getattr(self._function, name)

    def __setattr__(self, name, value):
        setattr(self._function, name, value)

    def __call__(self, *args):
        if self._name in {"renameatx_np", "renameat2"}:
            destination = os.fsdecode(args[3])
            if Path(destination).name == _target.name:
                _inject_replacement()
        elif self._name == "renamex_np":
            destination = Path(os.fsdecode(args[1]))
            if destination == _target:
                _inject_replacement()
        return self._function(*args)


class _LibraryProxy:
    def __init__(self, library):
        self._library = library

    def __getattr__(self, name):
        function = getattr(self._library, name)
        if name in {"renameatx_np", "renameat2", "renamex_np"}:
            return _FunctionProxy(function, name)
        return function


def _tracking_cdll(*args, **kwargs):
    return _LibraryProxy(_real_cdll(*args, **kwargs))


os.replace = _faulting_replace
ctypes.CDLL = _tracking_cdll
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_MUTABLE_TARGET": str(target),
            "PICKUP_FAULT_MARKER": str(self.root / "mutable-exchange-fault-fired"),
        }

    def immutable_commit_replacement_environment(
        self,
        *,
        immutable: Path,
        trigger_name: str = "track.json",
    ) -> dict[str, str]:
        adapter = self.root / "immutable-commit-replacement-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import ctypes
import os
from pathlib import Path

_real_cdll = ctypes.CDLL
_real_replace = os.replace
_immutable = Path(os.environ["PICKUP_FAULT_IMMUTABLE"])
_trigger_name = os.environ["PICKUP_FAULT_TRIGGER_NAME"]
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _inject_replacement():
    global _triggered
    if _triggered:
        return
    _triggered = True
    replacement = _immutable.with_name(".foreign-immutable-replacement")
    replacement.write_bytes(_immutable.read_bytes())
    replacement.chmod(_immutable.stat().st_mode & 0o777)
    _real_replace(replacement, _immutable)
    _marker.write_text(str(_immutable.stat().st_ino), encoding="utf-8")


class _FunctionProxy:
    def __init__(self, function, name):
        object.__setattr__(self, "_function", function)
        object.__setattr__(self, "_name", name)

    def __getattr__(self, name):
        return getattr(self._function, name)

    def __setattr__(self, name, value):
        setattr(self._function, name, value)

    def __call__(self, *args):
        if self._name in {"renameatx_np", "renameat2"}:
            destination_name = os.fsdecode(args[3])
            if destination_name == _trigger_name:
                _inject_replacement()
        elif self._name == "renamex_np":
            destination = Path(os.fsdecode(args[1]))
            if destination.name == _trigger_name:
                _inject_replacement()
        return self._function(*args)


class _LibraryProxy:
    def __init__(self, library):
        self._library = library

    def __getattr__(self, name):
        function = getattr(self._library, name)
        if name in {"renameatx_np", "renameat2", "renamex_np"}:
            return _FunctionProxy(function, name)
        return function


def _tracking_cdll(*args, **kwargs):
    return _LibraryProxy(_real_cdll(*args, **kwargs))


ctypes.CDLL = _tracking_cdll
""",
            encoding="utf-8",
        )
        return {
            "PYTHONPATH": str(adapter),
            "PICKUP_FAULT_IMMUTABLE": str(immutable),
            "PICKUP_FAULT_TRIGGER_NAME": trigger_name,
            "PICKUP_FAULT_MARKER": str(
                self.root / "immutable-commit-replacement-fired"
            ),
        }

    def inspect(self, selector: str | None = None) -> dict[str, object]:
        arguments = ["inspect", "--registry-root", str(self.registry)]
        if selector is not None:
            arguments.extend(["--selector", selector])
        return json.loads(self.run_cli(*arguments).stdout)

    def rewrite_latest_receipt(
        self,
        result: dict[str, object],
        mutate: object,
    ) -> tuple[Path, str]:
        receipt_path = Path(str(result["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        mutate(receipt)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        track_id = str(result["pickup"]["track_id"])
        receipt_id = str(result["receipt_id"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / track_id / "track.json"
        claim_path = self.registry / "tracks" / track_id / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        index["receipts"][receipt_id]["latest_receipt_sha256"] = receipt_hash
        claim["latest_receipt_sha256"] = receipt_hash
        if isinstance(track.get("active_claim"), dict):
            track["active_claim"]["latest_receipt_sha256"] = receipt_hash
            index["tracks"][track_id]["active_claim"]["latest_receipt_sha256"] = (
                receipt_hash
            )
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
        return receipt_path, receipt_hash

    def advance(
        self,
        claimed: dict[str, object],
        gate: str,
        *,
        expected: int = 0,
        receipt_id: str | None = None,
        track_id: str | None = None,
        checkpoint_id: str | None = None,
        expected_revision: int | None = None,
        expected_receipt_sha256: str | None = None,
        evidence: dict[str, object] | None = None,
        include_evidence: bool = True,
        compatibility_output: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "advance",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(compatibility_output or self.compatibility),
            "--track-id",
            track_id or str(claimed["pickup"]["track_id"]),
            "--checkpoint-id",
            checkpoint_id or str(claimed["pickup"]["checkpoint_id"]),
            "--receipt-id",
            receipt_id or str(claimed["receipt_id"]),
            "--expected-revision",
            str(
                expected_revision
                if expected_revision is not None
                else claimed["revision"]
            ),
            "--expected-receipt-sha256",
            expected_receipt_sha256 or str(claimed["receipt_sha256"]),
            "--gate",
            gate,
        ]
        if include_evidence:
            evidence_path = self.root / "evidence-{}.json".format(gate.lower())
            evidence_path.write_text(
                json.dumps(
                    evidence
                    or {
                        "schema_version": 1,
                        "gate": gate,
                        "status": "PASS",
                        "observed_at": "2026-09-02T18:00:00Z",
                        "checks": [
                            {
                                "name": "fixture-check",
                                "status": "PASS",
                                "detail": "Verified by the isolated test fixture.",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            arguments.extend(["--evidence-file", str(evidence_path)])
        arguments.extend(["--gitleaks-path", str(self.gitleaks)])
        return self.run_cli(
            *arguments,
            expected=expected,
            extra_env=extra_env,
        )

    def release(
        self,
        terminal: dict[str, object],
        *,
        expected: int = 0,
        compatibility_output: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "release",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(compatibility_output or self.compatibility),
            "--track-id",
            str(terminal["pickup"]["track_id"]),
            "--checkpoint-id",
            str(terminal["pickup"]["checkpoint_id"]),
            "--receipt-id",
            str(terminal["receipt_id"]),
            "--expected-revision",
            str(terminal["revision"]),
            "--expected-receipt-sha256",
            str(terminal["receipt_sha256"]),
            "--gitleaks-path",
            str(self.gitleaks),
            expected=expected,
        )

    def advance_to_live_state(self, claimed: dict[str, object]) -> dict[str, object]:
        current = claimed
        for gate in (
            "CANONICAL_PAIR_VERIFIED",
            "LIVE_STATE_VERIFIED",
        ):
            current = json.loads(self.advance(current, gate).stdout)
        return current

    def complete_ready(
        self,
        current: dict[str, object],
        *,
        expected: int = 0,
        compatibility_output: Path | None = None,
        drift: str = "NONE",
        current_phase: str = "Alpha definition",
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "complete",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(compatibility_output or self.compatibility),
            "--track-id",
            str(current["pickup"]["track_id"]),
            "--checkpoint-id",
            str(current["pickup"]["checkpoint_id"]),
            "--receipt-id",
            str(current["receipt_id"]),
            "--expected-revision",
            str(current["revision"]),
            "--expected-receipt-sha256",
            str(current["receipt_sha256"]),
            "--status",
            "READY",
            "--drift",
            drift,
            "--current-phase",
            current_phase,
            "--next-phase",
            "Alpha implementation",
        ]
        arguments.extend(["--gitleaks-path", str(self.gitleaks)])
        return self.run_cli(*arguments, expected=expected)


    def test_complete_rejects_unbounded_phase_metadata(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        claimed = json.loads(self.claim(selector).stdout)
        current = self.advance_to_live_state(claimed)
        rejected = self.complete_ready(current, current_phase="x" * 201, expected=2)
        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "TERMINAL_METADATA_INVALID")
        self.assertEqual(self.inspect(selector)["state"], "OPENING")

    def complete_aborted_result(
        self,
        current: dict[str, object],
        *,
        include_reason: bool = True,
        reason_code: str = "EXPLICIT_ABANDONMENT",
        reason: str = "The user explicitly abandoned this opening attempt.",
        expected: int = 0,
        compatibility_output: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "complete",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(compatibility_output or self.compatibility),
            "--track-id",
            str(current["pickup"]["track_id"]),
            "--checkpoint-id",
            str(current["pickup"]["checkpoint_id"]),
            "--receipt-id",
            str(current["receipt_id"]),
            "--expected-revision",
            str(current["revision"]),
            "--expected-receipt-sha256",
            str(current["receipt_sha256"]),
            "--status",
            "ABORTED",
            "--drift",
            "UNKNOWN",
        ]
        if include_reason:
            arguments.extend(
                [
                    "--reason-code",
                    reason_code,
                    "--reason",
                    reason,
                ]
            )
        arguments.extend(["--gitleaks-path", str(self.gitleaks)])
        return self.run_cli(*arguments, expected=expected)

    def complete_aborted(self, current: dict[str, object]) -> dict[str, object]:
        completed = self.complete_aborted_result(current)
        return json.loads(completed.stdout)

    def complete_review_required_result(
        self,
        current: dict[str, object],
        *,
        reason_code: str,
        reason: str,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "complete",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(self.compatibility),
            "--track-id",
            str(current["pickup"]["track_id"]),
            "--checkpoint-id",
            str(current["pickup"]["checkpoint_id"]),
            "--receipt-id",
            str(current["receipt_id"]),
            "--expected-revision",
            str(current["revision"]),
            "--expected-receipt-sha256",
            str(current["receipt_sha256"]),
            "--status",
            "REVIEW_REQUIRED",
            "--drift",
            "MATERIAL",
            "--reason-code",
            reason_code,
            "--reason",
            reason,
            "--gitleaks-path",
            str(self.gitleaks),
            expected=expected,
        )

    def test_publish_makes_one_immutable_available_package_inspectable(self) -> None:
        published = self.publish()

        inspected = json.loads(
            self.run_cli(
                "inspect",
                "--registry-root",
                str(self.registry),
                "--selector",
                str(published["selector"]),
            ).stdout
        )

        self.assertEqual(inspected["selector"], published["selector"])
        self.assertRegex(str(inspected["selector"]), SELECTOR_RE)
        self.assertEqual(inspected["state"], "AVAILABLE")
        self.assertEqual(inspected["generated_at"], "2026-09-02T12:55:09-05:00")
        package_dir = Path(str(inspected["package_path"]))
        self.assertEqual(
            (package_dir / "handoff.md").read_bytes(), self.handoff.read_bytes()
        )
        self.assertEqual(
            (package_dir / "checkpoint.json").read_bytes(), self.checkpoint.read_bytes()
        )
        for path in (self.registry / "index.json", package_dir / "package.json"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_new_checkpoint_supersedes_prior_package_without_rewriting_it(self) -> None:
        first = self.publish()
        first_manifest = Path(str(first["package_path"])) / "package.json"
        first_bytes = first_manifest.read_bytes()
        self.handoff.write_text("# Alpha handoff revision two\n", encoding="utf-8")
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-02T13:05:10-05:00"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        second = self.publish()
        first_after = json.loads(
            self.run_cli(
                "inspect",
                "--registry-root",
                str(self.registry),
                "--selector",
                str(first["selector"]),
            ).stdout
        )

        self.assertEqual(first_after["state"], "SUPERSEDED")
        self.assertEqual(second["state"], "AVAILABLE")
        self.assertEqual(first_manifest.read_bytes(), first_bytes)

    def test_new_checkpoint_links_an_immutable_publication_chain(self) -> None:
        first = self.publish()
        first_manifest = Path(str(first["package_path"])) / "package.json"
        self.handoff.write_text("# Alpha handoff revision two\n", encoding="utf-8")
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-02T13:05:10-05:00"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        second = self.publish()

        second_manifest = json.loads(
            (Path(str(second["package_path"])) / "package.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            second_manifest["previous_checkpoint_id"], first["checkpoint_id"]
        )
        self.assertEqual(
            second_manifest["previous_package_sha256"],
            hashlib.sha256(first_manifest.read_bytes()).hexdigest(),
        )

    def test_claim_rejects_superseded_package_after_coordinated_head_reset(
        self,
    ) -> None:
        first = self.publish()
        self.handoff.write_text("# Alpha handoff revision two\n", encoding="utf-8")
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-02T13:05:10-05:00"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
        second = self.publish()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        first_id = str(first["checkpoint_id"])
        second_id = str(second["checkpoint_id"])
        for view in (index["tracks"]["alpha"], track):
            view["latest_checkpoint_id"] = first_id
            view["packages"][first_id]["state"] = "AVAILABLE"
            view["packages"][second_id]["state"] = "SUPERSEDED"
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.claim(str(first["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_creates_schema_four_verifying_run(self) -> None:
        package = self.publish()

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertEqual(claimed["schema_version"], 4)
        self.assertEqual(claimed["revision"], 1)
        self.assertEqual(claimed["status"], "VERIFYING")
        self.assertEqual(claimed["pickup"]["selector"], package["selector"])
        self.assertFalse(claimed["scope"]["phase_authorized"])
        receipt_path = Path(str(claimed["receipt_path"]))
        self.assertTrue(receipt_path.is_file())

    def test_inspect_rejects_coordinated_invalid_claim_timestamp(self) -> None:
        package = self.publish()
        self.claim(str(package["selector"]))
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        index["tracks"]["alpha"]["active_claim"]["claimed_at"] = 7
        track["active_claim"]["claimed_at"] = 7
        claim["claimed_at"] = 7
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_updates_package_and_compatibility_views(self) -> None:
        package = self.publish()

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        inspected = self.inspect(str(package["selector"]))
        self.assertEqual(inspected["state"], "CLAIMED")
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(compatibility["receipt_id"], claimed["receipt_id"])

    def test_checkpoint_artifact_metadata_and_hash_come_from_one_capture(self) -> None:
        checkpoint_path = self.checkpoint
        forged = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        forged["generated_at"] = "2027-01-02T03:04:05Z"
        published = json.loads(
            self.publish_result(
                extra_env=self.checkpoint_metadata_read_fault_environment(
                    checkpoint_path, forged
                )
            ).stdout
        )

        forged_bytes = (json.dumps(forged) + "\n").encode()
        package_path = Path(str(published["package_path"]))
        manifest = json.loads(
            (package_path / "package.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["checkpoint_generated_at"], forged["generated_at"])
        self.assertEqual(
            manifest["checkpoint_sha256"], hashlib.sha256(forged_bytes).hexdigest()
        )
        self.assertEqual((package_path / "checkpoint.json").read_bytes(), forged_bytes)
        self.assertTrue((self.root / "checkpoint-fault-fired").is_file())

    def test_claim_rejects_workspace_outside_registry_binding_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        selector = str(package["selector"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}
        alternate_workspace = self.root / "alternate-workspace"
        alternate_workspace.mkdir()
        arguments = self.claim_arguments(selector)
        arguments[arguments.index("--workspace") + 1] = str(alternate_workspace)

        rejected = self.run_cli(*arguments, expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "WORKSPACE_INVALID"
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_rejects_noncanonical_compatibility_output_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        selector = str(package["selector"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}
        alternate_parent = self.workspace / "alternate"
        alternate_parent.mkdir()
        alternate_output = alternate_parent / "context-resume.json"
        arguments = self.claim_arguments(selector)
        arguments[arguments.index("--compatibility-output") + 1] = str(alternate_output)

        rejected = self.run_cli(*arguments, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())
        self.assertFalse(alternate_output.exists())
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_rejects_malformed_existing_compatibility_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        selector = str(package["selector"])
        self.compatibility.write_text("{not-json}\n", encoding="utf-8")
        self.compatibility.chmod(0o600)
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}

        rejected = self.claim(selector, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.compatibility.read_text(encoding="utf-8"), "{not-json}\n")
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_advance_rejects_forged_v4_compatibility_paths_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        compatibility["artifacts"]["skill"]["path"] = "/tmp/not-the-deployed-skill"
        receipt = dict(compatibility)
        receipt.pop("compatibility_summary")
        receipt.pop("receipt_sha256")
        compatibility["receipt_sha256"] = hashlib.sha256(
            (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
        ).hexdigest()
        self.compatibility.write_text(
            json.dumps(compatibility, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.compatibility.chmod(0o600)
        before = {path: path.read_bytes() for path in self.registry.rglob("*.json")}

        rejected = self.advance(
            claimed,
            "CANONICAL_PAIR_VERIFIED",
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertEqual(
            {path: path.read_bytes() for path in self.registry.rglob("*.json")},
            before,
        )

    def test_claim_accepts_valid_active_legacy_v3_compatibility(self) -> None:
        package = self.publish()
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))

        def artifact(path: Path) -> dict[str, object]:
            return {
                "path": str(path),
                "present": True,
                "regular_file": True,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

        checkpoint_artifact = artifact(self.checkpoint)
        checkpoint_artifact.update(
            {
                "schema_version": checkpoint["schema_version"],
                "context_status": checkpoint["context_status"],
                "generated_at": checkpoint["generated_at"],
            }
        )
        compatibility = {
            "schema_version": 3,
            "receipt_id": "tp-20260902T180000Z-1234abcd",
            "status": "VERIFYING",
            "terminal": False,
            "drift": "UNKNOWN",
            "started_at": "2026-09-02T18:00:00Z",
            "updated_at": "2026-09-02T18:00:00Z",
            "completed_at": None,
            "workspace": str(self.workspace),
            "invocation": {
                "fresh_task": "YES",
                "freshness_basis": "FIRST_SUBSTANTIVE_USER_TURN",
                "mode": "MANUAL_SKILL_SELECTOR",
                "model": "TEST",
                "reasoning_effort": "TEST",
            },
            "scope": {
                "operation": "READ_VERIFY_RECONSTRUCT",
                "phase_authorized": False,
                "allowed_writes": [str(self.compatibility)],
            },
            "artifacts": {
                "skill": artifact(SCRIPT.parents[1] / "SKILL.md"),
                "handoff": artifact(self.handoff),
                "checkpoint": checkpoint_artifact,
            },
            "last_completed_gate": "INVOCATION_RECORDED",
            "checkpoint_generated_at": checkpoint["generated_at"],
            "current_phase": None,
            "next_phase": None,
            "reason_code": None,
            "reason": None,
            "validation": {"json": True, "secret_scan": "PENDING"},
        }
        for field in ("current_phase", "next_phase", "reason"):
            with self.subTest(field=field):
                malformed = {**compatibility, field: ["invalid"]}
                self.compatibility.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
                self.compatibility.chmod(0o600)
                rejected = self.claim(str(package["selector"]), expected=3)
                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "COMPATIBILITY_OUTPUT_INVALID",
                )
        invalid = copy.deepcopy(compatibility)
        invalid.update(
            {
                "status": "READY",
                "terminal": True,
                "drift": "SECURITY",
                "updated_at": "2026-09-02T18:01:00Z",
                "completed_at": "2026-09-02T18:01:00Z",
                "last_completed_gate": "TELEMETRY_VALIDATED",
                "current_phase": "Alpha definition",
                "next_phase": "Alpha implementation",
                "validation": {"json": True, "secret_scan": "PASS"},
            }
        )
        self.compatibility.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
        self.compatibility.chmod(0o600)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        self.compatibility.write_text(
            json.dumps(compatibility) + "\n", encoding="utf-8"
        )
        self.compatibility.chmod(0o600)

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertEqual(claimed["pickup"]["selector"], package["selector"])
        self.assertEqual(
            json.loads(self.compatibility.read_text(encoding="utf-8"))[
                "schema_version"
            ],
            4,
        )

    def test_claim_accepts_legacy_v2_object_accepted_by_original_validator(
        self,
    ) -> None:
        package = self.publish()
        self.compatibility.write_text('{"schema_version": 2}\n', encoding="utf-8")
        self.compatibility.chmod(0o600)
        validated = subprocess.run(
            [
                sys.executable,
                str(LEGACY_SCRIPT),
                "validate",
                "--output",
                str(self.compatibility),
            ],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(validated.returncode, 0, validated.stderr)

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertEqual(claimed["pickup"]["selector"], package["selector"])
        self.assertEqual(
            json.loads(self.compatibility.read_text(encoding="utf-8"))[
                "schema_version"
            ],
            4,
        )

    def test_claim_accepts_legacy_v3_missing_checkpoint_telemetry(self) -> None:
        package = self.publish()
        legacy = self.write_legacy_v3_with_checkpoint_state("missing")
        self.assertFalse(legacy["artifacts"]["checkpoint"]["present"])

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertEqual(claimed["pickup"]["selector"], package["selector"])

    def test_claim_accepts_legacy_v3_nonregular_checkpoint_telemetry(self) -> None:
        package = self.publish()
        legacy = self.write_legacy_v3_with_checkpoint_state("nonregular")
        self.assertTrue(legacy["artifacts"]["checkpoint"]["present"])
        self.assertFalse(legacy["artifacts"]["checkpoint"]["regular_file"])

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertEqual(claimed["pickup"]["selector"], package["selector"])

    def test_claim_accepts_legacy_v3_unsupported_checkpoint_telemetry(self) -> None:
        package = self.publish()
        legacy = self.write_legacy_v3_with_checkpoint_state("unsupported")
        checkpoint = legacy["artifacts"]["checkpoint"]
        self.assertEqual(checkpoint["schema_version"], 1)
        self.assertEqual(checkpoint["context_status"], "HISTORICAL")
        self.assertEqual(checkpoint["generated_at"], "historical-value")

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertEqual(claimed["pickup"]["selector"], package["selector"])

    def test_claim_rejects_sibling_skill_file_without_mutation(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}
        fake_skill = self.root / "fake" / "SKILL.md"
        fake_skill.parent.mkdir()
        fake_skill.write_text("---\nname: treasurepickup\n---\n", encoding="utf-8")
        arguments = self.claim_arguments(selector)
        arguments[arguments.index("--skill-file") + 1] = str(fake_skill)

        rejected = self.run_cli(*arguments, expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "SKILL_FILE_INVALID"
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())

    def test_advance_rejects_noncanonical_compatibility_output_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        canonical_before = self.compatibility.read_bytes()
        receipts = Path(str(claimed["receipt_path"])).parent
        receipts_before = sorted(receipts.iterdir())
        alternate = self.workspace / "alternate" / "context-resume.json"
        alternate.parent.mkdir()

        rejected = self.advance(
            claimed,
            "CANONICAL_PAIR_VERIFIED",
            compatibility_output=alternate,
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertFalse(alternate.exists())
        self.assertEqual(self.compatibility.read_bytes(), canonical_before)
        self.assertEqual(sorted(receipts.iterdir()), receipts_before)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "CLAIMED")

    def test_complete_rejects_noncanonical_compatibility_output_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        canonical_before = self.compatibility.read_bytes()
        receipts = Path(str(claimed["receipt_path"])).parent
        receipts_before = sorted(receipts.iterdir())
        alternate = self.workspace / "alternate" / "context-resume.json"
        alternate.parent.mkdir()

        rejected = self.complete_aborted_result(
            claimed,
            compatibility_output=alternate,
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertFalse(alternate.exists())
        self.assertEqual(self.compatibility.read_bytes(), canonical_before)
        self.assertEqual(sorted(receipts.iterdir()), receipts_before)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "CLAIMED")

    def test_release_rejects_noncanonical_compatibility_output_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)
        canonical_before = self.compatibility.read_bytes()
        receipts = Path(str(aborted["receipt_path"])).parent
        receipts_before = sorted(receipts.iterdir())
        alternate = self.workspace / "alternate" / "context-resume.json"
        alternate.parent.mkdir()

        rejected = self.release(
            aborted,
            compatibility_output=alternate,
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertFalse(alternate.exists())
        self.assertEqual(self.compatibility.read_bytes(), canonical_before)
        self.assertEqual(sorted(receipts.iterdir()), receipts_before)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def assert_claim_rejects_compatibility_symlink(self, target: Path) -> None:
        package = self.publish()
        self.compatibility.symlink_to(target)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        self.assertTrue(self.compatibility.is_symlink())

    def test_claim_rejects_dangling_compatibility_symlink_before_mutation(
        self,
    ) -> None:
        self.assert_claim_rejects_compatibility_symlink(
            self.root / "missing-compatibility-target.json"
        )

    def test_claim_rejects_live_compatibility_symlink_before_mutation(self) -> None:
        target = self.root / "compatibility-target.json"
        target.write_text("{}\n", encoding="utf-8")
        self.assert_claim_rejects_compatibility_symlink(target)

    def test_claim_rejects_compatibility_symlink_created_during_secret_scan(
        self,
    ) -> None:
        package = self.publish()
        target = self.root / "missing-race-target.json"
        self.gitleaks.write_text(
            "#!/bin/sh\nln -s {} {} 2>/dev/null || true\nexit 0\n".format(
                shlex.quote(str(target)), shlex.quote(str(self.compatibility))
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        self.assertTrue(self.compatibility.is_symlink())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_rejects_compatibility_replacement_during_secret_scan(
        self,
    ) -> None:
        package = self.publish()
        self.write_valid_legacy_compatibility()
        before_identity = self.compatibility.stat().st_ino
        replacement = self.compatibility.with_suffix(".replacement")
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{{\"raced\": true}}' > {}\n"
            "chmod 600 {}\nmv {} {}\nexit 0\n".format(
                shlex.quote(str(replacement)),
                shlex.quote(str(replacement)),
                shlex.quote(str(replacement)),
                shlex.quote(str(self.compatibility)),
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertNotEqual(self.compatibility.stat().st_ino, before_identity)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_rejects_compatibility_deletion_during_secret_scan(self) -> None:
        package = self.publish()
        self.write_valid_legacy_compatibility()
        self.gitleaks.write_text(
            "#!/bin/sh\nrm -f {}\nexit 0\n".format(
                shlex.quote(str(self.compatibility))
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_INVALID",
        )
        self.assertFalse(self.compatibility.exists())
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_revalidates_registry_mode_after_secret_scan(self) -> None:
        package = self.publish()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}
        self.gitleaks.write_text(
            "#!/bin/sh\nchmod 755 {}\nexit 0\n".format(shlex.quote(str(self.registry))),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_MODE_INVALID"
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(self.compatibility.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        self.registry.chmod(0o700)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_claim_revalidates_registry_inventory_after_secret_scan(self) -> None:
        package = self.publish()
        rogue = self.registry / "rogue.json"
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '{}\\n' > {}\nchmod 600 {}\nexit 0\n".format(
                "{}",
                shlex.quote(str(rogue)),
                shlex.quote(str(rogue)),
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertFalse(self.compatibility.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        rogue.unlink()
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_claim_rejects_index_replacement_during_secret_scan(self) -> None:
        package = self.publish()
        index_path = self.registry / "index.json"
        before_identity = index_path.stat().st_ino
        replacement = index_path.with_suffix(".replacement")
        self.gitleaks.write_text(
            "#!/bin/sh\ncp {} {}\nchmod 600 {}\nmv {} {}\nexit 0\n".format(
                shlex.quote(str(index_path)),
                shlex.quote(str(replacement)),
                shlex.quote(str(replacement)),
                shlex.quote(str(replacement)),
                shlex.quote(str(index_path)),
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertNotEqual(index_path.stat().st_ino, before_identity)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_rejects_track_deletion_during_secret_scan(self) -> None:
        package = self.publish()
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        self.gitleaks.write_text(
            "#!/bin/sh\nrm -f {}\nexit 0\n".format(shlex.quote(str(track_path))),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertFalse(track_path.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_claim_rejects_unwritable_compatibility_parent_before_mutation(
        self,
    ) -> None:
        package = self.publish()
        parent = self.compatibility.parent
        original_mode = stat.S_IMODE(parent.stat().st_mode)
        parent.chmod(0o500)
        try:
            rejected = self.claim(str(package["selector"]), expected=3)
        finally:
            parent.chmod(original_mode)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "COMPATIBILITY_OUTPUT_PARENT_UNAVAILABLE",
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_inspect_does_not_rewrite_an_immutable_claim_receipt(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt_bytes = receipt_path.read_bytes()

        self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
        )
        self.assertEqual(receipt_path.read_bytes(), receipt_bytes)

    def test_inspect_rejects_index_mode_replacement_at_read_boundary(self) -> None:
        package = self.publish()
        index_path = self.registry / "index.json"

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
            extra_env=self.mode_replacement_on_open_environment(index_path),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_MODE_INVALID"
        )
        self.assertTrue((self.root / "mode-fault-fired").is_file())
        self.assertEqual(stat.S_IMODE(index_path.stat().st_mode), 0o644)

    def test_inspect_preserves_receipt_mode_failure_reason(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt_path.chmod(0o644)

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_MODE_INVALID"
        )

    def test_ambiguous_claim_requires_selector_without_mutation(
        self,
    ) -> None:
        self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        self.publish("beta", beta_resource)
        before = self.inspect()

        rejected = self.claim(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PICKUP_SELECTION_REQUIRED"
        )
        self.assertEqual(self.inspect(), before)
        self.assertFalse(self.compatibility.exists())

    def test_wrong_selector_cannot_quarantine_an_unrelated_drifted_package(
        self,
    ) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("tampered before wrong claim\n", encoding="utf-8")
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}

        rejected = self.claim(
            "missing@cp-20260902-125509-deadbeef",
            expected=2,
        )

        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "PICKUP_NOT_FOUND")
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse((self.registry / "tracks" / "alpha" / "quarantines").exists())
        packaged_handoff.write_bytes(original)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_claim_rejects_resource_scope_overlap_with_another_active_track(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.resource / "nested-beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))
        before = self.inspect(str(beta["selector"]))

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_CONFLICT"
        )
        self.assertEqual(self.inspect(str(beta["selector"])), before)
        beta_state = json.loads(
            self.run_cli(
                "inspect",
                "--registry-root",
                str(self.registry),
                "--selector",
                str(beta["selector"]),
            ).stdout
        )["state"]
        self.assertEqual(beta_state, "AVAILABLE")

    def test_nonoverlapping_claims_waiting_on_lock_both_succeed(self) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        markers = [
            self.root / "alpha-lock-attempted",
            self.root / "beta-lock-attempted",
        ]
        lock_descriptor = os.open(self.registry, os.O_RDONLY)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        processes: list[subprocess.Popen[str]] = []
        try:
            for package, marker in zip((alpha, beta), markers):
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(SCRIPT),
                            *self.claim_arguments(str(package["selector"])),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={
                            **os.environ,
                            "PYTHONDONTWRITEBYTECODE": "1",
                            **self.lock_attempt_environment(marker),
                        },
                    )
                )
            deadline = time.monotonic() + 5
            while not all(marker.is_file() for marker in markers):
                self.assertLess(time.monotonic(), deadline, "claim did not reach lock")
                time.sleep(0.01)
        finally:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            os.close(lock_descriptor)

        results = [process.communicate(timeout=10) for process in processes]

        self.assertEqual(
            [process.returncode for process in processes],
            [0, 0],
            results,
        )
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "CLAIMED")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "CLAIMED")

    def test_publish_rejects_double_slash_root_scope_alias(self) -> None:
        rejected = self.publish_result(resource=Path("//"), expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_TOO_BROAD"
        )
        self.assertFalse(self.registry.exists())

    def test_publish_rejects_macos_data_volume_root_scope(self) -> None:
        if sys.platform != "darwin" or not Path("/System/Volumes/Data").exists():
            self.skipTest("macOS Data volume is unavailable")

        rejected = self.publish_result(
            resource=Path("/System/Volumes/Data"), expected=2
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_TOO_BROAD"
        )
        self.assertFalse(self.registry.exists())

    def test_double_slash_scope_alias_conflicts_with_descendant(self) -> None:
        alias = Path("//{}".format(str(self.resource).lstrip("/")))
        alpha = self.publish("alpha", alias)
        self.assertEqual(alpha["resource_scopes"], [str(self.resource.resolve())])
        beta_resource = self.resource / "nested-beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_CONFLICT"
        )
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "AVAILABLE")

    def test_symlinked_scope_alias_conflicts_with_resolved_descendant(self) -> None:
        alias = self.workspace / "projects" / "alpha-alias"
        alias.symlink_to(self.resource, target_is_directory=True)
        alpha = self.publish("alpha", alias)
        self.assertEqual(alpha["resource_scopes"], [str(self.resource.resolve())])
        beta_resource = self.resource / "nested-beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_CONFLICT"
        )

    def test_macos_firmlink_scope_alias_conflicts_with_same_physical_path(
        self,
    ) -> None:
        logical = self.workspace
        physical = Path("/System/Volumes/Data") / logical.relative_to("/")
        if sys.platform != "darwin" or not logical.exists() or not physical.exists():
            self.skipTest("APFS firmlink pair is unavailable")
        if not os.path.samefile(logical, physical):
            self.skipTest("paths are not aliases on this host")
        alpha = self.publish("alpha", logical)
        beta = self.publish("beta", physical)
        self.claim(str(alpha["selector"]))

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_CONFLICT"
        )
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "AVAILABLE")

    @unittest.skipUnless(sys.platform == "darwin", "macOS path semantics")
    def test_case_alias_scope_conflicts_with_descendant(self) -> None:
        shared = self.workspace / "projects" / "Shared"
        shared.mkdir()
        alpha = self.publish("alpha", shared)
        beta_resource = self.workspace / "projects" / "shared" / "nested-beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_CONFLICT"
        )

    def test_claim_rejects_resource_scope_edits_that_disagree_with_manifest(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.resource / "nested-beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))
        fake_scope = self.workspace / "projects" / "fake-independent-beta"
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "beta" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        index["tracks"]["beta"]["resource_scopes"] = [str(fake_scope)]
        track["resource_scopes"] = [str(fake_scope)]
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_rejects_forbidden_fields_in_coordinated_mutable_views(
        self,
    ) -> None:
        package = self.publish()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        index["pidValue"] = 42
        index["tracks"]["alpha"]["ppid value"] = 41
        track["valuePid"] = 42
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")
        index_before = index_path.read_bytes()
        track_before = track_path.read_bytes()

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertEqual(index_path.read_bytes(), index_before)
        self.assertEqual(track_path.read_bytes(), track_before)
        self.assertFalse(self.compatibility.exists())

    def test_advance_rejects_forbidden_field_in_coordinated_claim_views(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        index["tracks"]["alpha"]["active_claim"]["windowId"] = "private-window"
        track["active_claim"]["windowId"] = "private-window"
        claim["windowId"] = "private-window"
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
        views_before = {
            path: path.read_bytes() for path in (index_path, track_path, claim_path)
        }
        receipt_path = Path(str(claimed["receipt_path"]))
        receipts_before = sorted(receipt_path.parent.iterdir())

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertEqual(
            {path: path.read_bytes() for path in views_before}, views_before
        )
        self.assertEqual(sorted(receipt_path.parent.iterdir()), receipts_before)

    def test_advance_rejects_coordinated_extra_field_in_immutable_receipt(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["unexpected"] = "not in schema"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        changed_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = changed_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = changed_hash
        track["active_claim"]["latest_receipt_sha256"] = changed_hash
        claim["latest_receipt_sha256"] = changed_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        claimed["receipt_sha256"] = changed_hash

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_advance_rejects_coordinated_wrong_type_in_immutable_receipt(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["workspace"] = 7
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        changed_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = changed_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = changed_hash
        track["active_claim"]["latest_receipt_sha256"] = changed_hash
        claim["latest_receipt_sha256"] = changed_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        claimed["receipt_sha256"] = changed_hash

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_advance_rejects_receipt_scope_not_bound_to_registry(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["scope"]["allowed_writes"] = ["/"]
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        changed_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = changed_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = changed_hash
        track["active_claim"]["latest_receipt_sha256"] = changed_hash
        claim["latest_receipt_sha256"] = changed_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        claimed["receipt_sha256"] = changed_hash

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_complete_rejects_forged_gate_without_transition_evidence(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["last_completed_gate"] = "LIVE_STATE_VERIFIED"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        changed_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        checkpoint_id = str(package["checkpoint_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = changed_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = changed_hash
        index["tracks"]["alpha"]["packages"][checkpoint_id]["state"] = "OPENING"
        track["active_claim"]["latest_receipt_sha256"] = changed_hash
        track["packages"][checkpoint_id]["state"] = "OPENING"
        claim["latest_receipt_sha256"] = changed_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        claimed["receipt_sha256"] = changed_hash

        rejected = self.complete_ready(claimed, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_inspect_rejects_forged_checkpoint_metadata_in_receipt(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["artifacts"]["checkpoint"]["generated_at"] = "2027-01-02T03:04:05Z"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        forged_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = forged_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = forged_hash
        track["active_claim"]["latest_receipt_sha256"] = forged_hash
        claim["latest_receipt_sha256"] = forged_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_inspect_rejects_checkpoint_artifact_downgraded_to_generic_shape(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        checkpoint = receipt["artifacts"]["checkpoint"]
        receipt["artifacts"]["checkpoint"] = {
            key: checkpoint[key]
            for key in ("path", "present", "regular_file", "sha256")
        }
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        forged_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = forged_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = forged_hash
        track["active_claim"]["latest_receipt_sha256"] = forged_hash
        claim["latest_receipt_sha256"] = forged_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_inspect_rejects_forged_ready_receipt_without_gate_evidence(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        first_path = Path(str(claimed["receipt_path"]))
        terminal = json.loads(first_path.read_text(encoding="utf-8"))
        terminal.update(
            {
                "revision": 2,
                "previous_receipt_sha256": claimed["receipt_sha256"],
                "event": "COMPLETED",
                "status": "READY",
                "terminal": True,
                "drift": "NONE",
                "updated_at": "2026-09-02T19:00:00Z",
                "completed_at": "2026-09-02T19:00:00Z",
                "last_completed_gate": "TELEMETRY_VALIDATED",
                "current_phase": "Alpha definition",
                "next_phase": "Alpha implementation",
            }
        )
        second_path = first_path.with_name(
            first_path.name.replace("-r0001.json", "-r0002.json")
        )
        second_path.write_text(
            json.dumps(terminal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        second_path.chmod(0o600)
        terminal_hash = hashlib.sha256(second_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        checkpoint_id = str(package["checkpoint_id"])
        closed_claim = {
            **claim,
            "active": False,
            "latest_revision": 2,
            "latest_receipt_sha256": terminal_hash,
            "latest_receipt_path": str(second_path),
            "closed_at": "2026-09-02T19:00:00Z",
            "terminal_status": "READY",
        }
        track["active_claim"] = None
        track["packages"][checkpoint_id]["state"] = "CONSUMED"
        index["tracks"]["alpha"] = track
        index["receipts"][receipt_id].update(
            {
                "latest_revision": 2,
                "latest_receipt_sha256": terminal_hash,
                "latest_receipt_path": str(second_path),
                "terminal_status": "READY",
            }
        )
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, closed_claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_inspect_rejects_boolean_registry_schema_version(self) -> None:
        self.publish()
        index_path = self.registry / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["schema_version"] = True
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect", "--registry-root", str(self.registry), expected=2
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "REGISTRY_SCHEMA_UNSUPPORTED",
        )

    def test_two_concurrent_claims_for_one_package_have_exactly_one_winner(
        self,
    ) -> None:
        package = self.publish()
        command = [
            sys.executable,
            str(SCRIPT),
            *self.claim_arguments(str(package["selector"])),
        ]
        markers = [self.root / "claim-one-started", self.root / "claim-two-started"]
        lock_descriptor = os.open(self.registry, os.O_RDONLY)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        processes: list[subprocess.Popen[str]] = []
        try:
            for marker in markers:
                processes.append(
                    subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={
                            **os.environ,
                            "PYTHONDONTWRITEBYTECODE": "1",
                            **self.lock_attempt_environment(marker),
                        },
                    )
                )
            deadline = time.monotonic() + 5
            while not all(marker.is_file() for marker in markers):
                self.assertLess(time.monotonic(), deadline, "claim did not reach lock")
                time.sleep(0.01)
        finally:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            os.close(lock_descriptor)
        results = [process.communicate(timeout=10) for process in processes]
        return_codes = sorted(process.returncode for process in processes)

        self.assertEqual(return_codes, [0, 3], results)
        loser = next(
            stderr
            for process, (_, stderr) in zip(processes, results)
            if process.returncode == 3
        )
        self.assertEqual(json.loads(loser)["reason_code"], "ALREADY_CLAIMED")
        receipts = list(
            (self.registry / "tracks" / "alpha" / "receipts").glob("*.json")
        )
        self.assertEqual(len(receipts), 1)

    def test_advance_appends_hash_linked_receipt_and_opens_package(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        first_path = Path(str(claimed["receipt_path"]))
        first_bytes = first_path.read_bytes()

        advanced = json.loads(self.advance(claimed, "CANONICAL_PAIR_VERIFIED").stdout)

        self.assertEqual(advanced["revision"], 2)
        self.assertEqual(advanced["previous_receipt_sha256"], claimed["receipt_sha256"])
        self.assertEqual(advanced["last_completed_gate"], "CANONICAL_PAIR_VERIFIED")
        self.assertEqual(
            advanced["transition_evidence"][-1]["gate"],
            "CANONICAL_PAIR_VERIFIED",
        )
        self.assertEqual(first_path.read_bytes(), first_bytes)
        self.assertNotEqual(advanced["receipt_path"], str(first_path))
        self.assertEqual(
            json.loads(
                self.run_cli(
                    "inspect",
                    "--registry-root",
                    str(self.registry),
                    "--selector",
                    str(package["selector"]),
                ).stdout
            )["state"],
            "OPENING",
        )

    def test_reclaim_during_opening_reports_already_claimed(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        self.advance(claimed, "CANONICAL_PAIR_VERIFIED")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "ALREADY_CLAIMED")

    def test_inspect_distinguishes_opening_from_consumed(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = json.loads(self.advance(claimed, "CANONICAL_PAIR_VERIFIED").stdout)

        opening = self.inspect(str(package["selector"]))

        self.assertEqual(opening["state"], "OPENING")
        self.assertTrue(opening["claim_active"])
        current = json.loads(self.advance(current, "LIVE_STATE_VERIFIED").stdout)
        self.complete_ready(current)
        consumed = self.inspect(str(package["selector"]))
        self.assertEqual(consumed["state"], "CONSUMED")
        self.assertFalse(consumed["claim_active"])

    def test_ready_completion_clears_claim_and_prevents_sequential_reopen(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        prior_receipts = {
            path: path.read_bytes()
            for path in (self.registry / "tracks" / "alpha" / "receipts").glob("*.json")
        }

        completed = json.loads(self.complete_ready(current).stdout)

        self.assertEqual(completed["status"], "READY")
        self.assertTrue(completed["terminal"])
        self.assertEqual(completed["last_completed_gate"], "TELEMETRY_VALIDATED")
        self.assertFalse(completed["scope"]["phase_authorized"])
        self.assertTrue(
            all(
                path.read_bytes() == content for path, content in prior_receipts.items()
            )
        )
        rejected = self.claim(str(package["selector"]), expected=3)
        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PICKUP_NOT_AVAILABLE"
        )

    def test_claim_rejects_consumed_package_after_coordinated_state_reset(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        self.complete_ready(current)
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        checkpoint_id = str(package["checkpoint_id"])
        index["tracks"]["alpha"]["packages"][checkpoint_id]["state"] = "AVAILABLE"
        track["packages"][checkpoint_id]["state"] = "AVAILABLE"
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_receipt_omits_external_policy_fields(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        completed = json.loads(self.complete_ready(current).stdout)
        self.assertEqual(completed["status"], "READY")
        self.assertNotIn("governance_verification", completed)
        self.assertNotIn("recommended_lane", completed)

    def test_non_ready_completion_requires_sanitized_reason_metadata(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        rejected = self.complete_aborted_result(
            claimed,
            include_reason=False,
            expected=2,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "NON_READY_REASON_REQUIRED",
        )
        for reason_code, reason in (
            ("not sanitized", "Safe reason."),
            ("SAFE_REASON", "unsafe\nreason"),
        ):
            with self.subTest(reason_code=reason_code, reason=reason):
                rejected = self.complete_aborted_result(
                    claimed,
                    reason_code=reason_code,
                    reason=reason,
                    expected=2,
                )
                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "NON_READY_REASON_INVALID",
                )

    def test_user_completion_cannot_claim_artifact_drift_provenance(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipts = Path(str(claimed["receipt_path"])).parent
        receipts_before = sorted(receipts.iterdir())
        for scanner_fails in (False, True):
            with self.subTest(scanner_fails=scanner_fails):
                if scanner_fails:
                    self.fail_secret_scan()
                rejected = self.complete_review_required_result(
                    claimed,
                    reason_code="PACKAGE_ARTIFACT_DRIFT",
                    reason="A claimed immutable package artifact changed.",
                    expected=2,
                )
                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "TERMINAL_REASON_RESERVED",
                )
                self.assertEqual(sorted(receipts.iterdir()), receipts_before)
                self.assertFalse(
                    (
                        self.registry
                        / "tracks"
                        / "alpha"
                        / "quarantines"
                        / "{}.json".format(package["checkpoint_id"])
                    ).exists()
                )
                self.assertEqual(
                    self.inspect(str(package["selector"]))["state"], "CLAIMED"
                )

    def test_artifact_drift_terminalizes_run_as_review_required(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("tampered after claim\n", encoding="utf-8")

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(terminal["drift"], "MATERIAL")
        self.assertEqual(terminal["reason_code"], "PACKAGE_ARTIFACT_DRIFT")
        packaged_handoff.write_bytes(original)
        inspected = json.loads(
            self.run_cli(
                "inspect",
                "--registry-root",
                str(self.registry),
                "--selector",
                str(package["selector"]),
            ).stdout
        )
        self.assertEqual(inspected["state"], "NEEDS_REVIEW")

    def test_unselected_active_drift_terminalizes_before_other_claim(self) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))
        alpha_handoff = Path(str(alpha["package_path"])) / "handoff.md"
        original = alpha_handoff.read_bytes()
        alpha_handoff.write_text("tampered active alpha\n", encoding="utf-8")
        self.fail_secret_scan()

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        alpha_handoff.write_bytes(original)
        alpha_state = self.inspect(str(alpha["selector"]))
        self.assertEqual(alpha_state["state"], "NEEDS_REVIEW")
        self.assertFalse(alpha_state["claim_active"])
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "AVAILABLE")
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(
            terminal["validation"]["secret_scan"],
            "PREVALIDATED_DERIVED_TERMINAL",
        )

    def test_exact_release_after_aborted_run_returns_package_to_available(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)

        released = json.loads(self.release(aborted).stdout)

        self.assertEqual(released["event"], "RELEASED")
        self.assertEqual(released["status"], "ABORTED")
        self.assertEqual(released["revision"], aborted["revision"] + 1)
        self.assertEqual(released["previous_receipt_sha256"], aborted["receipt_sha256"])
        inspected = json.loads(
            self.run_cli(
                "inspect",
                "--registry-root",
                str(self.registry),
                "--selector",
                str(package["selector"]),
            ).stdout
        )
        self.assertEqual(inspected["state"], "AVAILABLE")
        reclaimed = json.loads(self.claim(str(package["selector"])).stdout)
        self.assertNotEqual(reclaimed["receipt_id"], aborted["receipt_id"])
        self.assertEqual(
            reclaimed["previous_lifecycle_receipt_id"], released["receipt_id"]
        )
        self.assertEqual(
            reclaimed["previous_lifecycle_receipt_sha256"],
            released["receipt_sha256"],
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "CLAIMED")

    def test_stale_older_closed_claim_cannot_replace_latest_claim_view(self) -> None:
        package = self.publish()
        first_claim = json.loads(self.claim(str(package["selector"])).stdout)
        first_aborted = self.complete_aborted(first_claim)
        self.release(first_aborted)
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        stale_claim = claim_path.read_bytes()
        second_claim = json.loads(self.claim(str(package["selector"])).stdout)
        self.complete_aborted(second_claim)
        claim_path.write_bytes(stale_claim)

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_release_quarantines_package_drift_introduced_by_secret_scan(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        self.mutate_during_secret_scan(
            packaged_handoff, "tampered during release receipt scan"
        )

        rejected = self.release(aborted, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        checkpoint_id = str(package["checkpoint_id"])
        index = json.loads((self.registry / "index.json").read_text(encoding="utf-8"))
        package_entry = index["tracks"]["alpha"]["packages"][checkpoint_id]
        self.assertEqual(
            package_entry["quarantine_reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        self.assertTrue(
            (
                self.registry
                / "tracks"
                / "alpha"
                / "quarantines"
                / "{}.json".format(checkpoint_id)
            ).is_file()
        )
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_inspect_rejects_release_that_rewrites_aborted_run_semantics(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)
        released = json.loads(self.release(aborted).stdout)
        released_path = Path(str(released["receipt_path"]))
        forged = json.loads(released_path.read_text(encoding="utf-8"))
        forged["reason_code"] = "FORGED_RELEASE_REASON"
        forged["reason"] = "A coordinated rewrite changed the abandoned run."
        released_path.write_text(
            json.dumps(forged, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        forged_hash = hashlib.sha256(released_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        index["receipts"][str(released["receipt_id"])]["latest_receipt_sha256"] = (
            forged_hash
        )
        claim["latest_receipt_sha256"] = forged_hash
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_lifecycle_claim_requires_exact_released_aborted_predecessor(self) -> None:
        package = self.publish()
        first_claim = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(first_claim)
        released = json.loads(self.release(aborted).stdout)
        second_claim = json.loads(self.claim(str(package["selector"])).stdout)
        released_path = Path(str(released["receipt_path"]))
        aborted_path = Path(str(aborted["receipt_path"]))
        second_path = Path(str(second_claim["receipt_path"]))
        released_path.unlink()
        aborted_hash = hashlib.sha256(aborted_path.read_bytes()).hexdigest()
        forged_second = json.loads(second_path.read_text(encoding="utf-8"))
        forged_second["previous_lifecycle_receipt_sha256"] = aborted_hash
        second_path.write_text(
            json.dumps(forged_second, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        second_hash = hashlib.sha256(second_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        first_entry = index["receipts"][first_claim["receipt_id"]]
        first_entry.update(
            {
                "latest_revision": aborted["revision"],
                "latest_receipt_sha256": aborted_hash,
                "latest_receipt_path": str(aborted_path),
                "terminal_status": "ABORTED",
            }
        )
        first_entry.pop("released_at")
        second_entry = index["receipts"][second_claim["receipt_id"]]
        second_entry["latest_receipt_sha256"] = second_hash
        for view in (index["tracks"]["alpha"], track):
            view["active_claim"]["latest_receipt_sha256"] = second_hash
        claim["latest_receipt_sha256"] = second_hash
        second_entry["latest_receipt_sha256"] = second_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_publish_on_claimed_track_leaves_no_orphan_package(self) -> None:
        package = self.publish()
        self.claim(str(package["selector"]))
        self.handoff.write_text("# New checkpoint while claimed\n", encoding="utf-8")
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-02T13:15:11-05:00"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
        packages_root = self.registry / "tracks" / "alpha" / "packages"
        before = sorted(path.name for path in packages_root.iterdir())

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "TRACK_ACTIVE_CLAIM"
        )
        self.assertEqual(sorted(path.name for path in packages_root.iterdir()), before)

    def test_telemetry_gate_cannot_be_advanced_without_terminal_completion(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        rejected = self.advance(current, "TELEMETRY_VALIDATED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "GATE_TRANSITION_INVALID"
        )
        completed = json.loads(self.complete_ready(current).stdout)
        self.assertEqual(completed["status"], "READY")

    def test_registry_permissions_are_private_without_chmodding_compatibility_parent(
        self,
    ) -> None:
        state_dir = self.compatibility.parent
        state_dir.chmod(0o755)
        package = self.publish()
        self.claim(str(package["selector"]))

        self.assertEqual(stat.S_IMODE(state_dir.stat().st_mode), 0o755)
        registry_directories = [
            self.registry,
            *[path for path in self.registry.rglob("*") if path.is_dir()],
        ]
        registry_files = [path for path in self.registry.rglob("*") if path.is_file()]
        self.assertTrue(registry_directories)
        self.assertTrue(registry_files)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o700
                for path in registry_directories
            )
        )
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in registry_files)
        )
        self.assertFalse(
            any(path.name.startswith(".") for path in self.registry.rglob("*"))
        )

    def test_orphaned_claim_on_another_track_blocks_new_claim(self) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        claimed = json.loads(self.claim(str(alpha["selector"])).stdout)
        Path(str(claimed["receipt_path"])).unlink()
        before = (self.registry / "index.json").read_bytes()

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertEqual((self.registry / "index.json").read_bytes(), before)

    def test_missing_closed_claim_after_aborted_run_fails_closed(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        self.complete_aborted(claimed)
        (self.registry / "tracks" / "alpha" / "claim.json").unlink()

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_missing_closed_claim_after_ready_run_fails_closed(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        self.complete_ready(current)
        (self.registry / "tracks" / "alpha" / "claim.json").unlink()

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_every_transition_requires_exact_run_correlation(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        before = self.inspect(str(package["selector"]))
        cases = (
            ({"receipt_id": "tp-20000101T000000Z-00000000"}, "RECEIPT_ID_MISMATCH"),
            ({"track_id": "beta"}, "TRACK_ID_MISMATCH"),
            (
                {"checkpoint_id": "cp-20000101-000000-00000000"},
                "CHECKPOINT_ID_MISMATCH",
            ),
            ({"expected_revision": 99}, "RECEIPT_REVISION_CONFLICT"),
            ({"expected_receipt_sha256": "0" * 64}, "RECEIPT_HASH_CONFLICT"),
        )

        for overrides, reason_code in cases:
            with self.subTest(reason_code=reason_code):
                rejected = self.advance(
                    claimed,
                    "CANONICAL_PAIR_VERIFIED",
                    expected=3,
                    **overrides,
                )
                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"], reason_code
                )
                self.assertEqual(self.inspect(str(package["selector"])), before)
        accepted = json.loads(self.advance(claimed, "CANONICAL_PAIR_VERIFIED").stdout)
        self.assertEqual(accepted["revision"], 2)

    def test_wrong_transition_correlation_precedes_unrelated_drift_handling(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        alpha_claim = json.loads(self.claim(str(alpha["selector"])).stdout)
        self.claim(str(beta["selector"]))
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        original = beta_handoff.read_bytes()
        beta_handoff.write_text("tampered before wrong advance\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.registry.rglob("*.json")}

        rejected = self.advance(
            alpha_claim,
            "CANONICAL_PAIR_VERIFIED",
            expected_receipt_sha256="0" * 64,
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RECEIPT_HASH_CONFLICT"
        )
        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        beta_handoff.write_bytes(original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "CLAIMED")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "CLAIMED")

    def test_wrong_completion_correlation_precedes_unrelated_drift_handling(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        alpha_claim = json.loads(self.claim(str(alpha["selector"])).stdout)
        self.claim(str(beta["selector"]))
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        original = beta_handoff.read_bytes()
        beta_handoff.write_text("tampered before wrong complete\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.registry.rglob("*.json")}
        wrong = dict(alpha_claim)
        wrong["receipt_sha256"] = "0" * 64

        rejected = self.complete_aborted_result(wrong, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RECEIPT_HASH_CONFLICT"
        )
        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        beta_handoff.write_bytes(original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "CLAIMED")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "CLAIMED")

    def test_wrong_release_correlation_precedes_unrelated_drift_handling(self) -> None:
        alpha = self.publish("alpha")
        alpha_claim = json.loads(self.claim(str(alpha["selector"])).stdout)
        alpha_aborted = self.complete_aborted(alpha_claim)
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(beta["selector"]))
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        original = beta_handoff.read_bytes()
        beta_handoff.write_text("tampered before wrong release\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.registry.rglob("*.json")}
        wrong = dict(alpha_aborted)
        wrong["receipt_sha256"] = "0" * 64

        rejected = self.release(wrong, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "RELEASE_CORRELATION_MISMATCH",
        )
        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        beta_handoff.write_bytes(original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "NEEDS_REVIEW")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "CLAIMED")

    def test_superseded_package_cannot_be_claimed(self) -> None:
        first = self.publish()
        self.handoff.write_text("# Replacement handoff\n", encoding="utf-8")
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-02T14:00:00-05:00"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
        self.publish()
        before = self.inspect(str(first["selector"]))

        rejected = self.claim(str(first["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PICKUP_SUPERSEDED"
        )
        self.assertEqual(self.inspect(str(first["selector"])), before)

    def test_non_overlapping_tracks_keep_independent_active_receipt_histories(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)

        alpha_claim = json.loads(self.claim(str(alpha["selector"])).stdout)
        beta_claim = json.loads(self.claim(str(beta["selector"])).stdout)
        alpha_advanced = json.loads(
            self.advance(alpha_claim, "CANONICAL_PAIR_VERIFIED").stdout
        )
        beta_advanced = json.loads(
            self.advance(beta_claim, "CANONICAL_PAIR_VERIFIED").stdout
        )

        self.assertNotEqual(alpha_claim["receipt_id"], beta_claim["receipt_id"])
        self.assertEqual(alpha_advanced["pickup"]["track_id"], "alpha")
        self.assertEqual(beta_advanced["pickup"]["track_id"], "beta")
        self.assertEqual(alpha_advanced["revision"], 2)
        self.assertEqual(beta_advanced["revision"], 2)
        self.assertNotEqual(
            alpha_advanced["receipt_path"], beta_advanced["receipt_path"]
        )

    def test_new_receipt_id_uses_a_128_bit_random_suffix(self) -> None:
        package = self.publish()

        claimed = json.loads(self.claim(str(package["selector"])).stdout)

        self.assertRegex(
            str(claimed["receipt_id"]),
            r"^tp-\d{8}T\d{6}Z-[0-9a-f]{32}$",
        )

    def test_receipt_id_allocation_retries_index_and_namespace_collisions(
        self,
    ) -> None:
        registry_module = self.load_registry_module()
        timestamp = "2026-09-03T01:02:03Z"
        indexed_collision = "tp-20260903T010203Z-{}".format("a" * 32)
        namespace_collision = "tp-20260903T010203Z-{}".format("b" * 32)
        expected = "tp-20260903T010203Z-{}".format("c" * 32)
        for track_id in ("alpha", "beta"):
            (self.registry / "tracks" / track_id / "receipts").mkdir(
                parents=True,
                mode=0o700,
            )
        namespace_path = (
            self.registry
            / "tracks"
            / "beta"
            / "receipts"
            / "{}-r0001.json".format(namespace_collision)
        )
        namespace_path.write_text("{}\n", encoding="utf-8")
        index = {
            "tracks": {"alpha": {}, "beta": {}},
            "receipts": {indexed_collision: {}},
        }

        with mock.patch.object(
            registry_module.secrets,
            "token_hex",
            side_effect=("a" * 32, "b" * 32, "c" * 32),
        ):
            observed = registry_module.allocate_receipt_id(
                self.registry,
                index,
                timestamp,
            )

        self.assertEqual(observed, expected)

    def test_two_active_drifted_tracks_terminalize_without_recursion(self) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        alpha_claim = json.loads(self.claim(str(alpha["selector"])).stdout)
        self.claim(str(beta["selector"]))
        alpha_handoff = Path(str(alpha["package_path"])) / "handoff.md"
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        alpha_original = alpha_handoff.read_bytes()
        beta_original = beta_handoff.read_bytes()
        alpha_handoff.write_text("tampered active alpha\n", encoding="utf-8")
        beta_handoff.write_text("tampered active beta\n", encoding="utf-8")

        rejected = self.advance(alpha_claim, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        alpha_handoff.write_bytes(alpha_original)
        beta_handoff.write_bytes(beta_original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "NEEDS_REVIEW")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "NEEDS_REVIEW")
        self.assertFalse(self.inspect(str(alpha["selector"]))["claim_active"])
        self.assertFalse(self.inspect(str(beta["selector"]))["claim_active"])

    def test_drift_discovered_during_terminal_scan_joins_iterative_closure(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        alpha_claim = json.loads(self.claim(str(alpha["selector"])).stdout)
        self.claim(str(beta["selector"]))
        alpha_handoff = Path(str(alpha["package_path"])) / "handoff.md"
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        alpha_original = alpha_handoff.read_bytes()
        beta_original = beta_handoff.read_bytes()
        alpha_handoff.write_text(
            "alpha drift before reconciliation\n", encoding="utf-8"
        )
        self.mutate_during_secret_scan(
            beta_handoff, "beta drift introduced during alpha terminal scan"
        )

        rejected = self.advance(alpha_claim, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        alpha_handoff.write_bytes(alpha_original)
        beta_handoff.write_bytes(beta_original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "NEEDS_REVIEW")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "NEEDS_REVIEW")
        self.assertFalse(self.inspect(str(alpha["selector"]))["claim_active"])
        self.assertFalse(self.inspect(str(beta["selector"]))["claim_active"])

    def test_release_rejects_non_aborted_terminal_run(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("drift\n", encoding="utf-8")
        self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        packaged_handoff.write_bytes(original)
        before = self.inspect(str(package["selector"]))

        rejected = self.release(terminal, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RELEASE_NOT_PERMITTED"
        )
        self.assertEqual(self.inspect(str(package["selector"])), before)

    def test_claim_secret_scan_failure_leaves_package_unclaimed(self) -> None:
        package = self.publish()
        self.gitleaks.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        before = self.inspect(str(package["selector"]))

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "SENSITIVE_DATA_SCAN_FAILED"
        )
        self.assertEqual(self.inspect(str(package["selector"])), before)
        self.assertFalse(self.compatibility.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists())

    def test_publish_rejects_symlinked_handoff_without_registry_mutation(self) -> None:
        target = self.root / "real-handoff.md"
        self.handoff.replace(target)
        self.handoff.symlink_to(target)

        rejected = self.publish_result(expected=2)

        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "HANDOFF_INVALID")
        self.assertFalse((self.registry / "index.json").exists())

    def test_registry_json_contains_no_private_runtime_identity_fields(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        self.complete_ready(current)

        forbidden = {
            "process_id",
            "session_id",
            "task_id",
            "thread_id",
            "window_id",
            "window_title",
        }

        def keys(value: object) -> set[str]:
            if isinstance(value, dict):
                result = set(value)
                for child in value.values():
                    result.update(keys(child))
                return result
            if isinstance(value, list):
                result: set[str] = set()
                for child in value:
                    result.update(keys(child))
                return result
            return set()

        json_files = [*self.registry.rglob("*.json"), self.compatibility]
        self.assertTrue(json_files)
        for path in json_files:
            with self.subTest(path=path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(forbidden.isdisjoint(keys(payload)))
                if payload.get("schema_version") == 4:
                    self.assertFalse(payload["scope"]["phase_authorized"])

    def test_publish_rejects_checkpoint_pickup_metadata_mismatch(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["pickup"] = {
            "track_id": "different-track",
            "resource_scopes": [str(self.resource)],
        }
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PICKUP_METADATA_MISMATCH"
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_publish_sanitizes_canonical_handoff_symlink_loop(self) -> None:
        loop = self.root / "canonical-loop.md"
        loop.symlink_to(loop)
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["canonical_handoff"] = str(loop)
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "CANONICAL_PAIR_MISMATCH"
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_publish_accepts_matching_checkpoint_pickup_metadata(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["pickup"] = {
            "track_id": "alpha",
            "resource_scopes": [str(self.resource)],
        }
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        published = self.publish()

        self.assertEqual(published["track_id"], "alpha")
        self.assertEqual(published["resource_scopes"], [str(self.resource)])

    def test_publish_rejects_noncanonical_checkpoint_pickup_scopes(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["pickup"] = {
            "track_id": "alpha",
            "resource_scopes": [str(self.resource / ".." / "alpha")],
        }
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PICKUP_METADATA_MISMATCH"
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_publish_secret_scan_failure_leaves_no_package_or_index(self) -> None:
        self.gitleaks.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "SENSITIVE_DATA_SCAN_FAILED"
        )
        self.assertFalse((self.registry / "index.json").exists())
        packages = self.registry / "tracks" / "alpha" / "packages"
        self.assertFalse(packages.exists() and any(packages.iterdir()))

        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        published = self.publish()
        self.assertEqual(published["state"], "AVAILABLE")

    def test_publish_rejects_candidate_mode_changed_during_secret_scan(self) -> None:
        self.gitleaks.write_text(
            "#!/bin/sh\n"
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "--source" ]; then\n'
            "    shift\n"
            '    chmod 644 "$1/handoff.md"\n'
            "  fi\n"
            "  shift\n"
            "done\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertFalse((self.registry / "index.json").exists())
        packages = self.registry / "tracks" / "alpha" / "packages"
        candidates = list(packages.iterdir())
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].name.startswith(".cp-"))
        self.assertEqual(
            stat.S_IMODE((candidates[0] / "handoff.md").stat().st_mode),
            0o644,
        )
        self.assertFalse(any(not child.name.startswith(".") for child in candidates))

    def test_publish_unwritable_registry_parent_returns_sanitized_error(self) -> None:
        parent = self.root / "blocked-registry-parent"
        parent.mkdir()
        parent.chmod(0o500)
        registry = parent / "pickups"
        try:
            rejected = self.run_cli(
                "publish",
                "--registry-root",
                str(registry),
                "--track-id",
                "alpha",
                "--resource-scope",
                str(self.resource),
                "--handoff",
                str(self.handoff),
                "--checkpoint",
                str(self.checkpoint),
                "--gitleaks-path",
                str(self.gitleaks),
                expected=2,
            )
        finally:
            parent.chmod(0o700)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_ROOT_UNAVAILABLE"
        )
        self.assertNotIn("Traceback", rejected.stderr)
        self.assertFalse(registry.exists())

    def test_package_rollback_preserves_unowned_addition(self) -> None:
        rejected = self.run_cli(
            "publish",
            "--registry-root",
            str(self.registry),
            "--track-id",
            "alpha",
            "--resource-scope",
            str(self.resource),
            "--handoff",
            str(self.handoff),
            "--checkpoint",
            str(self.checkpoint),
            "--gitleaks-path",
            str(self.gitleaks),
            expected=3,
            extra_env=self.package_rollback_foreign_file_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        packages_root = self.registry / "tracks" / "alpha" / "packages"
        installed = [path for path in packages_root.iterdir() if path.is_dir()]
        self.assertEqual(len(installed), 1)
        self.assertEqual(
            (installed[0] / "foreign.txt").read_text(encoding="utf-8"),
            "foreign replacement evidence\n",
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_publication_cleanup_preserves_foreign_staging_file(self) -> None:
        self.add_foreign_staging_file_during_scan()

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        packages_root = self.registry / "tracks" / "alpha" / "packages"
        staging = [
            path for path in packages_root.iterdir() if path.name.startswith(".")
        ]
        self.assertEqual(len(staging), 1)
        self.assertEqual(
            (staging[0] / "foreign.txt").read_text(encoding="utf-8"),
            "foreign staging evidence\n",
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_claim_fsync_failure_before_immutable_install_is_retryable(self) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.fsync_fault_environment(
                "temporary-file",
                target=self.registry / "tracks" / "alpha" / "receipts",
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "IMMUTABLE_WRITE_FAILED"
        )
        self.assertTrue((self.root / "fsync-fault-fired").is_file())
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        self.assertFalse(
            any(path.name.startswith(".") for path in self.registry.rglob("*"))
        )
        claimed = json.loads(self.claim(selector).stdout)
        self.assertEqual(claimed["pickup"]["selector"], selector)

    def test_quarantine_fsync_failure_removes_owned_empty_parent(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        handoff = Path(str(package["package_path"])) / "handoff.md"
        original = handoff.read_bytes()
        handoff.write_text("tampered before quarantine\n", encoding="utf-8")

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.fsync_fault_environment(
                "directory",
                target=self.registry / "tracks" / "alpha" / "quarantines",
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "TRANSACTION_ROLLBACK_FAILED"
        )
        self.assertTrue((self.root / "fsync-fault-fired").is_file())
        quarantines = self.registry / "tracks" / "alpha" / "quarantines"
        self.assertFalse(quarantines.exists())
        handoff.write_bytes(original)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertEqual(
            json.loads(self.claim(selector).stdout)["pickup"]["selector"], selector
        )

    def test_claim_rolls_back_after_first_mutable_view_sync_failure(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.fsync_fault_environment(
                "directory-after-link",
                target=self.registry / "tracks" / "alpha",
                arm_destination=(self.registry / "tracks" / "alpha" / "claim.json"),
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "TRANSACTION_ROLLBACK_FAILED"
        )
        self.assertTrue((self.root / "fsync-fault-fired").is_file())
        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        self.assertFalse(
            any(path.name.startswith(".") for path in self.registry.rglob("*"))
        )
        claimed = json.loads(self.claim(selector).stdout)
        self.assertEqual(claimed["pickup"]["selector"], selector)

    def test_mutable_rollback_preserves_same_content_replacement(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.mutable_same_content_replacement_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue(claim_path.is_file())
        foreign_claim = json.loads(claim_path.read_text(encoding="utf-8"))
        self.assertTrue(foreign_claim["active"])
        rejected_inspect = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            selector,
            expected=3,
        )
        self.assertEqual(
            json.loads(rejected_inspect.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_mutable_cleanup_preserves_replaced_staging_inode(self) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.mutable_staging_replacement_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue((self.root / "staging-fault-fired").is_file())
        staging_candidates = list(
            (self.registry / "tracks" / "alpha").glob(".claim.json-*.tmp")
        )
        self.assertEqual(len(staging_candidates), 1)
        staging = staging_candidates[0]
        self.assertEqual(
            staging.read_text(encoding="utf-8"), "foreign staging replacement\n"
        )
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())

    def test_claim_rejects_post_unlink_foreign_staging_addition(self) -> None:
        package = self.publish()

        rejected = self.run_cli(
            *self.claim_arguments(str(package["selector"])),
            expected=3,
            extra_env=self.post_unlink_mutable_addition_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        leftovers = list((self.registry / "tracks" / "alpha").glob(".track.json-*.tmp"))
        self.assertEqual(len(leftovers), 1)
        self.assertEqual(
            leftovers[0].read_text(encoding="utf-8"),
            "foreign post-cleanup addition\n",
        )

    def test_claim_rejects_post_unlink_foreign_immutable_staging_addition(
        self,
    ) -> None:
        package = self.publish()

        rejected = self.run_cli(
            *self.claim_arguments(str(package["selector"])),
            expected=3,
            extra_env=self.post_unlink_immutable_addition_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        leftovers = list(receipts.glob(".tp-*.tmp"))
        self.assertEqual(len(leftovers), 1)
        self.assertEqual(
            leftovers[0].read_text(encoding="utf-8"),
            "foreign immutable post-cleanup addition\n",
        )

    def test_claim_rejects_foreign_receipts_directory_adoption(self) -> None:
        package = self.publish()
        track_root = self.registry / "tracks" / "alpha"
        before = {
            path: path.read_bytes()
            for path in (self.registry / "index.json", track_root / "track.json")
        }

        rejected = self.run_cli(
            *self.claim_arguments(str(package["selector"])),
            expected=3,
            extra_env=self.foreign_directory_adoption_environment(
                track_root, "receipts"
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        marker = track_root / "receipts" / "foreign-marker"
        self.assertEqual(
            marker.read_text(encoding="utf-8"), "foreign directory addition\n"
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(self.compatibility.exists())

    def test_publish_rejects_foreign_scaffold_directory_adoption(self) -> None:
        rejected = self.publish_result(
            expected=3,
            extra_env=self.foreign_directory_adoption_environment(
                self.registry, "tracks"
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        marker = self.registry / "tracks" / "foreign-marker"
        self.assertEqual(
            marker.read_text(encoding="utf-8"), "foreign directory addition\n"
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_claim_rejects_unrelated_foreign_entry_added_during_commit(
        self,
    ) -> None:
        package = self.publish()
        track_root = self.registry / "tracks" / "alpha"
        before = {
            path: path.read_bytes()
            for path in (self.registry / "index.json", track_root / "track.json")
        }

        rejected = self.run_cli(
            *self.claim_arguments(str(package["selector"])),
            expected=3,
            extra_env=self.foreign_registry_entry_during_commit_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        marker = track_root / "foreign-during-commit"
        self.assertEqual(
            marker.read_text(encoding="utf-8"), "foreign registry addition\n"
        )
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(self.compatibility.exists())

    def test_transaction_revalidates_prior_mutable_after_later_commit(self) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.prior_mutable_replacement_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue((self.root / "prior-mutable-fault-fired").is_file())
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        self.assertTrue(claim_path.is_file())
        rejected_inspect = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            selector,
            expected=3,
        )
        self.assertEqual(
            json.loads(rejected_inspect.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_transaction_guards_sealed_package_through_mutable_commit(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        package_handoff = Path(str(package["package_path"])) / "handoff.md"
        before_bytes = package_handoff.read_bytes()
        before_identity = package_handoff.stat().st_ino

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.immutable_commit_replacement_environment(
                immutable=package_handoff
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_INSTALL_CHANGED",
        )
        self.assertNotEqual(package_handoff.stat().st_ino, before_identity)
        self.assertEqual(package_handoff.read_bytes(), before_bytes)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))

    def test_transaction_guards_prior_receipt_through_later_commit(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        claimed = json.loads(self.claim(selector).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        before_bytes = receipt_path.read_bytes()
        before_identity = receipt_path.stat().st_ino

        rejected = self.advance(
            claimed,
            "CANONICAL_PAIR_VERIFIED",
            expected=3,
            extra_env=self.immutable_commit_replacement_environment(
                immutable=receipt_path
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_INSTALL_CHANGED",
        )
        self.assertNotEqual(receipt_path.stat().st_ino, before_identity)
        self.assertEqual(receipt_path.read_bytes(), before_bytes)
        inspected = self.inspect(selector)
        self.assertEqual(inspected["state"], "CLAIMED")
        receipt_files = list(receipt_path.parent.glob("*.json"))
        self.assertEqual(receipt_files, [receipt_path])

    def test_transaction_guards_deployed_skill_through_mutable_commit(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        copied_skill_root = self.root / "deployed" / "treasurepickup"
        copied_script = copied_skill_root / "scripts" / "pickup_registry.py"
        copied_script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, copied_script)
        copied_skill = copied_skill_root / "SKILL.md"
        shutil.copy2(SCRIPT.parents[1] / "SKILL.md", copied_skill)
        before_bytes = copied_skill.read_bytes()
        before_identity = copied_skill.stat().st_ino
        arguments = self.claim_arguments(selector)
        arguments[arguments.index("--skill-file") + 1] = str(copied_skill)

        completed = subprocess.run(
            [sys.executable, str(copied_script), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                **self.immutable_commit_replacement_environment(immutable=copied_skill),
            },
        )

        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertEqual(
            json.loads(completed.stderr)["reason_code"],
            "TRANSACTION_INSTALL_CHANGED",
        )
        self.assertNotEqual(copied_skill.stat().st_ino, before_identity)
        self.assertEqual(copied_skill.read_bytes(), before_bytes)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")

    def test_registry_lock_rejects_root_replacement_before_lock_open(self) -> None:
        self.publish()

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            expected=2,
            extra_env=self.registry_lock_root_replacement_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_LOCK_UNAVAILABLE"
        )
        self.assertTrue((self.root / "registry-lock-fault-fired").is_file())
        self.assertTrue(self.registry.is_symlink())
        foreign = self.registry.with_name("pickups-foreign-replacement")
        self.assertEqual(list(foreign.iterdir()), [])

    def test_registry_lock_rejects_root_swap_immediately_after_flock(self) -> None:
        rejected = self.publish_result(
            expected=2,
            extra_env=self.registry_root_swap_after_flock_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_LOCK_UNAVAILABLE"
        )
        original = self.registry.with_name("pickups-locked-original")
        self.assertTrue(original.is_dir())
        self.assertEqual(list(original.iterdir()), [])
        self.assertTrue(self.registry.is_dir())
        self.assertEqual(list(self.registry.iterdir()), [])

    def test_immutable_rollback_preserves_same_content_replacement(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        receipts = self.registry / "tracks" / "alpha" / "receipts"

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.immutable_same_content_replacement_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        receipt_files = list(receipts.glob("*.json"))
        self.assertEqual(len(receipt_files), 1)
        self.assertTrue(json.loads(receipt_files[0].read_text(encoding="utf-8")))
        self.assertTrue((self.root / "immutable-fault-fired").is_file())
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())

    def test_immutable_cleanup_preserves_replaced_staging_inode(self) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.immutable_staging_replacement_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue((self.root / "immutable-staging-fault-fired").is_file())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        staging_candidates = list(receipts.glob(".*.tmp"))
        self.assertEqual(len(staging_candidates), 1)
        self.assertEqual(
            staging_candidates[0].read_text(encoding="utf-8"),
            "foreign immutable staging replacement\n",
        )
        self.assertFalse(list(receipts.glob("*.json")))

    def test_existing_mutable_exchange_preserves_racing_replacement(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        track_path = self.registry / "tracks" / "alpha" / "track.json"

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.mutable_exchange_race_environment(track_path),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        marker = self.root / "mutable-exchange-fault-fired"
        self.assertTrue(marker.is_file())
        self.assertEqual(
            track_path.stat().st_ino, int(marker.read_text(encoding="utf-8"))
        )
        self.assertEqual(stat.S_IMODE(track_path.stat().st_mode), 0o644)
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())
        self.assertFalse(self.compatibility.exists())

    def test_claim_rolls_back_if_new_view_staging_unlink_fails(self) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.staged_inode_unlink_fault_environment(
                self.registry / "tracks" / "alpha"
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue((self.root / "unlink-fault-fired").is_file())
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse((self.registry / "tracks" / "alpha" / "claim.json").exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        self.assertFalse(
            any(path.name.startswith(".") for path in self.registry.rglob("*"))
        )
        self.assertEqual(
            json.loads(self.claim(selector).stdout)["pickup"]["selector"], selector
        )

    def test_owned_cleanup_syncs_parent_immediately_after_each_unlink(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        track_root = self.registry / "tracks" / "alpha"

        claimed = self.run_cli(
            *self.claim_arguments(selector),
            extra_env=self.cleanup_sync_trace_environment(track_root),
        )

        self.assertEqual(json.loads(claimed.stdout)["pickup"]["selector"], selector)
        events = (
            (self.root / "cleanup-sync-trace").read_text(encoding="utf-8").splitlines()
        )
        unlink_positions = [
            position for position, event in enumerate(events) if event == "UNLINK"
        ]
        self.assertGreaterEqual(len(unlink_positions), 2)
        for position in unlink_positions:
            self.assertLess(position + 1, len(events))
            self.assertEqual(events[position + 1], "SYNC")

    def test_late_mutable_cleanup_failure_restores_every_authoritative_view(
        self,
    ) -> None:
        package = self.publish()
        selector = str(package["selector"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        before = {path: path.read_bytes() for path in (index_path, track_path)}

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.late_mutable_cleanup_fault_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue((self.root / "late-mutable-cleanup-fault-fired").is_file())
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        self.assertFalse(
            any(path.name.startswith(".") for path in self.registry.rglob("*"))
        )

    def test_existing_view_rollback_syncs_exchange_before_staging_cleanup(
        self,
    ) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.rollback_exchange_sync_trace_environment(),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        events = (
            (self.root / "rollback-exchange-sync-trace")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[:2], ["FAULT_UNLINK", "SYNC"])
        self.assertIn("ROLLBACK_UNLINK", events[2:])
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        self.assertFalse(self.compatibility.exists())

    def test_claim_rolls_back_if_immutable_staging_unlink_fails(self) -> None:
        package = self.publish()
        selector = str(package["selector"])

        rejected = self.run_cli(
            *self.claim_arguments(selector),
            expected=3,
            extra_env=self.staged_inode_unlink_fault_environment(
                self.registry / "tracks" / "alpha" / "receipts"
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "IMMUTABLE_WRITE_FAILED"
        )
        self.assertTrue((self.root / "unlink-fault-fired").is_file())
        self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")
        receipts = self.registry / "tracks" / "alpha" / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        self.assertFalse(
            any(path.name.startswith(".") for path in self.registry.rglob("*"))
        )
        self.assertEqual(
            json.loads(self.claim(selector).stdout)["pickup"]["selector"], selector
        )

    def test_inspect_list_includes_durable_phase_context_for_selection(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["current_phase"] = "SHA-256 repair"
        checkpoint["next_phase"] = "DEAS definition"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
        package = self.publish()

        listed = json.loads(
            self.run_cli("inspect", "--registry-root", str(self.registry)).stdout
        )["packages"]

        self.assertEqual(
            listed,
            [
                {
                    "track_id": "alpha",
                    "checkpoint_id": package["checkpoint_id"],
                    "selector": package["selector"],
                    "state": "AVAILABLE",
                    "claim_active": False,
                    "generated_at": "2026-09-02T12:55:09-05:00",
                    "current_phase": "SHA-256 repair",
                    "next_phase": "DEAS definition",
                    "resource_scopes": [str(self.resource)],
                }
            ],
        )

    def test_inspect_of_missing_registry_is_read_only(self) -> None:
        self.assertFalse(self.registry.exists())

        listed = json.loads(
            self.run_cli("inspect", "--registry-root", str(self.registry)).stdout
        )

        self.assertEqual(listed["packages"], [])
        self.assertFalse(self.registry.exists())

    def test_inspect_rejects_relative_missing_registry_root(self) -> None:
        relative_root = "definitely-relative-and-absent"

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            relative_root,
            expected=2,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_ROOT_INVALID"
        )
        self.assertFalse((self.root / relative_root).exists())

    def test_inspect_rejects_dangling_index_symlink(self) -> None:
        self.registry.mkdir(parents=True, mode=0o700)
        (self.registry / "index.json").symlink_to(self.root / "missing-index.json")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_INDEX_INVALID"
        )

    def test_publish_rejects_dangling_index_symlink_without_replacing_it(
        self,
    ) -> None:
        self.registry.mkdir(parents=True, mode=0o700)
        missing_target = self.root / "missing-index.json"
        index_path = self.registry / "index.json"
        index_path.symlink_to(missing_target)

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_INDEX_INVALID"
        )
        self.assertTrue(index_path.is_symlink())
        self.assertFalse(missing_target.exists())

    def test_completion_artifact_drift_terminalizes_run_for_review(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        packaged_handoff.write_text("completion-time drift\n", encoding="utf-8")

        rejected = self.complete_ready(current, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(terminal["drift"], "MATERIAL")
        self.assertEqual(terminal["reason_code"], "PACKAGE_ARTIFACT_DRIFT")

    def test_advance_requires_structured_gate_evidence_without_mutation(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        before = self.inspect(str(package["selector"]))

        rejected = self.advance(
            claimed,
            "CANONICAL_PAIR_VERIFIED",
            include_evidence=False,
            expected=2,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "TRANSITION_EVIDENCE_REQUIRED"
        )
        self.assertEqual(self.inspect(str(package["selector"])), before)
        accepted = self.advance(claimed, "CANONICAL_PAIR_VERIFIED")
        self.assertEqual(json.loads(accepted.stdout)["revision"], 2)

    def test_advance_rejects_non_rfc3339_evidence_timestamp(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        for observed_at in (
            "2026-09-02 18:00:00+00:00",
            "2026-09-02T18:00:00+00:60",
        ):
            with self.subTest(observed_at=observed_at):
                evidence = {
                    "schema_version": 1,
                    "gate": "CANONICAL_PAIR_VERIFIED",
                    "status": "PASS",
                    "observed_at": observed_at,
                    "checks": [{"name": "fixture-check", "status": "PASS"}],
                }

                rejected = self.advance(
                    claimed,
                    "CANONICAL_PAIR_VERIFIED",
                    evidence=evidence,
                    expected=2,
                )

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "TRANSITION_EVIDENCE_INVALID",
                )
        accepted = json.loads(self.advance(claimed, "CANONICAL_PAIR_VERIFIED").stdout)
        self.assertEqual(accepted["revision"], 2)

    def test_advance_rejects_boolean_evidence_schema_version(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        evidence = {
            "schema_version": True,
            "gate": "CANONICAL_PAIR_VERIFIED",
            "status": "PASS",
            "observed_at": "2026-09-02T18:00:00Z",
            "checks": [{"name": "fixture-check", "status": "PASS"}],
        }

        rejected = self.advance(
            claimed,
            "CANONICAL_PAIR_VERIFIED",
            evidence=evidence,
            expected=2,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSITION_EVIDENCE_INVALID",
        )

    def test_advance_rejects_runtime_identity_in_nested_evidence(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        for identity_key in (
            "task_id",
            "sessionId",
            "pidValue",
            "ppid value",
            "valuePid",
            "sessionToken",
            "apiKey",
            "access-token",
            "refreshToken",
            "password",
            "clientSecret",
            "privateKey",
        ):
            with self.subTest(identity_key=identity_key):
                evidence = {
                    "schema_version": 1,
                    "gate": "CANONICAL_PAIR_VERIFIED",
                    "status": "PASS",
                    "observed_at": "2026-09-02T18:00:00Z",
                    "checks": [
                        {
                            "name": "fixture-check",
                            "status": "PASS",
                            "detail": {identity_key: "private-runtime-id"},
                        }
                    ],
                }

                rejected = self.advance(
                    claimed,
                    "CANONICAL_PAIR_VERIFIED",
                    evidence=evidence,
                    expected=2,
                )

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "PRIVATE_RUNTIME_IDENTIFIER_FIELD",
                )
        accepted = json.loads(self.advance(claimed, "CANONICAL_PAIR_VERIFIED").stdout)
        self.assertEqual(accepted["revision"], 2)

    def test_advance_rejects_extra_or_private_evidence_fields_without_mutation(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        receipts_before = sorted(receipt_path.parent.iterdir())
        state_before = self.inspect(str(package["selector"]))
        cases = (
            (
                "credential",
                {"credential": "placeholder"},
                "PRIVATE_RUNTIME_IDENTIFIER_FIELD",
            ),
            (
                "phase authorization",
                {"phase_authorized": True},
                "TRANSITION_EVIDENCE_INVALID",
            ),
            (
                "private identifier",
                {"check_extra": {"privateIdentifier": "opaque-person"}},
                "PRIVATE_RUNTIME_IDENTIFIER_FIELD",
            ),
        )
        for label, addition, reason_code in cases:
            with self.subTest(label=label):
                evidence = {
                    "schema_version": 1,
                    "gate": "CANONICAL_PAIR_VERIFIED",
                    "status": "PASS",
                    "observed_at": "2026-09-02T18:00:00Z",
                    "checks": [{"name": "fixture-check", "status": "PASS"}],
                }
                check_extra = addition.get("check_extra")
                if isinstance(check_extra, dict):
                    evidence["checks"][0].update(check_extra)
                else:
                    evidence.update(addition)

                rejected = self.advance(
                    claimed,
                    "CANONICAL_PAIR_VERIFIED",
                    evidence=evidence,
                    expected=2,
                )

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"], reason_code
                )
                self.assertEqual(self.inspect(str(package["selector"])), state_before)
                self.assertEqual(sorted(receipt_path.parent.iterdir()), receipts_before)

    def test_advance_rejects_unbounded_or_nonprintable_evidence_text(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        claimed = json.loads(self.claim(selector).stdout)
        for field, value in (
            ("name", "x" * 101),
            ("name", "control\nname"),
            ("detail", "x" * 501),
            ("detail", "control\tdetail"),
        ):
            with self.subTest(field=field, value_length=len(value)):
                check = {
                    "name": "bounded-check",
                    "status": "PASS",
                    "detail": "bounded detail",
                }
                check[field] = value
                evidence = {
                    "schema_version": 1,
                    "gate": "CANONICAL_PAIR_VERIFIED",
                    "status": "PASS",
                    "observed_at": "2026-09-02T18:00:00Z",
                    "checks": [check],
                }

                rejected = self.advance(
                    claimed,
                    "CANONICAL_PAIR_VERIFIED",
                    evidence=evidence,
                    expected=2,
                )

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "TRANSITION_EVIDENCE_INVALID",
                )
                self.assertEqual(self.inspect(selector)["state"], "CLAIMED")

    def test_claim_artifact_drift_quarantines_package_and_records_review(self) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("claim-time drift\n", encoding="utf-8")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        inspected = self.inspect(str(package["selector"]))
        self.assertEqual(inspected["state"], "NEEDS_REVIEW")
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(terminal["drift"], "MATERIAL")

    def test_claim_artifact_drift_remains_quarantined_when_scanner_fails(
        self,
    ) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("claim drift with scanner unavailable\n")
        self.fail_secret_scan()

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        inspected = self.inspect(str(package["selector"]))
        self.assertEqual(inspected["state"], "NEEDS_REVIEW")
        quarantine = (
            self.registry
            / "tracks"
            / "alpha"
            / "quarantines"
            / "{}.json".format(package["checkpoint_id"])
        )
        self.assertTrue(quarantine.is_file())

        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        retry = self.claim(str(package["selector"]), expected=3)
        self.assertEqual(
            json.loads(retry.stderr)["reason_code"], "PICKUP_NOT_AVAILABLE"
        )

    def test_active_artifact_drift_terminalizes_when_scanner_fails(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("active drift with scanner unavailable\n")
        self.fail_secret_scan()

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        inspected = self.inspect(str(package["selector"]))
        self.assertEqual(inspected["state"], "NEEDS_REVIEW")
        self.assertFalse(inspected["claim_active"])
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(terminal["reason_code"], "PACKAGE_ARTIFACT_DRIFT")

        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        retry = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)
        self.assertEqual(
            json.loads(retry.stderr)["reason_code"], "RECEIPT_REVISION_CONFLICT"
        )

    def test_claim_rechecks_sealed_package_after_receipt_secret_scan(self) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'raced package bytes' > {}\nexit 0\n".format(
                shlex.quote(str(packaged_handoff))
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_receipt_artifact_hash_must_match_sealed_manifest(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        packaged_handoff.write_text("forged receipt artifact bytes\n", encoding="utf-8")
        forged_artifact_hash = hashlib.sha256(packaged_handoff.read_bytes()).hexdigest()
        receipt_path = Path(str(claimed["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["artifacts"]["handoff"]["sha256"] = forged_artifact_hash
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        forged_receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_sha256"] = forged_receipt_hash
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_sha256"] = (
            forged_receipt_hash
        )
        track["active_claim"]["latest_receipt_sha256"] = forged_receipt_hash
        claim["latest_receipt_sha256"] = forged_receipt_hash
        for path, payload in (
            (index_path, index),
            (track_path, track),
            (claim_path, claim),
        ):
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        claimed["receipt_sha256"] = forged_receipt_hash

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_quarantines_drift_on_an_unselected_track(self) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        packaged_handoff = Path(str(alpha["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("unselected drift\n", encoding="utf-8")

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "NEEDS_REVIEW")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "AVAILABLE")
        quarantine = (
            self.registry
            / "tracks"
            / "alpha"
            / "quarantines"
            / "{}.json".format(alpha["checkpoint_id"])
        )
        self.assertTrue(quarantine.is_file())

    def test_claim_terminalizes_active_other_track_deployed_skill_drift(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        copied_skill_root = self.root / "deployed" / "treasurepickup"
        copied_script = copied_skill_root / "scripts" / "pickup_registry.py"
        copied_script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, copied_script)
        copied_skill = copied_skill_root / "SKILL.md"
        shutil.copy2(SCRIPT.parents[1] / "SKILL.md", copied_skill)

        def copied_claim(selector: str, expected: int = 0):
            arguments = self.claim_arguments(selector)
            arguments[arguments.index("--skill-file") + 1] = str(copied_skill)
            completed = subprocess.run(
                [sys.executable, str(copied_script), *arguments],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(completed.returncode, expected, completed.stderr)
            return completed

        def copied_inspect(selector: str) -> dict[str, object]:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(copied_script),
                    "inspect",
                    "--registry-root",
                    str(self.registry),
                    "--selector",
                    selector,
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)

        copied_claim(str(alpha["selector"]))
        copied_skill.write_text("deployed skill drift\n", encoding="utf-8")

        rejected = copied_claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        alpha_state = copied_inspect(str(alpha["selector"]))
        beta_state = copied_inspect(str(beta["selector"]))
        self.assertEqual(alpha_state["state"], "NEEDS_REVIEW")
        self.assertFalse(alpha_state["claim_active"])
        self.assertEqual(beta_state["state"], "AVAILABLE")
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(compatibility["status"], "REVIEW_REQUIRED")
        self.assertEqual(compatibility["drift"], "MATERIAL")
        self.assertEqual(compatibility["reason_code"], "PACKAGE_ARTIFACT_DRIFT")

    def test_publish_terminalizes_active_other_track_deployed_skill_drift(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        copied_skill_root = self.root / "deployed" / "treasurepickup"
        copied_script = copied_skill_root / "scripts" / "pickup_registry.py"
        copied_script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, copied_script)
        copied_skill = copied_skill_root / "SKILL.md"
        shutil.copy2(SCRIPT.parents[1] / "SKILL.md", copied_skill)
        claim_arguments = self.claim_arguments(str(alpha["selector"]))
        claim_arguments[claim_arguments.index("--skill-file") + 1] = str(copied_skill)
        claimed = subprocess.run(
            [sys.executable, str(copied_script), *claim_arguments],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(claimed.returncode, 0, claimed.stderr)
        copied_skill.write_text("deployed skill drift\n", encoding="utf-8")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()

        rejected = subprocess.run(
            [
                sys.executable,
                str(copied_script),
                "publish",
                "--registry-root",
                str(self.registry),
                "--track-id",
                "beta",
                "--resource-scope",
                str(beta_resource),
                "--handoff",
                str(self.handoff),
                "--checkpoint",
                str(self.checkpoint),
                "--gitleaks-path",
                str(self.gitleaks),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(rejected.returncode, 3, rejected.stderr)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        index = json.loads((self.registry / "index.json").read_text(encoding="utf-8"))
        alpha_track = index["tracks"]["alpha"]
        self.assertEqual(
            alpha_track["packages"][str(alpha["checkpoint_id"])]["state"],
            "NEEDS_REVIEW",
        )
        self.assertIsNone(alpha_track["active_claim"])
        self.assertNotIn("beta", index["tracks"])
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(compatibility["status"], "REVIEW_REQUIRED")
        self.assertEqual(compatibility["drift"], "MATERIAL")
        self.assertEqual(compatibility["reason_code"], "PACKAGE_ARTIFACT_DRIFT")

    def test_advance_terminalizes_missing_deployed_skill(self) -> None:
        package = self.publish()
        copied_skill_root = self.root / "deployed" / "treasurepickup"
        copied_script = copied_skill_root / "scripts" / "pickup_registry.py"
        copied_script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, copied_script)
        copied_skill = copied_skill_root / "SKILL.md"
        shutil.copy2(SCRIPT.parents[1] / "SKILL.md", copied_skill)
        claim_arguments = self.claim_arguments(str(package["selector"]))
        claim_arguments[claim_arguments.index("--skill-file") + 1] = str(copied_skill)
        claimed_result = subprocess.run(
            [sys.executable, str(copied_script), *claim_arguments],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(claimed_result.returncode, 0, claimed_result.stderr)
        claimed = json.loads(claimed_result.stdout)
        evidence_path = self.root / "evidence-canonical-pair-verified.json"
        evidence_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "gate": "CANONICAL_PAIR_VERIFIED",
                    "status": "PASS",
                    "observed_at": "2026-09-02T18:00:00Z",
                    "checks": [
                        {
                            "name": "fixture-check",
                            "status": "PASS",
                            "detail": "Verified by the isolated test fixture.",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        copied_skill.unlink()

        advanced = subprocess.run(
            [
                sys.executable,
                str(copied_script),
                "advance",
                "--registry-root",
                str(self.registry),
                "--compatibility-output",
                str(self.compatibility),
                "--track-id",
                str(claimed["pickup"]["track_id"]),
                "--checkpoint-id",
                str(claimed["pickup"]["checkpoint_id"]),
                "--receipt-id",
                str(claimed["receipt_id"]),
                "--expected-revision",
                str(claimed["revision"]),
                "--expected-receipt-sha256",
                str(claimed["receipt_sha256"]),
                "--gate",
                "CANONICAL_PAIR_VERIFIED",
                "--evidence-file",
                str(evidence_path),
                "--gitleaks-path",
                str(self.gitleaks),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(advanced.returncode, 3, advanced.stderr)
        self.assertEqual(
            json.loads(advanced.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(compatibility["status"], "REVIEW_REQUIRED")
        self.assertEqual(compatibility["drift"], "MATERIAL")
        self.assertEqual(compatibility["reason_code"], "PACKAGE_ARTIFACT_DRIFT")
        track = json.loads(
            (self.registry / "tracks" / "alpha" / "track.json").read_text(
                encoding="utf-8"
            )
        )
        checkpoint_id = str(package["checkpoint_id"])
        self.assertIsNone(track["active_claim"])
        self.assertEqual(track["packages"][checkpoint_id]["state"], "NEEDS_REVIEW")
        self.assertTrue(
            (
                self.registry
                / "tracks"
                / "alpha"
                / "quarantines"
                / f"{checkpoint_id}.json"
            ).is_file()
        )

    def test_inspect_rejects_drift_even_when_package_is_already_quarantined(
        self,
    ) -> None:
        package = self.publish()
        self.fail_secret_scan()
        self.publish_result(expected=3)
        manifest_path = Path(str(package["package_path"])) / "package.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["current_phase"] = "forged quarantined phase"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )

    def test_manifest_drift_is_detected_and_quarantined_during_claim(self) -> None:
        package = self.publish()
        manifest_path = Path(str(package["package_path"])) / "package.json"
        original = manifest_path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["current_phase"] = "tampered"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        manifest_path.write_bytes(original)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_manifest_drift_after_claim_terminalizes_run_for_review(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        manifest_path = Path(str(package["package_path"])) / "package.json"
        original = manifest_path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["current_phase"] = "tampered after claim"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        manifest_path.write_bytes(original)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")

    def test_claim_rejects_checkpoint_metadata_inconsistent_with_manifest(
        self,
    ) -> None:
        package = self.publish()
        package_path = Path(str(package["package_path"]))
        checkpoint_path = package_path / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-03T03:04:05Z"
        checkpoint_path.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
        checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        manifest_path = package_path / "package.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["checkpoint_sha256"] = checkpoint_hash
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        checkpoint_id = str(package["checkpoint_id"])
        for view in (index["tracks"]["alpha"], track):
            entry = view["packages"][checkpoint_id]
            entry["checkpoint_sha256"] = checkpoint_hash
            entry["package_sha256"] = manifest_hash
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_inspect_rejects_rehashed_noncanonical_manifest_source_path(
        self,
    ) -> None:
        package = self.publish()
        package_path = Path(str(package["package_path"]))
        manifest_path = package_path / "package.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_checkpoint = Path(str(manifest["source_checkpoint"]))
        manifest["source_checkpoint"] = str(
            source_checkpoint.parent
            / ".."
            / source_checkpoint.parent.name
            / source_checkpoint.name
        )
        self.assertEqual(
            Path(str(manifest["source_checkpoint"])).resolve(),
            source_checkpoint,
        )
        self.assertNotEqual(manifest["source_checkpoint"], str(source_checkpoint))
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        checkpoint_id = str(package["checkpoint_id"])
        index["tracks"]["alpha"]["packages"][checkpoint_id]["package_sha256"] = (
            manifest_hash
        )
        track["packages"][checkpoint_id]["package_sha256"] = manifest_hash
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_active_claim_file_cannot_be_hidden_by_clearing_registry_views(
        self,
    ) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        index["tracks"]["alpha"]["active_claim"] = None
        track["active_claim"] = None
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_advance_rejects_disagreement_between_index_and_track_view(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        track = json.loads(track_path.read_text(encoding="utf-8"))
        track["active_claim"]["latest_revision"] = 99
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(compatibility["revision"], 1)

    def test_publish_rejects_a_hidden_active_claim_without_new_package(self) -> None:
        package = self.publish()
        self.claim(str(package["selector"]))
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        index["tracks"]["alpha"]["active_claim"] = None
        track["active_claim"] = None
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")
        self.handoff.write_text("# replacement\n", encoding="utf-8")
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["generated_at"] = "2026-09-02T19:00:00Z"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        packages_root = self.registry / "tracks" / "alpha" / "packages"
        self.assertEqual(
            len([path for path in packages_root.iterdir() if path.is_dir()]), 1
        )

    def test_complete_rejects_disagreement_between_index_and_track_view(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        track = json.loads(track_path.read_text(encoding="utf-8"))
        track["active_claim"]["latest_revision"] = 99
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.complete_ready(current, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        compatibility = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertFalse(compatibility["terminal"])

    def test_release_rejects_disagreement_between_index_and_track_view(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        track = json.loads(track_path.read_text(encoding="utf-8"))
        track["updated_at"] = "2000-01-01T00:00:00Z"
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.release(aborted, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_advance_rejects_package_state_inconsistent_with_active_claim(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        checkpoint_id = str(claimed["pickup"]["checkpoint_id"])
        index["tracks"]["alpha"]["packages"][checkpoint_id]["state"] = "AVAILABLE"
        track["packages"][checkpoint_id]["state"] = "AVAILABLE"
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_publish_reconciles_active_receipt_before_reporting_track_busy(
        self,
    ) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        index_path = self.registry / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["receipts"][str(claimed["receipt_id"])]["latest_receipt_sha256"] = (
            "0" * 64
        )
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_rejects_an_unindexed_track_directory(self) -> None:
        alpha = self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))
        index_path = self.registry / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        del index["tracks"]["alpha"]
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_rejects_an_unindexed_unclaimed_track_directory(self) -> None:
        self.publish("alpha")
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        index_path = self.registry / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        del index["tracks"]["alpha"]
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")

        rejected = self.claim(str(beta["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_rejects_an_unindexed_package_directory(self) -> None:
        package = self.publish()
        package_path = Path(str(package["package_path"]))
        orphan = package_path.parent / "cp-20260903-000000-deadbeef"
        shutil.copytree(package_path, orphan)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_claim_rejects_an_unindexed_receipt_file(self) -> None:
        package = self.publish()
        receipts_root = self.registry / "tracks" / "alpha" / "receipts"
        receipts_root.mkdir(mode=0o700)
        orphan = receipts_root / "tp-20260902T180000Z-deadbeef-r0001.json"
        orphan.write_text("{}\n", encoding="utf-8")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_idempotent_republication_quarantines_stored_artifact_drift(
        self,
    ) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("tampered stored handoff\n", encoding="utf-8")

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_exact_repeat_quarantines_drift_introduced_by_secret_scan(self) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        self.mutate_during_secret_scan(
            packaged_handoff, "tampered during repeat publication scan"
        )

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_transition_terminalizes_drift_introduced_by_secret_scan(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        self.mutate_during_secret_scan(
            packaged_handoff, "tampered during gate receipt scan"
        )

        rejected = self.advance(claimed, "CANONICAL_PAIR_VERIFIED", expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        inspected = self.inspect(str(package["selector"]))
        self.assertEqual(inspected["state"], "NEEDS_REVIEW")
        self.assertFalse(inspected["claim_active"])
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(terminal["reason_code"], "PACKAGE_ARTIFACT_DRIFT")

    def test_completion_terminalizes_drift_introduced_by_secret_scan(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        current = self.advance_to_live_state(claimed)
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        self.mutate_during_secret_scan(
            packaged_handoff, "tampered during terminal receipt scan"
        )

        rejected = self.complete_ready(current, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        packaged_handoff.write_bytes(original)
        inspected = self.inspect(str(package["selector"]))
        self.assertEqual(inspected["state"], "NEEDS_REVIEW")
        self.assertFalse(inspected["claim_active"])
        terminal = json.loads(self.compatibility.read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "REVIEW_REQUIRED")
        self.assertEqual(terminal["reason_code"], "PACKAGE_ARTIFACT_DRIFT")

    def test_exact_repeat_revalidates_registry_after_secret_scan(self) -> None:
        package = self.publish()
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        original_track = track_path.read_bytes()
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '{}\\n' > {}\nchmod 600 {}\nexit 0\n".format(
                "{}",
                shlex.quote(str(track_path)),
                shlex.quote(str(track_path)),
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        track_path.write_bytes(original_track)
        track_path.chmod(0o600)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_idempotent_republication_detects_source_change_during_rescan(
        self,
    ) -> None:
        package = self.publish()
        changed = "changed during repeat publication verification"
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '%s\\n' {} > {}\nexit 0\n".format(
                shlex.quote(changed), shlex.quote(str(self.handoff))
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "SOURCE_CHANGED_DURING_PUBLICATION",
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_idempotent_republication_rechecks_sources_after_reconciliation(
        self,
    ) -> None:
        package = self.publish()
        package_path = Path(str(package["package_path"]))
        environment = self.mutate_source_after_repeat_reconciliation_starts(
            package_path,
            "changed after repeat reconciliation began\n",
        )

        rejected = self.publish_result(expected=3, extra_env=environment)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "SOURCE_CHANGED_DURING_PUBLICATION",
        )
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_claim_fails_closed_on_registry_artifact_mode_drift(self) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        packaged_handoff.chmod(0o644)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_MODE_INVALID"
        )

    def test_claim_fails_closed_on_package_directory_mode_drift(self) -> None:
        package = self.publish()
        Path(str(package["package_path"])).chmod(0o755)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_MODE_INVALID"
        )

    def test_failed_repeat_secret_scan_quarantines_package(self) -> None:
        package = self.publish()
        self.fail_secret_scan()

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "SENSITIVE_DATA_SCAN_FAILED"
        )
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )
        checkpoint_id = str(package["checkpoint_id"])
        event_path = (
            self.registry
            / "tracks"
            / "alpha"
            / "quarantines"
            / "{}.json".format(checkpoint_id)
        )
        event = json.loads(event_path.read_text(encoding="utf-8"))
        manifest = json.loads(
            (Path(str(package["package_path"])) / "package.json").read_text(
                encoding="utf-8"
            )
        )
        index = json.loads((self.registry / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(event["event"], "PACKAGE_QUARANTINED")
        self.assertEqual(event["reason_code"], "SENSITIVE_DATA_SCAN_FAILED")
        self.assertFalse(event["phase_authorized"])
        self.assertEqual(stat.S_IMODE(event_path.stat().st_mode), 0o600)
        self.assertEqual(
            hashlib.sha256(event_path.read_bytes()).hexdigest(),
            index["tracks"]["alpha"]["packages"][checkpoint_id][
                "quarantine_event_sha256"
            ],
        )
        self.assertEqual(
            hashlib.sha256(event_path.read_bytes()).hexdigest(),
            manifest["quarantine_template_sha256"]["SENSITIVE_DATA_SCAN_FAILED"],
        )
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        denied = self.claim(str(package["selector"]), expected=3)
        self.assertEqual(
            json.loads(denied.stderr)["reason_code"], "PICKUP_NOT_AVAILABLE"
        )

    def test_immutable_quarantine_event_blocks_coordinated_view_reset(self) -> None:
        package = self.publish()
        self.fail_secret_scan()
        self.publish_result(expected=3)
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        checkpoint_id = str(package["checkpoint_id"])
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        for view in (index["tracks"]["alpha"], track):
            view["packages"][checkpoint_id]["state"] = "AVAILABLE"
            view["packages"][checkpoint_id]["quarantine_reason_code"] = None
            view["packages"][checkpoint_id]["quarantine_event_sha256"] = None
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_quarantine_event_hash_drift_fails_closed(self) -> None:
        package = self.publish()
        self.fail_secret_scan()
        self.publish_result(expected=3)
        checkpoint_id = str(package["checkpoint_id"])
        event_path = (
            self.registry
            / "tracks"
            / "alpha"
            / "quarantines"
            / "{}.json".format(checkpoint_id)
        )
        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["reason_code"] = "PACKAGE_ARTIFACT_DRIFT"
        event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_release_rejects_a_closed_claim_path_mismatch(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        closed_claim = json.loads(claim_path.read_text(encoding="utf-8"))
        closed_claim["latest_receipt_path"] = str(self.root / "unrelated.json")
        claim_path.write_text(json.dumps(closed_claim) + "\n", encoding="utf-8")

        rejected = self.release(aborted, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_release_rejects_aborted_package_with_quarantine_evidence(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        aborted = self.complete_aborted(claimed)
        self.fail_secret_scan()
        scan_failure = self.publish_result(expected=3)
        self.assertEqual(
            json.loads(scan_failure.stderr)["reason_code"],
            "SENSITIVE_DATA_SCAN_FAILED",
        )
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)

        rejected = self.release(aborted, expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RELEASE_NOT_PERMITTED"
        )
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_inspect_fails_closed_on_inconsistent_registry_views(self) -> None:
        package = self.publish()
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        track = json.loads(track_path.read_text(encoding="utf-8"))
        track["updated_at"] = "2000-01-01T00:00:00Z"
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_publication_detects_source_change_during_secret_scan(self) -> None:
        changed = "changed while package candidate was scanned"
        self.gitleaks.write_text(
            "#!/bin/sh\nprintf '%s\\n' {} > {}\nexit 0\n".format(
                shlex.quote(changed), shlex.quote(str(self.handoff))
            ),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "SOURCE_CHANGED_DURING_PUBLICATION",
        )
        self.assertFalse((self.registry / "index.json").exists())

    def test_publication_sanitizes_scanner_exec_failure(self) -> None:
        self.gitleaks.write_text(
            "#!/definitely/missing/interpreter\nexit 0\n", encoding="utf-8"
        )
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "SECRET_SCANNER_UNAVAILABLE",
        )
        self.assertNotIn("Traceback", rejected.stderr)
        self.assertFalse((self.registry / "index.json").exists())

    def test_publication_destination_races_fail_cleanly_and_are_retryable(
        self,
    ) -> None:
        checkpoint_hash = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        checkpoint_id = "cp-20260902-125509-{}".format(checkpoint_hash[:8])
        package_path = self.registry / "tracks" / "alpha" / "packages" / checkpoint_id
        live_target = self.root / "live-package-race-target"
        live_target.mkdir()
        cases = (
            (
                "dangling symlink",
                "ln -s {} {}\n".format(
                    shlex.quote(str(self.root / "missing-package-race-target")),
                    shlex.quote(str(package_path)),
                ),
            ),
            (
                "live symlink",
                "ln -s {} {}\n".format(
                    shlex.quote(str(live_target)),
                    shlex.quote(str(package_path)),
                ),
            ),
            (
                "empty directory",
                "mkdir {}\n".format(shlex.quote(str(package_path))),
            ),
        )
        for label, race_command in cases:
            with self.subTest(label=label):
                self.gitleaks.write_text(
                    "#!/bin/sh\n{}exit 0\n".format(race_command),
                    encoding="utf-8",
                )
                self.gitleaks.chmod(0o700)

                rejected = self.publish_result(expected=3)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "PACKAGE_DESTINATION_CHANGED",
                )
                self.assertFalse((self.registry / "index.json").exists())
                if package_path.is_symlink():
                    package_path.unlink()
                else:
                    package_path.rmdir()
                self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                self.gitleaks.chmod(0o700)
                self.assertEqual(self.publish()["state"], "AVAILABLE")
                shutil.rmtree(self.registry)

    def test_publication_rejects_nested_runtime_identity_key_styles(self) -> None:
        original = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        identity_fields = (
            ("process_id", "private-runtime-id"),
            ("taskId", "private-runtime-id"),
            ("session Id", "private-runtime-id"),
            ("task", {"id": "private-runtime-id"}),
            ("taskIdValue", "private-runtime-id"),
            ("pidValue", 42),
            ("ppid value", 41),
            ("valuePid", 42),
            ("value_ppid", 41),
            ("processValue", "private-runtime-id"),
            ("valueProcess", "private-runtime-id"),
            ("sessionNumber", 12),
            ("activeThread", "private-runtime-id"),
            ("windowHandle", "private-runtime-id"),
            ("sessionToken", "private-runtime-id"),
            ("sessionUuid", "private-runtime-id"),
            ("thread-guid", "private-runtime-id"),
            ("task ref", "private-runtime-id"),
            ("windowReference", "private-runtime-id"),
            ("processKey", "private-runtime-id"),
            ("credentialValue", "private-runtime-id"),
            ("privateIdentifierValue", "private-runtime-id"),
            ("apiKey", "private-credential"),
            ("authToken", "private-credential"),
            ("accessToken", "private-credential"),
            ("refreshToken", "private-credential"),
            ("bearerToken", "private-credential"),
            ("password", "private-credential"),
            ("passphrase", "private-credential"),
            ("clientSecret", "private-credential"),
            ("clientKey", "private-credential"),
            ("secretKey", "private-credential"),
            ("privateKey", "private-credential"),
        )
        for identity_key, identity_value in identity_fields:
            with self.subTest(identity_key=identity_key):
                checkpoint = dict(original)
                checkpoint["metadata"] = {"nested": [{identity_key: identity_value}]}
                self.checkpoint.write_text(
                    json.dumps(checkpoint) + "\n", encoding="utf-8"
                )

                rejected = self.publish_result(expected=2)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "PRIVATE_RUNTIME_IDENTIFIER_FIELD",
                )
                self.assertFalse(self.registry.exists())

    def test_publication_rejects_non_rfc3339_checkpoint_timestamp(self) -> None:
        original = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        for generated_at in (
            "2026-09-02 12:55:09+00:00",
            "2026-09-02T12:55:09+00:60",
        ):
            with self.subTest(generated_at=generated_at):
                checkpoint = dict(original)
                checkpoint["generated_at"] = generated_at
                self.checkpoint.write_text(
                    json.dumps(checkpoint) + "\n", encoding="utf-8"
                )

                rejected = self.publish_result(expected=2)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "CHECKPOINT_TIMESTAMP_INVALID",
                )
                self.assertFalse(self.registry.exists())

    def test_publication_accepts_rfc3339_fraction_and_leap_second(self) -> None:
        original = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        for generated_at in (
            "2026-09-02T12:55:09.1Z",
            "2026-09-02T12:55:09.12Z",
            "2016-12-31T23:59:60Z",
        ):
            with self.subTest(generated_at=generated_at):
                checkpoint = dict(original)
                checkpoint["generated_at"] = generated_at
                self.checkpoint.write_text(
                    json.dumps(checkpoint) + "\n", encoding="utf-8"
                )

                published = self.publish()

                self.assertEqual(published["generated_at"], generated_at)
                shutil.rmtree(self.registry)

    def test_publication_rejects_non_string_phase_metadata(self) -> None:
        original = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        for field, value in (
            ("current_phase", True),
            ("next_phase", ["not", "a", "string"]),
        ):
            with self.subTest(field=field):
                checkpoint = dict(original)
                checkpoint[field] = value
                self.checkpoint.write_text(
                    json.dumps(checkpoint) + "\n", encoding="utf-8"
                )

                rejected = self.publish_result(expected=2)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "CHECKPOINT_PHASE_INVALID",
                )
                self.assertFalse(self.registry.exists())

    def test_publication_rejects_unbounded_or_nonprintable_phase_metadata(
        self,
    ) -> None:
        original = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        for value in ("x" * 201, "control\nphase", " padded phase "):
            with self.subTest(value_length=len(value)):
                checkpoint = dict(original)
                checkpoint["current_phase"] = value
                self.checkpoint.write_text(
                    json.dumps(checkpoint) + "\n", encoding="utf-8"
                )

                rejected = self.publish_result(expected=2)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "CHECKPOINT_PHASE_INVALID",
                )
                self.assertFalse(self.registry.exists())

    def test_publication_rejects_boolean_checkpoint_schema_version(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["schema_version"] = True
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "CHECKPOINT_SCHEMA_UNSUPPORTED",
        )
        self.assertFalse(self.registry.exists())

    def test_publication_rejects_noncanonical_track_separator(self) -> None:
        rejected = self.publish_result(track_id="alpha--beta", expected=2)

        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "TRACK_ID_INVALID")
        self.assertFalse(self.registry.exists())

    def test_publication_rejects_track_id_longer_than_sixty_three_characters(
        self,
    ) -> None:
        rejected = self.publish_result(track_id="a" * 64, expected=2)

        self.assertEqual(json.loads(rejected.stderr)["reason_code"], "TRACK_ID_INVALID")
        self.assertFalse(self.registry.exists())

    def test_publication_rejects_nonstandard_json_constants(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.checkpoint.write_text(
                    """{
  "schema_version": 2,
  "generated_at": "2026-09-02T12:55:09-05:00",
  "context_status": "READY",
  "canonical_handoff": %s,
  "invalid": %s
}\n"""
                    % (json.dumps(str(self.handoff)), constant),
                    encoding="utf-8",
                )

                rejected = self.publish_result(expected=2)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"], "CHECKPOINT_INVALID"
                )
                self.assertFalse(self.registry.exists())

    def test_publication_rejects_duplicate_checkpoint_members(self) -> None:
        self.checkpoint.write_text(
            """{
  "schema_version": 2,
  "generated_at": "2026-09-02T12:55:09-05:00",
  "generated_at": "2026-09-02T12:55:10-05:00",
  "context_status": "READY",
  "canonical_handoff": %s
}\n"""
            % json.dumps(str(self.handoff)),
            encoding="utf-8",
        )

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "CHECKPOINT_INVALID"
        )
        self.assertFalse(self.registry.exists())

    def test_advance_rejects_duplicate_evidence_members_without_mutation(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        evidence = self.root / "duplicate-evidence.json"
        evidence.write_text(
            """{
  "schema_version": 1,
  "gate": "CANONICAL_PAIR_VERIFIED",
  "status": "PASS",
  "status": "PASS",
  "observed_at": "2026-09-02T18:00:00Z",
  "checks": [{"name": "fixture", "status": "PASS"}]
}\n""",
            encoding="utf-8",
        )
        before = {
            path: path.read_bytes()
            for path in self.registry.rglob("*")
            if path.is_file()
        }

        rejected = self.run_cli(
            "advance",
            "--registry-root",
            str(self.registry),
            "--compatibility-output",
            str(self.compatibility),
            "--track-id",
            str(claimed["pickup"]["track_id"]),
            "--checkpoint-id",
            str(claimed["pickup"]["checkpoint_id"]),
            "--receipt-id",
            str(claimed["receipt_id"]),
            "--expected-revision",
            str(claimed["revision"]),
            "--expected-receipt-sha256",
            str(claimed["receipt_sha256"]),
            "--gate",
            "CANONICAL_PAIR_VERIFIED",
            "--evidence-file",
            str(evidence),
            "--gitleaks-path",
            str(self.gitleaks),
            expected=2,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "TRANSITION_EVIDENCE_INVALID"
        )
        self.assertEqual(
            before,
            {
                path: path.read_bytes()
                for path in self.registry.rglob("*")
                if path.is_file()
            },
        )

    def test_claim_rejects_unbounded_or_nonprintable_invocation_metadata(self) -> None:
        package = self.publish()
        selector = str(package["selector"])
        cases = (
            ("--model", ""),
            ("--model", " "),
            ("--model", "x" * 81),
            ("--effort", "\n"),
            ("--effort", "x" * 41),
        )
        for flag, value in cases:
            with self.subTest(flag=flag, value=repr(value)):
                arguments = self.claim_arguments(selector)
                arguments[arguments.index(flag) + 1] = value

                rejected = self.run_cli(*arguments, expected=2)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "INVOCATION_METADATA_INVALID",
                )
                self.assertEqual(self.inspect(selector)["state"], "AVAILABLE")

    def test_complete_rejects_removed_options_without_mutation(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        rejected = self.run_cli(
            "complete", "--registry-root", str(self.registry),
            "--track-id", str(claimed["pickup"]["track_id"]),
            "--checkpoint-id", str(claimed["pickup"]["checkpoint_id"]),
            "--receipt-id", str(claimed["receipt_id"]),
            "--expected-revision", str(claimed["revision"]),
            "--expected-receipt-sha256", str(claimed["receipt_sha256"]),
            "--status", "ABORTED", "--drift", "UNKNOWN",
            "--reason-code", "USER_ABORT", "--reason", "The user abandoned this opening.",
            "--governance-status=PASS", expected=2,
        )
        self.assertIn("unrecognized arguments", rejected.stderr)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "CLAIMED")

    def test_claim_preserves_foreign_scan_directory_replacement(self) -> None:
        package = self.publish()
        scan_temp = self.root / "scan-temp"
        scan_temp.mkdir(mode=0o700)
        recorded_path = self.root / "scan-path"
        scanner = """#!/bin/sh
source_path=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--source" ]; then
    source_path=$2
    break
  fi
  shift
done
printf '%s' "$source_path" > RECORD_PATH
mv "$source_path" "$source_path-owned"
mkdir "$source_path"
printf '%s\n' 'foreign scan marker' > "$source_path/foreign.txt"
exit 0
"""
        self.gitleaks.write_text(
            scanner.replace("RECORD_PATH", shlex.quote(str(recorded_path))),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)

        rejected = self.run_cli(
            *self.claim_arguments(str(package["selector"])),
            expected=3,
            extra_env={"TMPDIR": str(scan_temp)},
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        replaced_scan = Path(recorded_path.read_text(encoding="utf-8"))
        self.assertEqual(
            (replaced_scan / "foreign.txt").read_text(encoding="utf-8"),
            "foreign scan marker\n",
        )
        self.assertTrue(replaced_scan.with_name(replaced_scan.name + "-owned").exists())
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_claim_removes_owned_scan_directory_after_open_fault(self) -> None:
        package = self.publish()
        scan_temp = self.root / "scan-open-fault-temp"
        scan_temp.mkdir()
        marker = self.root / "scan-directory-open-fault-fired"
        environment = self.directory_open_fault_environment(
            parent=scan_temp,
            name_prefix="pickup-json-scan-",
            marker_name=marker.name,
        )
        environment["TMPDIR"] = str(scan_temp)

        rejected = self.run_cli(
            *self.claim_arguments(str(package["selector"])),
            expected=3,
            extra_env=environment,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "TRANSACTION_ROLLBACK_FAILED",
        )
        self.assertTrue(marker.is_file())
        self.assertEqual(list(scan_temp.iterdir()), [])
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        self.assertEqual(
            json.loads(self.claim(str(package["selector"])).stdout)["pickup"][
                "selector"
            ],
            package["selector"],
        )

    def test_publish_removes_new_quarantine_directory_after_open_fault(self) -> None:
        package = self.publish()
        track_root = self.registry / "tracks" / "alpha"
        marker = self.root / "quarantine-directory-open-fault-fired"
        self.fail_secret_scan()

        rejected = self.publish_result(
            expected=2,
            extra_env=self.directory_open_fault_environment(
                parent=track_root,
                name_prefix="quarantines",
                marker_name=marker.name,
            ),
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "REGISTRY_ROOT_UNAVAILABLE",
        )
        self.assertTrue(marker.is_file())
        self.assertFalse((track_root / "quarantines").exists())
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        self.assertEqual(self.publish()["state"], "AVAILABLE")

    def test_publish_retries_after_packages_directory_creation_fault(self) -> None:
        adapter = self.root / "packages-mkdir-fault-adapter"
        adapter.mkdir()
        (adapter / "sitecustomize.py").write_text(
            """import os
from pathlib import Path

_real_mkdir = os.mkdir
_target = Path(os.environ["PICKUP_FAULT_PACKAGES_ROOT"])
_marker = Path(os.environ["PICKUP_FAULT_MARKER"])
_triggered = False


def _faulting_mkdir(path, *args, **kwargs):
    global _triggered
    observed = Path(path)
    matches = observed == _target
    descriptor = kwargs.get("dir_fd")
    if (
        not observed.is_absolute()
        and descriptor is not None
        and _target.parent.exists()
    ):
        parent = os.fstat(descriptor)
        expected_parent = _target.parent.stat()
        matches = (
            observed.name == _target.name
            and (parent.st_dev, parent.st_ino)
            == (expected_parent.st_dev, expected_parent.st_ino)
        )
    if not _triggered and matches:
        _triggered = True
        _marker.write_text("fault fired\\n", encoding="utf-8")
        raise OSError("injected packages directory creation failure")
    return _real_mkdir(path, *args, **kwargs)


os.mkdir = _faulting_mkdir
""",
            encoding="utf-8",
        )
        marker = self.root / "packages-mkdir-fault-fired"

        rejected = self.run_cli(
            "publish",
            "--registry-root",
            str(self.registry),
            "--track-id",
            "alpha",
            "--resource-scope",
            str(self.resource),
            "--handoff",
            str(self.handoff),
            "--checkpoint",
            str(self.checkpoint),
            "--gitleaks-path",
            str(self.gitleaks),
            expected=2,
            extra_env={
                "PYTHONPATH": str(adapter),
                "PICKUP_FAULT_PACKAGES_ROOT": str(
                    self.registry / "tracks" / "alpha" / "packages"
                ),
                "PICKUP_FAULT_MARKER": str(marker),
            },
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "REGISTRY_ROOT_UNAVAILABLE"
        )
        self.assertTrue(marker.exists())
        self.assertFalse((self.registry / "tracks").exists())
        self.assertEqual(self.publish()["state"], "AVAILABLE")

    def test_missing_or_replaced_sealed_artifacts_quarantine_coordinate(self) -> None:
        cases = ("package-directory", "missing-file", "symlink-file", "directory-file")
        for case_name in cases:
            with self.subTest(case_name=case_name):
                package = self.publish()
                package_path = Path(str(package["package_path"]))
                backup = self.root / ("artifact-backup-" + case_name)
                if case_name == "package-directory":
                    package_path.rename(backup)
                else:
                    target_name = {
                        "missing-file": "handoff.md",
                        "symlink-file": "checkpoint.json",
                        "directory-file": "package.json",
                    }[case_name]
                    target = package_path / target_name
                    target.rename(backup)
                    if case_name == "symlink-file":
                        target.symlink_to(backup)
                    elif case_name == "directory-file":
                        target.mkdir(mode=0o700)

                rejected = self.claim(str(package["selector"]), expected=3)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "PACKAGE_ARTIFACT_DRIFT",
                )
                if case_name == "package-directory":
                    backup.rename(package_path)
                else:
                    target = package_path / target_name
                    if target.is_symlink():
                        target.unlink()
                    elif target.is_dir():
                        target.rmdir()
                    backup.rename(target)
                self.assertEqual(
                    self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
                )
                shutil.rmtree(self.registry)
                if self.compatibility.exists() or self.compatibility.is_symlink():
                    self.compatibility.unlink()

    def test_claim_closes_selected_and_unselected_preexisting_drift(self) -> None:
        alpha = self.publish()
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        alpha_handoff = Path(str(alpha["package_path"])) / "handoff.md"
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        alpha_original = alpha_handoff.read_bytes()
        beta_original = beta_handoff.read_bytes()
        alpha_handoff.write_text("alpha drift\n", encoding="utf-8")
        beta_handoff.write_text("beta drift\n", encoding="utf-8")

        rejected = self.claim(str(alpha["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        alpha_handoff.write_bytes(alpha_original)
        beta_handoff.write_bytes(beta_original)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "NEEDS_REVIEW")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "NEEDS_REVIEW")

    def test_claim_scan_closes_only_other_track_drift(self) -> None:
        alpha = self.publish()
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        beta_original = beta_handoff.read_bytes()
        self.mutate_during_secret_scan(beta_handoff, "beta scanner drift")

        rejected = self.claim(str(alpha["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        beta_handoff.write_bytes(beta_original)
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "AVAILABLE")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "NEEDS_REVIEW")

    def test_unclaimed_drift_scan_adds_other_track_to_same_closure(self) -> None:
        alpha = self.publish()
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        alpha_handoff = Path(str(alpha["package_path"])) / "handoff.md"
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        alpha_original = alpha_handoff.read_bytes()
        beta_original = beta_handoff.read_bytes()
        alpha_handoff.write_text("alpha preexisting drift\n", encoding="utf-8")
        self.mutate_during_secret_scan(beta_handoff, "beta scanner drift")

        rejected = self.claim(str(alpha["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        alpha_handoff.write_bytes(alpha_original)
        beta_handoff.write_bytes(beta_original)
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        self.assertEqual(self.inspect(str(alpha["selector"]))["state"], "NEEDS_REVIEW")
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "NEEDS_REVIEW")

    def test_exact_repeat_scanner_unavailable_quarantines_package(self) -> None:
        package = self.publish()
        self.gitleaks.write_text(
            "#!/definitely/missing/interpreter\nexit 0\n", encoding="utf-8"
        )
        self.gitleaks.chmod(0o700)

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "SECRET_SCANNER_UNAVAILABLE"
        )
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        self.assertEqual(
            self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
        )

    def test_candidate_scan_closes_drift_on_existing_track_only(self) -> None:
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        beta_handoff = Path(str(beta["package_path"])) / "handoff.md"
        beta_original = beta_handoff.read_bytes()
        self.mutate_during_secret_scan(beta_handoff, "beta scanner drift")

        rejected = self.publish_result(expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "PACKAGE_ARTIFACT_DRIFT"
        )
        index = json.loads((self.registry / "index.json").read_text(encoding="utf-8"))
        self.assertNotIn("alpha", index["tracks"])
        beta_handoff.write_bytes(beta_original)
        self.gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.gitleaks.chmod(0o700)
        self.assertEqual(self.inspect(str(beta["selector"]))["state"], "NEEDS_REVIEW")

    def test_unclaimed_drift_compatibility_race_has_no_registry_mutation(self) -> None:
        package = self.publish()
        packaged_handoff = Path(str(package["package_path"])) / "handoff.md"
        original = packaged_handoff.read_bytes()
        packaged_handoff.write_text("drift before compatibility race\n")
        self.gitleaks.write_text(
            """#!/bin/sh
ln -s definitely-missing %s
exit 0
"""
            % shlex.quote(str(self.compatibility)),
            encoding="utf-8",
        )
        self.gitleaks.chmod(0o700)
        before = {
            path: path.read_bytes()
            for path in self.registry.rglob("*")
            if path.is_file()
        }

        rejected = self.claim(str(package["selector"]), expected=3)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "COMPATIBILITY_OUTPUT_INVALID"
        )
        self.assertEqual(
            before,
            {
                path: path.read_bytes()
                for path in self.registry.rglob("*")
                if path.is_file()
            },
        )
        self.compatibility.unlink()
        packaged_handoff.write_bytes(original)
        self.assertEqual(self.inspect(str(package["selector"]))["state"], "AVAILABLE")

    def test_manifest_drift_receipt_uses_only_sealed_index_hashes(self) -> None:
        for malformed in (False, True):
            with self.subTest(malformed=malformed):
                package = self.publish()
                manifest_path = Path(str(package["package_path"])) / "package.json"
                original = manifest_path.read_bytes()
                if malformed:
                    manifest_path.write_text("{not-json\n", encoding="utf-8")
                else:
                    manifest = json.loads(original)
                    manifest["handoff_sha256"] = "0" * 64
                    manifest_path.write_text(
                        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
                    )

                rejected = self.claim(str(package["selector"]), expected=3)

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "PACKAGE_ARTIFACT_DRIFT",
                )
                manifest_path.write_bytes(original)
                self.assertEqual(
                    self.inspect(str(package["selector"]))["state"], "NEEDS_REVIEW"
                )
                shutil.rmtree(self.registry)
                if self.compatibility.exists() or self.compatibility.is_symlink():
                    self.compatibility.unlink()

    def test_active_receipt_path_must_use_literal_canonical_storage_path(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        receipt_path = Path(str(claimed["receipt_path"]))
        alias = str(receipt_path.parent / ".." / "receipts" / receipt_path.name)
        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "alpha" / "track.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt_id = str(claimed["receipt_id"])
        index["receipts"][receipt_id]["latest_receipt_path"] = alias
        index["tracks"]["alpha"]["active_claim"]["latest_receipt_path"] = alias
        track["active_claim"]["latest_receipt_path"] = alias
        claim["latest_receipt_path"] = alias
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_closed_receipt_path_alias_is_not_releasable_or_inspectable(self) -> None:
        package = self.publish()
        claimed = json.loads(self.claim(str(package["selector"])).stdout)
        terminal = json.loads(self.complete_aborted_result(claimed).stdout)
        receipt_path = Path(str(terminal["receipt_path"]))
        alias = str(receipt_path.parent / ".." / "receipts" / receipt_path.name)
        index_path = self.registry / "index.json"
        claim_path = self.registry / "tracks" / "alpha" / "claim.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        index["receipts"][str(terminal["receipt_id"])]["latest_receipt_path"] = alias
        claim["latest_receipt_path"] = alias
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")

        inspected = self.run_cli(
            "inspect",
            "--registry-root",
            str(self.registry),
            "--selector",
            str(package["selector"]),
            expected=3,
        )
        released = self.release(terminal, expected=3)

        self.assertEqual(
            json.loads(inspected.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        self.assertEqual(
            json.loads(released.stderr)["reason_code"],
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )

    def test_receipt_workspace_and_skill_paths_require_canonical_strings(self) -> None:
        for field in ("workspace", "skill"):
            with self.subTest(field=field):
                package = self.publish()
                claimed = json.loads(self.claim(str(package["selector"])).stdout)
                if field == "workspace":
                    alias = str(self.workspace / ".." / self.workspace.name)

                    def mutate(receipt: dict[str, object]) -> None:
                        receipt["workspace"] = alias

                else:
                    skill_alias = self.root / "skill-alias.md"
                    skill_alias.symlink_to(SCRIPT.parents[1] / "SKILL.md")

                    def mutate(receipt: dict[str, object]) -> None:
                        receipt["artifacts"]["skill"]["path"] = str(skill_alias)

                self.rewrite_latest_receipt(claimed, mutate)

                rejected = self.run_cli(
                    "inspect",
                    "--registry-root",
                    str(self.registry),
                    "--selector",
                    str(package["selector"]),
                    expected=3,
                )

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "ORPHANED_CLAIM_REVIEW_REQUIRED",
                )
                shutil.rmtree(self.registry)
                if self.compatibility.exists() or self.compatibility.is_symlink():
                    self.compatibility.unlink()

    def test_persisted_invocation_values_are_typed(self) -> None:
        cases = (
            ("model", ""),
            ("reasoning_effort", "x" * 41),
        )
        for field, value in cases:
            with self.subTest(field=field):
                package = self.publish()
                claimed = json.loads(self.claim(str(package["selector"])).stdout)

                def mutate(receipt: dict[str, object]) -> None:
                    receipt["invocation"][field] = value

                self.rewrite_latest_receipt(claimed, mutate)

                rejected = self.run_cli(
                    "inspect",
                    "--registry-root",
                    str(self.registry),
                    "--selector",
                    str(package["selector"]),
                    expected=3,
                )

                self.assertEqual(
                    json.loads(rejected.stderr)["reason_code"],
                    "ORPHANED_CLAIM_REVIEW_REQUIRED",
                )
                shutil.rmtree(self.registry)
                if self.compatibility.exists() or self.compatibility.is_symlink():
                    self.compatibility.unlink()

    def test_reconciliation_rejects_coordinated_overlapping_active_scopes(self) -> None:
        alpha = self.publish()
        beta_resource = self.workspace / "projects" / "beta"
        beta_resource.mkdir()
        beta = self.publish("beta", beta_resource)
        self.claim(str(alpha["selector"]))
        beta_claim = json.loads(self.claim(str(beta["selector"])).stdout)
        beta_package_path = Path(str(beta["package_path"]))
        manifest_path = beta_package_path / "package.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["resource_scopes"] = [str(self.resource.resolve())]
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        index_path = self.registry / "index.json"
        track_path = self.registry / "tracks" / "beta" / "track.json"
        claim_path = self.registry / "tracks" / "beta" / "claim.json"
        receipt_path = Path(str(beta_claim["receipt_path"]))
        index = json.loads(index_path.read_text(encoding="utf-8"))
        track = json.loads(track_path.read_text(encoding="utf-8"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for view in (track, index["tracks"]["beta"]):
            view["resource_scopes"] = [str(self.resource.resolve())]
            view["packages"][str(beta["checkpoint_id"])]["package_sha256"] = (
                manifest_hash
            )
        receipt["artifacts"]["package"]["sha256"] = manifest_hash
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        receipt_id = str(beta_claim["receipt_id"])
        claim["latest_receipt_sha256"] = receipt_hash
        track["active_claim"]["latest_receipt_sha256"] = receipt_hash
        index["tracks"]["beta"]["active_claim"]["latest_receipt_sha256"] = receipt_hash
        index["receipts"][receipt_id]["latest_receipt_sha256"] = receipt_hash
        track_path.write_text(json.dumps(track) + "\n", encoding="utf-8")
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
        index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")

        rejected = self.run_cli(
            "inspect", "--registry-root", str(self.registry), expected=3
        )

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "RESOURCE_SCOPE_CONFLICT"
        )

    def test_canonical_handoff_with_nul_is_sanitized(self) -> None:
        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        checkpoint["canonical_handoff"] = "bad\u0000path"
        self.checkpoint.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        rejected = self.publish_result(expected=2)

        self.assertEqual(
            json.loads(rejected.stderr)["reason_code"], "CANONICAL_PAIR_MISMATCH"
        )
        self.assertNotIn("Traceback", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
