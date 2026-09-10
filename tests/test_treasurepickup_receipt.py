from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Optional
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "treasurepickup_receipt.py"


class ReceiptCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "pickup_audit"
        self.workspace.mkdir()
        self.state_dir = self.workspace / "treasurepickup"
        self.state_dir.mkdir(parents=True)
        self.handoff = self.workspace / "trashpickup" / "current-context.md"
        self.handoff.parent.mkdir()
        self.handoff.write_text("# Current Context\n\n## Next Phase\nTest phase\n", encoding="utf-8")
        self.checkpoint = self.state_dir / "context-checkpoint.json"
        self.checkpoint.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "generated_at": "2026-09-01T19:00:00-05:00",
                    "context_status": "READY",
                    "canonical_handoff": str(self.handoff),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.skill_file = self.root / "SKILL.md"
        self.skill_file.write_text("---\nname: treasurepickup\n---\n", encoding="utf-8")
        self.output = self.state_dir / "context-resume.json"
        self.fake_gitleaks = self.root / "gitleaks"
        self.fake_gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.fake_gitleaks.chmod(0o700)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return completed

    def start(self, *, output: Optional[Path] = None, fresh_task: str = "YES") -> dict:
        target = output or self.output
        basis = {
            "YES": "FIRST_SUBSTANTIVE_USER_TURN",
            "NO": "PRIOR_TASK_CONTENT",
            "UNKNOWN": "UNVERIFIED",
        }[fresh_task]
        self.run_cli(
            "start",
            "--output",
            str(target),
            "--workspace",
            str(self.workspace),
            "--expected-workspace",
            str(self.workspace),
            "--handoff",
            str(self.handoff),
            "--checkpoint",
            str(self.checkpoint),
            "--skill-file",
            str(self.skill_file),
            "--fresh-task",
            fresh_task,
            "--freshness-basis",
            basis,
            "--invocation-mode",
            "MANUAL_SKILL_SELECTOR",
            "--model",
            "gpt-5.6-sol",
            "--effort",
            "max",
        )
        return json.loads(target.read_text(encoding="utf-8"))

    def advance_all(self, receipt_id: str) -> None:
        for gate in (
            "CANONICAL_PAIR_VERIFIED",
            "LIVE_STATE_VERIFIED",
        ):
            self.run_cli(
                "advance",
                "--output",
                str(self.output),
                "--receipt-id",
                receipt_id,
                "--gate",
                gate,
            )

    def complete_ready(self, receipt_id: str, *, expected: int = 0) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "complete",
            "--output",
            str(self.output),
            "--receipt-id",
            receipt_id,
            "--status",
            "READY",
            "--drift",
            "NONE",
            "--checkpoint-generated-at",
            "2026-09-01T19:00:00-05:00",
            "--current-phase",
            "Context refresh complete",
            "--next-phase",
            "Execution-authorization review",
            "--gitleaks-path",
            str(self.fake_gitleaks),
            expected=expected,
        )

    def test_start_replaces_legacy_ready_with_verifying_receipt(self) -> None:
        self.output.write_text(
            json.dumps({"schema_version": 2, "status": "READY", "drift": "NONE"}) + "\n",
            encoding="utf-8",
        )
        self.output.chmod(0o644)

        receipt = self.start()

        self.assertEqual(receipt["schema_version"], 3)
        self.assertEqual(receipt["status"], "VERIFYING")
        self.assertFalse(receipt["terminal"])
        self.assertEqual(receipt["last_completed_gate"], "INVOCATION_RECORDED")
        self.assertEqual(receipt["invocation"]["fresh_task"], "YES")
        self.assertEqual(receipt["invocation"]["model"], "gpt-5.6-sol")
        self.assertFalse(receipt["scope"]["phase_authorized"])
        self.assertTrue(receipt["receipt_id"].startswith("tp-"))
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(len(receipt["artifacts"]["handoff"]["sha256"]), 64)
        self.assertEqual(receipt["artifacts"]["checkpoint"]["schema_version"], 2)

    def test_nonfresh_and_unknown_tasks_fail_closed(self) -> None:
        nonfresh = self.start(fresh_task="NO")
        self.assertEqual(nonfresh["status"], "REVIEW_REQUIRED")
        self.assertEqual(nonfresh["drift"], "MATERIAL")
        self.assertEqual(nonfresh["reason_code"], "NOT_FRESH_TASK")
        self.assertTrue(nonfresh["terminal"])

        second_output = self.state_dir / "unknown-resume.json"
        unknown = self.start(output=second_output, fresh_task="UNKNOWN")
        self.assertEqual(unknown["status"], "REVIEW_REQUIRED")
        self.assertEqual(unknown["drift"], "UNKNOWN")
        self.assertEqual(unknown["reason_code"], "TASK_FRESHNESS_UNKNOWN")
        self.assertTrue(unknown["terminal"])

    def test_wrong_workspace_refuses_without_writing(self) -> None:
        wrong = self.root / "wrong-workspace"
        wrong.mkdir()
        completed = self.run_cli(
            "start",
            "--output",
            str(self.output),
            "--workspace",
            str(wrong),
            "--expected-workspace",
            str(self.workspace),
            "--handoff",
            str(self.handoff),
            "--checkpoint",
            str(self.checkpoint),
            "--skill-file",
            str(self.skill_file),
            "--fresh-task",
            "YES",
            "--freshness-basis",
            "FIRST_SUBSTANTIVE_USER_TURN",
            expected=2,
        )
        self.assertIn("WORKSPACE_MISMATCH", completed.stderr)
        self.assertFalse(self.output.exists())

    def test_receipt_id_prevents_cross_run_advance(self) -> None:
        first_output = self.state_dir / "first.json"
        second_output = self.state_dir / "second.json"
        first = self.start(output=first_output)
        second = self.start(output=second_output)
        self.assertNotEqual(first["receipt_id"], second["receipt_id"])

        before = first_output.read_bytes()
        self.run_cli(
            "advance",
            "--output",
            str(first_output),
            "--receipt-id",
            second["receipt_id"],
            "--gate",
            "CANONICAL_PAIR_VERIFIED",
            expected=2,
        )
        self.assertEqual(first_output.read_bytes(), before)

    def test_active_receipt_cannot_be_silently_overwritten(self) -> None:
        first = self.start()
        before = self.output.read_bytes()
        completed = self.run_cli(
            "start",
            "--output",
            str(self.output),
            "--workspace",
            str(self.workspace),
            "--expected-workspace",
            str(self.workspace),
            "--handoff",
            str(self.handoff),
            "--checkpoint",
            str(self.checkpoint),
            "--skill-file",
            str(self.skill_file),
            "--fresh-task",
            "YES",
            "--freshness-basis",
            "FIRST_SUBSTANTIVE_USER_TURN",
            expected=3,
        )
        self.assertIn(first["receipt_id"], completed.stderr)
        self.assertEqual(self.output.read_bytes(), before)

    def test_gates_must_advance_in_order(self) -> None:
        receipt = self.start()
        self.run_cli(
            "advance",
            "--output",
            str(self.output),
            "--receipt-id",
            receipt["receipt_id"],
            "--gate",
            "LIVE_STATE_VERIFIED",
            expected=2,
        )
        current = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(current["last_completed_gate"], "INVOCATION_RECORDED")

        before = self.output.read_bytes()
        self.complete_ready(receipt["receipt_id"], expected=2)
        self.assertEqual(self.output.read_bytes(), before)

    def test_ready_completion_is_terminal_and_summarized(self) -> None:
        receipt = self.start()
        self.advance_all(receipt["receipt_id"])
        self.complete_ready(receipt["receipt_id"])
        completed = json.loads(self.output.read_text(encoding="utf-8"))

        self.assertEqual(completed["status"], "READY")
        self.assertEqual(completed["drift"], "NONE")
        self.assertTrue(completed["terminal"])
        self.assertIsNotNone(completed["completed_at"])
        self.assertEqual(completed["last_completed_gate"], "TELEMETRY_VALIDATED")
        self.assertNotIn("governance_verification", completed)
        self.assertEqual(completed["validation"]["secret_scan"], "PASS")
        self.assertFalse(completed["scope"]["phase_authorized"])

        summary = self.run_cli("summary", "--output", str(self.output)).stdout.strip()
        self.assertIn("TP READY", summary)
        self.assertIn("fresh-task=YES", summary)
        self.assertNotIn("governance=", summary)
        self.assertIn("phase-authority=NO", summary)
        self.assertNotIn("\n", summary)

    def test_ready_completion_converts_artifact_drift_to_review_required(self) -> None:
        receipt = self.start()
        self.advance_all(receipt["receipt_id"])
        self.handoff.write_text("changed after receipt start\n", encoding="utf-8")

        self.complete_ready(receipt["receipt_id"], expected=3)
        completed = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(completed["status"], "REVIEW_REQUIRED")
        self.assertEqual(completed["drift"], "MATERIAL")
        self.assertEqual(completed["reason_code"], "ARTIFACT_CONTINUITY_CHANGED")
        self.assertTrue(completed["terminal"])

    def test_terminal_status_and_drift_contract_is_enforced(self) -> None:
        receipt = self.start()
        before = self.output.read_bytes()
        self.run_cli(
            "complete",
            "--output",
            str(self.output),
            "--receipt-id",
            receipt["receipt_id"],
            "--status",
            "STOP",
            "--drift",
            "NONE",
            expected=2,
        )
        self.assertEqual(self.output.read_bytes(), before)

    def test_secret_scan_failure_writes_only_sanitized_stop(self) -> None:
        failing_gitleaks = self.root / "failing-gitleaks"
        failing_gitleaks.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        failing_gitleaks.chmod(0o700)
        receipt = self.start()
        self.advance_all(receipt["receipt_id"])
        self.run_cli(
            "complete",
            "--output",
            str(self.output),
            "--receipt-id",
            receipt["receipt_id"],
            "--status",
            "READY",
            "--drift",
            "NONE",
            "--current-phase",
            "must-not-be-persisted-after-scan-failure",
            "--next-phase",
            "also-must-not-be-persisted",
            "--gitleaks-path",
            str(failing_gitleaks),
            expected=3,
        )
        stopped = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(stopped["status"], "STOP")
        self.assertEqual(stopped["drift"], "SECURITY")
        self.assertEqual(stopped["reason_code"], "SENSITIVE_DATA_SCAN_FAILED")
        self.assertIsNone(stopped["current_phase"])
        self.assertIsNone(stopped["next_phase"])
        self.assertNotIn("governance_verification", stopped)
        self.assertEqual(stopped["invocation"]["model"], "UNKNOWN")
        self.assertEqual(stopped["invocation"]["reasoning_effort"], "UNKNOWN")
        self.assertNotIn("must-not-be-persisted", self.output.read_text(encoding="utf-8"))

    def test_symlink_receipt_target_is_rejected(self) -> None:
        target = self.state_dir / "real.json"
        target.write_text("{}\n", encoding="utf-8")
        self.output.symlink_to(target)
        self.run_cli("summary", "--output", str(self.output), expected=2)
        self.assertEqual(target.read_text(encoding="utf-8"), "{}\n")

    def test_atomic_write_leaves_no_temporary_receipt(self) -> None:
        self.start()
        leftovers = list(self.state_dir.glob(".context-resume.json-*.tmp"))
        self.assertEqual(leftovers, [])

    def test_summary_marks_schema_two_as_legacy_and_unknown_freshness(self) -> None:
        self.output.write_text(
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
        summary = self.run_cli("summary", "--output", str(self.output)).stdout.strip()
        self.assertIn("TP LEGACY_V2", summary)
        self.assertIn("fresh-task=UNKNOWN", summary)
        self.assertIn("phase-authority=NO", summary)

    def test_receipt_contains_no_private_runtime_identifier_fields(self) -> None:
        receipt = self.start()

        def all_keys(value: object) -> set[str]:
            if isinstance(value, dict):
                result = set(value)
                for child in value.values():
                    result.update(all_keys(child))
                return result
            if isinstance(value, list):
                result: set[str] = set()
                for child in value:
                    result.update(all_keys(child))
                return result
            return set()

        keys = all_keys(receipt)
        self.assertTrue({"session_id", "thread_id", "window_title"}.isdisjoint(keys))


if __name__ == "__main__":
    unittest.main()
