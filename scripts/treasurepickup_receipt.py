#!/usr/bin/env python3
"""Deterministic flight receipts for the manual-only Treasure Pickup skill."""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_VERSION = 3
VERIFYING = "VERIFYING"
TERMINAL_STATES = {"READY", "BLOCKED", "REVIEW_REQUIRED", "STOP", "ABORTED"}
STATUSES = TERMINAL_STATES | {VERIFYING}
DRIFTS = {"EXPECTED", "BENIGN", "MATERIAL", "SECURITY", "UNKNOWN", "NONE"}
READY_DRIFTS = {"EXPECTED", "BENIGN", "NONE"}
FRESH_TASK_VALUES = {"YES", "NO", "UNKNOWN"}
FRESHNESS_BASES = {
    "FIRST_SUBSTANTIVE_USER_TURN",
    "PRIOR_TASK_CONTENT",
    "UNVERIFIED",
}
INVOCATION_MODES = {"MANUAL_SKILL_SELECTOR", "SLASH_COMMAND"}
GATES = (
    "INVOCATION_RECORDED",
    "CANONICAL_PAIR_VERIFIED",
    "LIVE_STATE_VERIFIED",
    "TELEMETRY_VALIDATED",
)
FORBIDDEN_KEYS = {"session_id", "thread_id", "window_title"}
RECEIPT_ID_RE = re.compile(r"^tp-\d{8}T\d{6}Z-[0-9a-f]{8}$")
DEFAULT_SKILL_FILE = Path(__file__).resolve().parents[1] / "SKILL.md"


class ReceiptError(Exception):
    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_receipt_id(timestamp: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "")
    compact = compact.replace("+0000", "Z")
    if compact.endswith("Z"):
        compact = compact[:-1] + "Z"
    return "tp-{}-{}".format(compact, secrets.token_hex(4))


def clean_text(
    value: Optional[str],
    field: str,
    *,
    max_length: int = 200,
    allow_none: bool = True,
) -> Optional[str]:
    if value is None:
        if allow_none:
            return None
        raise ReceiptError("{}_MISSING".format(field.upper()))
    cleaned = value.strip()
    if not cleaned:
        if allow_none:
            return None
        raise ReceiptError("{}_MISSING".format(field.upper()))
    if len(cleaned) > max_length:
        raise ReceiptError("{}_TOO_LONG".format(field.upper()))
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        raise ReceiptError("{}_CONTROL_CHARACTER".format(field.upper()))
    return cleaned


def validate_timestamp(value: Any, field: str, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str):
        raise ReceiptError("{}_INVALID".format(field.upper()))
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReceiptError("{}_INVALID".format(field.upper())) from exc
    if parsed.tzinfo is None:
        raise ReceiptError("{}_TIMEZONE_MISSING".format(field.upper()))


def resolved_existing_directory(path_text: str, field: str) -> Path:
    path = Path(path_text)
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ReceiptError("{}_UNAVAILABLE".format(field.upper())) from exc
    if not resolved.is_dir():
        raise ReceiptError("{}_NOT_DIRECTORY".format(field.upper()))
    return resolved


def resolved_output_path(path_text: str) -> Path:
    path = Path(path_text)
    try:
        parent = path.parent.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ReceiptError("OUTPUT_PARENT_UNAVAILABLE") from exc
    return parent / path.name


def ensure_within(path: Path, parent: Path) -> None:
    try:
        common = Path(os.path.commonpath([str(path), str(parent)]))
    except ValueError as exc:
        raise ReceiptError("OUTPUT_OUTSIDE_EXPECTED_WORKSPACE") from exc
    if common != parent:
        raise ReceiptError("OUTPUT_OUTSIDE_EXPECTED_WORKSPACE")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_file_state(path: Path) -> Tuple[bool, bool]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False, False
    return True, stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def artifact_record(path_text: str, *, checkpoint: bool = False) -> Dict[str, Any]:
    path = Path(path_text)
    present, regular = regular_file_state(path)
    record: Dict[str, Any] = {
        "path": str(path.absolute()),
        "present": present,
        "regular_file": regular,
        "sha256": file_sha256(path) if present and regular else None,
    }
    if checkpoint:
        record.update(
            {
                "schema_version": None,
                "context_status": None,
                "generated_at": None,
            }
        )
        if present and regular:
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                schema_version = parsed.get("schema_version")
                context_status = parsed.get("context_status")
                generated_at = parsed.get("generated_at")
                record["schema_version"] = schema_version if isinstance(schema_version, int) else None
                record["context_status"] = context_status if isinstance(context_status, str) else None
                record["generated_at"] = generated_at if isinstance(generated_at, str) else None
    return record


def read_json_object(path: Path) -> Dict[str, Any]:
    present, regular = regular_file_state(path)
    if not present:
        raise ReceiptError("RECEIPT_NOT_FOUND")
    if not regular:
        raise ReceiptError("RECEIPT_NOT_REGULAR_FILE")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("RECEIPT_INVALID_JSON") from exc
    if not isinstance(parsed, dict):
        raise ReceiptError("RECEIPT_NOT_OBJECT")
    return parsed


def forbidden_keys(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.append(key)
            found.extend(forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(forbidden_keys(child))
    return found


def validate_receipt(receipt: Dict[str, Any], output: Path, *, allow_pending_scan: bool = True) -> None:
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ReceiptError("RECEIPT_SCHEMA_UNSUPPORTED")
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise ReceiptError("RECEIPT_ID_INVALID")
    status_value = receipt.get("status")
    if status_value not in STATUSES:
        raise ReceiptError("RECEIPT_STATUS_INVALID")
    terminal = receipt.get("terminal")
    if not isinstance(terminal, bool):
        raise ReceiptError("RECEIPT_TERMINAL_FLAG_INVALID")
    if (status_value == VERIFYING and terminal) or (status_value in TERMINAL_STATES and not terminal):
        raise ReceiptError("RECEIPT_TERMINAL_STATE_INCONSISTENT")
    if receipt.get("drift") not in DRIFTS:
        raise ReceiptError("RECEIPT_DRIFT_INVALID")
    if receipt.get("last_completed_gate") not in GATES:
        raise ReceiptError("RECEIPT_GATE_INVALID")
    validate_timestamp(receipt.get("started_at"), "started_at")
    validate_timestamp(receipt.get("updated_at"), "updated_at")
    validate_timestamp(receipt.get("completed_at"), "completed_at", allow_none=True)
    workspace = receipt.get("workspace")
    if not isinstance(workspace, str) or not Path(workspace).is_absolute():
        raise ReceiptError("RECEIPT_WORKSPACE_INVALID")
    clean_text(workspace, "workspace", max_length=1024, allow_none=False)
    invocation = receipt.get("invocation")
    if not isinstance(invocation, dict):
        raise ReceiptError("RECEIPT_INVOCATION_INVALID")
    if invocation.get("fresh_task") not in FRESH_TASK_VALUES:
        raise ReceiptError("RECEIPT_FRESHNESS_INVALID")
    if invocation.get("freshness_basis") not in FRESHNESS_BASES:
        raise ReceiptError("RECEIPT_FRESHNESS_BASIS_INVALID")
    if invocation.get("mode") not in INVOCATION_MODES:
        raise ReceiptError("RECEIPT_INVOCATION_MODE_INVALID")
    clean_text(invocation.get("model"), "model", max_length=80, allow_none=False)
    clean_text(invocation.get("reasoning_effort"), "reasoning_effort", max_length=40, allow_none=False)
    scope = receipt.get("scope")
    if (
        not isinstance(scope, dict)
        or scope.get("operation") != "READ_VERIFY_RECONSTRUCT"
        or scope.get("phase_authorized") is not False
    ):
        raise ReceiptError("RECEIPT_AUTHORITY_INVALID")
    allowed_writes = scope.get("allowed_writes")
    if allowed_writes != [str(output)]:
        raise ReceiptError("RECEIPT_ALLOWED_WRITES_INVALID")
    if forbidden_keys(receipt):
        raise ReceiptError("RECEIPT_PRIVATE_IDENTIFIER_FIELD")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"skill", "handoff", "checkpoint"}:
        raise ReceiptError("RECEIPT_ARTIFACTS_INVALID")
    for artifact_name, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            raise ReceiptError("RECEIPT_ARTIFACT_INVALID")
        artifact_path = artifact.get("path")
        if not isinstance(artifact_path, str) or not Path(artifact_path).is_absolute():
            raise ReceiptError("RECEIPT_ARTIFACT_PATH_INVALID")
        clean_text(artifact_path, "artifact_path", max_length=2048, allow_none=False)
        if not isinstance(artifact.get("present"), bool) or not isinstance(artifact.get("regular_file"), bool):
            raise ReceiptError("RECEIPT_ARTIFACT_STATE_INVALID")
        artifact_hash = artifact.get("sha256")
        if artifact_hash is not None and (
            not isinstance(artifact_hash, str) or re.fullmatch(r"[0-9a-f]{64}", artifact_hash) is None
        ):
            raise ReceiptError("RECEIPT_ARTIFACT_HASH_INVALID")
        if artifact_name == "checkpoint":
            checkpoint_schema = artifact.get("schema_version")
            if checkpoint_schema is not None and not isinstance(checkpoint_schema, int):
                raise ReceiptError("RECEIPT_CHECKPOINT_SCHEMA_INVALID")
    for field in (
        "checkpoint_generated_at",
        "current_phase",
        "next_phase",
        "reason",
    ):
        clean_text(receipt.get(field), field, max_length=200)
    if receipt.get("checkpoint_generated_at") is not None:
        validate_timestamp(receipt.get("checkpoint_generated_at"), "checkpoint_generated_at")
    reason_code = receipt.get("reason_code")
    if reason_code is not None and (
        not isinstance(reason_code, str) or re.fullmatch(r"[A-Z0-9_]{1,80}", reason_code) is None
    ):
        raise ReceiptError("RECEIPT_REASON_CODE_INVALID")
    if status_value == VERIFYING:
        if receipt.get("completed_at") is not None:
            raise ReceiptError("RECEIPT_VERIFYING_COMPLETION_INVALID")
        if receipt.get("drift") != "UNKNOWN":
            raise ReceiptError("RECEIPT_VERIFYING_STATE_INVALID")
    elif not isinstance(receipt.get("completed_at"), str):
        raise ReceiptError("RECEIPT_COMPLETION_MISSING")
    else:
        validate_terminal_contract(status_value, receipt.get("drift"))
    validation = receipt.get("validation")
    if not isinstance(validation, dict) or validation.get("json") is not True:
        raise ReceiptError("RECEIPT_VALIDATION_INVALID")
    scan_state = validation.get("secret_scan")
    allowed_scan_states = {"PASS", "NOT_AVAILABLE", "NOT_RUN", "FAIL"}
    if allow_pending_scan:
        allowed_scan_states.add("PENDING")
    if scan_state not in allowed_scan_states:
        raise ReceiptError("RECEIPT_SECRET_SCAN_STATE_INVALID")
    if status_value == "READY":
        if receipt.get("drift") not in READY_DRIFTS:
            raise ReceiptError("READY_DRIFT_INVALID")
        if receipt.get("last_completed_gate") != "TELEMETRY_VALIDATED":
            raise ReceiptError("READY_GATE_INCOMPLETE")
        if scan_state not in {"PASS", "NOT_AVAILABLE"} and not (
            allow_pending_scan and scan_state == "PENDING"
        ):
            raise ReceiptError("READY_SECRET_SCAN_INCOMPLETE")


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    present, regular = regular_file_state(path)
    if present and not regular:
        raise ReceiptError("OUTPUT_NOT_REGULAR_FILE")
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        reparsed = json.loads(serialized)
    except json.JSONDecodeError as exc:
        raise ReceiptError("SERIALIZED_RECEIPT_INVALID") from exc
    if not isinstance(reparsed, dict):
        raise ReceiptError("SERIALIZED_RECEIPT_NOT_OBJECT")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{}-".format(path.name),
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        os.chmod(str(path), 0o600)
        try:
            directory_descriptor = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError:
            pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def receipt_directory_lock(output: Path) -> Iterable[None]:
    try:
        descriptor = os.open(str(output.parent), os.O_RDONLY)
    except OSError as exc:
        raise ReceiptError("RECEIPT_LOCK_UNAVAILABLE") from exc
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except OSError as exc:
            raise ReceiptError("RECEIPT_LOCK_UNAVAILABLE") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def locked_mutation(handler: Any) -> Any:
    @wraps(handler)
    def wrapped(args: argparse.Namespace) -> int:
        output = resolved_output_path(args.output)
        with receipt_directory_lock(output):
            return int(handler(args))

    return wrapped


def artifact_continuity_changes(receipt: Dict[str, Any]) -> List[str]:
    changes: List[str] = []
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        return ["artifacts"]
    for name in ("skill", "handoff", "checkpoint"):
        before = artifacts.get(name)
        if not isinstance(before, dict) or not isinstance(before.get("path"), str):
            changes.append(name)
            continue
        after = artifact_record(before["path"], checkpoint=(name == "checkpoint"))
        for field in ("present", "regular_file", "sha256"):
            if before.get(field) != after.get(field):
                changes.append(name)
                break
    return sorted(set(changes))


def receipt_summary(receipt: Dict[str, Any]) -> str:
    schema = receipt.get("schema_version")
    if schema == 2:
        prior_status = clean_text(str(receipt.get("status", "UNKNOWN")), "legacy_status") or "UNKNOWN"
        drift = clean_text(str(receipt.get("drift", "UNKNOWN")), "legacy_drift") or "UNKNOWN"
        return (
            "TP LEGACY_V2 | prior-status={} | receipt=NONE | fresh-task=UNKNOWN | "
            "workspace=UNKNOWN | checkpoint=UNKNOWN | gate=UNKNOWN | "
            "drift={} | phase-authority=NO"
        ).format(prior_status, drift)
    if schema != SCHEMA_VERSION:
        raise ReceiptError("RECEIPT_SCHEMA_UNSUPPORTED")
    invocation = receipt.get("invocation", {})
    checkpoint = receipt.get("artifacts", {}).get("checkpoint", {})
    return (
        "TP {status} | receipt={receipt_id} | fresh-task={fresh_task} | "
        "model={model}/{effort} | workspace={workspace} | checkpoint={checkpoint} | "
        "gate={gate} | drift={drift} | phase-authority=NO"
    ).format(
        status=receipt.get("status"),
        receipt_id=receipt.get("receipt_id"),
        fresh_task=invocation.get("fresh_task", "UNKNOWN"),
        model=invocation.get("model", "UNKNOWN"),
        effort=invocation.get("reasoning_effort", "UNKNOWN"),
        workspace=receipt.get("workspace", "UNKNOWN"),
        checkpoint=checkpoint.get("context_status") or "UNKNOWN",
        gate=receipt.get("last_completed_gate", "UNKNOWN"),
        drift=receipt.get("drift", "UNKNOWN"),
    )


def print_summary(receipt: Dict[str, Any]) -> None:
    summary = receipt_summary(receipt)
    if "\n" in summary or "\r" in summary:
        raise ReceiptError("SUMMARY_NOT_SINGLE_LINE")
    print(summary)


def validate_freshness_pair(fresh_task: str, basis: str) -> None:
    expected = {
        "YES": "FIRST_SUBSTANTIVE_USER_TURN",
        "NO": "PRIOR_TASK_CONTENT",
        "UNKNOWN": "UNVERIFIED",
    }
    if expected[fresh_task] != basis:
        raise ReceiptError("FRESHNESS_EVIDENCE_INCONSISTENT")


def start_receipt(args: argparse.Namespace) -> int:
    workspace = resolved_existing_directory(args.workspace, "workspace")
    expected_workspace = resolved_existing_directory(args.expected_workspace, "expected_workspace")
    if workspace != expected_workspace:
        raise ReceiptError("WORKSPACE_MISMATCH")
    output = resolved_output_path(args.output)
    ensure_within(output, expected_workspace)
    if output.exists():
        existing = read_json_object(output)
        if existing.get("schema_version") == SCHEMA_VERSION and existing.get("status") == VERIFYING:
            active_id = existing.get("receipt_id", "UNKNOWN")
            raise ReceiptError("ACTIVE_RECEIPT_EXISTS {}".format(active_id), exit_code=3)
    validate_freshness_pair(args.fresh_task, args.freshness_basis)
    model = clean_text(args.model, "model", max_length=80, allow_none=False)
    effort = clean_text(args.effort, "effort", max_length=40, allow_none=False)
    started_at = utc_now()
    receipt_id = new_receipt_id(started_at)
    terminal = args.fresh_task != "YES"
    status_value = VERIFYING
    drift = "UNKNOWN"
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    completed_at: Optional[str] = None
    if args.fresh_task == "NO":
        status_value = "REVIEW_REQUIRED"
        drift = "MATERIAL"
        reason_code = "NOT_FRESH_TASK"
        reason = "Treasure Pickup must begin in a fresh task."
        completed_at = started_at
    elif args.fresh_task == "UNKNOWN":
        status_value = "REVIEW_REQUIRED"
        drift = "UNKNOWN"
        reason_code = "TASK_FRESHNESS_UNKNOWN"
        reason = "Task freshness could not be verified."
        completed_at = started_at
    receipt: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "status": status_value,
        "terminal": terminal,
        "started_at": started_at,
        "updated_at": started_at,
        "completed_at": completed_at,
        "workspace": str(workspace),
        "invocation": {
            "mode": args.invocation_mode,
            "fresh_task": args.fresh_task,
            "freshness_basis": args.freshness_basis,
            "model": model,
            "reasoning_effort": effort,
        },
        "scope": {
            "operation": "READ_VERIFY_RECONSTRUCT",
            "phase_authorized": False,
            "allowed_writes": [str(output)],
        },
        "artifacts": {
            "skill": artifact_record(args.skill_file),
            "handoff": artifact_record(args.handoff),
            "checkpoint": artifact_record(args.checkpoint, checkpoint=True),
        },
        "last_completed_gate": "INVOCATION_RECORDED",
        "drift": drift,
        "checkpoint_generated_at": None,
        "current_phase": None,
        "next_phase": None,
        "reason_code": reason_code,
        "reason": reason,
        "validation": {
            "json": True,
            "secret_scan": "PENDING",
        },
    }
    validate_receipt(receipt, output)
    if terminal:
        scan_state = secret_scan(receipt, output, args.gitleaks_path)
        if scan_state == "FAIL":
            return terminalize_scan_failure(receipt, output)
        receipt["validation"]["secret_scan"] = scan_state
        validate_receipt(receipt, output, allow_pending_scan=False)
    atomic_write_json(output, receipt)
    print_summary(receipt)
    return 0


def require_active_receipt(output: Path, receipt_id: str) -> Dict[str, Any]:
    receipt = read_json_object(output)
    validate_receipt(receipt, output)
    if receipt.get("receipt_id") != receipt_id:
        raise ReceiptError("RECEIPT_ID_MISMATCH")
    if receipt.get("status") != VERIFYING or receipt.get("terminal") is not False:
        raise ReceiptError("RECEIPT_NOT_ACTIVE")
    return receipt


def advance_receipt(args: argparse.Namespace) -> int:
    output = resolved_output_path(args.output)
    receipt_id = clean_text(args.receipt_id, "receipt_id", max_length=80, allow_none=False)
    receipt = require_active_receipt(output, receipt_id or "")
    current_gate = receipt["last_completed_gate"]
    current_index = GATES.index(current_gate)
    requested_index = GATES.index(args.gate)
    if requested_index != current_index + 1 or args.gate == "TELEMETRY_VALIDATED":
        raise ReceiptError("GATE_TRANSITION_INVALID")
    receipt["last_completed_gate"] = args.gate
    receipt["updated_at"] = utc_now()
    validate_receipt(receipt, output)
    atomic_write_json(output, receipt)
    print_summary(receipt)
    return 0


def terminalize_artifact_drift(receipt: Dict[str, Any], output: Path) -> int:
    now = utc_now()
    receipt.update(
        {
            "status": "REVIEW_REQUIRED",
            "terminal": True,
            "updated_at": now,
            "completed_at": now,
            "drift": "MATERIAL",
            "reason_code": "ARTIFACT_CONTINUITY_CHANGED",
            "reason": "A flight-receipt artifact changed during verification.",
            "validation": {"json": True, "secret_scan": "NOT_RUN"},
        }
    )
    validate_receipt(receipt, output)
    atomic_write_json(output, receipt)
    print_summary(receipt)
    return 3


def secret_scan(candidate: Dict[str, Any], output: Path, explicit_path: Optional[str]) -> str:
    executable = explicit_path or shutil.which("gitleaks")
    if executable is None:
        return "NOT_AVAILABLE"
    executable_path = Path(executable)
    if not executable_path.exists() or not os.access(str(executable_path), os.X_OK):
        raise ReceiptError("GITLEAKS_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix=".treasurepickup-scan-", dir=str(output.parent)) as temporary:
        scan_file = Path(temporary) / "context-resume.json"
        scan_file.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        scan_file.chmod(0o600)
        completed = subprocess.run(
            [
                str(executable_path),
                "detect",
                "--no-git",
                "--source",
                temporary,
                "--redact",
                "--no-banner",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return "PASS" if completed.returncode == 0 else "FAIL"


def terminalize_scan_failure(receipt: Dict[str, Any], output: Path) -> int:
    now = utc_now()
    receipt["invocation"]["model"] = "UNKNOWN"
    receipt["invocation"]["reasoning_effort"] = "UNKNOWN"
    receipt.update(
        {
            "status": "STOP",
            "terminal": True,
            "updated_at": now,
            "completed_at": now,
            "drift": "SECURITY",
            "current_phase": None,
            "next_phase": None,
            "reason_code": "SENSITIVE_DATA_SCAN_FAILED",
            "reason": "Sanitized receipt validation did not pass.",
            "validation": {"json": True, "secret_scan": "FAIL"},
        }
    )
    validate_receipt(receipt, output)
    atomic_write_json(output, receipt)
    print_summary(receipt)
    return 3


def validate_terminal_contract(status_value: str, drift: str) -> None:
    allowed_drifts = {
        "READY": READY_DRIFTS,
        "BLOCKED": {"UNKNOWN"},
        "REVIEW_REQUIRED": {"MATERIAL", "UNKNOWN"},
        "STOP": {"SECURITY"},
        "ABORTED": {"UNKNOWN"},
    }
    if drift not in allowed_drifts[status_value]:
        raise ReceiptError("TERMINAL_STATUS_DRIFT_INCONSISTENT")


def complete_receipt(args: argparse.Namespace) -> int:
    output = resolved_output_path(args.output)
    receipt_id = clean_text(args.receipt_id, "receipt_id", max_length=80, allow_none=False)
    receipt = require_active_receipt(output, receipt_id or "")
    safe_receipt = copy.deepcopy(receipt)
    validate_terminal_contract(args.status, args.drift)
    if args.status == "READY":
        if receipt.get("last_completed_gate") != "LIVE_STATE_VERIFIED":
            raise ReceiptError("READY_GATES_INCOMPLETE")
        if args.drift not in READY_DRIFTS:
            raise ReceiptError("READY_DRIFT_INVALID")
        if artifact_continuity_changes(receipt):
            return terminalize_artifact_drift(receipt, output)
    now = utc_now()
    receipt.update(
        {
            "status": args.status,
            "terminal": True,
            "updated_at": now,
            "completed_at": now,
            "drift": args.drift,
            "checkpoint_generated_at": clean_text(
                args.checkpoint_generated_at,
                "checkpoint_generated_at",
                max_length=80,
            ),
            "current_phase": clean_text(args.current_phase, "current_phase"),
            "next_phase": clean_text(args.next_phase, "next_phase"),
            "reason_code": clean_text(args.reason_code, "reason_code", max_length=80),
            "reason": clean_text(args.reason, "reason"),
            "validation": {"json": True, "secret_scan": "PENDING"},
        }
    )
    if args.status == "READY":
        receipt["last_completed_gate"] = "TELEMETRY_VALIDATED"
    validate_receipt(receipt, output, allow_pending_scan=True)
    scan_state = secret_scan(receipt, output, args.gitleaks_path)
    if scan_state == "FAIL":
        return terminalize_scan_failure(safe_receipt, output)
    receipt["validation"]["secret_scan"] = scan_state
    validate_receipt(receipt, output, allow_pending_scan=False)
    atomic_write_json(output, receipt)
    print_summary(receipt)
    return 0


def show_summary(args: argparse.Namespace) -> int:
    output = resolved_output_path(args.output)
    receipt = read_json_object(output)
    if receipt.get("schema_version") == SCHEMA_VERSION:
        validate_receipt(receipt, output)
    print_summary(receipt)
    return 0


def validate_command(args: argparse.Namespace) -> int:
    output = resolved_output_path(args.output)
    receipt = read_json_object(output)
    if receipt.get("schema_version") == SCHEMA_VERSION:
        validate_receipt(receipt, output)
    elif receipt.get("schema_version") != 2:
        raise ReceiptError("RECEIPT_SCHEMA_UNSUPPORTED")
    print("VALID schema_version={}".format(receipt.get("schema_version")))
    return 0


def add_output_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Write the initial flight receipt")
    add_output_argument(start)
    start.add_argument("--workspace", default=os.getcwd())
    start.add_argument("--expected-workspace", default=None)
    start.add_argument("--handoff", default=None)
    start.add_argument("--checkpoint", default=None)
    start.add_argument("--skill-file", default=str(DEFAULT_SKILL_FILE))
    start.add_argument("--fresh-task", choices=sorted(FRESH_TASK_VALUES), required=True)
    start.add_argument("--freshness-basis", choices=sorted(FRESHNESS_BASES), required=True)
    start.add_argument("--invocation-mode", choices=sorted(INVOCATION_MODES), default="MANUAL_SKILL_SELECTOR")
    start.add_argument("--model", default="UNKNOWN")
    start.add_argument("--effort", default="UNKNOWN")
    start.add_argument("--gitleaks-path")
    start.set_defaults(handler=locked_mutation(start_receipt))

    advance = subparsers.add_parser("advance", help="Advance one verified flight-receipt gate")
    add_output_argument(advance)
    advance.add_argument("--receipt-id", required=True)
    advance.add_argument("--gate", choices=GATES[1:-1], required=True)
    advance.set_defaults(handler=locked_mutation(advance_receipt))

    complete = subparsers.add_parser("complete", help="Write a terminal flight-receipt result")
    add_output_argument(complete)
    complete.add_argument("--receipt-id", required=True)
    complete.add_argument("--status", choices=sorted(TERMINAL_STATES), required=True)
    complete.add_argument("--drift", choices=sorted(DRIFTS), required=True)
    complete.add_argument("--checkpoint-generated-at")
    complete.add_argument("--current-phase")
    complete.add_argument("--next-phase")
    complete.add_argument("--reason-code")
    complete.add_argument("--reason")
    complete.add_argument("--gitleaks-path")
    complete.set_defaults(handler=locked_mutation(complete_receipt))

    summary = subparsers.add_parser("summary", help="Print the one-line flight receipt")
    add_output_argument(summary)
    summary.set_defaults(handler=show_summary)

    validate_parser = subparsers.add_parser("validate", help="Validate receipt structure")
    add_output_argument(validate_parser)
    validate_parser.set_defaults(handler=validate_command)
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    workspace = Path(
        getattr(args, "expected_workspace", None)
        or os.environ.get("PICKUP_HOME")
        or Path.home() / "Desktop" / "pickup_audit"
    ).expanduser()
    if args.command == "start":
        if args.expected_workspace is None:
            args.expected_workspace = str(workspace)
        if args.handoff is None:
            args.handoff = str(workspace / "trashpickup" / "current-context.md")
        if args.checkpoint is None:
            args.checkpoint = str(workspace / "trashpickup" / "context-checkpoint.json")
    if args.output is None:
        args.output = str(workspace / "treasurepickup" / "context-resume.json")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        return int(args.handler(args))
    except ReceiptError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("INTERRUPTED", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
