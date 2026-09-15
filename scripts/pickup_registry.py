#!/usr/bin/env python3
"""Durable package selection and run coordination for Treasure Pickup."""

from __future__ import annotations

import argparse
import copy
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

REGISTRY_SCHEMA_VERSION = 1
PACKAGE_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 4
REGISTRY_DIRECTORY_MODE = 0o700
REGISTRY_FILE_MODE = 0o600
TRACK_ID_RE = re.compile(r"^(?=.{1,63}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
CHECKPOINT_ID_RE = re.compile(r"^cp-\d{8}-\d{6}-[0-9a-f]{8}$")
RECEIPT_ID_RE = re.compile(r"^tp-\d{8}T\d{6}Z-(?:[0-9a-f]{8}|[0-9a-f]{32})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(
    r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])-"
    r"(?P<day>0[1-9]|[12]\d|3[01])T"
    r"(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d):"
    r"(?P<second>[0-5]\d|60)(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
TERMINAL_REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
MAX_TERMINAL_REASON_LENGTH = 500
MAX_MODEL_LENGTH = 80
MAX_REASONING_EFFORT_LENGTH = 40
MAX_PHASE_LENGTH = 200
MAX_EVIDENCE_NAME_LENGTH = 100
MAX_EVIDENCE_DETAIL_LENGTH = 500
FORBIDDEN_KEYS = {
    "pid",
    "ppid",
    "process_id",
    "process_identifier",
    "process_name",
    "session_id",
    "session_identifier",
    "task_id",
    "task_identifier",
    "task_name",
    "thread_id",
    "thread_identifier",
    "window_id",
    "window_title",
}
FORBIDDEN_KEY_RE = re.compile(
    r"(?:^|_)(?:process|session|task|thread|window)_"
    r"(?:id|identifier|name|title)(?:_|$)"
)
CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
KEY_SEPARATOR_RE = re.compile(r"[^A-Za-z0-9]+")
FORBIDDEN_COMPACT_KEYS = frozenset(key.replace("_", "") for key in FORBIDDEN_KEYS)
FORBIDDEN_COMPACT_KEY_RE = re.compile(
    r"(?:process|session|task|thread|window)"
    r"(?:id|identifier|name|title|value|number|active|handle)"
    r"|(?:id|identifier|name|title|value|number|active|handle)"
    r"(?:process|session|task|thread|window)"
)
FORBIDDEN_PID_KEY_RE = re.compile(r"(?:^|_)(?:pid|ppid)(?:_|$)")
FORBIDDEN_PID_COMPACT_KEY_RE = re.compile(
    r"^(?:pid|ppid)(?:id|identifier|value|name|number)"
    r"|(?:id|identifier|value|name|number)(?:pid|ppid)$"
)
FORBIDDEN_RUNTIME_FAMILIES = frozenset(
    {"process", "session", "task", "thread", "window"}
)
FORBIDDEN_RUNTIME_IDENTITY_TERMS = frozenset(
    {
        "id",
        "identifier",
        "name",
        "title",
        "value",
        "number",
        "active",
        "handle",
        "uuid",
        "guid",
        "ref",
        "reference",
        "key",
        "token",
    }
)
FORBIDDEN_SENSITIVE_KEYS = frozenset(
    {
        "credential",
        "credentials",
        "private_id",
        "private_identifier",
    }
)
FORBIDDEN_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:credentials?|private_(?:id|identifier))(?:_|$)"
)
FORBIDDEN_SENSITIVE_COMPACT_KEY_RE = re.compile(
    r"(?:credential|credentials|privateid|privateidentifier)"
)
FORBIDDEN_CREDENTIAL_EXACT = frozenset(
    {
        "authorization",
        "auth",
        "credential",
        "credentials",
        "key",
        "token",
        "secret",
        "cookie",
        "cookies",
        "password",
        "passphrase",
        "api_key",
        "api_token",
        "auth_token",
        "access_token",
        "refresh_token",
        "bearer_token",
        "id_token",
        "oauth_token",
        "session_cookie",
        "client_secret",
        "client_key",
        "private_key",
        "secret_key",
        "ssh_key",
        "encryption_key",
        "signing_key",
        "webhook_secret",
        "database_password",
        "db_password",
    }
)
FORBIDDEN_CREDENTIAL_COMPACT = frozenset(
    key.replace("_", "") for key in FORBIDDEN_CREDENTIAL_EXACT
)
FORBIDDEN_CREDENTIAL_FAMILIES = frozenset(
    {
        "api",
        "auth",
        "authentication",
        "access",
        "refresh",
        "bearer",
        "client",
        "database",
        "db",
        "encryption",
        "oauth",
        "private",
        "secret",
        "signing",
        "ssh",
        "webhook",
    }
)
FORBIDDEN_CREDENTIAL_CARRIERS = frozenset({"key", "token", "secret"})
FORBIDDEN_CREDENTIAL_STANDALONE = frozenset(
    {
        "authorization",
        "auth",
        "credential",
        "credentials",
        "password",
        "passphrase",
        "token",
        "cookie",
        "cookies",
    }
)


class PackageState(str, Enum):
    AVAILABLE = "AVAILABLE"
    CLAIMED = "CLAIMED"
    OPENING = "OPENING"
    CONSUMED = "CONSUMED"
    SUPERSEDED = "SUPERSEDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Gate(str, Enum):
    INVOCATION_RECORDED = "INVOCATION_RECORDED"
    CANONICAL_PAIR_VERIFIED = "CANONICAL_PAIR_VERIFIED"
    LIVE_STATE_VERIFIED = "LIVE_STATE_VERIFIED"
    TELEMETRY_VALIDATED = "TELEMETRY_VALIDATED"


GATES = tuple(gate.value for gate in Gate)


class TerminalStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    STOP = "STOP"
    ABORTED = "ABORTED"


class DriftClass(str, Enum):
    NONE = "NONE"
    EXPECTED = "EXPECTED"
    BENIGN = "BENIGN"
    MATERIAL = "MATERIAL"
    SECURITY = "SECURITY"
    UNKNOWN = "UNKNOWN"


class ReceiptEvent(str, Enum):
    CLAIMED = "CLAIMED"
    GATE_ADVANCED = "GATE_ADVANCED"
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"


TERMINAL_DRIFT_POLICY = {
    TerminalStatus.READY: frozenset(
        {DriftClass.NONE, DriftClass.EXPECTED, DriftClass.BENIGN}
    ),
    TerminalStatus.BLOCKED: frozenset({DriftClass.UNKNOWN}),
    TerminalStatus.REVIEW_REQUIRED: frozenset(
        {DriftClass.MATERIAL, DriftClass.UNKNOWN}
    ),
    TerminalStatus.STOP: frozenset({DriftClass.SECURITY}),
    TerminalStatus.ABORTED: frozenset({DriftClass.UNKNOWN}),
}


PACKAGE_QUARANTINE_REASONS = frozenset(
    {"PACKAGE_ARTIFACT_DRIFT", "SENSITIVE_DATA_SCAN_FAILED"}
)
INDEX_VIEW_KEYS = frozenset({"schema_version", "updated_at", "tracks", "receipts"})
TRACK_VIEW_KEYS = frozenset(
    {
        "track_id",
        "resource_scopes",
        "latest_checkpoint_id",
        "packages",
        "active_claim",
        "updated_at",
    }
)
PACKAGE_ENTRY_KEYS = frozenset(
    {
        "state",
        "selector",
        "package_sha256",
        "handoff_sha256",
        "checkpoint_sha256",
        "previous_checkpoint_id",
        "previous_package_sha256",
        "quarantine_template_sha256",
        "latest_receipt_id",
        "quarantine_reason_code",
        "quarantine_event_sha256",
    }
)
RECEIPT_ENTRY_KEYS = frozenset(
    {
        "track_id",
        "checkpoint_id",
        "latest_revision",
        "latest_receipt_sha256",
        "latest_receipt_path",
    }
)
TERMINAL_RECEIPT_ENTRY_KEYS = RECEIPT_ENTRY_KEYS | {"terminal_status"}
RELEASED_RECEIPT_ENTRY_KEYS = TERMINAL_RECEIPT_ENTRY_KEYS | {"released_at"}
ACTIVE_CLAIM_KEYS = frozenset(
    {
        "schema_version",
        "active",
        "track_id",
        "checkpoint_id",
        "receipt_id",
        "latest_revision",
        "latest_receipt_sha256",
        "latest_receipt_path",
        "claimed_at",
    }
)
CLOSED_CLAIM_KEYS = ACTIVE_CLAIM_KEYS | {"closed_at", "terminal_status"}
RELEASED_CLAIM_KEYS = CLOSED_CLAIM_KEYS | {"released_at"}
BASE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "revision",
        "previous_receipt_sha256",
        "previous_lifecycle_receipt_id",
        "previous_lifecycle_receipt_sha256",
        "event",
        "status",
        "terminal",
        "drift",
        "started_at",
        "updated_at",
        "completed_at",
        "workspace",
        "pickup",
        "invocation",
        "scope",
        "artifacts",
        "last_completed_gate",
        "transition_evidence",
        "reason_code",
        "reason",
        "validation",
    }
)
TERMINAL_RECEIPT_KEYS = BASE_RECEIPT_KEYS | {"current_phase", "next_phase"}
RELEASED_RECEIPT_KEYS = TERMINAL_RECEIPT_KEYS | {"release_reason_code"}
PICKUP_RECEIPT_KEYS = frozenset({"track_id", "checkpoint_id", "selector"})
INVOCATION_RECEIPT_KEYS = frozenset(
    {"fresh_task", "freshness_basis", "mode", "model", "reasoning_effort"}
)
SCOPE_RECEIPT_KEYS = frozenset({"operation", "phase_authorized", "allowed_writes"})
ARTIFACT_KEYS = frozenset({"path", "present", "regular_file", "sha256"})
CHECKPOINT_ARTIFACT_KEYS = ARTIFACT_KEYS | {
    "schema_version",
    "context_status",
    "generated_at",
}
DRIFT_ARTIFACT_KEYS = frozenset(
    {"path", "expected_sha256", "present", "regular_file", "observed_sha256"}
)
LEGACY_V3_COMPATIBILITY_KEYS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "status",
        "terminal",
        "drift",
        "started_at",
        "updated_at",
        "completed_at",
        "workspace",
        "invocation",
        "scope",
        "artifacts",
        "last_completed_gate",
        "checkpoint_generated_at",
        "current_phase",
        "next_phase",
        "reason_code",
        "reason",
        "validation",
    }
)


@dataclass(frozen=True)
class RunCoordinates:
    track_id: str
    checkpoint_id: str
    receipt_id: str
    revision: int
    receipt_sha256: str

    def validate(self) -> None:
        validate_track_id(self.track_id)
        if CHECKPOINT_ID_RE.fullmatch(self.checkpoint_id) is None:
            raise RegistryError("CHECKPOINT_ID_INVALID")
        if (
            RECEIPT_ID_RE.fullmatch(self.receipt_id) is None
            or not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
            or SHA256_RE.fullmatch(self.receipt_sha256) is None
        ):
            raise RegistryError("RUN_COORDINATES_INVALID")


@dataclass(frozen=True)
class InvocationContext:
    workspace: Path
    fresh_task: str
    freshness_basis: str
    mode: str
    model: str
    effort: str
    skill_file: Path

    def validate(self) -> None:
        validate_fresh_invocation(self.fresh_task, self.freshness_basis)
        if self.mode not in {"MANUAL_SKILL_SELECTOR", "SLASH_COMMAND"}:
            raise RegistryError("INVOCATION_MODE_INVALID")
        if not bounded_printable_string(self.model, MAX_MODEL_LENGTH) or not (
            bounded_printable_string(self.effort, MAX_REASONING_EFFORT_LENGTH)
        ):
            raise RegistryError("INVOCATION_METADATA_INVALID")
        if not self.workspace.is_absolute() or not self.workspace.is_dir():
            raise RegistryError("WORKSPACE_INVALID")
        skill_file = regular_file(self.skill_file, "SKILL_FILE_INVALID")
        if (
            self.skill_file != deployed_skill_file()
            or skill_file != deployed_skill_file()
        ):
            raise RegistryError("SKILL_FILE_INVALID")

    def receipt_value(self) -> Dict[str, str]:
        return {
            "fresh_task": self.fresh_task,
            "freshness_basis": self.freshness_basis,
            "mode": self.mode,
            "model": self.model,
            "reasoning_effort": self.effort,
        }


@dataclass(frozen=True)
class ReceiptHistory:
    first: Dict[str, Any]
    latest: Dict[str, Any]
    latest_path: Path
    latest_sha256: str


@dataclass(frozen=True)
class PackageCoordinate:
    track_id: str
    checkpoint_id: str

    @property
    def selector(self) -> str:
        return "{}@{}".format(self.track_id, self.checkpoint_id)

    def package_path(self, registry_root: Path) -> Path:
        return (
            registry_root / "tracks" / self.track_id / "packages" / self.checkpoint_id
        )

    def quarantine_event_path(self, registry_root: Path) -> Path:
        return (
            registry_root
            / "tracks"
            / self.track_id
            / "quarantines"
            / "{}.json".format(self.checkpoint_id)
        )


@dataclass(frozen=True)
class ImmutableChainLink:
    node_id: str
    sha256: str
    predecessor_id: Optional[str]
    predecessor_sha256: Optional[str]


@dataclass(frozen=True)
class ImmutableWrite:
    path: Path
    data: bytes
    existing_reason_code: str = "IMMUTABLE_RECEIPT_EXISTS"
    cleanup_empty_parent: bool = False


@dataclass(frozen=True)
class MutableWrite:
    path: Path
    payload: Dict[str, Any]
    parent_reason_code: str = "OUTPUT_PARENT_UNAVAILABLE"
    invalid_reason_code: str = "MUTABLE_VIEW_INVALID"
    write_reason_code: str = "MUTABLE_WRITE_FAILED"
    expected_destination: Optional["MutableDestination"] = None


@dataclass(frozen=True)
class MutableDestination:
    existed: bool
    identity: Optional[tuple[int, int]]
    sha256: Optional[str]


@dataclass(frozen=True)
class ImmutableInstall:
    path: Path
    identity: tuple[int, int]
    sha256: str
    created_parent: bool = False
    parent_identity: Optional[tuple[int, int]] = None
    mode: int = REGISTRY_FILE_MODE
    parent_mode: Optional[int] = REGISTRY_DIRECTORY_MODE
    created_parent_parent_identity: Optional[tuple[int, int]] = None
    created_parent_parent_mode: Optional[int] = None
    staging_path: Optional[Path] = None


@dataclass(frozen=True)
class DirectoryInstall:
    path: Path
    identity: tuple[int, int]
    files: tuple[ImmutableInstall, ...]
    parent_identity: tuple[int, int]
    parent_mode: int


@dataclass(frozen=True)
class OwnedDirectory:
    path: Path
    identity: tuple[int, int]
    mode: int
    parent_identity: tuple[int, int]
    parent_mode: int


@dataclass(frozen=True)
class DirectoryExpectation:
    existed: bool
    identity: Optional[tuple[int, int]]
    mode: Optional[int]


@dataclass(frozen=True)
class RegistryRootGuard:
    path: Path
    identity: tuple[int, int]
    mode: int
    descriptor: int


_ACTIVE_REGISTRY_ROOT_GUARD: Optional[RegistryRootGuard] = None


@dataclass(frozen=True)
class NodeToken:
    kind: str
    identity: tuple[int, int]
    mode: int
    sha256: Optional[str] = None
    link_target: Optional[str] = None
    children: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathStateGuard:
    path: Path
    parent_identity: tuple[int, int]
    parent_mode: int
    token: Optional[NodeToken]


RegistrySnapshot = Dict[str, NodeToken]


@dataclass
class PreparedMutableWrite:
    write: MutableWrite
    temporary: Path
    parent_identity: tuple[int, int]
    parent_mode: int
    new_sha256: str
    new_identity: tuple[int, int]
    existed: bool
    previous_data: Optional[bytes]
    previous_identity: Optional[tuple[int, int]]
    previous_token: Optional[NodeToken]
    committed: bool = False
    temporary_consumed: bool = False
    exchange_active: bool = False
    cleanup_blocked: bool = False
    displaced_token: Optional[NodeToken] = None

    @classmethod
    def prepare(cls, write: MutableWrite) -> "PreparedMutableWrite":
        temporary: Optional[Path] = None
        parent_identity: Optional[tuple[int, int]] = None
        staged_identity: Optional[tuple[int, int]] = None
        digest: Optional[str] = None
        parent_mode: Optional[int] = None
        try:
            existing_directory(write.path.parent, write.parent_reason_code)
            parent_metadata = write.path.parent.lstat()
            parent_identity = (parent_metadata.st_dev, parent_metadata.st_ino)
            parent_mode = stat.S_IMODE(parent_metadata.st_mode)
            if parent_mode & 0o222 == 0 or not os.access(write.path.parent, os.W_OK):
                raise RegistryError(write.parent_reason_code, exit_code=3)
            existed = write.path.exists() or write.path.is_symlink()
            previous_data: Optional[bytes] = None
            previous_identity: Optional[tuple[int, int]] = None
            previous_token: Optional[NodeToken] = None
            expected = write.expected_destination
            if expected is not None and existed is not expected.existed:
                raise RegistryError(write.invalid_reason_code, exit_code=3)
            if existed:
                previous_data, metadata = stable_regular_capture(
                    write.path,
                    write.invalid_reason_code,
                    expected_mode=REGISTRY_FILE_MODE,
                )
                previous_identity = (metadata.st_dev, metadata.st_ino)
                previous_token = NodeToken(
                    kind="file",
                    identity=previous_identity,
                    mode=stat.S_IMODE(metadata.st_mode),
                    sha256=hashlib.sha256(previous_data).hexdigest(),
                )
                if expected is not None and (
                    previous_identity != expected.identity
                    or hashlib.sha256(previous_data).hexdigest() != expected.sha256
                ):
                    raise RegistryError(write.invalid_reason_code, exit_code=3)
            validate_mutable_payload(write)
            data = serialized_json(write.payload)
            digest = hashlib.sha256(data).hexdigest()
            descriptor, temporary, staged_identity = create_owned_staging_file(
                write.path.parent,
                prefix=".{}-".format(write.path.name),
                suffix=".tmp",
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                reason_code=write.write_reason_code,
            )
            try:
                staged = os.fstat(descriptor)
                if not stat.S_ISREG(staged.st_mode):
                    raise RegistryError(write.write_reason_code, exit_code=3)
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = -1
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            require_owned_regular(
                temporary,
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                identity=staged_identity,
                sha256=digest,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            return cls(
                write=write,
                temporary=temporary,
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                new_sha256=digest,
                new_identity=staged_identity,
                existed=existed,
                previous_data=previous_data,
                previous_identity=previous_identity,
                previous_token=previous_token,
            )
        except RegistryError as exc:
            if temporary is not None:
                if parent_identity is None or staged_identity is None or digest is None:
                    raise RegistryError(
                        "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                    ) from exc
                remove_owned_regular(
                    temporary,
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                    identity=staged_identity,
                    sha256=digest,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
            if exc.reason_code in {
                write.parent_reason_code,
                write.invalid_reason_code,
            }:
                raise RegistryError(exc.reason_code, exit_code=3) from exc
            raise
        except OSError as exc:
            if temporary is not None:
                if parent_identity is None or staged_identity is None or digest is None:
                    raise RegistryError(
                        "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                    ) from exc
                remove_owned_regular(
                    temporary,
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                    identity=staged_identity,
                    sha256=digest,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
            raise RegistryError(write.write_reason_code, exit_code=3) from exc

    def commit(self) -> None:
        try:
            require_owned_regular(
                self.temporary,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code=self.write.invalid_reason_code,
            )
            if self.existed:
                if self.previous_token is None:
                    raise RegistryError(self.write.invalid_reason_code, exit_code=3)
                require_node_token(
                    self.write.path,
                    parent_identity=self.parent_identity,
                    parent_mode=self.parent_mode,
                    token=self.previous_token,
                    reason_code=self.write.invalid_reason_code,
                )
                exchange_owned_paths(
                    self.temporary,
                    self.write.path,
                    parent_identity=self.parent_identity,
                    parent_mode=self.parent_mode,
                    reason_code=self.write.write_reason_code,
                )
                self.exchange_active = True
                try:
                    displaced = capture_node_token(
                        self.temporary,
                        parent_identity=self.parent_identity,
                        parent_mode=self.parent_mode,
                        reason_code="TRANSACTION_ROLLBACK_FAILED",
                    )
                    self.displaced_token = displaced
                    require_owned_regular(
                        self.write.path,
                        parent_identity=self.parent_identity,
                        parent_mode=self.parent_mode,
                        identity=self.new_identity,
                        sha256=self.new_sha256,
                        reason_code="TRANSACTION_ROLLBACK_FAILED",
                    )
                    if displaced != self.previous_token:
                        self.restore_exchange(displaced)
                        raise RegistryError(
                            self.write.invalid_reason_code,
                            exit_code=3,
                        )
                except RegistryError:
                    if self.exchange_active:
                        self.cleanup_blocked = True
                    raise
                self.committed = True
            else:
                if self.write.path.exists() or self.write.path.is_symlink():
                    raise RegistryError(self.write.invalid_reason_code, exit_code=3)
                link_owned_path_noreplace(
                    self.temporary,
                    self.write.path,
                    parent_identity=self.parent_identity,
                    parent_mode=self.parent_mode,
                    reason_code=self.write.invalid_reason_code,
                )
                self.committed = True
                remove_owned_regular(
                    self.temporary,
                    parent_identity=self.parent_identity,
                    parent_mode=self.parent_mode,
                    identity=self.new_identity,
                    sha256=self.new_sha256,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                self.temporary_consumed = True
            sync_owned_directory(
                self.write.path.parent,
                self.parent_identity,
                self.write.invalid_reason_code,
                expected_mode=self.parent_mode,
            )
            self.require_committed()
        except FileExistsError as exc:
            raise RegistryError(self.write.invalid_reason_code, exit_code=3) from exc
        except RegistryError:
            raise
        except OSError as exc:
            reason_code = (
                self.write.invalid_reason_code
                if self.write.path.is_symlink()
                else self.write.write_reason_code
            )
            raise RegistryError(reason_code, exit_code=3) from exc

    def restore_exchange(self, displaced: NodeToken) -> None:
        try:
            require_owned_regular(
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            require_node_token(
                self.temporary,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                token=displaced,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            exchange_owned_paths(
                self.temporary,
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            self.exchange_active = False
            sync_owned_directory(
                self.write.path.parent,
                self.parent_identity,
                "TRANSACTION_ROLLBACK_FAILED",
                expected_mode=self.parent_mode,
                sync_reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            require_node_token(
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                token=displaced,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            require_owned_regular(
                self.temporary,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            self.displaced_token = None
        except RegistryError:
            self.cleanup_blocked = True
            raise

    def require_committed(self) -> None:
        if not self.committed:
            raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
        try:
            require_owned_regular(
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code="TRANSACTION_INSTALL_CHANGED",
            )
        except RegistryError as exc:
            raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3) from exc

    def require_consumed_temporary_absent(self) -> None:
        if not self.temporary_consumed:
            return
        require_owned_absence(
            self.temporary,
            parent_identity=self.parent_identity,
            parent_mode=self.parent_mode,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )

    def rollback(self) -> None:
        if not self.committed:
            return
        try:
            require_owned_regular(
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            if self.existed:
                if self.previous_token is None:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                if self.exchange_active:
                    self.restore_exchange(self.previous_token)
                elif self.temporary_consumed:
                    self.restore_previous_content()
                else:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            else:
                remove_owned_regular(
                    self.write.path,
                    parent_identity=self.parent_identity,
                    parent_mode=self.parent_mode,
                    identity=self.new_identity,
                    sha256=self.new_sha256,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                sync_owned_directory(
                    self.write.path.parent,
                    self.parent_identity,
                    "TRANSACTION_ROLLBACK_FAILED",
                    expected_mode=self.parent_mode,
                    sync_reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
            self.committed = False
        except RegistryError:
            raise
        except OSError as exc:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc

    def restore_previous_content(self) -> None:
        if (
            self.previous_data is None
            or self.previous_token is None
            or self.previous_token.sha256 is None
        ):
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
        descriptor = -1
        temporary: Optional[Path] = None
        previous_identity: Optional[tuple[int, int]] = None
        exchanged = False
        try:
            descriptor, temporary, previous_identity = create_owned_staging_file(
                self.write.path.parent,
                prefix=".{}-rollback-".format(self.write.path.name),
                suffix=".tmp",
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(self.previous_data)
                stream.flush()
                os.fsync(stream.fileno())
            require_owned_regular(
                temporary,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=previous_identity,
                sha256=self.previous_token.sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            require_owned_regular(
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            exchange_owned_paths(
                temporary,
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            exchanged = True
            sync_owned_directory(
                self.write.path.parent,
                self.parent_identity,
                "TRANSACTION_ROLLBACK_FAILED",
                expected_mode=self.parent_mode,
                sync_reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            require_owned_regular(
                self.write.path,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=previous_identity,
                sha256=self.previous_token.sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            remove_owned_regular(
                temporary,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.new_identity,
                sha256=self.new_sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            temporary = None
            sync_owned_directory(
                self.write.path.parent,
                self.parent_identity,
                "TRANSACTION_ROLLBACK_FAILED",
                expected_mode=self.parent_mode,
                sync_reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            self.committed = False
            self.temporary_consumed = True
        except BaseException as exc:
            if descriptor >= 0:
                os.close(descriptor)
                descriptor = -1
            if temporary is not None and not exchanged:
                try:
                    if previous_identity is None:
                        raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                    remove_owned_regular(
                        temporary,
                        parent_identity=self.parent_identity,
                        parent_mode=self.parent_mode,
                        identity=previous_identity,
                        sha256=self.previous_token.sha256,
                        reason_code="TRANSACTION_ROLLBACK_FAILED",
                    )
                except BaseException as cleanup_error:
                    raise RegistryError(
                        "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                    ) from cleanup_error
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def cleanup(self) -> None:
        if self.cleanup_blocked:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
        if self.temporary_consumed:
            self.require_consumed_temporary_absent()
            return
        if self.exchange_active:
            if not self.committed or self.previous_token is None:
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            remove_owned_regular(
                self.temporary,
                parent_identity=self.parent_identity,
                parent_mode=self.parent_mode,
                identity=self.previous_token.identity,
                sha256=str(self.previous_token.sha256),
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            self.temporary_consumed = True
            self.exchange_active = False
            self.displaced_token = None
            self.require_consumed_temporary_absent()
            return
        remove_owned_regular(
            self.temporary,
            parent_identity=self.parent_identity,
            parent_mode=self.parent_mode,
            identity=self.new_identity,
            sha256=self.new_sha256,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        self.temporary_consumed = True
        self.require_consumed_temporary_absent()


class RegistryError(Exception):
    def __init__(self, reason_code: str, *, exit_code: int = 2) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.exit_code = exit_code


def require_registry_root_guard(guard: RegistryRootGuard) -> None:
    probe = -1
    try:
        before = guard.path.lstat()
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        probe = os.open(guard.path, flags)
        opened = os.fstat(probe)
        locked = os.fstat(guard.descriptor)
        after = guard.path.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(locked.st_mode)
            or not stat.S_ISDIR(after.st_mode)
            or stat.S_ISLNK(after.st_mode)
            or (before.st_dev, before.st_ino) != guard.identity
            or (opened.st_dev, opened.st_ino) != guard.identity
            or (locked.st_dev, locked.st_ino) != guard.identity
            or (after.st_dev, after.st_ino) != guard.identity
        ):
            raise RegistryError("REGISTRY_LOCK_UNAVAILABLE")
        if any(
            stat.S_IMODE(metadata.st_mode) != guard.mode
            for metadata in (before, opened, locked, after)
        ):
            raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
    except (OSError, RegistryError) as exc:
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError("REGISTRY_LOCK_UNAVAILABLE") from exc
    finally:
        if probe >= 0:
            os.close(probe)


def require_active_registry_root_for_path(path: Path) -> None:
    guard = _ACTIVE_REGISTRY_ROOT_GUARD
    if guard is None:
        return
    absolute = path.absolute()
    if absolute == guard.path or guard.path in absolute.parents:
        require_registry_root_guard(guard)


@contextmanager
def owned_directory_descriptor(
    path: Path,
    identity: tuple[int, int],
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
) -> Iterable[int]:
    descriptor = -1
    try:
        require_active_registry_root_for_path(path)
        before = path.lstat()
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        after = path.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(after.st_mode)
            or stat.S_ISLNK(after.st_mode)
            or (before.st_dev, before.st_ino) != identity
            or (opened.st_dev, opened.st_ino) != identity
            or (after.st_dev, after.st_ino) != identity
            or (
                expected_mode is not None
                and (
                    stat.S_IMODE(before.st_mode) != expected_mode
                    or stat.S_IMODE(opened.st_mode) != expected_mode
                    or stat.S_IMODE(after.st_mode) != expected_mode
                )
            )
        ):
            raise RegistryError(reason_code, exit_code=3)
        require_active_registry_root_for_path(path)
        yield descriptor
        final = path.lstat()
        if (
            not stat.S_ISDIR(final.st_mode)
            or stat.S_ISLNK(final.st_mode)
            or (final.st_dev, final.st_ino) != identity
            or (
                expected_mode is not None
                and stat.S_IMODE(final.st_mode) != expected_mode
            )
        ):
            raise RegistryError(reason_code, exit_code=3)
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError(reason_code, exit_code=3) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def owned_regular_capture(
    path: Path,
    *,
    parent_descriptor: int,
    identity: tuple[int, int],
    sha256: str,
    reason_code: str,
    expected_mode: int = REGISTRY_FILE_MODE,
) -> None:
    descriptor = -1
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or stat.S_IMODE(before.st_mode) != expected_mode
            or stat.S_IMODE(after.st_mode) != expected_mode
            or stat.S_IMODE(current.st_mode) != expected_mode
            or any(
                getattr(before, field) != getattr(after, field)
                for field in stable_fields
            )
            or any(
                getattr(after, field) != getattr(current, field)
                for field in stable_fields
            )
            or (current.st_dev, current.st_ino) != identity
            or hashlib.sha256(b"".join(chunks)).hexdigest() != sha256
        ):
            raise RegistryError(reason_code, exit_code=3)
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError(reason_code, exit_code=3) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def capture_node_token_at(
    name: str,
    *,
    parent_descriptor: int,
    reason_code: str,
) -> NodeToken:
    descriptor = -1
    try:
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = (before.st_dev, before.st_ino)
        mode = stat.S_IMODE(before.st_mode)
        if stat.S_ISREG(before.st_mode):
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(name, flags, dir_fd=parent_descriptor)
            opened_before = os.fstat(descriptor)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            opened_after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            stable_fields = (
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if (
                not stat.S_ISREG(opened_before.st_mode)
                or not stat.S_ISREG(opened_after.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or stat.S_IMODE(opened_before.st_mode) != mode
                or stat.S_IMODE(opened_after.st_mode) != mode
                or stat.S_IMODE(current.st_mode) != mode
                or any(
                    getattr(opened_before, field) != getattr(opened_after, field)
                    for field in stable_fields
                )
                or any(
                    getattr(opened_after, field) != getattr(current, field)
                    for field in stable_fields
                )
                or (current.st_dev, current.st_ino) != identity
            ):
                raise RegistryError(reason_code, exit_code=3)
            return NodeToken(
                kind="file",
                identity=identity,
                mode=mode,
                sha256=hashlib.sha256(b"".join(chunks)).hexdigest(),
            )
        if stat.S_ISLNK(before.st_mode):
            target = os.readlink(name, dir_fd=parent_descriptor)
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if (
                not stat.S_ISLNK(current.st_mode)
                or (current.st_dev, current.st_ino) != identity
            ):
                raise RegistryError(reason_code, exit_code=3)
            return NodeToken(
                kind="symlink",
                identity=identity,
                mode=mode,
                link_target=target,
            )
        if stat.S_ISDIR(before.st_mode):
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(name, flags, dir_fd=parent_descriptor)
            opened = os.fstat(descriptor)
            children = tuple(sorted(os.listdir(descriptor)))
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(current.st_mode)
                or stat.S_IMODE(opened.st_mode) != mode
                or stat.S_IMODE(current.st_mode) != mode
                or (opened.st_dev, opened.st_ino) != identity
                or (current.st_dev, current.st_ino) != identity
            ):
                raise RegistryError(reason_code, exit_code=3)
            return NodeToken(
                kind="directory",
                identity=identity,
                mode=mode,
                children=children,
            )
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != identity:
            raise RegistryError(reason_code, exit_code=3)
        return NodeToken(kind="other", identity=identity, mode=mode)
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError(reason_code, exit_code=3) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def require_node_token(
    path: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int],
    token: NodeToken,
    reason_code: str,
) -> None:
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        if (
            capture_node_token_at(
                path.name,
                parent_descriptor=parent,
                reason_code=reason_code,
            )
            != token
        ):
            raise RegistryError(reason_code, exit_code=3)


def capture_node_token(
    path: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int],
    reason_code: str,
) -> NodeToken:
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        return capture_node_token_at(
            path.name,
            parent_descriptor=parent,
            reason_code=reason_code,
        )


def exchange_owned_paths(
    left: Path,
    right: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int],
    reason_code: str,
) -> None:
    if left.parent != right.parent:
        raise RegistryError(reason_code, exit_code=3)
    with owned_directory_descriptor(
        left.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        library = ctypes.CDLL(None, use_errno=True)
        left_name = os.fsencode(left.name)
        right_name = os.fsencode(right.name)
        if sys.platform == "darwin" and hasattr(library, "renameatx_np"):
            rename = library.renameatx_np
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(parent, left_name, parent, right_name, 0x00000002)
        elif hasattr(library, "renameat2"):
            rename = library.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(parent, left_name, parent, right_name, 0x00000002)
        else:
            raise RegistryError(reason_code, exit_code=3)
        if result != 0:
            observed_errno = ctypes.get_errno()
            raise RegistryError(reason_code, exit_code=3) from OSError(
                observed_errno,
                os.strerror(observed_errno),
            )


def rename_owned_path_noreplace(
    source: Path,
    destination: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int],
    reason_code: str,
) -> None:
    if source.parent != destination.parent:
        raise RegistryError(reason_code, exit_code=3)
    with owned_directory_descriptor(
        source.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        library = ctypes.CDLL(None, use_errno=True)
        source_name = os.fsencode(source.name)
        destination_name = os.fsencode(destination.name)
        if sys.platform == "darwin" and hasattr(library, "renameatx_np"):
            rename = library.renameatx_np
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(parent, source_name, parent, destination_name, 0x00000004)
        elif hasattr(library, "renameat2"):
            rename = library.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(parent, source_name, parent, destination_name, 0x00000001)
        else:
            raise RegistryError(reason_code, exit_code=3)
        if result != 0:
            observed_errno = ctypes.get_errno()
            raise RegistryError(reason_code, exit_code=3) from OSError(
                observed_errno,
                os.strerror(observed_errno),
            )


def link_owned_path_noreplace(
    source: Path,
    destination: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int],
    reason_code: str,
) -> None:
    if source.parent != destination.parent:
        raise RegistryError(reason_code, exit_code=3)
    link_error: Optional[OSError] = None
    with owned_directory_descriptor(
        source.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        try:
            os.link(
                source.name,
                destination.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except OSError as exc:
            link_error = exc
    if link_error is not None:
        raise link_error


def create_owned_staging_file(
    parent_path: Path,
    *,
    prefix: str,
    suffix: str,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int],
    reason_code: str,
) -> tuple[int, Path, tuple[int, int]]:
    if (
        not prefix
        or Path(prefix).name != prefix
        or Path(suffix).name != suffix
        or "/" in prefix
        or "/" in suffix
    ):
        raise RegistryError(reason_code, exit_code=3)
    descriptor = -1
    temporary: Optional[Path] = None
    staged_identity: Optional[tuple[int, int]] = None
    try:
        with owned_directory_descriptor(
            parent_path,
            parent_identity,
            reason_code,
            expected_mode=parent_mode,
        ) as parent:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            for _ in range(16):
                name = "{}{}{}".format(prefix, secrets.token_hex(16), suffix)
                try:
                    descriptor = os.open(
                        name,
                        flags,
                        REGISTRY_FILE_MODE,
                        dir_fd=parent,
                    )
                except FileExistsError:
                    continue
                temporary = parent_path / name
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise RegistryError(reason_code, exit_code=3)
                os.fchmod(descriptor, REGISTRY_FILE_MODE)
                metadata = os.fstat(descriptor)
                if stat.S_IMODE(metadata.st_mode) != REGISTRY_FILE_MODE:
                    raise RegistryError(reason_code, exit_code=3)
                staged_identity = (metadata.st_dev, metadata.st_ino)
                return descriptor, temporary, staged_identity
        raise RegistryError(reason_code, exit_code=3)
    except BaseException as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None and staged_identity is not None:
            try:
                remove_owned_regular(
                    temporary,
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                    identity=staged_identity,
                    sha256=hashlib.sha256(b"").hexdigest(),
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
            except BaseException as cleanup_error:
                raise RegistryError(
                    "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                ) from cleanup_error
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError(reason_code, exit_code=3) from exc


def require_owned_regular(
    path: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int] = None,
    identity: tuple[int, int],
    sha256: str,
    reason_code: str,
    expected_mode: int = REGISTRY_FILE_MODE,
) -> None:
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        owned_regular_capture(
            path,
            parent_descriptor=parent,
            identity=identity,
            sha256=sha256,
            reason_code=reason_code,
            expected_mode=expected_mode,
        )


def require_owned_absence(
    path: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int] = None,
    reason_code: str,
) -> None:
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as parent:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise RegistryError(reason_code, exit_code=3)


def remove_owned_regular(
    path: Path,
    *,
    parent_identity: tuple[int, int],
    parent_mode: Optional[int] = None,
    identity: tuple[int, int],
    sha256: str,
    reason_code: str,
) -> None:
    expected = NodeToken(
        kind="file",
        identity=identity,
        mode=REGISTRY_FILE_MODE,
        sha256=sha256,
    )
    tombstone: Optional[Path] = None
    for _ in range(16):
        candidate = path.with_name(".pickup-remove-{}".format(secrets.token_hex(16)))
        if candidate.exists() or candidate.is_symlink():
            continue
        try:
            rename_owned_path_noreplace(
                path,
                candidate,
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                reason_code=reason_code,
            )
        except RegistryError as exc:
            if candidate.exists() or candidate.is_symlink():
                continue
            raise exc
        tombstone = candidate
        break
    if tombstone is None:
        raise RegistryError(reason_code, exit_code=3)
    try:
        observed = capture_node_token(
            tombstone,
            parent_identity=parent_identity,
            parent_mode=parent_mode,
            reason_code=reason_code,
        )
        if observed != expected:
            rename_owned_path_noreplace(
                tombstone,
                path,
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                reason_code=reason_code,
            )
            raise RegistryError(reason_code, exit_code=3)
        with owned_directory_descriptor(
            tombstone.parent,
            parent_identity,
            reason_code,
            expected_mode=parent_mode,
        ) as parent:
            owned_regular_capture(
                tombstone,
                parent_descriptor=parent,
                identity=identity,
                sha256=sha256,
                reason_code=reason_code,
            )
            # All pickup writers hold the registry-root lock.  Within that
            # cooperative boundary, this private random name cannot be replaced
            # between its final identity check and descriptor-relative removal.
            os.unlink(tombstone.name, dir_fd=parent)
            os.fsync(parent)
    except BaseException as exc:
        restore_error: Optional[BaseException] = None
        try:
            if tombstone is not None and (tombstone.exists() or tombstone.is_symlink()):
                if (
                    capture_node_token(
                        tombstone,
                        parent_identity=parent_identity,
                        parent_mode=parent_mode,
                        reason_code=reason_code,
                    )
                    != expected
                ):
                    raise RegistryError(reason_code, exit_code=3)
                rename_owned_path_noreplace(
                    tombstone,
                    path,
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                    reason_code=reason_code,
                )
        except BaseException as observed_restore_error:
            restore_error = observed_restore_error
        if restore_error is not None:
            raise RegistryError(reason_code, exit_code=3) from restore_error
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError(reason_code, exit_code=3) from exc


def sync_owned_directory(
    path: Path,
    identity: tuple[int, int],
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
    sync_reason_code: str = "DIRECTORY_SYNC_FAILED",
) -> None:
    with owned_directory_descriptor(
        path,
        identity,
        reason_code,
        expected_mode=expected_mode,
    ) as descriptor:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            raise RegistryError(
                sync_reason_code,
                exit_code=(
                    3 if sync_reason_code == "TRANSACTION_ROLLBACK_FAILED" else 2
                ),
            ) from exc


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def require_rfc3339(value: Any, reason_code: str) -> str:
    if not isinstance(value, str):
        raise RegistryError(reason_code)
    match = RFC3339_RE.fullmatch(value)
    if match is None:
        raise RegistryError(reason_code)
    try:
        datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError as exc:
        raise RegistryError(reason_code) from exc
    return value


def exact_integer(value: Any, expected: Optional[int] = None) -> bool:
    return type(value) is int and (expected is None or value == expected)


def optional_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def bounded_printable_string(value: Any, maximum_length: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= maximum_length
        and value.isprintable()
    )


def optional_bounded_printable_string(value: Any, maximum_length: int) -> bool:
    return value is None or bounded_printable_string(value, maximum_length)


def reject_json_constant(value: str) -> None:
    raise ValueError("non-standard JSON constant: {}".format(value))


def unique_json_object(pairs: list[tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object member")
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        parse_constant=reject_json_constant,
        object_pairs_hook=unique_json_object,
    )


def stable_regular_capture(
    path: Path,
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RegistryError(reason_code) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RegistryError(reason_code)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise RegistryError(reason_code) from exc
    finally:
        os.close(descriptor)
    try:
        current = path.lstat()
    except OSError as exc:
        raise RegistryError(reason_code) from exc
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        not stat.S_ISREG(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or stat.S_IMODE(before.st_mode) != stat.S_IMODE(after.st_mode)
        or stat.S_IMODE(after.st_mode) != stat.S_IMODE(current.st_mode)
        or any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        )
        or any(
            getattr(after, field) != getattr(current, field) for field in stable_fields
        )
    ):
        raise RegistryError(reason_code)
    if expected_mode is not None and (
        stat.S_IMODE(before.st_mode) != expected_mode
        or stat.S_IMODE(after.st_mode) != expected_mode
        or stat.S_IMODE(current.st_mode) != expected_mode
    ):
        raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
    return b"".join(chunks), current


def stable_regular_bytes(
    path: Path,
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
) -> bytes:
    return stable_regular_capture(
        path,
        reason_code,
        expected_mode=expected_mode,
    )[0]


def sha256_file(
    path: Path,
    reason_code: str = "FILE_READ_FAILED",
    *,
    expected_mode: Optional[int] = None,
) -> str:
    return hashlib.sha256(
        stable_regular_bytes(path, reason_code, expected_mode=expected_mode)
    ).hexdigest()


def serialized_json(payload: Dict[str, Any]) -> bytes:
    try:
        data = (
            json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if not isinstance(strict_json_loads(data.decode("utf-8")), dict):
            raise RegistryError("SERIALIZED_JSON_INVALID")
    except (TypeError, ValueError) as exc:
        raise RegistryError("SERIALIZED_JSON_INVALID") from exc
    return data


def regular_file(path: Path, reason_code: str) -> Path:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
        current = path.lstat()
        resolved_metadata = resolved.lstat()
    except OSError as exc:
        raise RegistryError(reason_code) from exc
    identity = (metadata.st_dev, metadata.st_ino)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (current.st_dev, current.st_ino) != identity
        or (resolved_metadata.st_dev, resolved_metadata.st_ino) != identity
    ):
        raise RegistryError(reason_code)
    return resolved


def canonical_absolute_path_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        path = Path(value)
        return path.is_absolute() and value == str(path.resolve())
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def capture_owned_directory(path: Path, reason_code: str) -> OwnedDirectory:
    try:
        parent = path.parent.lstat()
    except OSError as exc:
        raise RegistryError(reason_code, exit_code=3) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise RegistryError(reason_code, exit_code=3)
    parent_identity = (parent.st_dev, parent.st_ino)
    parent_mode = stat.S_IMODE(parent.st_mode)
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        reason_code,
        expected_mode=parent_mode,
    ) as descriptor:
        token = capture_node_token_at(
            path.name,
            parent_descriptor=descriptor,
            reason_code=reason_code,
        )
    if token.kind != "directory":
        raise RegistryError(reason_code, exit_code=3)
    return OwnedDirectory(
        path=path,
        identity=token.identity,
        mode=token.mode,
        parent_identity=parent_identity,
        parent_mode=parent_mode,
    )


def create_owned_temporary_directory(
    parent_path: Path,
    prefix: str,
    reason_code: str,
) -> OwnedDirectory:
    if not prefix or Path(prefix).name != prefix:
        raise RegistryError(reason_code, exit_code=3)
    try:
        parent = parent_path.lstat()
    except OSError as exc:
        raise RegistryError(reason_code, exit_code=3) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise RegistryError(reason_code, exit_code=3)
    parent_identity = (parent.st_dev, parent.st_ino)
    parent_mode = stat.S_IMODE(parent.st_mode)
    ownership: Optional[OwnedDirectory] = None
    try:
        with owned_directory_descriptor(
            parent_path,
            parent_identity,
            reason_code,
            expected_mode=parent_mode,
        ) as parent_descriptor:
            for _ in range(16):
                name = "{}{}".format(prefix, secrets.token_hex(16))
                try:
                    os.mkdir(
                        name,
                        mode=REGISTRY_DIRECTORY_MODE,
                        dir_fd=parent_descriptor,
                    )
                except FileExistsError:
                    continue
                current = os.stat(
                    name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode):
                    raise RegistryError(reason_code, exit_code=3)
                ownership = OwnedDirectory(
                    path=parent_path / name,
                    identity=(current.st_dev, current.st_ino),
                    mode=stat.S_IMODE(current.st_mode),
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                )
                token = capture_node_token_at(
                    name,
                    parent_descriptor=parent_descriptor,
                    reason_code=reason_code,
                )
                if (
                    token.kind != "directory"
                    or token.mode != REGISTRY_DIRECTORY_MODE
                    or token.children
                ):
                    raise RegistryError(reason_code, exit_code=3)
                if token.identity != ownership.identity:
                    raise RegistryError(reason_code, exit_code=3)
                os.fsync(parent_descriptor)
                break
        if ownership is None:
            raise RegistryError(reason_code, exit_code=3)
        return ownership
    except BaseException as exc:
        if ownership is not None:
            try:
                remove_owned_empty_directories((ownership,))
            except BaseException as rollback_error:
                raise RegistryError(
                    "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                ) from rollback_error
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError(reason_code, exit_code=3) from exc


def capture_directory_expectation(path: Path, reason_code: str) -> DirectoryExpectation:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return DirectoryExpectation(existed=False, identity=None, mode=None)
    except OSError as exc:
        raise RegistryError(reason_code, exit_code=3) from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RegistryError(reason_code, exit_code=3)
    return DirectoryExpectation(
        existed=True,
        identity=(metadata.st_dev, metadata.st_ino),
        mode=stat.S_IMODE(metadata.st_mode),
    )


def secure_directory(
    path: Path,
    *,
    expectation: Optional[DirectoryExpectation] = None,
    reason_code: str = "REGISTRY_ROOT_INVALID",
) -> Optional[OwnedDirectory]:
    if expectation is None:
        expectation = capture_directory_expectation(path, reason_code)
    created = False
    child_descriptor = -1
    created_identity: Optional[tuple[int, int]] = None
    created_mode: Optional[int] = None
    try:
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
            raise RegistryError("REGISTRY_ROOT_UNAVAILABLE")
        parent_identity = (parent.st_dev, parent.st_ino)
        parent_mode = stat.S_IMODE(parent.st_mode)
        with owned_directory_descriptor(
            path.parent,
            parent_identity,
            "REGISTRY_ROOT_UNAVAILABLE",
            expected_mode=parent_mode,
        ) as parent_descriptor:
            try:
                initial = os.stat(
                    path.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                if expectation.existed:
                    raise RegistryError(reason_code, exit_code=3)
                try:
                    os.mkdir(
                        path.name,
                        mode=REGISTRY_DIRECTORY_MODE,
                        dir_fd=parent_descriptor,
                    )
                except FileExistsError as exc:
                    raise RegistryError(reason_code, exit_code=3) from exc
                created = True
            else:
                if (
                    not expectation.existed
                    or expectation.identity != (initial.st_dev, initial.st_ino)
                    or expectation.mode != stat.S_IMODE(initial.st_mode)
                ):
                    raise RegistryError(reason_code, exit_code=3)
            current = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode):
                raise RegistryError("REGISTRY_ROOT_INVALID")
            if created:
                created_identity = (current.st_dev, current.st_ino)
                created_mode = stat.S_IMODE(current.st_mode)
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            child_descriptor = os.open(
                path.name,
                flags,
                dir_fd=parent_descriptor,
            )
            opened = os.fstat(child_descriptor)
            if not stat.S_ISDIR(opened.st_mode) or (current.st_dev, current.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise RegistryError("REGISTRY_ROOT_INVALID")
            if created:
                os.fchmod(child_descriptor, REGISTRY_DIRECTORY_MODE)
                opened = os.fstat(child_descriptor)
            elif stat.S_IMODE(opened.st_mode) != REGISTRY_DIRECTORY_MODE:
                raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
            final = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(final.st_mode)
                or stat.S_ISLNK(final.st_mode)
                or (final.st_dev, final.st_ino) != (opened.st_dev, opened.st_ino)
                or stat.S_IMODE(final.st_mode) != REGISTRY_DIRECTORY_MODE
            ):
                raise RegistryError("REGISTRY_ROOT_INVALID")
            created_identity = (opened.st_dev, opened.st_ino)
            created_mode = stat.S_IMODE(opened.st_mode)
            if created:
                os.fsync(parent_descriptor)
        if not created:
            return None
        if created_identity is None or created_mode is None:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
        return OwnedDirectory(
            path=path,
            identity=created_identity,
            mode=created_mode,
            parent_identity=parent_identity,
            parent_mode=parent_mode,
        )
    except BaseException as exc:
        if created and created_identity is not None and created_mode is not None:
            try:
                remove_owned_empty_directories(
                    (
                        OwnedDirectory(
                            path=path,
                            identity=created_identity,
                            mode=created_mode,
                            parent_identity=parent_identity,
                            parent_mode=parent_mode,
                        ),
                    )
                )
            except BaseException as rollback_error:
                raise RegistryError(
                    "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                ) from rollback_error
        if isinstance(exc, RegistryError):
            if exc.reason_code == "REGISTRY_ROOT_UNAVAILABLE" and isinstance(
                exc.__cause__, OSError
            ):
                raise RegistryError("REGISTRY_ROOT_UNAVAILABLE") from exc
            raise
        raise RegistryError("REGISTRY_ROOT_UNAVAILABLE") from exc
    finally:
        if child_descriptor >= 0:
            os.close(child_descriptor)


def existing_directory(path: Path, reason_code: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RegistryError(reason_code) from exc
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RegistryError(reason_code)


def require_mode(path: Path, expected: int) -> None:
    try:
        observed = stat.S_IMODE(path.lstat().st_mode)
    except OSError as exc:
        raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3) from exc
    if observed != expected:
        raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)


def read_json_object(
    path: Path,
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
) -> Dict[str, Any]:
    data = read_regular_bytes(path, reason_code, expected_mode=expected_mode)
    return json_object_from_bytes(data, reason_code)


def read_hashed_json_object(
    path: Path,
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
) -> tuple[Dict[str, Any], str]:
    data = read_regular_bytes(path, reason_code, expected_mode=expected_mode)
    return json_object_from_bytes(data, reason_code), hashlib.sha256(data).hexdigest()


def read_regular_bytes(
    path: Path,
    reason_code: str,
    *,
    expected_mode: Optional[int] = None,
) -> bytes:
    return stable_regular_bytes(path, reason_code, expected_mode=expected_mode)


def capture_mutable_destination(
    path: Path,
    *,
    parent_reason_code: str,
    invalid_reason_code: str,
) -> MutableDestination:
    try:
        existing_directory(path.parent, parent_reason_code)
        if not path.exists() and not path.is_symlink():
            return MutableDestination(existed=False, identity=None, sha256=None)
        data, metadata = stable_regular_capture(
            path,
            invalid_reason_code,
            expected_mode=REGISTRY_FILE_MODE,
        )
    except (OSError, RegistryError) as exc:
        raise RegistryError(invalid_reason_code, exit_code=3) from exc
    return MutableDestination(
        existed=True,
        identity=(metadata.st_dev, metadata.st_ino),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def json_object_from_bytes(data: bytes, reason_code: str) -> Dict[str, Any]:
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RegistryError(reason_code) from exc
    if not isinstance(value, dict):
        raise RegistryError(reason_code)
    return value


def preflight_compatibility_output(path: Path) -> MutableDestination:
    existing_directory(path.parent, "COMPATIBILITY_OUTPUT_PARENT_UNAVAILABLE")
    destination = capture_mutable_destination(
        path,
        parent_reason_code="COMPATIBILITY_OUTPUT_PARENT_UNAVAILABLE",
        invalid_reason_code="COMPATIBILITY_OUTPUT_INVALID",
    )
    if not destination.existed:
        return destination
    try:
        data, metadata = stable_regular_capture(path, "COMPATIBILITY_OUTPUT_INVALID")
        if (
            destination.identity != (metadata.st_dev, metadata.st_ino)
            or destination.sha256 != hashlib.sha256(data).hexdigest()
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        payload = json_object_from_bytes(data, "COMPATIBILITY_OUTPUT_INVALID")
        validate_existing_compatibility(payload, path)
    except RegistryError as exc:
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3) from exc
    return destination


def legacy_v3_clean_text(
    value: Any,
    *,
    maximum_length: int,
    allow_none: bool = True,
) -> bool:
    if value is None:
        return allow_none
    if not isinstance(value, str):
        return False
    cleaned = value.strip()
    if not cleaned:
        return allow_none
    return len(cleaned) <= maximum_length and not any(
        ord(character) < 32 or ord(character) == 127 for character in cleaned
    )


def legacy_v3_timestamp(value: Any, *, allow_none: bool = False) -> bool:
    if value is None:
        return allow_none
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def legacy_v3_forbidden_keys(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"session_id", "thread_id", "window_title"}:
                found.append(key)
            found.extend(legacy_v3_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(legacy_v3_forbidden_keys(child))
    return found


def validate_legacy_v3_compatibility(payload: Dict[str, Any], path: Path) -> None:
    invocation = payload.get("invocation")
    scope = payload.get("scope")
    artifacts = payload.get("artifacts")
    validation = payload.get("validation")
    status = payload.get("status")
    terminal = payload.get("terminal")
    drift = payload.get("drift")
    if (
        not exact_integer(payload.get("schema_version"), 3)
        or legacy_v3_forbidden_keys(payload)
        or not isinstance(payload.get("receipt_id"), str)
        or RECEIPT_ID_RE.fullmatch(payload["receipt_id"]) is None
        or status not in {"VERIFYING", *(value.value for value in TerminalStatus)}
        or type(terminal) is not bool
        or (status == "VERIFYING") == terminal
        or drift not in {value.value for value in DriftClass}
        or payload.get("last_completed_gate") not in GATES
        or not isinstance(payload.get("workspace"), str)
        or not Path(payload["workspace"]).is_absolute()
        or not legacy_v3_clean_text(
            payload.get("workspace"), maximum_length=1024, allow_none=False
        )
        or not isinstance(invocation, dict)
        or invocation.get("fresh_task") not in {"YES", "NO", "UNKNOWN"}
        or invocation.get("freshness_basis")
        not in {"FIRST_SUBSTANTIVE_USER_TURN", "PRIOR_TASK_CONTENT", "UNVERIFIED"}
        or invocation.get("mode") not in {"MANUAL_SKILL_SELECTOR", "SLASH_COMMAND"}
        or not legacy_v3_clean_text(
            invocation.get("model"), maximum_length=80, allow_none=False
        )
        or not legacy_v3_clean_text(
            invocation.get("reasoning_effort"),
            maximum_length=40,
            allow_none=False,
        )
        or not isinstance(scope, dict)
        or scope.get("operation") != "READ_VERIFY_RECONSTRUCT"
        or scope.get("phase_authorized") is not False
        or scope.get("allowed_writes") != [str(path)]
        or not isinstance(artifacts, dict)
        or set(artifacts) != {"skill", "handoff", "checkpoint"}
        or not isinstance(validation, dict)
        or validation.get("json") is not True
        or validation.get("secret_scan")
        not in {"PASS", "PENDING", "NOT_AVAILABLE", "NOT_RUN", "FAIL"}
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    for name, record in artifacts.items():
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("path"), str)
            or not Path(record["path"]).is_absolute()
            or not legacy_v3_clean_text(
                record.get("path"), maximum_length=2048, allow_none=False
            )
            or type(record.get("present")) is not bool
            or type(record.get("regular_file")) is not bool
            or not valid_sha256_or_none(record.get("sha256"))
            or (
                name == "checkpoint"
                and record.get("schema_version") is not None
                and not isinstance(record.get("schema_version"), int)
            )
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    if not all(
        legacy_v3_timestamp(value, allow_none=allow_none)
        for value, allow_none in (
            (payload.get("started_at"), False),
            (payload.get("updated_at"), False),
            (payload.get("completed_at"), True),
        )
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    checkpoint_generated_at = payload.get("checkpoint_generated_at")
    if checkpoint_generated_at is not None and not legacy_v3_timestamp(
        checkpoint_generated_at
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    if not all(
        legacy_v3_clean_text(payload.get(field), maximum_length=200)
        for field in (
            "checkpoint_generated_at",
            "current_phase",
            "next_phase",
            "reason",
        )
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    reason_code = payload.get("reason_code")
    if reason_code is not None and (
        not isinstance(reason_code, str)
        or re.fullmatch(r"[A-Z0-9_]{1,80}", reason_code) is None
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    if status == "VERIFYING":
        if (
            payload.get("completed_at") is not None
            or drift != DriftClass.UNKNOWN.value
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        return
    if not isinstance(payload.get("completed_at"), str):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    try:
        terminal_status = TerminalStatus(status)
        drift_class = DriftClass(drift)
    except ValueError as exc:
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3) from exc
    if drift_class not in TERMINAL_DRIFT_POLICY[terminal_status]:
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
    if terminal_status is TerminalStatus.READY and (
        payload.get("last_completed_gate") != Gate.TELEMETRY_VALIDATED.value
        or validation.get("secret_scan") not in {"PASS", "NOT_AVAILABLE", "PENDING"}
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)


def validate_existing_compatibility(payload: Dict[str, Any], path: Path) -> None:
    schema_version = payload.get("schema_version")
    if exact_integer(schema_version, RECEIPT_SCHEMA_VERSION):
        validate_mutable_payload(MutableWrite(path=path, payload=payload))
        receipt = dict(payload)
        receipt.pop("compatibility_summary")
        receipt.pop("receipt_sha256")
        pickup = receipt.get("pickup")
        artifacts = receipt.get("artifacts")
        if not isinstance(pickup, dict) or not isinstance(artifacts, dict):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        coordinate = PackageCoordinate(
            track_id=str(pickup.get("track_id", "")),
            checkpoint_id=str(pickup.get("checkpoint_id", "")),
        )
        package_record = artifacts.get("package")
        handoff_record = artifacts.get("handoff")
        checkpoint_record = artifacts.get("checkpoint")
        if not all(
            isinstance(record, dict)
            for record in (package_record, handoff_record, checkpoint_record)
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)

        def expected_artifact_hash(record: Dict[str, Any]) -> Any:
            if frozenset(record) == DRIFT_ARTIFACT_KEYS:
                return record.get("expected_sha256")
            return record.get("sha256")

        validate_receipt_bindings(
            registry_root=path.parent / "pickups",
            coordinate=coordinate,
            package_entry={
                "package_sha256": expected_artifact_hash(package_record),
                "handoff_sha256": expected_artifact_hash(handoff_record),
                "checkpoint_sha256": expected_artifact_hash(checkpoint_record),
            },
            package_manifest=None,
            receipt=receipt,
        )
        return
    if exact_integer(schema_version, 2):
        return
    if exact_integer(schema_version, 3):
        validate_legacy_v3_compatibility(payload, path)
        return
    raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)


def validate_compatibility_registry_event(
    *,
    path: Path,
    destination: MutableDestination,
    registry_root: Path,
    index: Dict[str, Any],
) -> None:
    if not destination.existed:
        return
    try:
        data, metadata = stable_regular_capture(
            path,
            "COMPATIBILITY_OUTPUT_INVALID",
            expected_mode=REGISTRY_FILE_MODE,
        )
        if (
            destination.identity != (metadata.st_dev, metadata.st_ino)
            or destination.sha256 != hashlib.sha256(data).hexdigest()
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        payload = json_object_from_bytes(data, "COMPATIBILITY_OUTPUT_INVALID")
        if not exact_integer(payload.get("schema_version"), RECEIPT_SCHEMA_VERSION):
            return
        validate_existing_compatibility(payload, path)
        receipt = dict(payload)
        receipt_hash = receipt.pop("receipt_sha256")
        receipt.pop("compatibility_summary")
        receipt_id = receipt.get("receipt_id")
        revision = receipt.get("revision")
        pickup = receipt.get("pickup")
        if (
            not isinstance(receipt_id, str)
            or not exact_integer(revision)
            or not isinstance(pickup, dict)
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        track_id = pickup.get("track_id")
        checkpoint_id = pickup.get("checkpoint_id")
        if not isinstance(track_id, str) or not isinstance(checkpoint_id, str):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        receipts = index.get("receipts")
        tracks = index.get("tracks")
        if not isinstance(receipts, dict) or not isinstance(tracks, dict):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        entry = receipts.get(receipt_id)
        track = tracks.get(track_id)
        if not isinstance(entry, dict) or not isinstance(track, dict):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        package_entry = package_entry_for(track, checkpoint_id)
        receipt_path = (
            registry_root
            / "tracks"
            / track_id
            / "receipts"
            / "{}-r{:04d}.json".format(receipt_id, revision)
        )
        if (
            entry.get("track_id") != track_id
            or entry.get("checkpoint_id") != checkpoint_id
            or entry.get("latest_revision") != revision
            or entry.get("latest_receipt_sha256") != receipt_hash
            or entry.get("latest_receipt_path") != str(receipt_path)
        ):
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        stored, stored_hash = read_hashed_json_object(
            receipt_path,
            "COMPATIBILITY_OUTPUT_INVALID",
            expected_mode=REGISTRY_FILE_MODE,
        )
        if stored != receipt or stored_hash != receipt_hash:
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)
        validate_receipt_bindings(
            registry_root=registry_root,
            coordinate=PackageCoordinate(track_id, checkpoint_id),
            package_entry=package_entry,
            package_manifest=None,
            receipt=receipt,
        )
    except RegistryError as exc:
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3) from exc


def registry_invocation_bindings(registry_root: Path) -> tuple[Path, Path]:
    resolved_registry = registry_root.resolve()
    workspace = resolved_registry.parent.parent
    compatibility_output = (
        workspace / "treasurepickup" / "context-resume.json"
    )
    return workspace, compatibility_output


def deployed_skill_file() -> Path:
    return Path(__file__).resolve().parents[1] / "SKILL.md"


def validate_invocation_bindings(
    *,
    registry_root: Path,
    compatibility_output: Path,
    invocation: InvocationContext,
) -> None:
    expected_workspace, expected_compatibility = registry_invocation_bindings(
        registry_root
    )
    if (
        invocation.workspace != expected_workspace
        or invocation.workspace.resolve() != expected_workspace
    ):
        raise RegistryError("WORKSPACE_INVALID")
    validate_compatibility_binding(registry_root, compatibility_output)


def validate_compatibility_binding(
    registry_root: Path, compatibility_output: Path
) -> None:
    _, expected_compatibility = registry_invocation_bindings(registry_root)
    if (
        compatibility_output != expected_compatibility
        or compatibility_output.resolve() != expected_compatibility
    ):
        raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3)


def validate_registry_root_path(registry_root: Path) -> None:
    try:
        if not registry_root.is_absolute() or registry_root != registry_root.resolve():
            raise RegistryError("REGISTRY_ROOT_INVALID")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise RegistryError("REGISTRY_ROOT_INVALID") from exc


@contextmanager
def registry_lock(registry_root: Path, *, create: bool = True) -> Iterable[None]:
    global _ACTIVE_REGISTRY_ROOT_GUARD
    validate_registry_root_path(registry_root)
    if create:
        secure_directory(registry_root)
    else:
        existing_directory(registry_root, "REGISTRY_ROOT_UNAVAILABLE")
    try:
        before = registry_root.lstat()
    except OSError as exc:
        raise RegistryError("REGISTRY_LOCK_UNAVAILABLE") from exc
    identity = (before.st_dev, before.st_ino)
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise RegistryError("REGISTRY_LOCK_UNAVAILABLE")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(registry_root, flags)
        opened = os.fstat(descriptor)
        after_open = registry_root.lstat()
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(after_open.st_mode)
            or stat.S_ISLNK(after_open.st_mode)
            or (opened.st_dev, opened.st_ino) != identity
            or (after_open.st_dev, after_open.st_ino) != identity
        ):
            raise RegistryError("REGISTRY_LOCK_UNAVAILABLE")
    except OSError as exc:
        raise RegistryError("REGISTRY_LOCK_UNAVAILABLE") from exc
    except RegistryError:
        os.close(descriptor)
        raise
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = registry_root.lstat()
        if (
            not stat.S_ISDIR(locked.st_mode)
            or stat.S_ISLNK(locked.st_mode)
            or (locked.st_dev, locked.st_ino) != identity
        ):
            raise RegistryError("REGISTRY_LOCK_UNAVAILABLE")
        guard = RegistryRootGuard(
            path=registry_root,
            identity=identity,
            mode=stat.S_IMODE(locked.st_mode),
            descriptor=descriptor,
        )
        require_registry_root_guard(guard)
        if _ACTIVE_REGISTRY_ROOT_GUARD is not None:
            raise RegistryError("REGISTRY_LOCK_UNAVAILABLE")
    except OSError as exc:
        os.close(descriptor)
        raise RegistryError("REGISTRY_LOCK_UNAVAILABLE") from exc
    except RegistryError:
        os.close(descriptor)
        raise
    _ACTIVE_REGISTRY_ROOT_GUARD = guard
    try:
        yield
    finally:
        lock_error: Optional[RegistryError] = None
        try:
            require_registry_root_guard(guard)
        except RegistryError as exc:
            lock_error = exc
        finally:
            _ACTIVE_REGISTRY_ROOT_GUARD = None
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        if lock_error is not None:
            raise lock_error


def empty_index() -> Dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "updated_at": utc_now(),
        "tracks": {},
        "receipts": {},
    }


def load_index(registry_root: Path) -> Dict[str, Any]:
    path = registry_root / "index.json"
    if not path.exists():
        if path.is_symlink():
            raise RegistryError("REGISTRY_INDEX_INVALID", exit_code=3)
        return empty_index()
    index = read_json_object(
        path,
        "REGISTRY_INDEX_INVALID",
        expected_mode=REGISTRY_FILE_MODE,
    )
    if not exact_integer(index.get("schema_version"), REGISTRY_SCHEMA_VERSION):
        raise RegistryError("REGISTRY_SCHEMA_UNSUPPORTED")
    if (
        set(index) != INDEX_VIEW_KEYS
        or forbidden_keys(index)
        or not isinstance(index.get("tracks"), dict)
        or not isinstance(index.get("receipts"), dict)
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    try:
        require_rfc3339(index.get("updated_at"), "REGISTRY_INDEX_INVALID")
    except RegistryError as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    return index


def validate_track_id(track_id: str) -> str:
    if TRACK_ID_RE.fullmatch(track_id) is None:
        raise RegistryError("TRACK_ID_INVALID")
    return track_id


def checkpoint_identity(checkpoint: Dict[str, Any], checkpoint_hash: str) -> str:
    schema_version = checkpoint.get("schema_version")
    if schema_version is not None and not exact_integer(schema_version):
        raise RegistryError("CHECKPOINT_SCHEMA_UNSUPPORTED")
    if checkpoint.get("context_status") != "READY":
        raise RegistryError("CHECKPOINT_NOT_READY")
    generated_at = require_rfc3339(
        checkpoint.get("generated_at"), "CHECKPOINT_TIMESTAMP_INVALID"
    )
    match = RFC3339_RE.fullmatch(generated_at)
    if match is None:
        raise RegistryError("CHECKPOINT_TIMESTAMP_INVALID")
    timestamp = "{}{}{}-{}{}{}".format(
        match.group("year"),
        match.group("month"),
        match.group("day"),
        match.group("hour"),
        match.group("minute"),
        match.group("second"),
    )
    return "cp-{}-{}".format(timestamp, checkpoint_hash[:8])


def physical_path(path: Path) -> Path:
    resolved = Path(os.path.realpath(path))
    if sys.platform != "darwin" or not hasattr(fcntl, "F_GETPATH"):
        return resolved
    existing = resolved
    suffix: list[str] = []
    while not existing.exists():
        if existing == existing.parent:
            return resolved
        suffix.append(existing.name)
        existing = existing.parent
    descriptor = -1
    try:
        descriptor = os.open(existing, os.O_RDONLY)
        canonical_bytes = fcntl.fcntl(descriptor, fcntl.F_GETPATH, b"\0" * 1024)
        canonical = Path(canonical_bytes.split(b"\0", 1)[0].decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RegistryError("RESOURCE_SCOPE_INVALID") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    for component in reversed(suffix):
        canonical /= component
    return canonical


def normalize_resource_scopes(values: Sequence[str]) -> list[str]:
    if not values:
        raise RegistryError("RESOURCE_SCOPE_MISSING")
    normalized: list[str] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            raise RegistryError("RESOURCE_SCOPE_NOT_ABSOLUTE")
        cleaned = os.path.normpath(str(path))
        if cleaned.startswith(os.path.sep * 2):
            cleaned = os.path.sep + cleaned.lstrip(os.path.sep)
        cleaned = str(physical_path(Path(cleaned)))
        if cleaned == os.path.sep or (
            sys.platform == "darwin" and cleaned == "/System/Volumes/Data"
        ):
            raise RegistryError("RESOURCE_SCOPE_TOO_BROAD")
        normalized.append(cleaned)
    return sorted(set(normalized))


def resource_scopes_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    for left_path in left:
        for right_path in right:
            comparison_left = unicodedata.normalize("NFC", left_path)
            comparison_right = unicodedata.normalize("NFC", right_path)
            if sys.platform == "darwin":
                comparison_left = comparison_left.casefold()
                comparison_right = comparison_right.casefold()
            try:
                common = os.path.commonpath([comparison_left, comparison_right])
            except ValueError:
                continue
            if common == comparison_left or common == comparison_right:
                return True
    return False


def remove_owned_empty_directories(directories: Iterable[OwnedDirectory]) -> None:
    for directory in directories:
        path = directory.path
        expected = NodeToken(
            kind="directory",
            identity=directory.identity,
            mode=directory.mode,
            children=(),
        )
        tombstone: Optional[Path] = None
        try:
            observed = capture_node_token(
                path,
                parent_identity=directory.parent_identity,
                parent_mode=directory.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            if observed != expected:
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            for _ in range(16):
                candidate = path.with_name(
                    ".pickup-remove-dir-{}".format(secrets.token_hex(16))
                )
                if candidate.exists() or candidate.is_symlink():
                    continue
                rename_owned_path_noreplace(
                    path,
                    candidate,
                    parent_identity=directory.parent_identity,
                    parent_mode=directory.parent_mode,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                tombstone = candidate
                break
            if tombstone is None:
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            require_node_token(
                tombstone,
                parent_identity=directory.parent_identity,
                parent_mode=directory.parent_mode,
                token=expected,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            with owned_directory_descriptor(
                tombstone,
                directory.identity,
                "TRANSACTION_ROLLBACK_FAILED",
                expected_mode=directory.mode,
            ) as child:
                if os.listdir(child):
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            with owned_directory_descriptor(
                tombstone.parent,
                directory.parent_identity,
                "TRANSACTION_ROLLBACK_FAILED",
                expected_mode=directory.parent_mode,
            ) as parent:
                # See remove_owned_regular: final pathname removal relies on the
                # registry's cooperative-writer lock after exact revalidation.
                os.rmdir(tombstone.name, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            require_owned_absence(
                path,
                parent_identity=directory.parent_identity,
                parent_mode=directory.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
        except BaseException as exc:
            restore_error: Optional[BaseException] = None
            try:
                if tombstone is not None and (
                    tombstone.exists() or tombstone.is_symlink()
                ):
                    require_node_token(
                        tombstone,
                        parent_identity=directory.parent_identity,
                        parent_mode=directory.parent_mode,
                        token=expected,
                        reason_code="TRANSACTION_ROLLBACK_FAILED",
                    )
                    rename_owned_path_noreplace(
                        tombstone,
                        path,
                        parent_identity=directory.parent_identity,
                        parent_mode=directory.parent_mode,
                        reason_code="TRANSACTION_ROLLBACK_FAILED",
                    )
            except BaseException as observed_restore_error:
                restore_error = observed_restore_error
            if restore_error is not None:
                raise RegistryError(
                    "TRANSACTION_ROLLBACK_FAILED", exit_code=3
                ) from restore_error
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc


def directory_install_token(source: Path, destination: Path) -> DirectoryInstall:
    source_metadata = source.lstat()
    parent_metadata = destination.parent.lstat()
    if (
        not stat.S_ISDIR(source_metadata.st_mode)
        or stat.S_ISLNK(source_metadata.st_mode)
        or stat.S_IMODE(source_metadata.st_mode) != REGISTRY_DIRECTORY_MODE
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or stat.S_IMODE(parent_metadata.st_mode) != REGISTRY_DIRECTORY_MODE
    ):
        raise RegistryError("PACKAGE_INSTALL_FAILED", exit_code=3)
    installs: list[ImmutableInstall] = []
    try:
        children = list(source.iterdir())
    except OSError as exc:
        raise RegistryError("PACKAGE_INSTALL_FAILED", exit_code=3) from exc
    if {child.name for child in children} != {
        "handoff.md",
        "checkpoint.json",
        "package.json",
    } or any(not child.is_file() or child.is_symlink() for child in children):
        raise RegistryError("PACKAGE_INSTALL_FAILED", exit_code=3)
    for child in children:
        resolved = regular_file(child, "PACKAGE_INSTALL_FAILED")
        data, metadata = stable_regular_capture(resolved, "PACKAGE_INSTALL_FAILED")
        if stat.S_IMODE(metadata.st_mode) != REGISTRY_FILE_MODE:
            raise RegistryError("PACKAGE_INSTALL_FAILED", exit_code=3)
        installs.append(
            ImmutableInstall(
                path=destination / child.name,
                identity=(metadata.st_dev, metadata.st_ino),
                sha256=hashlib.sha256(data).hexdigest(),
                parent_identity=(source_metadata.st_dev, source_metadata.st_ino),
            )
        )
    return DirectoryInstall(
        path=destination,
        identity=(source_metadata.st_dev, source_metadata.st_ino),
        files=tuple(installs),
        parent_identity=(parent_metadata.st_dev, parent_metadata.st_ino),
        parent_mode=stat.S_IMODE(parent_metadata.st_mode),
    )


def install_directory_noreplace(source: Path, destination: Path) -> DirectoryInstall:
    install = directory_install_token(source, destination)
    try:
        rename_owned_path_noreplace(
            source,
            destination,
            parent_identity=install.parent_identity,
            parent_mode=install.parent_mode,
            reason_code="PACKAGE_INSTALL_FAILED",
        )
    except RegistryError as exc:
        cause = exc.__cause__
        if isinstance(cause, OSError) and cause.errno in {
            errno.EEXIST,
            errno.ENOTEMPTY,
        }:
            raise RegistryError("PACKAGE_DESTINATION_CHANGED", exit_code=3) from exc
        raise
    try:
        require_directory_install(install)
    except RegistryError as exc:
        try:
            rollback_directory_install(install)
        except RegistryError as rollback_error:
            raise rollback_error from exc
        raise RegistryError("PACKAGE_INSTALL_FAILED", exit_code=3) from exc
    return install


def rollback_directory_install(install: DirectoryInstall) -> None:
    tombstone: Optional[Path] = None
    files_removed = False
    expected_directory = NodeToken(
        kind="directory",
        identity=install.identity,
        mode=REGISTRY_DIRECTORY_MODE,
        children=tuple(sorted(entry.path.name for entry in install.files)),
    )
    try:
        require_directory_install(install)
        for _ in range(16):
            candidate = install.path.with_name(
                ".pickup-remove-package-{}".format(secrets.token_hex(16))
            )
            if candidate.exists() or candidate.is_symlink():
                continue
            rename_owned_path_noreplace(
                install.path,
                candidate,
                parent_identity=install.parent_identity,
                parent_mode=install.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            tombstone = candidate
            break
        if tombstone is None:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
        require_node_token(
            tombstone,
            parent_identity=install.parent_identity,
            parent_mode=install.parent_mode,
            token=expected_directory,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        for entry in install.files:
            require_owned_regular(
                tombstone / entry.path.name,
                parent_identity=install.identity,
                parent_mode=REGISTRY_DIRECTORY_MODE,
                identity=entry.identity,
                sha256=entry.sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
        for entry in install.files:
            remove_owned_regular(
                tombstone / entry.path.name,
                parent_identity=install.identity,
                parent_mode=REGISTRY_DIRECTORY_MODE,
                identity=entry.identity,
                sha256=entry.sha256,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
            files_removed = True
        remove_owned_empty_directories(
            (
                OwnedDirectory(
                    path=tombstone,
                    identity=install.identity,
                    mode=REGISTRY_DIRECTORY_MODE,
                    parent_identity=install.parent_identity,
                    parent_mode=install.parent_mode,
                ),
            )
        )
    except BaseException as exc:
        restore_error: Optional[BaseException] = None
        try:
            if (
                tombstone is not None
                and not files_removed
                and (tombstone.exists() or tombstone.is_symlink())
            ):
                require_node_token(
                    tombstone,
                    parent_identity=install.parent_identity,
                    parent_mode=install.parent_mode,
                    token=expected_directory,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                for entry in install.files:
                    require_owned_regular(
                        tombstone / entry.path.name,
                        parent_identity=install.identity,
                        parent_mode=REGISTRY_DIRECTORY_MODE,
                        identity=entry.identity,
                        sha256=entry.sha256,
                        reason_code="TRANSACTION_ROLLBACK_FAILED",
                    )
                rename_owned_path_noreplace(
                    tombstone,
                    install.path,
                    parent_identity=install.parent_identity,
                    parent_mode=install.parent_mode,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
        except BaseException as observed_restore_error:
            restore_error = observed_restore_error
        if restore_error is not None:
            raise RegistryError(
                "TRANSACTION_ROLLBACK_FAILED", exit_code=3
            ) from restore_error
        raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc


def require_immutable_install(install: ImmutableInstall) -> None:
    if install.staging_path is not None:
        try:
            if install.parent_identity is None:
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            require_owned_absence(
                install.staging_path,
                parent_identity=install.parent_identity,
                parent_mode=install.parent_mode,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
        except RegistryError as exc:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc
    try:
        if install.parent_identity is None:
            raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
        require_owned_regular(
            install.path,
            parent_identity=install.parent_identity,
            parent_mode=install.parent_mode,
            identity=install.identity,
            sha256=install.sha256,
            reason_code="TRANSACTION_INSTALL_CHANGED",
            expected_mode=install.mode,
        )
    except RegistryError as exc:
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3) from exc


def require_directory_install(install: DirectoryInstall) -> None:
    try:
        require_node_token(
            install.path,
            parent_identity=install.parent_identity,
            parent_mode=install.parent_mode,
            token=NodeToken(
                kind="directory",
                identity=install.identity,
                mode=REGISTRY_DIRECTORY_MODE,
                children=tuple(sorted(entry.path.name for entry in install.files)),
            ),
            reason_code="TRANSACTION_INSTALL_CHANGED",
        )
        for entry in install.files:
            require_immutable_install(entry)
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3) from exc


def capture_file_guard(
    path: Path,
    *,
    expected_sha256: Optional[str] = None,
    expected_mode: Optional[int] = REGISTRY_FILE_MODE,
    expected_parent_mode: Optional[int] = REGISTRY_DIRECTORY_MODE,
) -> ImmutableInstall:
    try:
        parent = path.parent.lstat()
    except OSError as exc:
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3) from exc
    parent_identity = (parent.st_dev, parent.st_ino)
    parent_mode = stat.S_IMODE(parent.st_mode)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or (expected_parent_mode is not None and parent_mode != expected_parent_mode)
    ):
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        "TRANSACTION_INSTALL_CHANGED",
        expected_mode=parent_mode,
    ) as descriptor:
        token = capture_node_token_at(
            path.name,
            parent_descriptor=descriptor,
            reason_code="TRANSACTION_INSTALL_CHANGED",
        )
    if (
        token.kind != "file"
        or token.sha256 is None
        or (expected_mode is not None and token.mode != expected_mode)
        or (expected_sha256 is not None and token.sha256 != expected_sha256)
    ):
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
    return ImmutableInstall(
        path=path,
        identity=token.identity,
        sha256=token.sha256,
        parent_identity=parent_identity,
        mode=token.mode,
        parent_mode=parent_mode,
    )


def capture_path_state_guard(path: Path) -> PathStateGuard:
    try:
        parent = path.parent.lstat()
    except OSError as exc:
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3) from exc
    parent_identity = (parent.st_dev, parent.st_ino)
    parent_mode = stat.S_IMODE(parent.st_mode)
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
    with owned_directory_descriptor(
        path.parent,
        parent_identity,
        "TRANSACTION_INSTALL_CHANGED",
        expected_mode=parent_mode,
    ) as descriptor:
        try:
            os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            token = None
        else:
            token = capture_node_token_at(
                path.name,
                parent_descriptor=descriptor,
                reason_code="TRANSACTION_INSTALL_CHANGED",
            )
    return PathStateGuard(
        path=path,
        parent_identity=parent_identity,
        parent_mode=parent_mode,
        token=token,
    )


def require_path_state_guard(guard: PathStateGuard) -> None:
    try:
        if guard.token is None:
            require_owned_absence(
                guard.path,
                parent_identity=guard.parent_identity,
                parent_mode=guard.parent_mode,
                reason_code="TRANSACTION_INSTALL_CHANGED",
            )
        else:
            require_node_token(
                guard.path,
                parent_identity=guard.parent_identity,
                parent_mode=guard.parent_mode,
                token=guard.token,
                reason_code="TRANSACTION_INSTALL_CHANGED",
            )
    except RegistryError as exc:
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3) from exc


def capture_registry_immutable_guards(
    *,
    registry_root: Path,
    index: Dict[str, Any],
    pending_paths: Sequence[Path] = (),
    excluded_coordinates: Sequence[PackageCoordinate] = (),
) -> tuple[ImmutableInstall, ...]:
    pending = set(pending_paths)
    excluded = set(excluded_coordinates)
    guards: list[ImmutableInstall] = []
    tracks = index.get("tracks")
    receipts = index.get("receipts")
    if not isinstance(tracks, dict) or not isinstance(receipts, dict):
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
    for track_id, track in tracks.items():
        packages = track.get("packages") if isinstance(track, dict) else None
        if not isinstance(track_id, str) or not isinstance(packages, dict):
            raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
        for checkpoint_id, package_entry in packages.items():
            coordinate = PackageCoordinate(track_id, checkpoint_id)
            if not isinstance(package_entry, dict):
                raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
            package_path = coordinate.package_path(registry_root)
            if coordinate not in excluded:
                for filename, hash_field in (
                    ("package.json", "package_sha256"),
                    ("handoff.md", "handoff_sha256"),
                    ("checkpoint.json", "checkpoint_sha256"),
                ):
                    guards.append(
                        capture_file_guard(
                            package_path / filename,
                            expected_sha256=package_entry.get(hash_field),
                        )
                    )
            event_path = coordinate.quarantine_event_path(registry_root)
            event_hash = package_entry.get("quarantine_event_sha256")
            if event_path in pending:
                continue
            if event_hash is not None:
                guards.append(
                    capture_file_guard(event_path, expected_sha256=event_hash)
                )
    for receipt_id, entry in receipts.items():
        if not isinstance(receipt_id, str) or not isinstance(entry, dict):
            raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
        track_id = entry.get("track_id")
        latest_revision = entry.get("latest_revision")
        if not isinstance(track_id, str) or type(latest_revision) is not int:
            raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
        for revision in range(1, latest_revision + 1):
            path = (
                registry_root
                / "tracks"
                / track_id
                / "receipts"
                / "{}-r{:04d}.json".format(receipt_id, revision)
            )
            if path in pending:
                continue
            expected_hash = (
                entry.get("latest_receipt_sha256")
                if revision == latest_revision
                else None
            )
            guards.append(capture_file_guard(path, expected_sha256=expected_hash))
    return tuple(guards)


def capture_receipt_skill_guard(receipt: Dict[str, Any]) -> ImmutableInstall:
    artifacts = receipt.get("artifacts")
    skill = artifacts.get("skill") if isinstance(artifacts, dict) else None
    if (
        not isinstance(skill, dict)
        or not isinstance(skill.get("path"), str)
        or not isinstance(skill.get("sha256"), str)
    ):
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
    path = Path(skill["path"])
    return capture_file_guard(
        path,
        expected_sha256=skill["sha256"],
        expected_mode=None,
        expected_parent_mode=None,
    )


def capture_receipt_skill_state_guard(receipt: Dict[str, Any]) -> PathStateGuard:
    artifacts = receipt.get("artifacts")
    skill = artifacts.get("skill") if isinstance(artifacts, dict) else None
    if not isinstance(skill, dict) or not isinstance(skill.get("path"), str):
        raise RegistryError("TRANSACTION_INSTALL_CHANGED", exit_code=3)
    return capture_path_state_guard(Path(skill["path"]))


def capture_registry_snapshot(
    registry_root: Path, *, excluded_roots: Sequence[Path] = ()
) -> RegistrySnapshot:
    require_active_registry_root_for_path(registry_root)
    excluded = tuple(path.absolute() for path in excluded_roots)

    def is_excluded(path: Path) -> bool:
        absolute = path.absolute()
        return any(root == absolute or root in absolute.parents for root in excluded)

    snapshot: RegistrySnapshot = {}
    try:
        candidates = [registry_root, *registry_root.rglob("*")]
        for candidate in candidates:
            if is_excluded(candidate):
                continue
            relative = (
                "."
                if candidate == registry_root
                else str(candidate.relative_to(registry_root))
            )
            metadata = candidate.lstat()
            if stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                kind = "file"
                data, metadata = stable_regular_capture(
                    candidate, "ORPHANED_CLAIM_REVIEW_REQUIRED"
                )
                digest: Optional[str] = hashlib.sha256(data).hexdigest()
                link_target: Optional[str] = None
                children: tuple[str, ...] = ()
            elif stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                kind = "directory"
                digest = None
                link_target = None
                children = tuple(
                    sorted(
                        child.name
                        for child in candidate.iterdir()
                        if not is_excluded(child)
                    )
                )
            else:
                kind = "other"
                digest = None
                link_target = (
                    os.readlink(candidate) if stat.S_ISLNK(metadata.st_mode) else None
                )
                children = ()
            snapshot[relative] = NodeToken(
                kind=kind,
                identity=(metadata.st_dev, metadata.st_ino),
                mode=stat.S_IMODE(metadata.st_mode),
                sha256=digest,
                link_target=link_target,
                children=children,
            )
    except (OSError, RegistryError) as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    require_active_registry_root_for_path(registry_root)
    return snapshot


def require_registry_snapshot(
    registry_root: Path,
    expected: RegistrySnapshot,
    *,
    excluded_roots: Sequence[Path] = (),
) -> None:
    observed = capture_registry_snapshot(registry_root, excluded_roots=excluded_roots)
    if observed == expected:
        return
    if set(observed) == set(expected) and any(
        observed[path].mode != expected[path].mode
        and NodeToken(
            kind=observed[path].kind,
            identity=observed[path].identity,
            mode=expected[path].mode,
            sha256=observed[path].sha256,
            link_target=observed[path].link_target,
            children=observed[path].children,
        )
        == expected[path]
        for path in expected
    ):
        raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
    changed_paths = {
        path
        for path in set(observed) | set(expected)
        if observed.get(path) != expected.get(path)
    }
    if changed_paths and all("packages" in Path(path).parts for path in changed_paths):
        raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
    raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)


def registry_relative_path(registry_root: Path, path: Path) -> Optional[str]:
    try:
        return str(path.relative_to(registry_root))
    except ValueError:
        return None


def expected_transaction_registry_paths(
    *,
    registry_root: Path,
    initial: RegistrySnapshot,
    immutable_writes: Sequence[ImmutableWrite],
    mutable_writes: Sequence[MutableWrite],
) -> tuple[set[str], set[str]]:
    expected = set(initial)
    targets: set[str] = set()
    paths = [write.path for write in immutable_writes]
    paths.extend(write.path for write in mutable_writes)
    for path in paths:
        relative = registry_relative_path(registry_root, path)
        if relative is None:
            continue
        targets.add(relative)
        expected.add(relative)
        parent = Path(relative).parent
        while parent != Path("."):
            expected.add(str(parent))
            parent = parent.parent
    return expected, targets


def require_transaction_registry_inventory(
    *,
    registry_root: Path,
    initial: RegistrySnapshot,
    immutable_writes: Sequence[ImmutableWrite],
    mutable_writes: Sequence[MutableWrite],
) -> None:
    try:
        observed = capture_registry_snapshot(registry_root)
        expected_paths, target_paths = expected_transaction_registry_paths(
            registry_root=registry_root,
            initial=initial,
            immutable_writes=immutable_writes,
            mutable_writes=mutable_writes,
        )
        if set(observed) != expected_paths:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
        for relative in expected_paths:
            token = observed[relative]
            initial_token = initial.get(relative)
            if token.kind == "directory":
                relative_path = Path(relative)
                expected_children = tuple(
                    sorted(
                        Path(candidate).name
                        for candidate in expected_paths
                        if candidate != "." and Path(candidate).parent == relative_path
                    )
                )
                if token.children != expected_children:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                if initial_token is None:
                    if token.mode != REGISTRY_DIRECTORY_MODE:
                        raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                elif (
                    initial_token.kind != "directory"
                    or token.identity != initial_token.identity
                    or token.mode != initial_token.mode
                ):
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                continue
            if relative in target_paths:
                continue
            if initial_token is None or token != initial_token:
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
    except RegistryError as exc:
        if exc.reason_code == "TRANSACTION_ROLLBACK_FAILED":
            raise
        raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc


def forbidden_keys(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized_key = CAMEL_CASE_BOUNDARY_RE.sub("_", key_text)
            normalized_key = KEY_SEPARATOR_RE.sub("_", normalized_key).strip("_")
            normalized_key = normalized_key.lower()
            normalized_tokens = frozenset(normalized_key.split("_"))
            compact_key = KEY_SEPARATOR_RE.sub("", key_text).lower()
            credential_pair = any(
                family in normalized_tokens
                and any(
                    carrier != family and carrier in normalized_tokens
                    for carrier in FORBIDDEN_CREDENTIAL_CARRIERS
                )
                for family in FORBIDDEN_CREDENTIAL_FAMILIES
            )
            if (
                normalized_key in FORBIDDEN_KEYS
                or FORBIDDEN_KEY_RE.search(normalized_key) is not None
                or compact_key in FORBIDDEN_COMPACT_KEYS
                or FORBIDDEN_COMPACT_KEY_RE.search(compact_key) is not None
                or FORBIDDEN_PID_KEY_RE.search(normalized_key) is not None
                or FORBIDDEN_PID_COMPACT_KEY_RE.search(compact_key) is not None
                or normalized_key in FORBIDDEN_RUNTIME_FAMILIES
                or compact_key in FORBIDDEN_RUNTIME_FAMILIES
                or (
                    not normalized_tokens.isdisjoint(FORBIDDEN_RUNTIME_FAMILIES)
                    and not normalized_tokens.isdisjoint(
                        FORBIDDEN_RUNTIME_IDENTITY_TERMS
                    )
                )
                or normalized_key in FORBIDDEN_SENSITIVE_KEYS
                or FORBIDDEN_SENSITIVE_KEY_RE.search(normalized_key) is not None
                or FORBIDDEN_SENSITIVE_COMPACT_KEY_RE.search(compact_key) is not None
                or normalized_key in FORBIDDEN_CREDENTIAL_EXACT
                or compact_key in FORBIDDEN_CREDENTIAL_COMPACT
                or not normalized_tokens.isdisjoint(FORBIDDEN_CREDENTIAL_STANDALONE)
                or credential_pair
            ):
                found.append(key)
            found.extend(forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(forbidden_keys(child))
    return found


def run_secret_scan(candidate: Path, gitleaks_path: str) -> None:
    scanner = Path(gitleaks_path)
    if not scanner.is_file() or not os.access(scanner, os.X_OK):
        raise RegistryError("SECRET_SCANNER_UNAVAILABLE")
    try:
        completed = subprocess.run(
            [
                str(scanner),
                "detect",
                "--no-git",
                "--source",
                str(candidate),
                "--redact",
                "--no-banner",
                "--no-color",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RegistryError("SECRET_SCANNER_UNAVAILABLE") from exc
    if completed.returncode != 0:
        raise RegistryError("SENSITIVE_DATA_SCAN_FAILED", exit_code=3)


def scan_json_payload(
    filename: str, payload: Dict[str, Any], gitleaks_path: str
) -> bytes:
    if forbidden_keys(payload):
        raise RegistryError("PRIVATE_RUNTIME_IDENTIFIER_FIELD")
    if Path(filename).name != filename:
        raise RegistryError("SERIALIZED_JSON_INVALID")
    data = serialized_json(payload)
    ownership = create_owned_temporary_directory(
        Path(tempfile.gettempdir()).resolve(),
        "pickup-json-scan-",
        "TRANSACTION_ROLLBACK_FAILED",
    )
    temporary = ownership.path
    candidate_install: Optional[ImmutableInstall] = None
    primary_error: Optional[BaseException] = None
    try:
        candidate_install = write_immutable_bytes(temporary / filename, data)
        run_secret_scan(temporary, gitleaks_path)
    except BaseException as exc:
        primary_error = exc
    cleanup_error: Optional[RegistryError] = None
    if candidate_install is not None:
        try:
            remove_transaction_immutable(candidate_install)
        except (OSError, RegistryError) as exc:
            cleanup_error = RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            cleanup_error.__cause__ = exc
    try:
        remove_owned_empty_directories((ownership,))
    except (OSError, RegistryError) as exc:
        if cleanup_error is None:
            cleanup_error = RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            cleanup_error.__cause__ = exc
    if cleanup_error is not None:
        if primary_error is not None:
            raise cleanup_error from primary_error
        raise cleanup_error
    if primary_error is not None:
        raise primary_error
    return data


def write_immutable_bytes(
    path: Path,
    data: bytes,
    *,
    existing_reason_code: str = "IMMUTABLE_RECEIPT_EXISTS",
) -> ImmutableInstall:
    owned_parent = secure_directory(
        path.parent,
        reason_code="TRANSACTION_ROLLBACK_FAILED",
    )
    parent_created = owned_parent is not None
    parent_metadata = path.parent.lstat()
    parent_identity = (parent_metadata.st_dev, parent_metadata.st_ino)
    parent_mode = stat.S_IMODE(parent_metadata.st_mode)
    if owned_parent is not None and owned_parent.identity != parent_identity:
        raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
    if parent_mode != REGISTRY_DIRECTORY_MODE:
        raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
    descriptor = -1
    temporary: Optional[Path] = None
    staging_path: Optional[Path] = None
    installed = False
    staging_removed = False
    staged_identity: Optional[tuple[int, int]] = None
    digest = hashlib.sha256(data).hexdigest()
    try:
        descriptor, temporary, staged_identity = create_owned_staging_file(
            path.parent,
            prefix=".{}-".format(path.name),
            suffix=".tmp",
            parent_identity=parent_identity,
            parent_mode=parent_mode,
            reason_code="IMMUTABLE_WRITE_FAILED",
        )
        staging_path = temporary
        staged = os.fstat(descriptor)
        if not stat.S_ISREG(staged.st_mode):
            raise RegistryError("IMMUTABLE_WRITE_FAILED", exit_code=3)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        require_owned_regular(
            temporary,
            parent_identity=parent_identity,
            parent_mode=parent_mode,
            identity=staged_identity,
            sha256=digest,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        try:
            link_owned_path_noreplace(
                temporary,
                path,
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                reason_code=existing_reason_code,
            )
        except FileExistsError as exc:
            raise RegistryError(existing_reason_code) from exc
        installed = True
        remove_owned_regular(
            temporary,
            parent_identity=parent_identity,
            parent_mode=parent_mode,
            identity=staged_identity,
            sha256=digest,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        staging_removed = True
        temporary = None
        require_owned_absence(
            staging_path,
            parent_identity=parent_identity,
            parent_mode=parent_mode,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        sync_owned_directory(
            path.parent,
            parent_identity,
            "IMMUTABLE_WRITE_FAILED",
            expected_mode=parent_mode,
        )
        require_immutable_install(
            ImmutableInstall(
                path=path,
                identity=staged_identity,
                sha256=digest,
                created_parent=parent_created,
                parent_identity=parent_identity,
                staging_path=staging_path,
            )
        )
    except (OSError, RegistryError) as exc:
        rollback_failed = False
        if installed:
            try:
                if staged_identity is None:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                remove_owned_regular(
                    path,
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                    identity=staged_identity,
                    sha256=digest,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                sync_owned_directory(
                    path.parent,
                    parent_identity,
                    "TRANSACTION_ROLLBACK_FAILED",
                    expected_mode=parent_mode,
                    sync_reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                installed = False
            except (OSError, RegistryError):
                rollback_failed = True
        if temporary is not None:
            try:
                if staged_identity is None:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                remove_owned_regular(
                    temporary,
                    parent_identity=parent_identity,
                    parent_mode=parent_mode,
                    identity=staged_identity,
                    sha256=digest,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                temporary = None
            except (OSError, RegistryError):
                rollback_failed = True
        if parent_created:
            try:
                if owned_parent is None:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                remove_owned_empty_directories((owned_parent,))
            except (OSError, RegistryError):
                rollback_failed = True
        if rollback_failed:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc
        if (
            isinstance(exc, RegistryError)
            and exc.reason_code == existing_reason_code
            and not installed
        ):
            raise
        if (
            isinstance(exc, RegistryError)
            and exc.reason_code == "TRANSACTION_ROLLBACK_FAILED"
            and staging_removed
        ):
            raise
        raise RegistryError("IMMUTABLE_WRITE_FAILED", exit_code=3) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            if staged_identity is None:
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            remove_owned_regular(
                temporary,
                parent_identity=parent_identity,
                parent_mode=parent_mode,
                identity=staged_identity,
                sha256=digest,
                reason_code="TRANSACTION_ROLLBACK_FAILED",
            )
    if staged_identity is None:
        raise RegistryError("IMMUTABLE_WRITE_FAILED", exit_code=3)
    return ImmutableInstall(
        path=path,
        identity=staged_identity,
        sha256=digest,
        created_parent=parent_created,
        parent_identity=parent_identity,
        mode=REGISTRY_FILE_MODE,
        parent_mode=parent_mode,
        created_parent_parent_identity=(
            owned_parent.parent_identity if owned_parent is not None else None
        ),
        created_parent_parent_mode=(
            owned_parent.parent_mode if owned_parent is not None else None
        ),
        staging_path=staging_path,
    )


def remove_transaction_immutable(
    install: ImmutableInstall, *, cleanup_empty_parent: bool = False
) -> None:
    try:
        path = install.path
        if install.parent_identity is None:
            raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
        remove_owned_regular(
            path,
            parent_identity=install.parent_identity,
            parent_mode=REGISTRY_DIRECTORY_MODE,
            identity=install.identity,
            sha256=install.sha256,
            reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        sync_owned_directory(
            path.parent,
            install.parent_identity,
            "TRANSACTION_ROLLBACK_FAILED",
            expected_mode=REGISTRY_DIRECTORY_MODE,
            sync_reason_code="TRANSACTION_ROLLBACK_FAILED",
        )
        if cleanup_empty_parent and install.created_parent:
            if (
                install.parent_mode is None
                or install.created_parent_parent_identity is None
                or install.created_parent_parent_mode is None
            ):
                raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
            remove_owned_empty_directories(
                (
                    OwnedDirectory(
                        path=path.parent,
                        identity=install.parent_identity,
                        mode=install.parent_mode,
                        parent_identity=install.created_parent_parent_identity,
                        parent_mode=install.created_parent_parent_mode,
                    ),
                )
            )
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3) from exc


def commit_file_transaction(
    *,
    registry_root: Path,
    immutable_writes: Sequence[ImmutableWrite],
    mutable_writes: Sequence[MutableWrite],
    guarded_directory_installs: Sequence[DirectoryInstall] = (),
    guarded_immutable_installs: Sequence[ImmutableInstall] = (),
    guarded_path_states: Sequence[PathStateGuard] = (),
) -> list[str]:
    prepared: list[PreparedMutableWrite] = []
    immutable_installs: list[ImmutableInstall] = []
    committed_mutables: list[PreparedMutableWrite] = []
    initial_registry = capture_registry_snapshot(registry_root)

    def require_installs() -> None:
        for install in immutable_installs:
            require_immutable_install(install)
        for install in guarded_directory_installs:
            require_directory_install(install)
        for install in guarded_immutable_installs:
            require_immutable_install(install)
        for guard in guarded_path_states:
            require_path_state_guard(guard)
        for staged in committed_mutables:
            staged.require_committed()
            staged.require_consumed_temporary_absent()

    try:
        for write in mutable_writes:
            prepared.append(PreparedMutableWrite.prepare(write))
        require_installs()
        for write in immutable_writes:
            immutable_installs.append(
                write_immutable_bytes(
                    write.path,
                    write.data,
                    existing_reason_code=write.existing_reason_code,
                )
            )
            require_installs()
        for staged in prepared:
            require_installs()
            try:
                staged.commit()
            finally:
                if staged.committed:
                    committed_mutables.append(staged)
            require_installs()
        require_installs()
        for staged in prepared:
            staged.cleanup()
        require_installs()
        require_transaction_registry_inventory(
            registry_root=registry_root,
            initial=initial_registry,
            immutable_writes=immutable_writes,
            mutable_writes=mutable_writes,
        )
        require_installs()
        return [install.sha256 for install in immutable_installs]
    except BaseException as exc:
        rollback_error: Optional[RegistryError] = None
        for staged in reversed(committed_mutables):
            try:
                staged.rollback()
            except RegistryError as rollback_exc:
                rollback_error = rollback_exc
                break
        if rollback_error is None:
            for write, install in reversed(
                list(zip(immutable_writes, immutable_installs))
            ):
                try:
                    remove_transaction_immutable(
                        install,
                        cleanup_empty_parent=write.cleanup_empty_parent,
                    )
                except RegistryError as rollback_exc:
                    rollback_error = rollback_exc
                    break
        for staged in prepared:
            if rollback_error is not None and staged.committed:
                continue
            try:
                staged.cleanup()
            except RegistryError as cleanup_exc:
                if rollback_error is None:
                    rollback_error = cleanup_exc
        if rollback_error is not None:
            raise rollback_error from exc
        raise


def receipt_result(
    *,
    receipt: Dict[str, Any],
    receipt_path: Path,
    receipt_sha256: str,
) -> Dict[str, Any]:
    result = dict(receipt)
    result["receipt_path"] = str(receipt_path)
    result["receipt_sha256"] = receipt_sha256
    return result


def compatibility_write(
    *,
    compatibility_output: Path,
    receipt: Dict[str, Any],
    receipt_sha256: str,
    expected_destination: MutableDestination,
) -> MutableWrite:
    compatibility = dict(receipt)
    compatibility["compatibility_summary"] = True
    compatibility["receipt_sha256"] = receipt_sha256
    return MutableWrite(
        path=compatibility_output,
        payload=compatibility,
        parent_reason_code="COMPATIBILITY_OUTPUT_PARENT_UNAVAILABLE",
        invalid_reason_code="COMPATIBILITY_OUTPUT_INVALID",
        write_reason_code="COMPATIBILITY_OUTPUT_PARENT_UNAVAILABLE",
        expected_destination=expected_destination,
    )


def prepare_receipt_data(
    *,
    registry_root: Path,
    receipt_path: Path,
    receipt: Dict[str, Any],
    gitleaks_path: str,
    allow_prevalidated_drift_terminal: bool = False,
) -> bytes:
    validate_receipt_schema(receipt)
    pre_scan_registry = capture_registry_snapshot(registry_root)
    receipt_data: Optional[bytes] = None
    scan_error: Optional[RegistryError] = None
    try:
        receipt_data = scan_json_payload(receipt_path.name, receipt, gitleaks_path)
    except RegistryError as exc:
        scan_error = exc
    except BaseException:
        require_registry_snapshot(registry_root, pre_scan_registry)
        raise
    try:
        require_registry_snapshot(registry_root, pre_scan_registry)
    except RegistryError as exc:
        scan_error = exc
    if scan_error is None:
        if receipt_data is None:
            raise RegistryError("SERIALIZED_JSON_INVALID")
        return receipt_data
    if (
        not allow_prevalidated_drift_terminal
        or scan_error.reason_code
        not in {
            "SENSITIVE_DATA_SCAN_FAILED",
            "SECRET_SCANNER_UNAVAILABLE",
            "PACKAGE_ARTIFACT_DRIFT",
        }
        or receipt.get("event") != ReceiptEvent.COMPLETED.value
        or receipt.get("status") != TerminalStatus.REVIEW_REQUIRED.value
        or receipt.get("terminal") is not True
        or receipt.get("reason_code") != "PACKAGE_ARTIFACT_DRIFT"
        or forbidden_keys(receipt)
    ):
        raise scan_error
    validation = receipt.get("validation")
    if not isinstance(validation, dict) or validation.get("json") is not True:
        raise scan_error
    receipt["validation"] = {
        "json": True,
        "secret_scan": "PREVALIDATED_DERIVED_TERMINAL",
    }
    validate_receipt_schema(receipt)
    return serialized_json(receipt)


def capture_receipt_destinations(
    *,
    registry_root: Path,
    track_id: str,
    compatibility_output: Path,
    compatibility_destination: MutableDestination,
    include_claim: bool,
) -> Dict[Path, MutableDestination]:
    track_root = registry_root / "tracks" / track_id
    paths = [track_root / "track.json", registry_root / "index.json"]
    if include_claim:
        paths.append(track_root / "claim.json")
    destinations = {
        path: capture_mutable_destination(
            path,
            parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
            invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        for path in paths
    }
    destinations[compatibility_output] = compatibility_destination
    return destinations


def persist_receipt_event(
    *,
    registry_root: Path,
    compatibility_output: Path,
    track_id: str,
    receipt: Dict[str, Any],
    receipt_path: Path,
    receipt_data: bytes,
    claim_view: Optional[Dict[str, Any]],
    track_view: Dict[str, Any],
    index_view: Dict[str, Any],
    destination_expectations: Dict[Path, MutableDestination],
    additional_immutables: Sequence[ImmutableWrite] = (),
    excluded_guard_coordinates: Sequence[PackageCoordinate] = (),
    allow_receipt_skill_drift: bool = False,
) -> Dict[str, Any]:
    receipt_hash = hashlib.sha256(receipt_data).hexdigest()
    markdown_path = None
    if receipt["event"] == ReceiptEvent.COMPLETED.value:
        markdown_path = compatibility_output.parent / "receipts" / receipt_path.with_suffix(".md").name
        outcome = "DONE" if receipt["status"] == TerminalStatus.READY.value else receipt["status"]
        markdown = (
            "# Treasure Pickup Receipt\n\nTREASUREPICKUP: {}\n\n".format(outcome)
            + "Stored checks from this run; unobserved later state remains unknown.\n"
            + "The user controls artifact custody. No authorization for subsequent work.\n\n```json\n"
        ).encode("utf-8") + receipt_data + b"```\n"
        additional_immutables = (
            *additional_immutables,
            ImmutableWrite(path=markdown_path, data=markdown, cleanup_empty_parent=True),
        )
    track_root = registry_root / "tracks" / track_id
    mutable_writes: list[MutableWrite] = []
    if claim_view is not None:
        mutable_writes.append(
            MutableWrite(
                path=track_root / "claim.json",
                payload=claim_view,
                parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_destination=destination_expectations[
                    track_root / "claim.json"
                ],
            )
        )
    mutable_writes.extend(
        [
            MutableWrite(
                path=track_root / "track.json",
                payload=track_view,
                parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_destination=destination_expectations[
                    track_root / "track.json"
                ],
            ),
            MutableWrite(
                path=registry_root / "index.json",
                payload=index_view,
                parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_destination=destination_expectations[
                    registry_root / "index.json"
                ],
            ),
            compatibility_write(
                compatibility_output=compatibility_output,
                receipt=receipt,
                receipt_sha256=receipt_hash,
                expected_destination=destination_expectations[compatibility_output],
            ),
        ]
    )
    pending_paths = [write.path for write in additional_immutables]
    pending_paths.append(receipt_path)
    guarded_immutables = list(
        capture_registry_immutable_guards(
            registry_root=registry_root,
            index=index_view,
            pending_paths=pending_paths,
            excluded_coordinates=excluded_guard_coordinates,
        )
    )
    guarded_path_states: list[PathStateGuard] = []
    if allow_receipt_skill_drift:
        guarded_path_states.append(capture_receipt_skill_state_guard(receipt))
    else:
        guarded_immutables.append(capture_receipt_skill_guard(receipt))
    revision = receipt.get("revision")
    previous_hash = receipt.get("previous_receipt_sha256")
    if type(revision) is int and revision > 1 and isinstance(previous_hash, str):
        previous_path = receipt_path.with_name(
            "{}-r{:04d}.json".format(receipt["receipt_id"], revision - 1)
        )
        guarded_immutables.append(
            capture_file_guard(previous_path, expected_sha256=previous_hash)
        )
    commit_file_transaction(
        registry_root=registry_root,
        immutable_writes=(
            *additional_immutables,
            ImmutableWrite(path=receipt_path, data=receipt_data),
        ),
        mutable_writes=mutable_writes,
        guarded_immutable_installs=guarded_immutables,
        guarded_path_states=guarded_path_states,
    )
    result = receipt_result(
        receipt=receipt,
        receipt_path=receipt_path,
        receipt_sha256=receipt_hash,
    )
    if markdown_path is not None:
        result["markdown_receipt_path"] = str(markdown_path)
    return result


def package_summary(
    package: Dict[str, Any],
    package_path: Path,
    *,
    state: Optional[str] = None,
    claim_active: bool = False,
) -> Dict[str, Any]:
    return {
        "track_id": package["track_id"],
        "checkpoint_id": package["checkpoint_id"],
        "selector": package["selector"],
        "state": state or package["published_state"],
        "claim_active": claim_active,
        "generated_at": package["checkpoint_generated_at"],
        "current_phase": package.get("current_phase"),
        "next_phase": package.get("next_phase"),
        "resource_scopes": package["resource_scopes"],
        "package_path": str(package_path),
    }


def publication_scaffold_matches(
    registry_root: Path,
    coordinate: PackageCoordinate,
    index: Dict[str, Any],
) -> bool:
    """Recognize only the empty/unindexed shape left by a failed publication.

    A conflicting destination may remain inside the packages directory.  It is
    never inspected, removed, or adopted; the caller reports the conflict.
    """
    if (
        index.get("tracks") != {}
        or index.get("receipts") != {}
        or (registry_root / "index.json").exists()
        or (registry_root / "index.json").is_symlink()
    ):
        return False
    expected = (
        (registry_root, {"tracks"}),
        (registry_root / "tracks", {coordinate.track_id}),
        (registry_root / "tracks" / coordinate.track_id, {"packages"}),
    )
    try:
        for directory, expected_names in expected:
            metadata = directory.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != REGISTRY_DIRECTORY_MODE
                or {child.name for child in directory.iterdir()} != expected_names
            ):
                return False
        packages_root = registry_root / "tracks" / coordinate.track_id / "packages"
        packages_metadata = packages_root.lstat()
        if (
            not stat.S_ISDIR(packages_metadata.st_mode)
            or stat.S_ISLNK(packages_metadata.st_mode)
            or stat.S_IMODE(packages_metadata.st_mode) != REGISTRY_DIRECTORY_MODE
        ):
            return False
        return {child.name for child in packages_root.iterdir()} <= {
            coordinate.checkpoint_id
        }
    except OSError:
        return False


def require_publication_sources_unchanged(
    *,
    handoff_path: Path,
    checkpoint_path: Path,
    handoff_hash: str,
    checkpoint_hash: str,
) -> None:
    if (
        sha256_file(regular_file(handoff_path, "SOURCE_CHANGED_DURING_PUBLICATION"))
        != handoff_hash
        or sha256_file(
            regular_file(checkpoint_path, "SOURCE_CHANGED_DURING_PUBLICATION")
        )
        != checkpoint_hash
    ):
        raise RegistryError("SOURCE_CHANGED_DURING_PUBLICATION", exit_code=3)


def publish_checkpoint(
    *,
    registry_root: Path,
    track_id: str,
    handoff_path: Path,
    checkpoint_path: Path,
    resource_scopes: Sequence[str],
    gitleaks_path: str,
) -> Dict[str, Any]:
    track_id = validate_track_id(track_id)
    handoff_path = regular_file(handoff_path, "HANDOFF_INVALID")
    checkpoint_path = regular_file(checkpoint_path, "CHECKPOINT_INVALID")
    handoff_bytes = read_regular_bytes(handoff_path, "HANDOFF_INVALID")
    checkpoint_bytes = read_regular_bytes(checkpoint_path, "CHECKPOINT_INVALID")
    checkpoint = json_object_from_bytes(checkpoint_bytes, "CHECKPOINT_INVALID")
    if forbidden_keys(checkpoint):
        raise RegistryError("PRIVATE_RUNTIME_IDENTIFIER_FIELD")
    if not optional_bounded_printable_string(
        checkpoint.get("current_phase"), MAX_PHASE_LENGTH
    ) or not optional_bounded_printable_string(
        checkpoint.get("next_phase"), MAX_PHASE_LENGTH
    ):
        raise RegistryError("CHECKPOINT_PHASE_INVALID")
    canonical_handoff = checkpoint.get("canonical_handoff")
    try:
        canonical_handoff_matches = isinstance(
            canonical_handoff, str
        ) and canonical_handoff == str(handoff_path)
    except (OSError, RuntimeError, TypeError, ValueError):
        canonical_handoff_matches = False
    if not canonical_handoff_matches:
        raise RegistryError("CANONICAL_PAIR_MISMATCH")
    scopes = normalize_resource_scopes(resource_scopes)
    checkpoint_pickup = checkpoint.get("pickup")
    if checkpoint_pickup is not None:
        if not isinstance(checkpoint_pickup, dict):
            raise RegistryError("PICKUP_METADATA_MISMATCH")
        recorded_scopes = checkpoint_pickup.get("resource_scopes")
        if not isinstance(recorded_scopes, list) or not all(
            isinstance(value, str) for value in recorded_scopes
        ):
            raise RegistryError("PICKUP_METADATA_MISMATCH")
        try:
            normalized_recorded_scopes = normalize_resource_scopes(recorded_scopes)
        except RegistryError as exc:
            raise RegistryError("PICKUP_METADATA_MISMATCH") from exc
        if (
            checkpoint_pickup.get("track_id") != track_id
            or recorded_scopes != normalized_recorded_scopes
            or normalized_recorded_scopes != scopes
        ):
            raise RegistryError("PICKUP_METADATA_MISMATCH")
    handoff_hash = hashlib.sha256(handoff_bytes).hexdigest()
    checkpoint_hash = hashlib.sha256(checkpoint_bytes).hexdigest()
    checkpoint_id = checkpoint_identity(checkpoint, checkpoint_hash)
    coordinate = PackageCoordinate(track_id, checkpoint_id)
    selector = coordinate.selector
    quarantine_templates = quarantine_event_templates(
        coordinate=coordinate,
        handoff_sha256=handoff_hash,
        checkpoint_sha256=checkpoint_hash,
    )
    quarantine_template_hashes = {
        reason_code: hashlib.sha256(data).hexdigest()
        for reason_code, data in quarantine_templates.items()
    }
    published_at = utc_now()
    track_root = registry_root / "tracks" / track_id
    packages_root = track_root / "packages"
    package_path = coordinate.package_path(registry_root)

    with registry_lock(registry_root):
        index = load_index(registry_root)
        if not publication_scaffold_matches(registry_root, coordinate, index):
            reconcile_mutation(
                registry_root=registry_root,
                index=index,
                gitleaks_path=gitleaks_path,
            )
        track_entry = index["tracks"].get(track_id)
        if track_entry is not None:
            if not isinstance(track_entry, dict):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            if track_entry.get("resource_scopes") != scopes:
                raise RegistryError("TRACK_RESOURCE_SCOPE_CHANGED")
            if track_entry.get("active_claim") is not None:
                raise RegistryError("TRACK_ACTIVE_CLAIM", exit_code=3)
        if package_path.exists() or package_path.is_symlink():
            if not isinstance(track_entry, dict):
                raise RegistryError("PACKAGE_DESTINATION_CHANGED", exit_code=3)
            package_entry = package_entry_for(track_entry, checkpoint_id)
            try:
                package = load_verified_package(package_path, package_entry)
            except RegistryError as exc:
                if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                    raise
                quarantine_package(
                    registry_root=registry_root,
                    index=index,
                    track=track_entry,
                    coordinate=coordinate,
                    reason_code="PACKAGE_ARTIFACT_DRIFT",
                )
                raise
            if (
                package.get("handoff_sha256") == handoff_hash
                and package.get("checkpoint_sha256") == checkpoint_hash
                and package.get("selector") == selector
            ):
                repeat_destinations = {
                    path: capture_mutable_destination(
                        path,
                        parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                        invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                    )
                    for path in (
                        track_root / "track.json",
                        registry_root / "index.json",
                    )
                }
                try:
                    run_secret_scan(package_path, gitleaks_path)
                    package = load_verified_package(package_path, package_entry)
                except RegistryError as exc:
                    quarantine_reason = (
                        "SENSITIVE_DATA_SCAN_FAILED"
                        if exc.reason_code
                        in {"SENSITIVE_DATA_SCAN_FAILED", "SECRET_SCANNER_UNAVAILABLE"}
                        else exc.reason_code
                    )
                    if quarantine_reason in PACKAGE_QUARANTINE_REASONS:
                        quarantine_package(
                            registry_root=registry_root,
                            index=index,
                            track=track_entry,
                            coordinate=coordinate,
                            reason_code=quarantine_reason,
                            destination_expectations=repeat_destinations,
                        )
                        try:
                            reconcile_mutation(
                                registry_root=registry_root,
                                index=index,
                                gitleaks_path=gitleaks_path,
                            )
                        except RegistryError as closure_error:
                            if closure_error.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                                raise closure_error from exc
                    raise
                require_publication_sources_unchanged(
                    handoff_path=handoff_path,
                    checkpoint_path=checkpoint_path,
                    handoff_hash=handoff_hash,
                    checkpoint_hash=checkpoint_hash,
                )
                reconcile_mutation(
                    registry_root=registry_root,
                    index=index,
                    gitleaks_path=gitleaks_path,
                )
                package = load_verified_package(package_path, package_entry)
                require_publication_sources_unchanged(
                    handoff_path=handoff_path,
                    checkpoint_path=checkpoint_path,
                    handoff_hash=handoff_hash,
                    checkpoint_hash=checkpoint_hash,
                )
                return package_summary(
                    package,
                    package_path,
                    state=package_entry.get("state"),
                )
            raise RegistryError("CHECKPOINT_ID_COLLISION")

        previous_checkpoint_id: Optional[str] = None
        previous_package_hash: Optional[str] = None
        if track_entry is not None:
            previous_checkpoint_id = track_entry.get("latest_checkpoint_id")
            if not isinstance(previous_checkpoint_id, str):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            previous_package_hash = package_entry_for(
                track_entry, previous_checkpoint_id
            ).get("package_sha256")
            if (
                not isinstance(previous_package_hash, str)
                or SHA256_RE.fullmatch(previous_package_hash) is None
            ):
                raise RegistryError("REGISTRY_INDEX_INVALID")

        tracks_root = registry_root / "tracks"
        created_directories: list[OwnedDirectory] = []
        view_destinations: Dict[Path, MutableDestination] = {}
        temporary: Optional[Path] = None
        package_install: Optional[DirectoryInstall] = None
        temporary_ownership: Optional[OwnedDirectory] = None
        staging_installs: list[ImmutableInstall] = []
        publication_error: Optional[BaseException] = None
        try:
            for path in (tracks_root, track_root, packages_root):
                created = secure_directory(
                    path,
                    reason_code="TRANSACTION_ROLLBACK_FAILED",
                )
                if created is not None:
                    created_directories.append(created)
            view_destinations = {
                path: capture_mutable_destination(
                    path,
                    parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                    invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                )
                for path in (track_root / "track.json", registry_root / "index.json")
            }
            temporary_ownership = create_owned_temporary_directory(
                packages_root,
                ".{}-".format(checkpoint_id),
                "TRANSACTION_ROLLBACK_FAILED",
            )
            temporary = temporary_ownership.path
            staging_installs.append(
                write_immutable_bytes(temporary / "handoff.md", handoff_bytes)
            )
            staging_installs.append(
                write_immutable_bytes(temporary / "checkpoint.json", checkpoint_bytes)
            )
            if (
                sha256_file(temporary / "handoff.md") != handoff_hash
                or sha256_file(temporary / "checkpoint.json") != checkpoint_hash
            ):
                raise RegistryError("SOURCE_CHANGED_DURING_PUBLICATION", exit_code=3)
            package = {
                "schema_version": PACKAGE_SCHEMA_VERSION,
                "track_id": track_id,
                "checkpoint_id": checkpoint_id,
                "selector": selector,
                "published_state": PackageState.AVAILABLE.value,
                "published_at": published_at,
                "checkpoint_generated_at": checkpoint.get("generated_at"),
                "current_phase": checkpoint.get("current_phase"),
                "next_phase": checkpoint.get("next_phase"),
                "resource_scopes": scopes,
                "source_handoff": str(handoff_path),
                "source_checkpoint": str(checkpoint_path),
                "handoff_sha256": handoff_hash,
                "checkpoint_sha256": checkpoint_hash,
                "previous_checkpoint_id": previous_checkpoint_id,
                "previous_package_sha256": previous_package_hash,
                "quarantine_template_sha256": quarantine_template_hashes,
            }
            package_install_token = write_immutable_bytes(
                temporary / "package.json", serialized_json(package)
            )
            staging_installs.append(package_install_token)
            package_hash = package_install_token.sha256
            template_installs: list[ImmutableInstall] = []
            for reason_code, data in quarantine_templates.items():
                template_path = temporary / "quarantine-template-{}.json".format(
                    reason_code.lower()
                )
                template_installs.append(write_immutable_bytes(template_path, data))
            pre_scan_registry = capture_registry_snapshot(
                registry_root, excluded_roots=(temporary, package_path)
            )
            try:
                run_secret_scan(temporary, gitleaks_path)
            finally:
                for template_install in reversed(template_installs):
                    remove_transaction_immutable(template_install)
            require_registry_snapshot(
                registry_root,
                pre_scan_registry,
                excluded_roots=(temporary, package_path),
            )
            sync_owned_directory(
                temporary,
                temporary_ownership.identity,
                "TRANSACTION_INSTALL_CHANGED",
                expected_mode=temporary_ownership.mode,
            )
            if (
                sha256_file(temporary / "handoff.md") != handoff_hash
                or sha256_file(temporary / "checkpoint.json") != checkpoint_hash
                or sha256_file(temporary / "package.json") != package_hash
                or sha256_file(
                    regular_file(handoff_path, "SOURCE_CHANGED_DURING_PUBLICATION")
                )
                != handoff_hash
                or sha256_file(
                    regular_file(checkpoint_path, "SOURCE_CHANGED_DURING_PUBLICATION")
                )
                != checkpoint_hash
            ):
                raise RegistryError("SOURCE_CHANGED_DURING_PUBLICATION", exit_code=3)
            package_install = install_directory_noreplace(temporary, package_path)
            sync_owned_directory(
                packages_root,
                package_install.parent_identity,
                "TRANSACTION_INSTALL_CHANGED",
                expected_mode=package_install.parent_mode,
            )
        except BaseException as exc:
            if package_install is not None and not (
                isinstance(exc, RegistryError)
                and exc.reason_code == "TRANSACTION_ROLLBACK_FAILED"
            ):
                try:
                    rollback_directory_install(package_install)
                except RegistryError as rollback_error:
                    raise rollback_error from exc
            publication_error = exc
        finally:
            if temporary is not None and (temporary.exists() or temporary.is_symlink()):
                if temporary_ownership is None:
                    raise RegistryError("TRANSACTION_ROLLBACK_FAILED", exit_code=3)
                for staging_install in reversed(staging_installs):
                    remove_transaction_immutable(staging_install)
                remove_owned_empty_directories((temporary_ownership,))
            if not package_path.exists() and not package_path.is_symlink():
                remove_owned_empty_directories(reversed(created_directories))

        if publication_error is not None:
            if (
                isinstance(publication_error, RegistryError)
                and publication_error.reason_code == "PACKAGE_ARTIFACT_DRIFT"
            ):
                try:
                    reconcile_mutation(
                        registry_root=registry_root,
                        index=index,
                        gitleaks_path=gitleaks_path,
                    )
                except RegistryError as closure_error:
                    if closure_error.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                        raise closure_error from publication_error
            raise publication_error

        if track_entry is None:
            track_entry = {
                "track_id": track_id,
                "resource_scopes": scopes,
                "latest_checkpoint_id": checkpoint_id,
                "packages": {},
                "active_claim": None,
                "updated_at": published_at,
            }
        packages = track_entry.get("packages")
        if not isinstance(packages, dict):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        for prior in packages.values():
            if not isinstance(prior, dict):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            prior["state"] = (
                PackageState.NEEDS_REVIEW.value
                if prior.get("quarantine_reason_code") in PACKAGE_QUARANTINE_REASONS
                else PackageState.SUPERSEDED.value
            )
        packages[checkpoint_id] = {
            "state": PackageState.AVAILABLE.value,
            "selector": selector,
            "package_sha256": package_hash,
            "handoff_sha256": handoff_hash,
            "checkpoint_sha256": checkpoint_hash,
            "previous_checkpoint_id": previous_checkpoint_id,
            "previous_package_sha256": previous_package_hash,
            "quarantine_template_sha256": quarantine_template_hashes,
            "latest_receipt_id": None,
            "quarantine_reason_code": None,
            "quarantine_event_sha256": None,
        }
        track_entry["latest_checkpoint_id"] = checkpoint_id
        track_entry["updated_at"] = published_at
        index["tracks"][track_id] = track_entry
        index["updated_at"] = published_at
        if package_install is None:
            raise RegistryError("PACKAGE_INSTALL_FAILED", exit_code=3)
        try:
            guarded_immutables = capture_registry_immutable_guards(
                registry_root=registry_root,
                index=index,
            )
            commit_file_transaction(
                registry_root=registry_root,
                immutable_writes=(),
                mutable_writes=(
                    MutableWrite(
                        path=track_root / "track.json",
                        payload=track_entry,
                        parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                        invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                        expected_destination=view_destinations[
                            track_root / "track.json"
                        ],
                    ),
                    MutableWrite(
                        path=registry_root / "index.json",
                        payload=index,
                        parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                        invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                        expected_destination=view_destinations[
                            registry_root / "index.json"
                        ],
                    ),
                ),
                guarded_directory_installs=(package_install,),
                guarded_immutable_installs=guarded_immutables,
            )
        except BaseException as exc:
            if (
                isinstance(exc, RegistryError)
                and exc.reason_code == "TRANSACTION_ROLLBACK_FAILED"
            ):
                raise
            try:
                if package_install is not None:
                    rollback_directory_install(package_install)
                remove_owned_empty_directories(reversed(created_directories))
            except RegistryError as rollback_error:
                raise rollback_error from exc
            raise
        return package_summary(
            package, package_path, state=PackageState.AVAILABLE.value
        )


def parse_selector(selector: str) -> PackageCoordinate:
    parts = selector.split("@")
    if len(parts) != 2:
        raise RegistryError("PICKUP_SELECTOR_INVALID")
    track_id, checkpoint_id = parts
    validate_track_id(track_id)
    if CHECKPOINT_ID_RE.fullmatch(checkpoint_id) is None:
        raise RegistryError("PICKUP_SELECTOR_INVALID")
    return PackageCoordinate(track_id, checkpoint_id)


def new_receipt_id(timestamp: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "")
    if compact.endswith("Z"):
        compact = compact[:-1] + "Z"
    return "tp-{}-{}".format(compact, secrets.token_hex(16))


def receipt_id_exists(
    registry_root: Path,
    index: Dict[str, Any],
    receipt_id: str,
) -> bool:
    tracks = index.get("tracks")
    receipts = index.get("receipts")
    if not isinstance(tracks, dict) or not isinstance(receipts, dict):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    if receipt_id in receipts:
        return True
    tracks_root = registry_root / "tracks"
    try:
        if not tracks_root.exists():
            if tracks_root.is_symlink():
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            return False
        on_disk_tracks = {child.name for child in tracks_root.iterdir()}
        if not on_disk_tracks <= set(tracks):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        for track_id in tracks:
            receipts_root = tracks_root / track_id / "receipts"
            if not receipts_root.exists():
                if receipts_root.is_symlink():
                    raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
                continue
            metadata = receipts_root.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != REGISTRY_DIRECTORY_MODE
            ):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            prefix = "{}-r".format(receipt_id)
            if any(child.name.startswith(prefix) for child in receipts_root.iterdir()):
                return True
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    return False


def allocate_receipt_id(
    registry_root: Path,
    index: Dict[str, Any],
    timestamp: str,
) -> str:
    for _ in range(64):
        candidate = new_receipt_id(timestamp)
        if not receipt_id_exists(registry_root, index, candidate):
            return candidate
    raise RegistryError("RECEIPT_ID_UNAVAILABLE", exit_code=3)


def package_entry_for(track: Dict[str, Any], checkpoint_id: str) -> Dict[str, Any]:
    packages = track.get("packages")
    if not isinstance(packages, dict):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    entry = packages.get(checkpoint_id)
    if not isinstance(entry, dict):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    return entry


def lifecycle_predecessor(
    package_entry: Dict[str, Any], index: Dict[str, Any]
) -> tuple[Optional[str], Optional[str]]:
    receipt_id = package_entry.get("latest_receipt_id")
    if receipt_id is None:
        return None, None
    if not isinstance(receipt_id, str):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    receipt_entry = index.get("receipts", {}).get(receipt_id)
    if not isinstance(receipt_entry, dict):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    receipt_hash = receipt_entry.get("latest_receipt_sha256")
    if not isinstance(receipt_hash, str) or SHA256_RE.fullmatch(receipt_hash) is None:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    return receipt_id, receipt_hash


def build_initial_receipt(
    *,
    registry_root: Path,
    timestamp: str,
    receipt_id: str,
    coordinate: PackageCoordinate,
    invocation: InvocationContext,
    artifacts: Dict[str, Any],
    previous_lifecycle_receipt_id: Optional[str],
    previous_lifecycle_receipt_sha256: Optional[str],
) -> Dict[str, Any]:
    expected_workspace, expected_compatibility = registry_invocation_bindings(
        registry_root
    )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "revision": 1,
        "previous_receipt_sha256": None,
        "previous_lifecycle_receipt_id": previous_lifecycle_receipt_id,
        "previous_lifecycle_receipt_sha256": previous_lifecycle_receipt_sha256,
        "event": ReceiptEvent.CLAIMED.value,
        "status": "VERIFYING",
        "terminal": False,
        "drift": DriftClass.UNKNOWN.value,
        "started_at": timestamp,
        "updated_at": timestamp,
        "completed_at": None,
        "workspace": str(expected_workspace),
        "pickup": {
            "track_id": coordinate.track_id,
            "checkpoint_id": coordinate.checkpoint_id,
            "selector": coordinate.selector,
        },
        "invocation": invocation.receipt_value(),
        "scope": {
            "operation": "READ_VERIFY_RECONSTRUCT",
            "phase_authorized": False,
            "allowed_writes": [
                str(registry_root.resolve()),
                str(expected_compatibility),
            ],
        },
        "artifacts": artifacts,
        "last_completed_gate": Gate.INVOCATION_RECORDED.value,
        "transition_evidence": [],
        "reason_code": None,
        "reason": None,
        "validation": {"json": True, "secret_scan": "PASS"},
    }


def artifact_record(
    path: Path,
    *,
    checkpoint: bool = False,
    expected_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    path = regular_file(path, "PACKAGE_ARTIFACT_INVALID")
    data = read_regular_bytes(path, "PACKAGE_ARTIFACT_INVALID")
    observed_sha256 = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and observed_sha256 != expected_sha256:
        raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
    record: Dict[str, Any] = {
        "path": str(path),
        "present": True,
        "regular_file": True,
        "sha256": observed_sha256,
    }
    if checkpoint:
        value = json_object_from_bytes(data, "CHECKPOINT_INVALID")
        record.update(
            {
                "schema_version": value.get("schema_version"),
                "context_status": value.get("context_status"),
                "generated_at": value.get("generated_at"),
            }
        )
    return record


def artifact_drift_record(path: Path, expected_sha256: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "path": str(path),
        "expected_sha256": expected_sha256,
        "present": False,
        "regular_file": False,
        "observed_sha256": None,
    }
    try:
        resolved = regular_file(path, "PACKAGE_ARTIFACT_DRIFT")
        observed_sha256 = sha256_file(resolved, "PACKAGE_ARTIFACT_DRIFT")
    except RegistryError:
        return record
    record.update(
        {
            "path": str(resolved),
            "present": True,
            "regular_file": True,
            "observed_sha256": observed_sha256,
        }
    )
    return record


def verify_handoff(metadata, selected, handoff_bytes=None):
    digest = None if handoff_bytes is None else hashlib.sha256(handoff_bytes).hexdigest()
    checks = {}
    for name, expected, observed in (
        ("identity", selected, metadata.get("selector")),
        ("integrity", metadata.get("handoff_sha256"), digest),
    ):
        if not all(isinstance(value, str) and value for value in (expected, observed)):
            checks[name] = "UNKNOWN"
        else:
            checks[name] = "PASS" if expected == observed else "FAIL"

    failed = "FAIL" in checks.values()
    unknown = "UNKNOWN" in checks.values()
    return {
        "status": "REVIEW_REQUIRED" if failed else "BLOCKED" if unknown else "PASS",
        "drift": "MATERIAL" if failed else "UNKNOWN" if unknown else "NONE",
        "checks": checks,
        "live_state": "UNKNOWN",
        "phase_authorized": False,
    }, 1 if failed else 2 if unknown else 0


def verify_package_payload(
    package_path: Path, package: Dict[str, Any], selected: str
) -> None:
    handoff = regular_file(package_path / "handoff.md", "PACKAGE_ARTIFACT_DRIFT")
    handoff_bytes = read_regular_bytes(
        handoff, "PACKAGE_ARTIFACT_DRIFT", expected_mode=REGISTRY_FILE_MODE
    )
    _, exit_code = verify_handoff(package, selected, handoff_bytes)
    if exit_code:
        raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
    checkpoint = regular_file(package_path / "checkpoint.json", "PACKAGE_ARTIFACT_DRIFT")
    if sha256_file(
        checkpoint, "PACKAGE_ARTIFACT_DRIFT", expected_mode=REGISTRY_FILE_MODE
    ) != package.get("checkpoint_sha256"):
        raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)


def load_verified_package(
    package_path: Path, package_entry: Dict[str, Any]
) -> Dict[str, Any]:
    manifest_path = regular_file(
        package_path / "package.json", "PACKAGE_ARTIFACT_DRIFT"
    )
    expected_manifest_hash = package_entry.get("package_sha256")
    package, observed_manifest_hash = read_hashed_json_object(
        manifest_path,
        "PACKAGE_ARTIFACT_DRIFT",
        expected_mode=REGISTRY_FILE_MODE,
    )
    if (
        not isinstance(expected_manifest_hash, str)
        or observed_manifest_hash != expected_manifest_hash
    ):
        raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
    verify_package_payload(package_path, package, package_entry.get("selector"))
    return package


def quarantine_event_payload(
    *,
    coordinate: PackageCoordinate,
    handoff_sha256: str,
    checkpoint_sha256: str,
    reason_code: str,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "event": "PACKAGE_QUARANTINED",
        "track_id": coordinate.track_id,
        "checkpoint_id": coordinate.checkpoint_id,
        "selector": coordinate.selector,
        "handoff_sha256": handoff_sha256,
        "checkpoint_sha256": checkpoint_sha256,
        "reason_code": reason_code,
        "phase_authorized": False,
        "validation": {
            "json": True,
            "secret_scan": "PREVALIDATED_AT_PUBLICATION",
        },
    }


def quarantine_event_templates(
    *,
    coordinate: PackageCoordinate,
    handoff_sha256: str,
    checkpoint_sha256: str,
) -> Dict[str, bytes]:
    return {
        reason_code: serialized_json(
            quarantine_event_payload(
                coordinate=coordinate,
                handoff_sha256=handoff_sha256,
                checkpoint_sha256=checkpoint_sha256,
                reason_code=reason_code,
            )
        )
        for reason_code in sorted(PACKAGE_QUARANTINE_REASONS)
    }


def validate_quarantine_event_payload(
    *,
    event: Any,
    coordinate: PackageCoordinate,
    package_entry: Dict[str, Any],
    reason_code: str,
) -> None:
    expected_keys = {
        "schema_version",
        "event",
        "track_id",
        "checkpoint_id",
        "selector",
        "handoff_sha256",
        "checkpoint_sha256",
        "reason_code",
        "phase_authorized",
        "validation",
    }
    if (
        not isinstance(event, dict)
        or set(event) != expected_keys
        or not exact_integer(event.get("schema_version"), 1)
        or event.get("event") != "PACKAGE_QUARANTINED"
        or event.get("track_id") != coordinate.track_id
        or event.get("checkpoint_id") != coordinate.checkpoint_id
        or event.get("selector") != coordinate.selector
        or event.get("handoff_sha256") != package_entry.get("handoff_sha256")
        or event.get("checkpoint_sha256") != package_entry.get("checkpoint_sha256")
        or event.get("reason_code") != reason_code
        or event.get("phase_authorized") is not False
        or event.get("validation")
        != {"json": True, "secret_scan": "PREVALIDATED_AT_PUBLICATION"}
        or forbidden_keys(event)
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)


def validate_quarantine_event(
    *,
    registry_root: Path,
    coordinate: PackageCoordinate,
    package_entry: Dict[str, Any],
) -> None:
    reason_code = package_entry.get("quarantine_reason_code")
    expected_hash = package_entry.get("quarantine_event_sha256")
    template_hashes = package_entry.get("quarantine_template_sha256")
    if (
        reason_code not in PACKAGE_QUARANTINE_REASONS
        or not isinstance(expected_hash, str)
        or SHA256_RE.fullmatch(expected_hash) is None
        or not isinstance(template_hashes, dict)
        or template_hashes.get(reason_code) != expected_hash
    ):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    event_path = coordinate.quarantine_event_path(registry_root)
    regular_file(event_path, "ORPHANED_CLAIM_REVIEW_REQUIRED")
    event, observed_hash = read_hashed_json_object(
        event_path,
        "ORPHANED_CLAIM_REVIEW_REQUIRED",
        expected_mode=REGISTRY_FILE_MODE,
    )
    if observed_hash != expected_hash:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    validate_quarantine_event_payload(
        event=event,
        coordinate=coordinate,
        package_entry=package_entry,
        reason_code=reason_code,
    )


def prepare_quarantine_event(
    *,
    coordinate: PackageCoordinate,
    package_entry: Dict[str, Any],
    reason_code: str,
) -> bytes:
    templates = package_entry.get("quarantine_template_sha256")
    if (
        reason_code not in PACKAGE_QUARANTINE_REASONS
        or not isinstance(templates, dict)
        or not isinstance(templates.get(reason_code), str)
    ):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    payload = quarantine_event_payload(
        coordinate=coordinate,
        handoff_sha256=package_entry.get("handoff_sha256"),
        checkpoint_sha256=package_entry.get("checkpoint_sha256"),
        reason_code=reason_code,
    )
    data = serialized_json(payload)
    if hashlib.sha256(data).hexdigest() != templates[reason_code]:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    return data


def quarantine_package(
    *,
    registry_root: Path,
    index: Dict[str, Any],
    track: Dict[str, Any],
    coordinate: PackageCoordinate,
    reason_code: str,
    destination_expectations: Optional[Dict[Path, MutableDestination]] = None,
    excluded_guard_coordinates: Sequence[PackageCoordinate] = (),
) -> None:
    if reason_code not in PACKAGE_QUARANTINE_REASONS:
        raise RegistryError("REGISTRY_INDEX_INVALID")
    package_entry = package_entry_for(track, coordinate.checkpoint_id)
    if package_entry.get("quarantine_reason_code") is not None:
        validate_quarantine_event(
            registry_root=registry_root,
            coordinate=coordinate,
            package_entry=package_entry,
        )
        return
    prepared_event = prepare_quarantine_event(
        coordinate=coordinate,
        package_entry=package_entry,
        reason_code=reason_code,
    )
    event = json_object_from_bytes(prepared_event, "SERIALIZED_JSON_INVALID")
    validate_quarantine_event_payload(
        event=event,
        coordinate=coordinate,
        package_entry=package_entry,
        reason_code=reason_code,
    )
    event_path = coordinate.quarantine_event_path(registry_root)
    event_hash = hashlib.sha256(prepared_event).hexdigest()
    timestamp = utc_now()
    track_root = registry_root / "tracks" / coordinate.track_id
    if destination_expectations is None:
        destination_expectations = {
            path: capture_mutable_destination(
                path,
                parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
            )
            for path in (track_root / "track.json", registry_root / "index.json")
        }
    guard_exclusions = set(excluded_guard_coordinates)
    if reason_code == "PACKAGE_ARTIFACT_DRIFT":
        guard_exclusions.add(coordinate)
    guarded_immutables = capture_registry_immutable_guards(
        registry_root=registry_root,
        index=index,
        pending_paths=(event_path,),
        excluded_coordinates=tuple(guard_exclusions),
    )
    package_entry["state"] = PackageState.NEEDS_REVIEW.value
    package_entry["quarantine_reason_code"] = reason_code
    package_entry["quarantine_event_sha256"] = event_hash
    track["updated_at"] = timestamp
    index["updated_at"] = timestamp
    commit_file_transaction(
        registry_root=registry_root,
        immutable_writes=(
            ImmutableWrite(
                path=event_path,
                data=prepared_event,
                existing_reason_code="IMMUTABLE_QUARANTINE_EXISTS",
                cleanup_empty_parent=True,
            ),
        ),
        mutable_writes=(
            MutableWrite(
                path=track_root / "track.json",
                payload=track,
                parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_destination=destination_expectations[
                    track_root / "track.json"
                ],
            ),
            MutableWrite(
                path=registry_root / "index.json",
                payload=index,
                parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
                invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_destination=destination_expectations[
                    registry_root / "index.json"
                ],
            ),
        ),
        guarded_immutable_installs=guarded_immutables,
    )


def persist_unclaimed_package_drift(
    *,
    registry_root: Path,
    compatibility_output: Path,
    index: Dict[str, Any],
    track: Dict[str, Any],
    coordinate: PackageCoordinate,
    invocation: InvocationContext,
    gitleaks_path: str,
    compatibility_destination: MutableDestination,
) -> None:
    timestamp = utc_now()
    receipt_id = allocate_receipt_id(registry_root, index, timestamp)
    package_path = coordinate.package_path(registry_root)
    package_entry = package_entry_for(track, coordinate.checkpoint_id)
    previous_receipt_id, previous_receipt_hash = lifecycle_predecessor(
        package_entry, index
    )
    receipt = build_initial_receipt(
        registry_root=registry_root,
        timestamp=timestamp,
        receipt_id=receipt_id,
        coordinate=coordinate,
        invocation=invocation,
        artifacts={
            "skill": artifact_record(invocation.skill_file),
            "package": artifact_drift_record(
                package_path / "package.json",
                package_entry.get("package_sha256"),
            ),
            "handoff": artifact_drift_record(
                package_path / "handoff.md", package_entry.get("handoff_sha256")
            ),
            "checkpoint": artifact_drift_record(
                package_path / "checkpoint.json",
                package_entry.get("checkpoint_sha256"),
            ),
        },
        previous_lifecycle_receipt_id=previous_receipt_id,
        previous_lifecycle_receipt_sha256=previous_receipt_hash,
    )
    receipt.update(
        {
            "event": ReceiptEvent.COMPLETED.value,
            "status": TerminalStatus.REVIEW_REQUIRED.value,
            "terminal": True,
            "drift": DriftClass.MATERIAL.value,
            "completed_at": timestamp,
            "reason_code": "PACKAGE_ARTIFACT_DRIFT",
            "reason": "An immutable pickup package artifact changed before claim.",
        }
    )
    receipt_path = (
        registry_root
        / "tracks"
        / coordinate.track_id
        / "receipts"
        / "{}-r0001.json".format(receipt_id)
    )
    additional_immutables: list[ImmutableWrite] = []
    quarantine_update: Optional[tuple[str, str]] = None
    if package_entry.get("quarantine_reason_code") is None:
        event_data = prepare_quarantine_event(
            coordinate=coordinate,
            package_entry=package_entry,
            reason_code="PACKAGE_ARTIFACT_DRIFT",
        )
        event_hash = hashlib.sha256(event_data).hexdigest()
        quarantine_update = ("PACKAGE_ARTIFACT_DRIFT", event_hash)
        additional_immutables.append(
            ImmutableWrite(
                path=coordinate.quarantine_event_path(registry_root),
                data=event_data,
                existing_reason_code="IMMUTABLE_QUARANTINE_EXISTS",
                cleanup_empty_parent=True,
            )
        )
    else:
        validate_quarantine_event(
            registry_root=registry_root,
            coordinate=coordinate,
            package_entry=package_entry,
        )
    destination_expectations = capture_receipt_destinations(
        registry_root=registry_root,
        track_id=coordinate.track_id,
        compatibility_output=compatibility_output,
        compatibility_destination=compatibility_destination,
        include_claim=False,
    )
    validate_receipt_bindings(
        registry_root=registry_root,
        coordinate=coordinate,
        package_entry=package_entry,
        package_manifest=None,
        receipt=receipt,
    )
    try:
        receipt_data = prepare_receipt_data(
            registry_root=registry_root,
            receipt_path=receipt_path,
            receipt=receipt,
            gitleaks_path=gitleaks_path,
        )
    except RegistryError as exc:
        if exc.reason_code not in {
            "SENSITIVE_DATA_SCAN_FAILED",
            "SECRET_SCANNER_UNAVAILABLE",
            "PACKAGE_ARTIFACT_DRIFT",
        }:
            raise
        observed_compatibility = preflight_compatibility_output(compatibility_output)
        if observed_compatibility != compatibility_destination:
            raise RegistryError("COMPATIBILITY_OUTPUT_INVALID", exit_code=3) from exc
        observed_drift = reconcile_registry_views(
            registry_root,
            index,
            collect_artifact_drift=True,
        )
        quarantine_package(
            registry_root=registry_root,
            index=index,
            track=track,
            coordinate=coordinate,
            reason_code="PACKAGE_ARTIFACT_DRIFT",
            destination_expectations=destination_expectations,
            excluded_guard_coordinates=observed_drift,
        )
        return
    observed_drift = reconcile_registry_views(
        registry_root,
        index,
        collect_artifact_drift=True,
    )
    if quarantine_update is not None:
        (
            package_entry["quarantine_reason_code"],
            package_entry["quarantine_event_sha256"],
        ) = quarantine_update
    receipt_hash = hashlib.sha256(receipt_data).hexdigest()
    package_entry["state"] = PackageState.NEEDS_REVIEW.value
    package_entry["latest_receipt_id"] = receipt_id
    track["active_claim"] = None
    track["updated_at"] = timestamp
    index["receipts"][receipt_id] = {
        "track_id": coordinate.track_id,
        "checkpoint_id": coordinate.checkpoint_id,
        "latest_revision": 1,
        "latest_receipt_sha256": receipt_hash,
        "latest_receipt_path": str(receipt_path),
        "terminal_status": TerminalStatus.REVIEW_REQUIRED.value,
    }
    index["updated_at"] = timestamp
    persist_receipt_event(
        registry_root=registry_root,
        compatibility_output=compatibility_output,
        track_id=coordinate.track_id,
        receipt=receipt,
        receipt_path=receipt_path,
        receipt_data=receipt_data,
        claim_view=None,
        track_view=track,
        index_view=index,
        destination_expectations=destination_expectations,
        additional_immutables=additional_immutables,
        excluded_guard_coordinates=observed_drift,
    )


def close_unclaimed_artifact_drift(
    *,
    registry_root: Path,
    compatibility_output: Path,
    compatibility_destination: MutableDestination,
    index: Dict[str, Any],
    track: Dict[str, Any],
    coordinate: PackageCoordinate,
    invocation: InvocationContext,
    gitleaks_path: str,
) -> None:
    try:
        persist_unclaimed_package_drift(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            index=index,
            track=track,
            coordinate=coordinate,
            invocation=invocation,
            gitleaks_path=gitleaks_path,
            compatibility_destination=compatibility_destination,
        )
    except RegistryError as exc:
        if exc.reason_code not in {
            "SENSITIVE_DATA_SCAN_FAILED",
            "SECRET_SCANNER_UNAVAILABLE",
        }:
            raise


def validate_fresh_invocation(fresh_task: str, freshness_basis: str) -> None:
    if fresh_task != "YES" or freshness_basis != "FIRST_SUBSTANTIVE_USER_TURN":
        raise RegistryError("FRESH_TASK_REQUIRED")


def validate_transition_evidence_object(
    evidence: Any, expected_gate: Optional[str]
) -> None:
    if (
        not isinstance(evidence, dict)
        or set(evidence)
        != {
            "schema_version",
            "gate",
            "status",
            "observed_at",
            "checks",
        }
        or not exact_integer(evidence.get("schema_version"), 1)
        or (expected_gate is not None and evidence.get("gate") != expected_gate)
        or evidence.get("gate") not in GATES
        or evidence.get("status") != "PASS"
    ):
        raise RegistryError("TRANSITION_EVIDENCE_INVALID")
    require_rfc3339(evidence.get("observed_at"), "TRANSITION_EVIDENCE_INVALID")
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        raise RegistryError("TRANSITION_EVIDENCE_INVALID")
    for check in checks:
        if (
            not isinstance(check, dict)
            or not {"name", "status"}.issubset(check)
            or not set(check).issubset({"name", "status", "detail"})
            or not bounded_printable_string(check.get("name"), MAX_EVIDENCE_NAME_LENGTH)
            or check.get("status") != "PASS"
            or (
                "detail" in check
                and not bounded_printable_string(
                    check.get("detail"), MAX_EVIDENCE_DETAIL_LENGTH
                )
            )
        ):
            raise RegistryError("TRANSITION_EVIDENCE_INVALID")


def load_transition_evidence(path: Optional[Path], gate: str) -> Dict[str, Any]:
    if path is None:
        raise RegistryError("TRANSITION_EVIDENCE_REQUIRED")
    evidence = read_json_object(path, "TRANSITION_EVIDENCE_INVALID")
    if forbidden_keys(evidence):
        raise RegistryError("PRIVATE_RUNTIME_IDENTIFIER_FIELD")
    validate_transition_evidence_object(evidence, gate)
    return evidence


def resolve_package_selection(
    index: Dict[str, Any], selector: Optional[str]
) -> tuple[PackageCoordinate, Dict[str, Any], str]:
    if selector is None:
        available: list[tuple[PackageCoordinate, Dict[str, Any], str]] = []
        for track_id, track in index["tracks"].items():
            if not isinstance(track, dict) or not isinstance(
                track.get("packages"), dict
            ):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            for checkpoint_id, entry in track["packages"].items():
                if (
                    isinstance(entry, dict)
                    and entry.get("state") == PackageState.AVAILABLE.value
                ):
                    available.append(
                        (
                            PackageCoordinate(track_id, checkpoint_id),
                            track,
                            PackageState.AVAILABLE.value,
                        )
                    )
        if not available:
            raise RegistryError("NO_AVAILABLE_PICKUP")
        if len(available) != 1:
            raise RegistryError("PICKUP_SELECTION_REQUIRED")
        return available[0]
    coordinate = parse_selector(selector)
    track = index["tracks"].get(coordinate.track_id)
    if not isinstance(track, dict) or not isinstance(track.get("packages"), dict):
        raise RegistryError("PICKUP_NOT_FOUND")
    entry = track["packages"].get(coordinate.checkpoint_id)
    if not isinstance(entry, dict):
        raise RegistryError("PICKUP_NOT_FOUND")
    state = entry.get("state")
    if not isinstance(state, str):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    return coordinate, track, state


def require_available_package_state(state: str) -> None:
    if state in {PackageState.CLAIMED.value, PackageState.OPENING.value}:
        raise RegistryError("ALREADY_CLAIMED", exit_code=3)
    if state == PackageState.SUPERSEDED.value:
        raise RegistryError("PICKUP_SUPERSEDED", exit_code=3)
    if state != PackageState.AVAILABLE.value:
        raise RegistryError("PICKUP_NOT_AVAILABLE", exit_code=3)


def validate_claim_view_schema(claim: Dict[str, Any]) -> None:
    try:
        active = claim.get("active")
        keys = frozenset(claim)
        if active is True:
            valid_keys = keys == ACTIVE_CLAIM_KEYS
        elif active is False:
            valid_keys = keys in {CLOSED_CLAIM_KEYS, RELEASED_CLAIM_KEYS}
        else:
            valid_keys = False
        track_id = claim.get("track_id")
        checkpoint_id = claim.get("checkpoint_id")
        receipt_id = claim.get("receipt_id")
        revision = claim.get("latest_revision")
        receipt_sha256 = claim.get("latest_receipt_sha256")
        receipt_path = claim.get("latest_receipt_path")
        if (
            not valid_keys
            or forbidden_keys(claim)
            or not exact_integer(claim.get("schema_version"), REGISTRY_SCHEMA_VERSION)
            or not isinstance(track_id, str)
            or TRACK_ID_RE.fullmatch(track_id) is None
            or not isinstance(checkpoint_id, str)
            or CHECKPOINT_ID_RE.fullmatch(checkpoint_id) is None
            or not isinstance(receipt_id, str)
            or RECEIPT_ID_RE.fullmatch(receipt_id) is None
            or not exact_integer(revision)
            or revision < 1
            or not isinstance(receipt_sha256, str)
            or SHA256_RE.fullmatch(receipt_sha256) is None
            or not isinstance(receipt_path, str)
            or not Path(receipt_path).is_absolute()
            or Path(receipt_path).name != "{}-r{:04d}.json".format(receipt_id, revision)
        ):
            raise ValueError
        require_rfc3339(claim.get("claimed_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
        if active is False:
            require_rfc3339(claim.get("closed_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
            if claim.get("terminal_status") not in {
                value.value for value in TerminalStatus
            }:
                raise ValueError
        if keys == RELEASED_CLAIM_KEYS:
            require_rfc3339(claim.get("released_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
            if claim.get("terminal_status") != TerminalStatus.ABORTED.value:
                raise ValueError
    except (TypeError, ValueError, RegistryError):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)


def valid_sha256_or_none(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and SHA256_RE.fullmatch(value) is not None
    )


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_terminal_reason(reason_code: Any, reason: Any) -> bool:
    return (
        isinstance(reason_code, str)
        and TERMINAL_REASON_CODE_RE.fullmatch(reason_code) is not None
        and isinstance(reason, str)
        and bool(reason)
        and reason == reason.strip()
        and len(reason) <= MAX_TERMINAL_REASON_LENGTH
        and reason.isprintable()
    )


def is_unclaimed_artifact_drift_receipt(receipt: Dict[str, Any]) -> bool:
    return (
        frozenset(receipt) == BASE_RECEIPT_KEYS
        and receipt.get("event") == ReceiptEvent.COMPLETED.value
        and exact_integer(receipt.get("revision"), 1)
        and receipt.get("status") == TerminalStatus.REVIEW_REQUIRED.value
        and receipt.get("terminal") is True
        and receipt.get("drift") == DriftClass.MATERIAL.value
        and receipt.get("last_completed_gate") == Gate.INVOCATION_RECORDED.value
        and receipt.get("transition_evidence") == []
        and receipt.get("reason_code") == "PACKAGE_ARTIFACT_DRIFT"
    )


def receipt_artifact_key_policy(receipt: Dict[str, Any]) -> Dict[str, frozenset[str]]:
    if is_unclaimed_artifact_drift_receipt(receipt):
        return {
            "skill": ARTIFACT_KEYS,
            "package": DRIFT_ARTIFACT_KEYS,
            "handoff": DRIFT_ARTIFACT_KEYS,
            "checkpoint": DRIFT_ARTIFACT_KEYS,
        }
    return {
        "skill": ARTIFACT_KEYS,
        "package": ARTIFACT_KEYS,
        "handoff": ARTIFACT_KEYS,
        "checkpoint": CHECKPOINT_ARTIFACT_KEYS,
    }


def released_receipt_from(
    previous: Dict[str, Any],
    *,
    revision: Any,
    previous_receipt_sha256: Any,
    updated_at: Any,
) -> Dict[str, Any]:
    released = copy.deepcopy(previous)
    released.update(
        {
            "revision": revision,
            "previous_receipt_sha256": previous_receipt_sha256,
            "event": ReceiptEvent.RELEASED.value,
            "updated_at": updated_at,
            "release_reason_code": "EXPLICIT_ABORT_RELEASE",
        }
    )
    return released


def validate_receipt_schema(receipt: Dict[str, Any]) -> None:
    try:
        keys = frozenset(receipt)
        revision = receipt.get("revision")
        event = receipt.get("event")
        status = receipt.get("status")
        terminal = receipt.get("terminal")
        drift = receipt.get("drift")
        last_gate = receipt.get("last_completed_gate")
        if (
            keys
            not in {BASE_RECEIPT_KEYS, TERMINAL_RECEIPT_KEYS, RELEASED_RECEIPT_KEYS}
            or forbidden_keys(receipt)
            or not exact_integer(receipt.get("schema_version"), RECEIPT_SCHEMA_VERSION)
            or not exact_integer(revision)
            or revision < 1
            or type(terminal) is not bool
            or not isinstance(receipt.get("receipt_id"), str)
            or RECEIPT_ID_RE.fullmatch(receipt["receipt_id"]) is None
            or not valid_sha256_or_none(receipt.get("previous_receipt_sha256"))
            or not optional_string(receipt.get("previous_lifecycle_receipt_id"))
            or not valid_sha256_or_none(
                receipt.get("previous_lifecycle_receipt_sha256")
            )
            or (
                (receipt.get("previous_lifecycle_receipt_id") is None)
                != (receipt.get("previous_lifecycle_receipt_sha256") is None)
            )
            or (
                receipt.get("previous_lifecycle_receipt_id") is not None
                and RECEIPT_ID_RE.fullmatch(receipt["previous_lifecycle_receipt_id"])
                is None
            )
            or event not in {value.value for value in ReceiptEvent}
            or not isinstance(status, str)
            or drift not in {value.value for value in DriftClass}
            or last_gate not in GATES
            or not isinstance(receipt.get("workspace"), str)
            or not Path(receipt["workspace"]).is_absolute()
            or not optional_string(receipt.get("reason_code"))
            or not optional_string(receipt.get("reason"))
        ):
            raise ValueError
        pickup = receipt.get("pickup")
        invocation = receipt.get("invocation")
        scope = receipt.get("scope")
        artifacts = receipt.get("artifacts")
        validation = receipt.get("validation")
        transition_evidence = receipt.get("transition_evidence")
        if (
            not isinstance(pickup, dict)
            or frozenset(pickup) != PICKUP_RECEIPT_KEYS
            or not isinstance(pickup.get("track_id"), str)
            or TRACK_ID_RE.fullmatch(pickup["track_id"]) is None
            or not isinstance(pickup.get("checkpoint_id"), str)
            or CHECKPOINT_ID_RE.fullmatch(pickup["checkpoint_id"]) is None
            or pickup.get("selector")
            != "{}@{}".format(pickup["track_id"], pickup["checkpoint_id"])
            or not isinstance(invocation, dict)
            or frozenset(invocation) != INVOCATION_RECEIPT_KEYS
            or invocation.get("fresh_task") != "YES"
            or invocation.get("freshness_basis") != "FIRST_SUBSTANTIVE_USER_TURN"
            or invocation.get("mode") not in {"MANUAL_SKILL_SELECTOR", "SLASH_COMMAND"}
            or not bounded_printable_string(invocation.get("model"), MAX_MODEL_LENGTH)
            or not bounded_printable_string(
                invocation.get("reasoning_effort"), MAX_REASONING_EFFORT_LENGTH
            )
            or not isinstance(scope, dict)
            or frozenset(scope) != SCOPE_RECEIPT_KEYS
            or scope.get("operation") != "READ_VERIFY_RECONSTRUCT"
            or scope.get("phase_authorized") is not False
            or not isinstance(scope.get("allowed_writes"), list)
            or not all(
                isinstance(value, str) and Path(value).is_absolute()
                for value in scope["allowed_writes"]
            )
            or not isinstance(artifacts, dict)
            or set(artifacts) != {"skill", "package", "handoff", "checkpoint"}
            or not isinstance(validation, dict)
            or set(validation) != {"json", "secret_scan"}
            or validation.get("json") is not True
            or validation.get("secret_scan")
            not in {"PASS", "PREVALIDATED_DERIVED_TERMINAL"}
            or (
                validation.get("secret_scan") == "PREVALIDATED_DERIVED_TERMINAL"
                and (
                    receipt.get("event") != ReceiptEvent.COMPLETED.value
                    or receipt.get("status") != TerminalStatus.REVIEW_REQUIRED.value
                    or receipt.get("terminal") is not True
                    or receipt.get("reason_code") != "PACKAGE_ARTIFACT_DRIFT"
                )
            )
            or not isinstance(transition_evidence, list)
        ):
            raise ValueError
        for evidence in transition_evidence:
            validate_transition_evidence_object(evidence, None)
        evidence_gates = [evidence["gate"] for evidence in transition_evidence]
        if (
            evidence_gates != list(GATES[1 : len(evidence_gates) + 1])
            or len(evidence_gates) > len(GATES) - 2
        ):
            raise ValueError
        expected_artifact_keys = receipt_artifact_key_policy(receipt)
        for name, record in artifacts.items():
            if (
                not isinstance(record, dict)
                or frozenset(record) != expected_artifact_keys[name]
            ):
                raise ValueError
            if (
                not isinstance(record.get("path"), str)
                or not Path(record["path"]).is_absolute()
                or type(record.get("present")) is not bool
                or type(record.get("regular_file")) is not bool
            ):
                raise ValueError
            if frozenset(record) == DRIFT_ARTIFACT_KEYS:
                if (
                    not isinstance(record.get("expected_sha256"), str)
                    or SHA256_RE.fullmatch(record["expected_sha256"]) is None
                    or not valid_sha256_or_none(record.get("observed_sha256"))
                    or (
                        record.get("present") is True
                        and (
                            record.get("regular_file") is not True
                            or record.get("observed_sha256") is None
                        )
                    )
                    or (
                        record.get("present") is False
                        and (
                            record.get("regular_file") is not False
                            or record.get("observed_sha256") is not None
                        )
                    )
                ):
                    raise ValueError
            else:
                if (
                    not isinstance(record.get("sha256"), str)
                    or SHA256_RE.fullmatch(record["sha256"]) is None
                    or record.get("present") is not True
                    or record.get("regular_file") is not True
                ):
                    raise ValueError
                if frozenset(record) == CHECKPOINT_ARTIFACT_KEYS:
                    if (
                        record.get("schema_version") is not None
                        and not exact_integer(record.get("schema_version"))
                    ) or record.get("context_status") != "READY":
                        raise ValueError
                    require_rfc3339(
                        record.get("generated_at"),
                        "ORPHANED_CLAIM_REVIEW_REQUIRED",
                    )
        require_rfc3339(receipt.get("started_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
        require_rfc3339(receipt.get("updated_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
        completed_at = receipt.get("completed_at")
        if completed_at is not None:
            require_rfc3339(completed_at, "ORPHANED_CLAIM_REVIEW_REQUIRED")
        if event == ReceiptEvent.CLAIMED.value:
            if (
                keys != BASE_RECEIPT_KEYS
                or revision != 1
                or receipt.get("previous_receipt_sha256") is not None
                or status != "VERIFYING"
                or terminal is not False
                or drift != DriftClass.UNKNOWN.value
                or receipt.get("updated_at") != receipt.get("started_at")
                or completed_at is not None
                or last_gate != Gate.INVOCATION_RECORDED.value
                or transition_evidence
                or receipt.get("reason_code") is not None
                or receipt.get("reason") is not None
            ):
                raise ValueError
        elif event == ReceiptEvent.GATE_ADVANCED.value:
            if (
                keys != BASE_RECEIPT_KEYS
                or revision != len(transition_evidence) + 1
                or not isinstance(receipt.get("previous_receipt_sha256"), str)
                or status != "VERIFYING"
                or terminal is not False
                or drift != DriftClass.UNKNOWN.value
                or completed_at is not None
                or not transition_evidence
                or last_gate != evidence_gates[-1]
                or receipt.get("reason_code") is not None
                or receipt.get("reason") is not None
            ):
                raise ValueError
        elif event == ReceiptEvent.COMPLETED.value:
            try:
                terminal_status = TerminalStatus(status)
                drift_class = DriftClass(drift)
            except ValueError as exc:
                raise ValueError from exc
            if (
                terminal is not True
                or completed_at is None
                or completed_at != receipt.get("updated_at")
                or drift_class not in TERMINAL_DRIFT_POLICY[terminal_status]
                or (
                    revision == 1 and receipt.get("previous_receipt_sha256") is not None
                )
                or (
                    revision > 1
                    and not isinstance(receipt.get("previous_receipt_sha256"), str)
                )
            ):
                raise ValueError
            if keys == BASE_RECEIPT_KEYS:
                if (
                    revision != 1
                    or status != TerminalStatus.REVIEW_REQUIRED.value
                    or drift != DriftClass.MATERIAL.value
                    or last_gate != Gate.INVOCATION_RECORDED.value
                    or transition_evidence
                    or receipt.get("reason_code") != "PACKAGE_ARTIFACT_DRIFT"
                ):
                    raise ValueError
            elif keys != TERMINAL_RECEIPT_KEYS:
                raise ValueError
            else:
                if (
                    last_gate != Gate.TELEMETRY_VALIDATED.value
                    or not optional_bounded_printable_string(
                        receipt.get("current_phase"), MAX_PHASE_LENGTH
                    )
                    or not optional_bounded_printable_string(
                        receipt.get("next_phase"), MAX_PHASE_LENGTH
                    )
                ):
                    raise ValueError
            if terminal_status is TerminalStatus.READY:
                if (
                    keys != TERMINAL_RECEIPT_KEYS
                    or not bounded_printable_string(
                        receipt.get("current_phase"), MAX_PHASE_LENGTH
                    )
                    or not bounded_printable_string(
                        receipt.get("next_phase"), MAX_PHASE_LENGTH
                    )
                    or receipt.get("reason_code") is not None
                    or receipt.get("reason") is not None
                    or evidence_gates != list(GATES[1:-1])
                ):
                    raise ValueError
            elif not valid_terminal_reason(
                receipt.get("reason_code"), receipt.get("reason")
            ):
                raise ValueError
        else:
            if (
                keys != RELEASED_RECEIPT_KEYS
                or revision < 2
                or not isinstance(receipt.get("previous_receipt_sha256"), str)
                or terminal is not True
                or status != TerminalStatus.ABORTED.value
                or drift != DriftClass.UNKNOWN.value
                or completed_at is None
                or last_gate != Gate.TELEMETRY_VALIDATED.value
                or not valid_terminal_reason(
                    receipt.get("reason_code"), receipt.get("reason")
                )
                or receipt.get("release_reason_code") != "EXPLICIT_ABORT_RELEASE"
                or not optional_bounded_printable_string(
                    receipt.get("current_phase"), MAX_PHASE_LENGTH
                )
                or not optional_bounded_printable_string(
                    receipt.get("next_phase"), MAX_PHASE_LENGTH
                )
            ):
                raise ValueError
        if validation.get("secret_scan") == "PREVALIDATED_DERIVED_TERMINAL":
            if (
                keys != TERMINAL_RECEIPT_KEYS
                or drift != DriftClass.MATERIAL.value
                or last_gate != Gate.TELEMETRY_VALIDATED.value
                or receipt.get("current_phase") is not None
                or receipt.get("next_phase") is not None
                or receipt.get("reason")
                != "A claimed immutable package artifact changed."
            ):
                raise ValueError
    except (KeyError, TypeError, ValueError, RegistryError) as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc


def validate_mutable_payload(write: MutableWrite) -> None:
    payload = write.payload
    if forbidden_keys(payload):
        raise RegistryError("PRIVATE_RUNTIME_IDENTIFIER_FIELD")
    try:
        if write.path.name == "claim.json":
            validate_claim_view_schema(payload)
            return
        if write.path.name == "track.json":
            if (
                frozenset(payload) != TRACK_VIEW_KEYS
                or not isinstance(payload.get("track_id"), str)
                or payload.get("track_id") != write.path.parent.name
                or not isinstance(payload.get("resource_scopes"), list)
                or normalize_resource_scopes(payload["resource_scopes"])
                != payload["resource_scopes"]
                or not isinstance(payload.get("latest_checkpoint_id"), str)
                or CHECKPOINT_ID_RE.fullmatch(payload["latest_checkpoint_id"]) is None
                or not isinstance(payload.get("packages"), dict)
                or not payload["packages"]
                or not (
                    payload.get("active_claim") is None
                    or isinstance(payload.get("active_claim"), dict)
                )
            ):
                raise ValueError
            require_rfc3339(payload.get("updated_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
            if isinstance(payload.get("active_claim"), dict):
                validate_claim_view_schema(payload["active_claim"])
            return
        if write.path.name == "index.json":
            if (
                frozenset(payload) != INDEX_VIEW_KEYS
                or not exact_integer(
                    payload.get("schema_version"), REGISTRY_SCHEMA_VERSION
                )
                or not isinstance(payload.get("tracks"), dict)
                or not isinstance(payload.get("receipts"), dict)
            ):
                raise ValueError
            require_rfc3339(payload.get("updated_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
            return
        if payload.get("compatibility_summary") is True:
            receipt = dict(payload)
            receipt_hash = receipt.pop("receipt_sha256", None)
            receipt.pop("compatibility_summary", None)
            validate_receipt_schema(receipt)
            if (
                not isinstance(receipt_hash, str)
                or receipt_hash != hashlib.sha256(serialized_json(receipt)).hexdigest()
            ):
                raise ValueError
            return
    except (KeyError, TypeError, ValueError, RegistryError) as exc:
        if isinstance(exc, RegistryError):
            raise
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    raise RegistryError("MUTABLE_VIEW_SCHEMA_UNSUPPORTED", exit_code=3)


def reconcile_claim_view(
    registry_root: Path, track_id: str, track: Dict[str, Any]
) -> None:
    claim_path = registry_root / "tracks" / track_id / "claim.json"
    active_claim = track.get("active_claim")
    if not claim_path.exists() and not claim_path.is_symlink():
        if active_claim is not None:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        return
    persisted_claim = read_json_object(
        claim_path,
        "ORPHANED_CLAIM_REVIEW_REQUIRED",
        expected_mode=REGISTRY_FILE_MODE,
    )
    validate_claim_view_schema(persisted_claim)
    if active_claim is None:
        packages = track.get("packages")
        if (
            persisted_claim.get("active") is not False
            or not isinstance(packages, dict)
            or any(
                isinstance(entry, dict)
                and entry.get("state")
                in {PackageState.CLAIMED.value, PackageState.OPENING.value}
                for entry in packages.values()
            )
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        return
    if not isinstance(active_claim, dict):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    validate_claim_view_schema(active_claim)
    if persisted_claim != active_claim:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)


def validate_receipt_bindings(
    *,
    registry_root: Path,
    coordinate: PackageCoordinate,
    package_entry: Dict[str, Any],
    package_manifest: Optional[Dict[str, Any]],
    receipt: Dict[str, Any],
) -> None:
    workspace = receipt.get("workspace")
    scope = receipt.get("scope")
    artifacts = receipt.get("artifacts")
    if (
        not isinstance(workspace, str)
        or not isinstance(scope, dict)
        or not isinstance(artifacts, dict)
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    expected_workspace, expected_compatibility = registry_invocation_bindings(
        registry_root
    )
    expected_allowed_writes = [
        str(registry_root.resolve()),
        str(expected_compatibility),
    ]
    if (
        workspace != str(expected_workspace)
        or scope.get("allowed_writes") != expected_allowed_writes
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    package_path = coordinate.package_path(registry_root)
    expected_artifacts = {
        "package": (
            package_path / "package.json",
            package_entry.get("package_sha256"),
        ),
        "handoff": (
            package_path / "handoff.md",
            package_entry.get("handoff_sha256"),
        ),
        "checkpoint": (
            package_path / "checkpoint.json",
            package_entry.get("checkpoint_sha256"),
        ),
    }
    for name, (expected_path, expected_hash) in expected_artifacts.items():
        record = artifacts.get(name)
        if not isinstance(record, dict) or record.get("path") != str(expected_path):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        if frozenset(record) == DRIFT_ARTIFACT_KEYS:
            observed_expected_hash = record.get("expected_sha256")
        else:
            observed_expected_hash = record.get("sha256")
        if observed_expected_hash != expected_hash:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    checkpoint_record = artifacts.get("checkpoint")
    if package_manifest is not None and not is_unclaimed_artifact_drift_receipt(
        receipt
    ):
        if (
            not isinstance(checkpoint_record, dict)
            or frozenset(checkpoint_record) != CHECKPOINT_ARTIFACT_KEYS
            or checkpoint_record.get("context_status") != "READY"
            or checkpoint_record.get("generated_at")
            != package_manifest.get("checkpoint_generated_at")
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    skill = artifacts.get("skill")
    if (
        not isinstance(skill, dict)
        or frozenset(skill) != ARTIFACT_KEYS
        or not isinstance(skill.get("path"), str)
        or skill["path"] != str(deployed_skill_file())
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)


def validate_receipt_history(
    registry_root: Path,
    receipt_id: str,
    entry: Dict[str, Any],
    package_entry: Dict[str, Any],
    package_manifest: Optional[Dict[str, Any]],
) -> ReceiptHistory:
    track_id = entry.get("track_id")
    checkpoint_id = entry.get("checkpoint_id")
    latest_revision = entry.get("latest_revision")
    latest_sha256 = entry.get("latest_receipt_sha256")
    if (
        RECEIPT_ID_RE.fullmatch(receipt_id) is None
        or not isinstance(track_id, str)
        or TRACK_ID_RE.fullmatch(track_id) is None
        or not isinstance(checkpoint_id, str)
        or CHECKPOINT_ID_RE.fullmatch(checkpoint_id) is None
        or not isinstance(latest_revision, int)
        or isinstance(latest_revision, bool)
        or latest_revision < 1
        or not isinstance(latest_sha256, str)
        or SHA256_RE.fullmatch(latest_sha256) is None
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    coordinate = PackageCoordinate(track_id, checkpoint_id)
    receipts_root = registry_root / "tracks" / track_id / "receipts"
    previous_hash: Optional[str] = None
    previous_receipt: Optional[Dict[str, Any]] = None
    first: Optional[Dict[str, Any]] = None
    latest: Optional[Dict[str, Any]] = None
    latest_path: Optional[Path] = None
    for revision in range(1, latest_revision + 1):
        receipt_path = receipts_root / "{}-r{:04d}.json".format(receipt_id, revision)
        try:
            receipt, receipt_hash = read_hashed_json_object(
                regular_file(receipt_path, "ORPHANED_CLAIM_REVIEW_REQUIRED"),
                "ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_mode=REGISTRY_FILE_MODE,
            )
            validate_receipt_schema(receipt)
            validate_receipt_bindings(
                registry_root=registry_root,
                coordinate=coordinate,
                package_entry=package_entry,
                package_manifest=package_manifest,
                receipt=receipt,
            )
        except RegistryError as exc:
            if exc.reason_code == "REGISTRY_MODE_INVALID":
                raise
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
        pickup = receipt.get("pickup")
        scope = receipt.get("scope")
        if (
            not exact_integer(receipt.get("schema_version"), RECEIPT_SCHEMA_VERSION)
            or receipt.get("receipt_id") != receipt_id
            or not exact_integer(receipt.get("revision"), revision)
            or receipt.get("previous_receipt_sha256") != previous_hash
            or not isinstance(pickup, dict)
            or pickup.get("track_id") != track_id
            or pickup.get("checkpoint_id") != checkpoint_id
            or pickup.get("selector") != coordinate.selector
            or not isinstance(scope, dict)
            or scope.get("phase_authorized") is not False
            or forbidden_keys(receipt)
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        predecessor_id = receipt.get("previous_lifecycle_receipt_id")
        predecessor_hash = receipt.get("previous_lifecycle_receipt_sha256")
        if (predecessor_id is None) != (predecessor_hash is None) or (
            predecessor_id is not None
            and (
                not isinstance(predecessor_id, str)
                or RECEIPT_ID_RE.fullmatch(predecessor_id) is None
                or not isinstance(predecessor_hash, str)
                or SHA256_RE.fullmatch(predecessor_hash) is None
            )
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        if first is None:
            first = receipt
        elif predecessor_id != first.get(
            "previous_lifecycle_receipt_id"
        ) or predecessor_hash != first.get("previous_lifecycle_receipt_sha256"):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        if previous_receipt is not None:
            for field in (
                "receipt_id",
                "started_at",
                "workspace",
                "pickup",
                "invocation",
                "scope",
                "artifacts",
                "previous_lifecycle_receipt_id",
                "previous_lifecycle_receipt_sha256",
            ):
                if receipt.get(field) != previous_receipt.get(field):
                    raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            prior_evidence = previous_receipt.get("transition_evidence")
            current_evidence = receipt.get("transition_evidence")
            if not isinstance(prior_evidence, list) or not isinstance(
                current_evidence, list
            ):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            if receipt.get("event") == ReceiptEvent.GATE_ADVANCED.value:
                valid_transition = (
                    previous_receipt.get("terminal") is False
                    and current_evidence[:-1] == prior_evidence
                    and len(current_evidence) == len(prior_evidence) + 1
                )
            elif receipt.get("event") == ReceiptEvent.COMPLETED.value:
                valid_transition = (
                    previous_receipt.get("terminal") is False
                    and current_evidence == prior_evidence
                )
            elif receipt.get("event") == ReceiptEvent.RELEASED.value:
                expected_release = released_receipt_from(
                    previous_receipt,
                    revision=receipt.get("revision"),
                    previous_receipt_sha256=receipt.get("previous_receipt_sha256"),
                    updated_at=receipt.get("updated_at"),
                )
                valid_transition = (
                    previous_receipt.get("event") == ReceiptEvent.COMPLETED.value
                    and previous_receipt.get("terminal") is True
                    and previous_receipt.get("status") == TerminalStatus.ABORTED.value
                    and receipt == expected_release
                )
            else:
                valid_transition = False
            if not valid_transition:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        previous_hash = receipt_hash
        previous_receipt = receipt
        latest = receipt
        latest_path = receipt_path
    if (
        first is None
        or latest is None
        or latest_path is None
        or previous_hash != latest_sha256
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    stored_path = entry.get("latest_receipt_path")
    if not isinstance(stored_path, str) or stored_path != str(latest_path):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    terminal_status = entry.get("terminal_status")
    if latest.get("terminal") is True:
        expected_entry_keys = (
            RELEASED_RECEIPT_ENTRY_KEYS
            if latest.get("event") == ReceiptEvent.RELEASED.value
            else TERMINAL_RECEIPT_ENTRY_KEYS
        )
        if frozenset(entry) != expected_entry_keys or terminal_status != latest.get(
            "status"
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        if latest.get("event") == ReceiptEvent.RELEASED.value:
            try:
                require_rfc3339(
                    entry.get("released_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED"
                )
            except RegistryError as exc:
                raise RegistryError(
                    "ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3
                ) from exc
            if entry.get("released_at") != latest.get("updated_at"):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    elif latest.get("terminal") is not False or terminal_status is not None:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    elif frozenset(entry) != RECEIPT_ENTRY_KEYS:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    return ReceiptHistory(
        first=first,
        latest=latest,
        latest_path=latest_path,
        latest_sha256=latest_sha256,
    )


def directory_children(path: Path, *, allow_missing: bool = False) -> list[Path]:
    if not path.exists() and not path.is_symlink():
        if allow_missing:
            return []
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    try:
        existing_directory(path, "ORPHANED_CLAIM_REVIEW_REQUIRED")
        require_mode(path, REGISTRY_DIRECTORY_MODE)
        return list(path.iterdir())
    except RegistryError:
        raise
    except OSError as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc


def reconcile_package_directories(
    registry_root: Path,
    track_id: str,
    packages: Dict[str, Any],
) -> set[PackageCoordinate]:
    packages_root = registry_root / "tracks" / track_id / "packages"
    children = directory_children(packages_root)
    children_by_name = {child.name: child for child in children}
    if set(children_by_name) - set(packages):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    required_files = {"handoff.md", "checkpoint.json", "package.json"}
    artifact_drift: set[PackageCoordinate] = set()
    for checkpoint_id in packages:
        coordinate = PackageCoordinate(track_id, checkpoint_id)
        package_path = children_by_name.get(checkpoint_id)
        if package_path is None:
            artifact_drift.add(coordinate)
            continue
        try:
            package_metadata = package_path.lstat()
            if not stat.S_ISDIR(package_metadata.st_mode) or stat.S_ISLNK(
                package_metadata.st_mode
            ):
                artifact_drift.add(coordinate)
                continue
            if stat.S_IMODE(package_metadata.st_mode) != REGISTRY_DIRECTORY_MODE:
                raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
            package_children = list(package_path.iterdir())
            package_children_by_name = {child.name: child for child in package_children}
            if set(package_children_by_name) - required_files:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            if required_files - set(package_children_by_name):
                artifact_drift.add(coordinate)
                continue
            for child in package_children_by_name.values():
                child_metadata = child.lstat()
                if not stat.S_ISREG(child_metadata.st_mode) or stat.S_ISLNK(
                    child_metadata.st_mode
                ):
                    artifact_drift.add(coordinate)
                    break
                if stat.S_IMODE(child_metadata.st_mode) != REGISTRY_FILE_MODE:
                    raise RegistryError("REGISTRY_MODE_INVALID", exit_code=3)
        except RegistryError:
            raise
        except OSError as exc:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    return artifact_drift


def reconcile_quarantine_files(
    registry_root: Path,
    track_id: str,
    packages: Dict[str, Any],
) -> None:
    expected_checkpoint_ids = {
        checkpoint_id
        for checkpoint_id, package_entry in packages.items()
        if isinstance(package_entry, dict)
        and package_entry.get("quarantine_reason_code") is not None
    }
    quarantines_root = registry_root / "tracks" / track_id / "quarantines"
    if not expected_checkpoint_ids:
        if quarantines_root.exists() or quarantines_root.is_symlink():
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        return
    children = directory_children(quarantines_root)
    expected_names = {
        "{}.json".format(checkpoint_id) for checkpoint_id in expected_checkpoint_ids
    }
    if (
        any(not child.is_file() or child.is_symlink() for child in children)
        or {child.name for child in children} != expected_names
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    for checkpoint_id in expected_checkpoint_ids:
        validate_quarantine_event(
            registry_root=registry_root,
            coordinate=PackageCoordinate(track_id, checkpoint_id),
            package_entry=packages[checkpoint_id],
        )


def reconcile_receipt_files(
    registry_root: Path,
    tracks: Dict[str, Any],
    receipts: Dict[str, Any],
) -> None:
    expected_by_track = {track_id: set() for track_id in tracks}
    for receipt_id, receipt_entry in receipts.items():
        track_id = receipt_entry.get("track_id")
        latest_revision = receipt_entry.get("latest_revision")
        if track_id not in expected_by_track or not isinstance(latest_revision, int):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        expected_by_track[track_id].update(
            "{}-r{:04d}.json".format(receipt_id, revision)
            for revision in range(1, latest_revision + 1)
        )
    for track_id, expected_names in expected_by_track.items():
        receipts_root = registry_root / "tracks" / track_id / "receipts"
        children = directory_children(receipts_root, allow_missing=not expected_names)
        if (
            any(not child.is_file() or child.is_symlink() for child in children)
            or {child.name for child in children} != expected_names
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        for child in children:
            require_mode(child, REGISTRY_FILE_MODE)


def immutable_chain_head(links: Sequence[ImmutableChainLink]) -> Optional[str]:
    if not links:
        return None
    links_by_id = {link.node_id: link for link in links}
    if len(links_by_id) != len(links):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    referenced: set[str] = set()
    roots: set[str] = set()
    successor_counts = {node_id: 0 for node_id in links_by_id}
    for link in links:
        predecessor_id = link.predecessor_id
        predecessor_hash = link.predecessor_sha256
        if predecessor_id is None:
            if predecessor_hash is not None:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            roots.add(link.node_id)
            continue
        predecessor = links_by_id.get(predecessor_id)
        if (
            predecessor is None
            or predecessor_id == link.node_id
            or predecessor.sha256 != predecessor_hash
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        successor_counts[predecessor_id] += 1
        if successor_counts[predecessor_id] != 1:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        referenced.add(predecessor_id)
    heads = set(links_by_id) - referenced
    if len(roots) != 1 or len(heads) != 1:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    head_id = heads.pop()
    visited: set[str] = set()
    cursor: Optional[str] = head_id
    while cursor is not None:
        if cursor in visited:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        visited.add(cursor)
        cursor = links_by_id[cursor].predecessor_id
    if visited != set(links_by_id):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    return head_id


def lifecycle_head(
    histories: Dict[str, ReceiptHistory],
) -> Optional[tuple[str, ReceiptHistory]]:
    for history in histories.values():
        predecessor_id = history.first.get("previous_lifecycle_receipt_id")
        if predecessor_id is None:
            continue
        predecessor = histories.get(predecessor_id)
        if (
            predecessor is None
            or predecessor.latest.get("event") != ReceiptEvent.RELEASED.value
            or predecessor.latest.get("terminal") is not True
            or predecessor.latest.get("status") != TerminalStatus.ABORTED.value
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    head_id = immutable_chain_head(
        [
            ImmutableChainLink(
                node_id=receipt_id,
                sha256=history.latest_sha256,
                predecessor_id=history.first.get("previous_lifecycle_receipt_id"),
                predecessor_sha256=history.first.get(
                    "previous_lifecycle_receipt_sha256"
                ),
            )
            for receipt_id, history in histories.items()
        ]
    )
    return None if head_id is None else (head_id, histories[head_id])


def publication_head(packages: Dict[str, Any]) -> str:
    head_id = immutable_chain_head(
        [
            ImmutableChainLink(
                node_id=checkpoint_id,
                sha256=package_entry.get("package_sha256"),
                predecessor_id=package_entry.get("previous_checkpoint_id"),
                predecessor_sha256=package_entry.get("previous_package_sha256"),
            )
            for checkpoint_id, package_entry in packages.items()
        ]
    )
    if head_id is None:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    return head_id


def reconcile_packaged_checkpoint(
    *,
    coordinate: PackageCoordinate,
    package_path: Path,
    manifest: Dict[str, Any],
    track: Dict[str, Any],
    package_entry: Dict[str, Any],
) -> None:
    try:
        checkpoint, observed_checkpoint_hash = read_hashed_json_object(
            package_path / "checkpoint.json",
            "PACKAGE_ARTIFACT_DRIFT",
        )
        if forbidden_keys(checkpoint):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        checkpoint_hash = manifest.get("checkpoint_sha256")
        if not isinstance(checkpoint_hash, str):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        if observed_checkpoint_hash != checkpoint_hash:
            raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
        if checkpoint_identity(checkpoint, checkpoint_hash) != coordinate.checkpoint_id:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        source_handoff = manifest.get("source_handoff")
        source_checkpoint = manifest.get("source_checkpoint")
        canonical_handoff = checkpoint.get("canonical_handoff")
        if (
            not canonical_absolute_path_string(source_handoff)
            or not canonical_absolute_path_string(source_checkpoint)
            or not isinstance(canonical_handoff, str)
            or not optional_bounded_printable_string(
                checkpoint.get("current_phase"), MAX_PHASE_LENGTH
            )
            or not optional_bounded_printable_string(
                checkpoint.get("next_phase"), MAX_PHASE_LENGTH
            )
            or not optional_bounded_printable_string(
                manifest.get("current_phase"), MAX_PHASE_LENGTH
            )
            or not optional_bounded_printable_string(
                manifest.get("next_phase"), MAX_PHASE_LENGTH
            )
            or canonical_handoff != source_handoff
            or checkpoint.get("generated_at") != manifest.get("checkpoint_generated_at")
            or checkpoint.get("current_phase") != manifest.get("current_phase")
            or checkpoint.get("next_phase") != manifest.get("next_phase")
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        scopes = track.get("resource_scopes")
        checkpoint_pickup = checkpoint.get("pickup")
        if checkpoint_pickup is not None:
            if not isinstance(checkpoint_pickup, dict):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            recorded_scopes = checkpoint_pickup.get("resource_scopes")
            if not isinstance(recorded_scopes, list) or not all(
                isinstance(value, str) for value in recorded_scopes
            ):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            if (
                checkpoint_pickup.get("track_id") != coordinate.track_id
                or recorded_scopes != normalize_resource_scopes(recorded_scopes)
                or recorded_scopes != scopes
            ):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        expected_templates = {
            reason_code: hashlib.sha256(data).hexdigest()
            for reason_code, data in quarantine_event_templates(
                coordinate=coordinate,
                handoff_sha256=manifest.get("handoff_sha256"),
                checkpoint_sha256=checkpoint_hash,
            ).items()
        }
        if (
            manifest.get("quarantine_template_sha256") != expected_templates
            or package_entry.get("quarantine_template_sha256") != expected_templates
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    except (OSError, TypeError, ValueError, RegistryError) as exc:
        if isinstance(exc, RegistryError) and exc.reason_code in {
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
            "PACKAGE_ARTIFACT_DRIFT",
        }:
            raise
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc


def reconcile_package_manifest(
    *,
    registry_root: Path,
    coordinate: PackageCoordinate,
    track: Dict[str, Any],
    package_entry: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    package_path = coordinate.package_path(registry_root)
    manifest_path = package_path / "package.json"
    try:
        manifest, manifest_hash = read_hashed_json_object(
            manifest_path,
            "PACKAGE_ARTIFACT_DRIFT",
            expected_mode=REGISTRY_FILE_MODE,
        )
    except RegistryError as exc:
        if exc.reason_code == "PACKAGE_ARTIFACT_DRIFT":
            return None
        raise
    if manifest_hash != package_entry.get("package_sha256"):
        return None
    expected_keys = {
        "schema_version",
        "track_id",
        "checkpoint_id",
        "selector",
        "published_state",
        "published_at",
        "checkpoint_generated_at",
        "current_phase",
        "next_phase",
        "resource_scopes",
        "source_handoff",
        "source_checkpoint",
        "handoff_sha256",
        "checkpoint_sha256",
        "previous_checkpoint_id",
        "previous_package_sha256",
        "quarantine_template_sha256",
    }
    expected = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "track_id": coordinate.track_id,
        "checkpoint_id": coordinate.checkpoint_id,
        "selector": coordinate.selector,
        "published_state": PackageState.AVAILABLE.value,
        "resource_scopes": track.get("resource_scopes"),
        "package_handoff_sha256": package_entry.get("handoff_sha256"),
        "package_checkpoint_sha256": package_entry.get("checkpoint_sha256"),
        "previous_checkpoint_id": package_entry.get("previous_checkpoint_id"),
        "previous_package_sha256": package_entry.get("previous_package_sha256"),
        "quarantine_template_sha256": package_entry.get("quarantine_template_sha256"),
    }
    observed = {
        "schema_version": manifest.get("schema_version"),
        "track_id": manifest.get("track_id"),
        "checkpoint_id": manifest.get("checkpoint_id"),
        "selector": manifest.get("selector"),
        "published_state": manifest.get("published_state"),
        "resource_scopes": manifest.get("resource_scopes"),
        "package_handoff_sha256": manifest.get("handoff_sha256"),
        "package_checkpoint_sha256": manifest.get("checkpoint_sha256"),
        "previous_checkpoint_id": manifest.get("previous_checkpoint_id"),
        "previous_package_sha256": manifest.get("previous_package_sha256"),
        "quarantine_template_sha256": manifest.get("quarantine_template_sha256"),
    }
    if (
        set(manifest) != expected_keys
        or forbidden_keys(manifest)
        or not exact_integer(manifest.get("schema_version"), PACKAGE_SCHEMA_VERSION)
        or observed != expected
    ):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    try:
        require_rfc3339(manifest.get("published_at"), "ORPHANED_CLAIM_REVIEW_REQUIRED")
        require_rfc3339(
            manifest.get("checkpoint_generated_at"),
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
    except RegistryError as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    try:
        verify_package_payload(package_path, manifest, coordinate.selector)
    except RegistryError as exc:
        if exc.reason_code == "PACKAGE_ARTIFACT_DRIFT":
            return None
        raise
    try:
        reconcile_packaged_checkpoint(
            coordinate=coordinate,
            package_path=package_path,
            manifest=manifest,
            track=track,
            package_entry=package_entry,
        )
    except RegistryError as exc:
        if exc.reason_code == "PACKAGE_ARTIFACT_DRIFT":
            return None
        raise
    return manifest


def state_from_lifecycle(history: ReceiptHistory) -> PackageState:
    latest = history.latest
    if latest.get("event") == ReceiptEvent.RELEASED.value:
        if (
            latest.get("terminal") is not True
            or latest.get("status") != TerminalStatus.ABORTED.value
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        return PackageState.AVAILABLE
    if latest.get("terminal") is False:
        if latest.get("status") != "VERIFYING":
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        gate = latest.get("last_completed_gate")
        if gate == Gate.INVOCATION_RECORDED.value:
            return PackageState.CLAIMED
        if gate in {
            Gate.CANONICAL_PAIR_VERIFIED.value,
            Gate.LIVE_STATE_VERIFIED.value,
        }:
            return PackageState.OPENING
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    if latest.get("terminal") is not True:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    try:
        status = TerminalStatus(latest.get("status"))
    except (TypeError, ValueError) as exc:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
    return (
        PackageState.CONSUMED
        if status is TerminalStatus.READY
        else PackageState.NEEDS_REVIEW
    )


def expected_package_state(
    *,
    coordinate: PackageCoordinate,
    track: Dict[str, Any],
    package_entry: Dict[str, Any],
    histories: Dict[str, ReceiptHistory],
) -> PackageState:
    head = lifecycle_head(histories)
    latest_receipt_id = package_entry.get("latest_receipt_id")
    if head is None:
        if latest_receipt_id is not None:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    elif latest_receipt_id != head[0]:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    quarantine_reason = package_entry.get("quarantine_reason_code")
    if quarantine_reason is not None:
        if quarantine_reason not in PACKAGE_QUARANTINE_REASONS:
            raise RegistryError("REGISTRY_INDEX_INVALID")
        return PackageState.NEEDS_REVIEW
    if coordinate.checkpoint_id != track.get("latest_checkpoint_id"):
        return PackageState.SUPERSEDED
    if head is None:
        return PackageState.AVAILABLE
    _, history = head
    return state_from_lifecycle(history)


def latest_claimed_history_for_track(
    track_id: str,
    track: Dict[str, Any],
    histories_by_package: Dict[tuple[str, str], Dict[str, ReceiptHistory]],
) -> Optional[tuple[str, str, ReceiptHistory]]:
    packages = track.get("packages")
    checkpoint_id = track.get("latest_checkpoint_id")
    if not isinstance(packages, dict) or not isinstance(checkpoint_id, str):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    visited_packages: set[str] = set()
    while checkpoint_id is not None:
        if checkpoint_id in visited_packages:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        visited_packages.add(checkpoint_id)
        package_entry = packages.get(checkpoint_id)
        if not isinstance(package_entry, dict):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        package_histories = histories_by_package.get((track_id, checkpoint_id), {})
        head = lifecycle_head(package_histories)
        visited_receipts: set[str] = set()
        while head is not None:
            receipt_id, history = head
            if receipt_id in visited_receipts:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            visited_receipts.add(receipt_id)
            if history.first.get("event") == ReceiptEvent.CLAIMED.value:
                return checkpoint_id, receipt_id, history
            predecessor_id = history.first.get("previous_lifecycle_receipt_id")
            if predecessor_id is None:
                break
            predecessor = package_histories.get(predecessor_id)
            if predecessor is None:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            head = predecessor_id, predecessor
        predecessor_checkpoint = package_entry.get("previous_checkpoint_id")
        if predecessor_checkpoint is not None and not isinstance(
            predecessor_checkpoint, str
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        checkpoint_id = predecessor_checkpoint
    return None


def expected_closed_claim_view(
    *,
    track_id: str,
    checkpoint_id: str,
    receipt_id: str,
    history: ReceiptHistory,
    receipt_entry: Dict[str, Any],
) -> Dict[str, Any]:
    latest = history.latest
    expected = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "active": False,
        "track_id": track_id,
        "checkpoint_id": checkpoint_id,
        "receipt_id": receipt_id,
        "latest_revision": receipt_entry.get("latest_revision"),
        "latest_receipt_sha256": receipt_entry.get("latest_receipt_sha256"),
        "latest_receipt_path": receipt_entry.get("latest_receipt_path"),
        "claimed_at": history.first.get("started_at"),
        "closed_at": latest.get("completed_at"),
        "terminal_status": latest.get("status"),
    }
    if latest.get("event") == ReceiptEvent.RELEASED.value:
        expected["released_at"] = latest.get("updated_at")
    validate_claim_view_schema(expected)
    return expected


def reconcile_registry_views(
    registry_root: Path,
    index: Dict[str, Any],
    *,
    collect_artifact_drift: bool = False,
) -> set[PackageCoordinate]:
    tracks = index.get("tracks")
    receipts = index.get("receipts")
    if not isinstance(tracks, dict) or not isinstance(receipts, dict):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    registry_children = directory_children(registry_root)
    registry_child_names = {child.name for child in registry_children}
    if not registry_child_names <= {"index.json", "tracks"}:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    tracks_root = registry_root / "tracks"
    artifact_drift: set[PackageCoordinate] = set()
    package_manifests: Dict[PackageCoordinate, Dict[str, Any]] = {}
    indexed_track_ids = set(tracks)
    if not tracks_root.exists() and not tracks_root.is_symlink():
        if indexed_track_ids:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    else:
        try:
            existing_directory(tracks_root, "ORPHANED_CLAIM_REVIEW_REQUIRED")
            require_mode(tracks_root, REGISTRY_DIRECTORY_MODE)
            observed_track_ids = {
                child.name
                for child in tracks_root.iterdir()
                if child.is_dir() and not child.is_symlink()
            }
            invalid_children = [
                child
                for child in tracks_root.iterdir()
                if not child.is_dir() or child.is_symlink()
            ]
        except RegistryError:
            raise
        except OSError as exc:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
        if invalid_children or observed_track_ids != indexed_track_ids:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    for track_id, track in tracks.items():
        if (
            not isinstance(track_id, str)
            or not isinstance(track, dict)
            or set(track) != TRACK_VIEW_KEYS
            or forbidden_keys(track)
            or track.get("track_id") != track_id
        ):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        validate_track_id(track_id)
        try:
            require_rfc3339(track.get("updated_at"), "REGISTRY_INDEX_INVALID")
        except RegistryError as exc:
            raise RegistryError("REGISTRY_INDEX_INVALID") from exc
        track_root = registry_root / "tracks" / track_id
        track_children = directory_children(track_root)
        track_child_names = {child.name for child in track_children}
        if not {"track.json", "packages"}.issubset(track_child_names) or not (
            track_child_names
            <= {
                "track.json",
                "claim.json",
                "packages",
                "quarantines",
                "receipts",
            }
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        track_path = track_root / "track.json"
        persisted_track = read_json_object(
            track_path,
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
            expected_mode=REGISTRY_FILE_MODE,
        )
        if persisted_track != track:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        reconcile_claim_view(registry_root, track_id, track)
        packages = track.get("packages")
        if not isinstance(packages, dict) or not packages:
            raise RegistryError("REGISTRY_INDEX_INVALID")
        scopes = track.get("resource_scopes")
        if not isinstance(scopes, list) or not all(
            isinstance(value, str) for value in scopes
        ):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        try:
            if normalize_resource_scopes(scopes) != scopes:
                raise RegistryError("REGISTRY_INDEX_INVALID")
        except RegistryError as exc:
            raise RegistryError("REGISTRY_INDEX_INVALID") from exc
        latest_checkpoint_id = track.get("latest_checkpoint_id")
        if latest_checkpoint_id not in packages:
            raise RegistryError("REGISTRY_INDEX_INVALID")
        for checkpoint_id, package_entry in packages.items():
            latest_receipt_id = (
                package_entry.get("latest_receipt_id")
                if isinstance(package_entry, dict)
                else None
            )
            previous_checkpoint_id = (
                package_entry.get("previous_checkpoint_id")
                if isinstance(package_entry, dict)
                else None
            )
            previous_package_hash = (
                package_entry.get("previous_package_sha256")
                if isinstance(package_entry, dict)
                else None
            )
            quarantine_reason = (
                package_entry.get("quarantine_reason_code")
                if isinstance(package_entry, dict)
                else None
            )
            quarantine_event_hash = (
                package_entry.get("quarantine_event_sha256")
                if isinstance(package_entry, dict)
                else None
            )
            quarantine_template_hashes = (
                package_entry.get("quarantine_template_sha256")
                if isinstance(package_entry, dict)
                else None
            )
            if (
                not isinstance(checkpoint_id, str)
                or CHECKPOINT_ID_RE.fullmatch(checkpoint_id) is None
                or not isinstance(package_entry, dict)
                or set(package_entry) != PACKAGE_ENTRY_KEYS
                or forbidden_keys(package_entry)
            ):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            coordinate = PackageCoordinate(track_id, checkpoint_id)
            if (
                package_entry.get("selector") != coordinate.selector
                or package_entry.get("state")
                not in {state.value for state in PackageState}
                or any(
                    not isinstance(package_entry.get(field), str)
                    or SHA256_RE.fullmatch(package_entry[field]) is None
                    for field in (
                        "package_sha256",
                        "handoff_sha256",
                        "checkpoint_sha256",
                    )
                )
                or "latest_receipt_id" not in package_entry
                or (
                    latest_receipt_id is not None
                    and (
                        not isinstance(latest_receipt_id, str)
                        or RECEIPT_ID_RE.fullmatch(latest_receipt_id) is None
                    )
                )
                or "quarantine_reason_code" not in package_entry
                or "quarantine_event_sha256" not in package_entry
                or not isinstance(quarantine_template_hashes, dict)
                or set(quarantine_template_hashes) != PACKAGE_QUARANTINE_REASONS
                or any(
                    not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
                    for value in (
                        quarantine_template_hashes.values()
                        if isinstance(quarantine_template_hashes, dict)
                        else ()
                    )
                )
                or (
                    quarantine_reason is not None
                    and (
                        not isinstance(quarantine_reason, str)
                        or quarantine_reason not in PACKAGE_QUARANTINE_REASONS
                    )
                )
                or (quarantine_reason is None) != (quarantine_event_hash is None)
                or (
                    quarantine_event_hash is not None
                    and (
                        not isinstance(quarantine_event_hash, str)
                        or SHA256_RE.fullmatch(quarantine_event_hash) is None
                    )
                )
                or "previous_checkpoint_id" not in package_entry
                or "previous_package_sha256" not in package_entry
                or (previous_checkpoint_id is None) != (previous_package_hash is None)
                or (
                    previous_checkpoint_id is not None
                    and (
                        not isinstance(previous_checkpoint_id, str)
                        or CHECKPOINT_ID_RE.fullmatch(previous_checkpoint_id) is None
                        or not isinstance(previous_package_hash, str)
                        or SHA256_RE.fullmatch(previous_package_hash) is None
                    )
                )
            ):
                raise RegistryError("REGISTRY_INDEX_INVALID")
        artifact_drift.update(
            reconcile_package_directories(registry_root, track_id, packages)
        )
        reconcile_quarantine_files(registry_root, track_id, packages)
        for checkpoint_id, package_entry in packages.items():
            coordinate = PackageCoordinate(track_id, checkpoint_id)
            if coordinate in artifact_drift:
                continue
            manifest = reconcile_package_manifest(
                registry_root=registry_root,
                coordinate=coordinate,
                track=track,
                package_entry=package_entry,
            )
            if manifest is None:
                artifact_drift.add(coordinate)
            else:
                package_manifests[coordinate] = manifest
        if publication_head(packages) != latest_checkpoint_id:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)

    active_scopes = [
        (track_id, track["resource_scopes"])
        for track_id, track in tracks.items()
        if isinstance(track, dict) and isinstance(track.get("active_claim"), dict)
    ]
    for position, (_, left_scopes) in enumerate(active_scopes):
        for _, right_scopes in active_scopes[position + 1 :]:
            if resource_scopes_overlap(left_scopes, right_scopes):
                raise RegistryError("RESOURCE_SCOPE_CONFLICT", exit_code=3)

    histories: Dict[str, ReceiptHistory] = {}
    histories_by_package: Dict[tuple[str, str], Dict[str, ReceiptHistory]] = {}
    for receipt_id, receipt_entry in receipts.items():
        if (
            not isinstance(receipt_id, str)
            or not isinstance(receipt_entry, dict)
            or frozenset(receipt_entry)
            not in {
                RECEIPT_ENTRY_KEYS,
                TERMINAL_RECEIPT_ENTRY_KEYS,
                RELEASED_RECEIPT_ENTRY_KEYS,
            }
            or forbidden_keys(receipt_entry)
        ):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        track_id = receipt_entry.get("track_id")
        checkpoint_id = receipt_entry.get("checkpoint_id")
        track = tracks.get(track_id)
        packages = track.get("packages") if isinstance(track, dict) else None
        package_entry = (
            packages.get(checkpoint_id) if isinstance(packages, dict) else None
        )
        if not isinstance(track, dict) or not isinstance(package_entry, dict):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        history = validate_receipt_history(
            registry_root,
            receipt_id,
            receipt_entry,
            package_entry,
            package_manifests.get(PackageCoordinate(track_id, checkpoint_id)),
        )
        histories[receipt_id] = history
        histories_by_package.setdefault((track_id, checkpoint_id), {})[receipt_id] = (
            history
        )

    reconcile_receipt_files(registry_root, tracks, receipts)

    for track_id, track in tracks.items():
        packages = track["packages"]
        for checkpoint_id, package_entry in packages.items():
            coordinate = PackageCoordinate(track_id, checkpoint_id)
            expected_state = expected_package_state(
                coordinate=coordinate,
                track=track,
                package_entry=package_entry,
                histories=histories_by_package.get((track_id, checkpoint_id), {}),
            )
            if package_entry.get("state") != expected_state.value:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            if coordinate in artifact_drift and not collect_artifact_drift:
                raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
        active_claim = track.get("active_claim")
        if isinstance(active_claim, dict):
            checkpoint_id = active_claim.get("checkpoint_id")
            package_entry = packages.get(checkpoint_id)
            if (
                active_claim.get("active") is not True
                or not isinstance(package_entry, dict)
                or package_entry.get("state")
                not in {PackageState.CLAIMED.value, PackageState.OPENING.value}
                or package_entry.get("latest_receipt_id")
                != active_claim.get("receipt_id")
            ):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        elif any(
            isinstance(package_entry, dict)
            and package_entry.get("state")
            in {PackageState.CLAIMED.value, PackageState.OPENING.value}
            for package_entry in packages.values()
        ):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)

    for receipt_id, receipt_entry in receipts.items():
        latest = histories[receipt_id].latest
        track = tracks[receipt_entry["track_id"]]
        active_claim = track.get("active_claim")
        if latest.get("terminal") is False:
            if not isinstance(active_claim, dict):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            for field in (
                "track_id",
                "checkpoint_id",
                "latest_revision",
                "latest_receipt_sha256",
                "latest_receipt_path",
            ):
                if active_claim.get(field) != receipt_entry.get(field):
                    raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            if active_claim.get("receipt_id") != receipt_id:
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            if active_claim.get("claimed_at") != histories[receipt_id].first.get(
                "started_at"
            ):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    for track_id, track in tracks.items():
        if track.get("active_claim") is not None:
            continue
        claim_path = registry_root / "tracks" / track_id / "claim.json"
        latest_claimed = latest_claimed_history_for_track(
            track_id, track, histories_by_package
        )
        if latest_claimed is None:
            if claim_path.exists() or claim_path.is_symlink():
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            continue
        checkpoint_id, receipt_id, history = latest_claimed
        receipt_entry = receipts.get(receipt_id)
        if not isinstance(receipt_entry, dict):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        try:
            closed_claim = read_json_object(
                claim_path,
                "ORPHANED_CLAIM_REVIEW_REQUIRED",
                expected_mode=REGISTRY_FILE_MODE,
            )
            expected_claim = expected_closed_claim_view(
                track_id=track_id,
                checkpoint_id=checkpoint_id,
                receipt_id=receipt_id,
                history=history,
                receipt_entry=receipt_entry,
            )
        except RegistryError as exc:
            if exc.reason_code == "REGISTRY_MODE_INVALID":
                raise
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
        if closed_claim != expected_claim:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    return artifact_drift


def reconcile_mutation(
    *,
    registry_root: Path,
    index: Dict[str, Any],
    gitleaks_path: str,
    compatibility_output: Optional[Path] = None,
    compatibility_destination: Optional[MutableDestination] = None,
    invocation: Optional[InvocationContext] = None,
) -> set[PackageCoordinate]:
    artifact_drift = reconcile_registry_views(
        registry_root,
        index,
        collect_artifact_drift=True,
    )
    handled: set[PackageCoordinate] = set()
    next_compatibility_destination = compatibility_destination
    if compatibility_output is not None:
        if next_compatibility_destination is None:
            next_compatibility_destination = preflight_compatibility_output(
                compatibility_output
            )
        validate_compatibility_registry_event(
            path=compatibility_output,
            destination=next_compatibility_destination,
            registry_root=registry_root,
            index=index,
        )
    pending = set(artifact_drift)
    while pending:
        coordinate = min(
            pending, key=lambda value: (value.track_id, value.checkpoint_id)
        )
        track = index.get("tracks", {}).get(coordinate.track_id)
        if not isinstance(track, dict):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        active = track.get("active_claim")
        if isinstance(active, dict) and active.get("checkpoint_id") == (
            coordinate.checkpoint_id
        ):
            output = compatibility_output
            if output is None:
                _, output = registry_invocation_bindings(registry_root)
            validate_compatibility_binding(registry_root, output)
            destination = next_compatibility_destination
            if destination is None:
                destination = preflight_compatibility_output(output)
            validate_compatibility_registry_event(
                path=output,
                destination=destination,
                registry_root=registry_root,
                index=index,
            )
            coordinates = RunCoordinates(
                track_id=coordinate.track_id,
                checkpoint_id=coordinate.checkpoint_id,
                receipt_id=str(active.get("receipt_id", "")),
                revision=active.get("latest_revision"),
                receipt_sha256=str(active.get("latest_receipt_sha256", "")),
            )
            _, claim, current, _ = load_exact_run(
                registry_root=registry_root,
                index=index,
                coordinates=coordinates,
            )
            persist_terminal_run(
                registry_root=registry_root,
                compatibility_output=output,
                index=index,
                track=track,
                claim=claim,
                current=current,
                coordinates=coordinates,
                status=TerminalStatus.REVIEW_REQUIRED,
                drift=DriftClass.MATERIAL,
                current_phase=None,
                next_phase=None,
                reason_code="PACKAGE_ARTIFACT_DRIFT",
                reason="A claimed immutable package artifact changed.",
                gitleaks_path=gitleaks_path,
                compatibility_destination=destination,
                artifact_drift_detected=True,
                reconcile_before_commit=False,
            )
            next_compatibility_destination = preflight_compatibility_output(output)
        else:
            if invocation is not None and compatibility_output is not None:
                destination = next_compatibility_destination
                if destination is None:
                    destination = preflight_compatibility_output(compatibility_output)
                validate_compatibility_registry_event(
                    path=compatibility_output,
                    destination=destination,
                    registry_root=registry_root,
                    index=index,
                )
                close_unclaimed_artifact_drift(
                    registry_root=registry_root,
                    compatibility_output=compatibility_output,
                    compatibility_destination=destination,
                    index=index,
                    track=track,
                    coordinate=coordinate,
                    invocation=invocation,
                    gitleaks_path=gitleaks_path,
                )
                next_compatibility_destination = preflight_compatibility_output(
                    compatibility_output
                )
            else:
                quarantine_package(
                    registry_root=registry_root,
                    index=index,
                    track=track,
                    coordinate=coordinate,
                    reason_code="PACKAGE_ARTIFACT_DRIFT",
                    excluded_guard_coordinates=artifact_drift,
                )
        handled.add(coordinate)
        artifact_drift.update(
            reconcile_registry_views(
                registry_root,
                index,
                collect_artifact_drift=True,
            )
        )
        pending = artifact_drift - handled
    active_drift_handled = False
    tracks = index.get("tracks")
    if not isinstance(tracks, dict):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    for track_id in sorted(tracks):
        track = tracks[track_id]
        if not isinstance(track, dict):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        active = track.get("active_claim")
        if active is None:
            continue
        if not isinstance(active, dict):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        coordinates = RunCoordinates(
            track_id=track_id,
            checkpoint_id=str(active.get("checkpoint_id", "")),
            receipt_id=str(active.get("receipt_id", "")),
            revision=active.get("latest_revision"),
            receipt_sha256=str(active.get("latest_receipt_sha256", "")),
        )
        active_track, claim, current, _ = load_exact_run(
            registry_root=registry_root,
            index=index,
            coordinates=coordinates,
        )
        try:
            verify_active_artifacts_or_terminalize(
                registry_root=registry_root,
                compatibility_output=compatibility_output,
                index=index,
                track=active_track,
                claim=claim,
                current=current,
                coordinates=coordinates,
                gitleaks_path=gitleaks_path,
                compatibility_destination=next_compatibility_destination,
                reconcile_before_commit=False,
            )
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            active_drift_handled = True
            output = compatibility_output
            if output is None:
                _, output = registry_invocation_bindings(registry_root)
            next_compatibility_destination = preflight_compatibility_output(output)
    if handled or active_drift_handled:
        raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
    return artifact_drift


def claim_checkpoint(
    *,
    registry_root: Path,
    compatibility_output: Path,
    selector: Optional[str],
    invocation: InvocationContext,
    gitleaks_path: str,
) -> Dict[str, Any]:
    invocation.validate()
    validate_invocation_bindings(
        registry_root=registry_root,
        compatibility_output=compatibility_output,
        invocation=invocation,
    )
    with registry_lock(registry_root):
        compatibility_destination = preflight_compatibility_output(compatibility_output)
        index = load_index(registry_root)
        selection = resolve_package_selection(index, selector)
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
            invocation=invocation,
        )

        def close_detected_drift() -> None:
            reconcile_mutation(
                registry_root=registry_root,
                index=index,
                gitleaks_path=gitleaks_path,
                compatibility_output=compatibility_output,
                compatibility_destination=compatibility_destination,
                invocation=invocation,
            )

        for existing_track_id, existing_track in index["tracks"].items():
            if not isinstance(existing_track, dict):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            reconcile_claim_view(registry_root, existing_track_id, existing_track)
            active = existing_track.get("active_claim")
            if active is None:
                continue
            if not isinstance(active, dict):
                raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
            active_coordinates = RunCoordinates(
                track_id=existing_track_id,
                checkpoint_id=str(active.get("checkpoint_id", "")),
                receipt_id=str(active.get("receipt_id", "")),
                revision=active.get("latest_revision"),
                receipt_sha256=str(active.get("latest_receipt_sha256", "")),
            )
            active_track, active_claim, active_receipt, _ = load_exact_run(
                registry_root=registry_root,
                index=index,
                coordinates=active_coordinates,
            )
            verify_active_artifacts_or_terminalize(
                registry_root=registry_root,
                compatibility_output=compatibility_output,
                index=index,
                track=active_track,
                claim=active_claim,
                current=active_receipt,
                coordinates=active_coordinates,
                gitleaks_path=gitleaks_path,
                compatibility_destination=compatibility_destination,
            )
        coordinate, track, selected_state = selection
        require_available_package_state(selected_state)
        track_id = coordinate.track_id
        checkpoint_id = coordinate.checkpoint_id
        if track.get("active_claim") is not None:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        package_path = coordinate.package_path(registry_root)
        package_entry = package_entry_for(track, checkpoint_id)
        try:
            package = load_verified_package(package_path, package_entry)
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            close_detected_drift()
            raise
        scopes = track.get("resource_scopes")
        if not isinstance(scopes, list) or not all(
            isinstance(value, str) for value in scopes
        ):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        for other_track_id, other_track in index["tracks"].items():
            if other_track_id == track_id:
                continue
            if not isinstance(other_track, dict):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            if other_track.get("active_claim") is None:
                continue
            other_scopes = other_track.get("resource_scopes")
            if not isinstance(other_scopes, list) or not all(
                isinstance(value, str) for value in other_scopes
            ):
                raise RegistryError("REGISTRY_INDEX_INVALID")
            if resource_scopes_overlap(scopes, other_scopes):
                raise RegistryError("RESOURCE_SCOPE_CONFLICT", exit_code=3)
        handoff = package_path / "handoff.md"
        checkpoint = package_path / "checkpoint.json"
        timestamp = utc_now()
        receipt_id = allocate_receipt_id(registry_root, index, timestamp)
        previous_receipt_id, previous_receipt_hash = lifecycle_predecessor(
            package_entry, index
        )
        try:
            receipt = build_initial_receipt(
                registry_root=registry_root,
                timestamp=timestamp,
                receipt_id=receipt_id,
                coordinate=coordinate,
                invocation=invocation,
                artifacts={
                    "skill": artifact_record(invocation.skill_file),
                    "package": artifact_record(
                        package_path / "package.json",
                        expected_sha256=package_entry.get("package_sha256"),
                    ),
                    "handoff": artifact_record(
                        handoff,
                        expected_sha256=package_entry.get("handoff_sha256"),
                    ),
                    "checkpoint": artifact_record(
                        checkpoint,
                        checkpoint=True,
                        expected_sha256=package_entry.get("checkpoint_sha256"),
                    ),
                },
                previous_lifecycle_receipt_id=previous_receipt_id,
                previous_lifecycle_receipt_sha256=previous_receipt_hash,
            )
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            close_detected_drift()
            raise
        receipts_root = registry_root / "tracks" / track_id / "receipts"
        receipt_path = receipts_root / "{}-r0001.json".format(receipt_id)
        try:
            validate_receipt_schema(receipt)
            validate_receipt_bindings(
                registry_root=registry_root,
                coordinate=coordinate,
                package_entry=package_entry,
                package_manifest=package,
                receipt=receipt,
            )
        except RegistryError as exc:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3) from exc
        destination_expectations = capture_receipt_destinations(
            registry_root=registry_root,
            track_id=track_id,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
            include_claim=True,
        )
        try:
            receipt_data = prepare_receipt_data(
                registry_root=registry_root,
                receipt_path=receipt_path,
                receipt=receipt,
                gitleaks_path=gitleaks_path,
            )
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            close_detected_drift()
            raise
        try:
            load_verified_package(package_path, package_entry)
            reconcile_mutation(
                registry_root=registry_root,
                index=index,
                gitleaks_path=gitleaks_path,
                compatibility_output=compatibility_output,
                compatibility_destination=compatibility_destination,
                invocation=invocation,
            )
            load_verified_package(package_path, package_entry)
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            close_detected_drift()
            raise
        receipt_hash = hashlib.sha256(receipt_data).hexdigest()
        claim = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "active": True,
            "track_id": track_id,
            "checkpoint_id": checkpoint_id,
            "receipt_id": receipt_id,
            "latest_revision": 1,
            "latest_receipt_sha256": receipt_hash,
            "latest_receipt_path": str(receipt_path),
            "claimed_at": timestamp,
        }
        package_entry["state"] = PackageState.CLAIMED.value
        package_entry["latest_receipt_id"] = receipt_id
        track["active_claim"] = claim
        track["updated_at"] = timestamp
        index["receipts"][receipt_id] = {
            "track_id": track_id,
            "checkpoint_id": checkpoint_id,
            "latest_revision": 1,
            "latest_receipt_sha256": receipt_hash,
            "latest_receipt_path": str(receipt_path),
        }
        index["updated_at"] = timestamp
        return persist_receipt_event(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            track_id=track_id,
            receipt=receipt,
            receipt_path=receipt_path,
            receipt_data=receipt_data,
            claim_view=claim,
            track_view=track,
            index_view=index,
            destination_expectations=destination_expectations,
        )


def load_exact_run(
    *,
    registry_root: Path,
    index: Dict[str, Any],
    coordinates: RunCoordinates,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Path]:
    coordinates.validate()
    receipt_entry = index["receipts"].get(coordinates.receipt_id)
    if not isinstance(receipt_entry, dict):
        raise RegistryError("RECEIPT_ID_MISMATCH", exit_code=3)
    if receipt_entry.get("track_id") != coordinates.track_id:
        raise RegistryError("TRACK_ID_MISMATCH", exit_code=3)
    if receipt_entry.get("checkpoint_id") != coordinates.checkpoint_id:
        raise RegistryError("CHECKPOINT_ID_MISMATCH", exit_code=3)
    if receipt_entry.get("latest_revision") != coordinates.revision:
        raise RegistryError("RECEIPT_REVISION_CONFLICT", exit_code=3)
    if receipt_entry.get("latest_receipt_sha256") != coordinates.receipt_sha256:
        raise RegistryError("RECEIPT_HASH_CONFLICT", exit_code=3)
    track = index["tracks"].get(coordinates.track_id)
    if not isinstance(track, dict):
        raise RegistryError("REGISTRY_INDEX_INVALID")
    claim = track.get("active_claim")
    if not isinstance(claim, dict):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    for field, expected in (
        ("track_id", coordinates.track_id),
        ("checkpoint_id", coordinates.checkpoint_id),
        ("receipt_id", coordinates.receipt_id),
        ("latest_revision", coordinates.revision),
        ("latest_receipt_sha256", coordinates.receipt_sha256),
    ):
        if claim.get(field) != expected:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    persisted_claim = read_json_object(
        registry_root / "tracks" / coordinates.track_id / "claim.json",
        "ORPHANED_CLAIM_REVIEW_REQUIRED",
    )
    if persisted_claim != claim:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    receipt_path_value = receipt_entry.get("latest_receipt_path")
    if not isinstance(receipt_path_value, str):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    receipt_path = Path(receipt_path_value)
    expected_path = (
        registry_root
        / "tracks"
        / coordinates.track_id
        / "receipts"
        / "{}-r{:04d}.json".format(coordinates.receipt_id, coordinates.revision)
    )
    if receipt_path_value != str(expected_path):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    receipt, receipt_hash = read_hashed_json_object(
        regular_file(receipt_path, "ORPHANED_CLAIM_REVIEW_REQUIRED"),
        "ORPHANED_CLAIM_REVIEW_REQUIRED",
    )
    if receipt_hash != coordinates.receipt_sha256:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    validate_receipt_schema(receipt)
    if (
        not exact_integer(receipt.get("schema_version"), RECEIPT_SCHEMA_VERSION)
        or receipt.get("receipt_id") != coordinates.receipt_id
        or not exact_integer(receipt.get("revision"), coordinates.revision)
        or receipt.get("terminal") is not False
        or receipt.get("status") != "VERIFYING"
    ):
        raise RegistryError("RUN_NOT_ACTIVE", exit_code=3)
    return track, claim, receipt, receipt_path


def verify_receipt_artifacts(receipt: Dict[str, Any]) -> None:
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RegistryError("RECEIPT_ARTIFACTS_INVALID")
    for name in ("skill", "package", "handoff", "checkpoint"):
        record = artifacts.get(name)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise RegistryError("RECEIPT_ARTIFACTS_INVALID")
        try:
            path = regular_file(Path(record["path"]), "PACKAGE_ARTIFACT_DRIFT")
            observed_sha256 = sha256_file(path, "PACKAGE_ARTIFACT_DRIFT")
        except RegistryError as exc:
            raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3) from exc
        if observed_sha256 != record.get("sha256"):
            raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)


def verify_active_artifacts_or_terminalize(
    *,
    registry_root: Path,
    compatibility_output: Optional[Path],
    index: Dict[str, Any],
    track: Dict[str, Any],
    claim: Dict[str, Any],
    current: Dict[str, Any],
    coordinates: RunCoordinates,
    gitleaks_path: str,
    compatibility_destination: Optional[MutableDestination],
    reconcile_before_commit: bool = True,
) -> None:
    try:
        package_entry = package_entry_for(track, coordinates.checkpoint_id)
        load_verified_package(
            PackageCoordinate(
                coordinates.track_id, coordinates.checkpoint_id
            ).package_path(registry_root),
            package_entry,
        )
        verify_receipt_artifacts(current)
    except RegistryError as exc:
        if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
            raise
        output = compatibility_output
        if output is None:
            _, output = registry_invocation_bindings(registry_root)
        validate_compatibility_binding(registry_root, output)
        destination = compatibility_destination
        if destination is None:
            destination = preflight_compatibility_output(output)
        validate_compatibility_registry_event(
            path=output,
            destination=destination,
            registry_root=registry_root,
            index=index,
        )
        persist_terminal_run(
            registry_root=registry_root,
            compatibility_output=output,
            index=index,
            track=track,
            claim=claim,
            current=current,
            coordinates=coordinates,
            status=TerminalStatus.REVIEW_REQUIRED,
            drift=DriftClass.MATERIAL,
            current_phase=None,
            next_phase=None,
            reason_code="PACKAGE_ARTIFACT_DRIFT",
            reason="A claimed immutable package artifact changed.",
            gitleaks_path=gitleaks_path,
            compatibility_destination=destination,
            artifact_drift_detected=True,
            reconcile_before_commit=reconcile_before_commit,
        )
        raise


def transition_run(
    *,
    registry_root: Path,
    compatibility_output: Path,
    coordinates: RunCoordinates,
    gate: str,
    evidence_file: Optional[Path],
    gitleaks_path: str,
) -> Dict[str, Any]:
    coordinates.validate()
    validate_compatibility_binding(registry_root, compatibility_output)
    track_id = coordinates.track_id
    checkpoint_id = coordinates.checkpoint_id
    receipt_id = coordinates.receipt_id
    expected_revision = coordinates.revision
    expected_receipt_sha256 = coordinates.receipt_sha256
    if gate not in GATES:
        raise RegistryError("GATE_INVALID")
    if gate == "TELEMETRY_VALIDATED":
        raise RegistryError("GATE_TRANSITION_INVALID", exit_code=3)
    evidence = load_transition_evidence(evidence_file, gate)
    with registry_lock(registry_root):
        compatibility_destination = preflight_compatibility_output(compatibility_output)
        index = load_index(registry_root)
        track, claim, current, _ = load_exact_run(
            registry_root=registry_root,
            index=index,
            coordinates=coordinates,
        )
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        current_gate = current.get("last_completed_gate")
        if current_gate not in GATES:
            raise RegistryError("RECEIPT_GATE_INVALID")
        current_index = GATES.index(current_gate)
        if current_index + 1 >= len(GATES) or gate != GATES[current_index + 1]:
            raise RegistryError("GATE_TRANSITION_INVALID", exit_code=3)
        verify_active_artifacts_or_terminalize(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            index=index,
            track=track,
            claim=claim,
            current=current,
            coordinates=coordinates,
            gitleaks_path=gitleaks_path,
            compatibility_destination=compatibility_destination,
        )
        timestamp = utc_now()
        next_receipt = copy.deepcopy(current)
        next_receipt["revision"] = expected_revision + 1
        next_receipt["previous_receipt_sha256"] = expected_receipt_sha256
        next_receipt["event"] = ReceiptEvent.GATE_ADVANCED.value
        next_receipt["updated_at"] = timestamp
        next_receipt["last_completed_gate"] = gate
        evidence_history = next_receipt.get("transition_evidence")
        if not isinstance(evidence_history, list):
            raise RegistryError("RECEIPT_EVIDENCE_INVALID")
        evidence_history.append(evidence)
        receipt_path = (
            registry_root
            / "tracks"
            / track_id
            / "receipts"
            / "{}-r{:04d}.json".format(receipt_id, expected_revision + 1)
        )
        destination_expectations = capture_receipt_destinations(
            registry_root=registry_root,
            track_id=track_id,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
            include_claim=True,
        )
        try:
            receipt_data = prepare_receipt_data(
                registry_root=registry_root,
                receipt_path=receipt_path,
                receipt=next_receipt,
                gitleaks_path=gitleaks_path,
            )
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            reconcile_mutation(
                registry_root=registry_root,
                index=index,
                gitleaks_path=gitleaks_path,
                compatibility_output=compatibility_output,
                compatibility_destination=compatibility_destination,
            )
            raise
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        verify_active_artifacts_or_terminalize(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            index=index,
            track=track,
            claim=claim,
            current=current,
            coordinates=coordinates,
            gitleaks_path=gitleaks_path,
            compatibility_destination=compatibility_destination,
        )
        receipt_hash = hashlib.sha256(receipt_data).hexdigest()
        claim["latest_revision"] = expected_revision + 1
        claim["latest_receipt_sha256"] = receipt_hash
        claim["latest_receipt_path"] = str(receipt_path)
        track["active_claim"] = claim
        track["updated_at"] = timestamp
        if gate == "CANONICAL_PAIR_VERIFIED":
            package_entry_for(track, checkpoint_id)["state"] = (
                PackageState.OPENING.value
            )
        receipt_entry = index["receipts"][receipt_id]
        receipt_entry["latest_revision"] = expected_revision + 1
        receipt_entry["latest_receipt_sha256"] = receipt_hash
        receipt_entry["latest_receipt_path"] = str(receipt_path)
        index["updated_at"] = timestamp
        return persist_receipt_event(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            track_id=track_id,
            receipt=next_receipt,
            receipt_path=receipt_path,
            receipt_data=receipt_data,
            claim_view=claim,
            track_view=track,
            index_view=index,
            destination_expectations=destination_expectations,
        )


def validate_terminal_contract(
    status: str,
    drift: str,
    reason_code: Optional[str],
    reason: Optional[str],
) -> tuple[TerminalStatus, DriftClass]:
    try:
        terminal_status = TerminalStatus(status)
    except ValueError as exc:
        raise RegistryError("TERMINAL_STATUS_INVALID") from exc
    try:
        drift_class = DriftClass(drift)
    except ValueError as exc:
        raise RegistryError("TERMINAL_DRIFT_INVALID") from exc
    if drift_class not in TERMINAL_DRIFT_POLICY[terminal_status]:
        raise RegistryError("TERMINAL_DRIFT_INVALID")
    if terminal_status is not TerminalStatus.READY:
        if (
            not isinstance(reason_code, str)
            or not reason_code
            or not isinstance(reason, str)
            or not reason
        ):
            raise RegistryError("NON_READY_REASON_REQUIRED")
        if (
            TERMINAL_REASON_CODE_RE.fullmatch(reason_code) is None
            or reason != reason.strip()
            or len(reason) > MAX_TERMINAL_REASON_LENGTH
            or not reason.isprintable()
        ):
            raise RegistryError("NON_READY_REASON_INVALID")
        if reason_code == "PACKAGE_ARTIFACT_DRIFT":
            raise RegistryError("TERMINAL_REASON_RESERVED")
    return terminal_status, drift_class


def persist_terminal_run(
    *,
    registry_root: Path,
    compatibility_output: Path,
    index: Dict[str, Any],
    track: Dict[str, Any],
    claim: Dict[str, Any],
    current: Dict[str, Any],
    coordinates: RunCoordinates,
    status: TerminalStatus,
    drift: DriftClass,
    current_phase: Optional[str],
    next_phase: Optional[str],
    reason_code: Optional[str],
    reason: Optional[str],
    gitleaks_path: str,
    compatibility_destination: MutableDestination,
    artifact_drift_detected: bool = False,
    reconcile_before_commit: bool = True,
) -> Dict[str, Any]:
    track_id = coordinates.track_id
    checkpoint_id = coordinates.checkpoint_id
    expected_revision = coordinates.revision
    expected_receipt_sha256 = coordinates.receipt_sha256
    timestamp = utc_now()
    next_receipt = copy.deepcopy(current)
    next_receipt.update(
        {
            "revision": expected_revision + 1,
            "previous_receipt_sha256": expected_receipt_sha256,
            "event": ReceiptEvent.COMPLETED.value,
            "status": status.value,
            "terminal": True,
            "drift": drift.value,
            "updated_at": timestamp,
            "completed_at": timestamp,
            "last_completed_gate": "TELEMETRY_VALIDATED",
            "current_phase": current_phase,
            "next_phase": next_phase,
            "reason_code": reason_code,
            "reason": reason,
        }
    )
    receipt_path = (
        registry_root
        / "tracks"
        / track_id
        / "receipts"
        / "{}-r{:04d}.json".format(current["receipt_id"], expected_revision + 1)
    )
    package_entry = package_entry_for(track, checkpoint_id)
    additional_immutables: list[ImmutableWrite] = []
    quarantine_update: Optional[tuple[str, str]] = None
    if artifact_drift_detected:
        if (
            status is not TerminalStatus.REVIEW_REQUIRED
            or drift is not DriftClass.MATERIAL
            or reason_code != "PACKAGE_ARTIFACT_DRIFT"
        ):
            raise RegistryError("ARTIFACT_DRIFT_TERMINAL_INVALID")
        if package_entry.get("quarantine_reason_code") is None:
            event_data = prepare_quarantine_event(
                coordinate=PackageCoordinate(track_id, checkpoint_id),
                package_entry=package_entry,
                reason_code="PACKAGE_ARTIFACT_DRIFT",
            )
            event_hash = hashlib.sha256(event_data).hexdigest()
            quarantine_update = ("PACKAGE_ARTIFACT_DRIFT", event_hash)
            additional_immutables.append(
                ImmutableWrite(
                    path=PackageCoordinate(
                        track_id, checkpoint_id
                    ).quarantine_event_path(registry_root),
                    data=event_data,
                    existing_reason_code="IMMUTABLE_QUARANTINE_EXISTS",
                    cleanup_empty_parent=True,
                )
            )
        else:
            validate_quarantine_event(
                registry_root=registry_root,
                coordinate=PackageCoordinate(track_id, checkpoint_id),
                package_entry=package_entry,
            )
    destination_expectations = capture_receipt_destinations(
        registry_root=registry_root,
        track_id=track_id,
        compatibility_output=compatibility_output,
        compatibility_destination=compatibility_destination,
        include_claim=True,
    )
    try:
        receipt_data = prepare_receipt_data(
            registry_root=registry_root,
            receipt_path=receipt_path,
            receipt=next_receipt,
            gitleaks_path=gitleaks_path,
            allow_prevalidated_drift_terminal=artifact_drift_detected,
        )
    except RegistryError as exc:
        if artifact_drift_detected or exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
            raise
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        raise
    if reconcile_before_commit:
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        observed_drift: set[PackageCoordinate] = set()
    else:
        observed_drift = reconcile_registry_views(
            registry_root,
            index,
            collect_artifact_drift=True,
        )
    if not artifact_drift_detected:
        try:
            load_verified_package(
                PackageCoordinate(track_id, checkpoint_id).package_path(registry_root),
                package_entry,
            )
            verify_receipt_artifacts(current)
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            reconcile_mutation(
                registry_root=registry_root,
                compatibility_output=compatibility_output,
                index=index,
                gitleaks_path=gitleaks_path,
                compatibility_destination=compatibility_destination,
            )
            raise
    if quarantine_update is not None:
        (
            package_entry["quarantine_reason_code"],
            package_entry["quarantine_event_sha256"],
        ) = quarantine_update
    receipt_hash = hashlib.sha256(receipt_data).hexdigest()
    package_entry["state"] = (
        PackageState.CONSUMED.value
        if status is TerminalStatus.READY
        else PackageState.NEEDS_REVIEW.value
    )
    closed_claim = dict(claim)
    closed_claim.update(
        {
            "active": False,
            "latest_revision": expected_revision + 1,
            "latest_receipt_sha256": receipt_hash,
            "latest_receipt_path": str(receipt_path),
            "closed_at": timestamp,
            "terminal_status": status.value,
        }
    )
    track["active_claim"] = None
    track["updated_at"] = timestamp
    receipt_entry = index["receipts"][current["receipt_id"]]
    receipt_entry.update(
        {
            "latest_revision": expected_revision + 1,
            "latest_receipt_sha256": receipt_hash,
            "latest_receipt_path": str(receipt_path),
            "terminal_status": status.value,
        }
    )
    index["updated_at"] = timestamp
    return persist_receipt_event(
        registry_root=registry_root,
        compatibility_output=compatibility_output,
        track_id=track_id,
        receipt=next_receipt,
        receipt_path=receipt_path,
        receipt_data=receipt_data,
        claim_view=closed_claim,
        track_view=track,
        index_view=index,
        destination_expectations=destination_expectations,
        additional_immutables=additional_immutables,
        excluded_guard_coordinates=observed_drift,
        allow_receipt_skill_drift=artifact_drift_detected,
    )


def complete_run(
    *,
    registry_root: Path,
    compatibility_output: Path,
    coordinates: RunCoordinates,
    status: str,
    drift: str,
    current_phase: Optional[str],
    next_phase: Optional[str],
    reason_code: Optional[str],
    reason: Optional[str],
    gitleaks_path: str,
) -> Dict[str, Any]:
    coordinates.validate()
    validate_compatibility_binding(registry_root, compatibility_output)
    if (
        not optional_bounded_printable_string(current_phase, MAX_PHASE_LENGTH)
        or not optional_bounded_printable_string(next_phase, MAX_PHASE_LENGTH)
    ):
        raise RegistryError("TERMINAL_METADATA_INVALID")
    terminal_status, drift_class = validate_terminal_contract(
        status,
        drift,
        reason_code,
        reason,
    )
    if terminal_status is TerminalStatus.READY:
        required_metadata = (
            current_phase,
            next_phase,
        )
        if any(value is None for value in required_metadata):
            raise RegistryError("READY_METADATA_INCOMPLETE")
    with registry_lock(registry_root):
        compatibility_destination = preflight_compatibility_output(compatibility_output)
        index = load_index(registry_root)
        track, claim, current, _ = load_exact_run(
            registry_root=registry_root,
            index=index,
            coordinates=coordinates,
        )
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        if (
            terminal_status is TerminalStatus.READY
            and current.get("last_completed_gate") != "LIVE_STATE_VERIFIED"
        ):
            raise RegistryError("READY_GATES_INCOMPLETE", exit_code=3)
        verify_active_artifacts_or_terminalize(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            index=index,
            track=track,
            claim=claim,
            current=current,
            coordinates=coordinates,
            gitleaks_path=gitleaks_path,
            compatibility_destination=compatibility_destination,
        )
        return persist_terminal_run(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            index=index,
            track=track,
            claim=claim,
            current=current,
            coordinates=coordinates,
            status=terminal_status,
            drift=drift_class,
            current_phase=current_phase,
            next_phase=next_phase,
            reason_code=reason_code,
            reason=reason,
            gitleaks_path=gitleaks_path,
            compatibility_destination=compatibility_destination,
        )


def release_checkpoint(
    *,
    registry_root: Path,
    compatibility_output: Path,
    coordinates: RunCoordinates,
    gitleaks_path: str,
) -> Dict[str, Any]:
    coordinates.validate()
    validate_compatibility_binding(registry_root, compatibility_output)
    track_id = coordinates.track_id
    checkpoint_id = coordinates.checkpoint_id
    receipt_id = coordinates.receipt_id
    expected_revision = coordinates.revision
    expected_receipt_sha256 = coordinates.receipt_sha256
    with registry_lock(registry_root):
        compatibility_destination = preflight_compatibility_output(compatibility_output)
        index = load_index(registry_root)
        receipt_entry = index["receipts"].get(receipt_id)
        if not isinstance(receipt_entry, dict):
            raise RegistryError("RECEIPT_ID_MISMATCH", exit_code=3)
        expected_fields = {
            "track_id": track_id,
            "checkpoint_id": checkpoint_id,
            "latest_revision": expected_revision,
            "latest_receipt_sha256": expected_receipt_sha256,
        }
        for field, expected in expected_fields.items():
            if receipt_entry.get(field) != expected:
                raise RegistryError("RELEASE_CORRELATION_MISMATCH", exit_code=3)
        track = index["tracks"].get(track_id)
        if not isinstance(track, dict) or track.get("active_claim") is not None:
            raise RegistryError("RELEASE_NOT_PERMITTED", exit_code=3)
        package_entry = package_entry_for(track, checkpoint_id)
        if package_entry.get("state") != PackageState.NEEDS_REVIEW.value:
            raise RegistryError("RELEASE_NOT_PERMITTED", exit_code=3)
        if (
            package_entry.get("quarantine_reason_code") is not None
            or package_entry.get("quarantine_event_sha256") is not None
        ):
            raise RegistryError("RELEASE_NOT_PERMITTED", exit_code=3)
        claim_path = registry_root / "tracks" / track_id / "claim.json"
        closed_claim = read_json_object(claim_path, "ORPHANED_CLAIM_REVIEW_REQUIRED")
        for field, expected in {
            **expected_fields,
            "receipt_id": receipt_id,
            "active": False,
            "terminal_status": TerminalStatus.ABORTED.value,
        }.items():
            if closed_claim.get(field) != expected:
                raise RegistryError("RELEASE_NOT_PERMITTED", exit_code=3)
        receipt_path_value = receipt_entry.get("latest_receipt_path")
        if not isinstance(receipt_path_value, str):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        receipt_path = Path(receipt_path_value)
        expected_receipt_path = (
            registry_root
            / "tracks"
            / track_id
            / "receipts"
            / "{}-r{:04d}.json".format(receipt_id, expected_revision)
        )
        if receipt_path_value != str(expected_receipt_path):
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        current, observed_receipt_hash = read_hashed_json_object(
            regular_file(receipt_path, "ORPHANED_CLAIM_REVIEW_REQUIRED"),
            "ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        if observed_receipt_hash != expected_receipt_sha256:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        validate_receipt_schema(current)
        if (
            not exact_integer(current.get("schema_version"), RECEIPT_SCHEMA_VERSION)
            or current.get("receipt_id") != receipt_id
            or not exact_integer(current.get("revision"), expected_revision)
            or current.get("status") != TerminalStatus.ABORTED.value
            or current.get("terminal") is not True
        ):
            raise RegistryError("RELEASE_NOT_PERMITTED", exit_code=3)
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        verify_receipt_artifacts(current)
        timestamp = utc_now()
        released = released_receipt_from(
            current,
            revision=expected_revision + 1,
            previous_receipt_sha256=expected_receipt_sha256,
            updated_at=timestamp,
        )
        released_path = (
            registry_root
            / "tracks"
            / track_id
            / "receipts"
            / "{}-r{:04d}.json".format(receipt_id, expected_revision + 1)
        )
        destination_expectations = capture_receipt_destinations(
            registry_root=registry_root,
            track_id=track_id,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
            include_claim=True,
        )
        try:
            receipt_data = prepare_receipt_data(
                registry_root=registry_root,
                receipt_path=released_path,
                receipt=released,
                gitleaks_path=gitleaks_path,
            )
        except RegistryError as exc:
            if exc.reason_code != "PACKAGE_ARTIFACT_DRIFT":
                raise
            reconcile_mutation(
                registry_root=registry_root,
                index=index,
                gitleaks_path=gitleaks_path,
                compatibility_output=compatibility_output,
                compatibility_destination=compatibility_destination,
            )
            raise
        reconcile_mutation(
            registry_root=registry_root,
            index=index,
            gitleaks_path=gitleaks_path,
            compatibility_output=compatibility_output,
            compatibility_destination=compatibility_destination,
        )
        receipt_hash = hashlib.sha256(receipt_data).hexdigest()
        package_entry["state"] = PackageState.AVAILABLE.value
        closed_claim.update(
            {
                "latest_revision": expected_revision + 1,
                "latest_receipt_sha256": receipt_hash,
                "latest_receipt_path": str(released_path),
                "released_at": timestamp,
            }
        )
        track["updated_at"] = timestamp
        receipt_entry.update(
            {
                "latest_revision": expected_revision + 1,
                "latest_receipt_sha256": receipt_hash,
                "latest_receipt_path": str(released_path),
                "released_at": timestamp,
            }
        )
        index["updated_at"] = timestamp
        return persist_receipt_event(
            registry_root=registry_root,
            compatibility_output=compatibility_output,
            track_id=track_id,
            receipt=released,
            receipt_path=released_path,
            receipt_data=receipt_data,
            claim_view=closed_claim,
            track_view=track,
            index_view=index,
            destination_expectations=destination_expectations,
        )


def registry_ready_result(index: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "registry": "READY",
        "schema_version": index["schema_version"],
        "packages": sum(
            len(track["packages"])
            for track in index["tracks"].values()
        ),
        "claims": sum(
            isinstance(track.get("active_claim"), dict)
            for track in index["tracks"].values()
        ),
    }


def create_empty_registry(registry_root: Path) -> Dict[str, Any]:
    if directory_children(registry_root):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)

    tracks_root = registry_root / "tracks"
    tracks_expectation = capture_directory_expectation(
        tracks_root, "ORPHANED_CLAIM_REVIEW_REQUIRED"
    )
    owned_tracks = secure_directory(
        tracks_root,
        expectation=tracks_expectation,
        reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
    )
    if owned_tracks is None:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)

    committed = False
    try:
        index_path = registry_root / "index.json"
        destination = capture_mutable_destination(
            index_path,
            parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
            invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
        )
        if destination.existed:
            raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
        index = empty_index()
        write = MutableWrite(
            path=index_path,
            payload=index,
            parent_reason_code="REGISTRY_VIEW_PARENT_UNAVAILABLE",
            invalid_reason_code="ORPHANED_CLAIM_REVIEW_REQUIRED",
            expected_destination=destination,
        )
        validate_mutable_payload(write)
        commit_file_transaction(
            registry_root=registry_root,
            immutable_writes=(),
            mutable_writes=(write,),
        )
        committed = True
        return index
    except BaseException:
        if not committed:
            remove_owned_empty_directories((owned_tracks,))
        raise


def validate_initialized_registry(
    registry_root: Path, index: Dict[str, Any]
) -> None:
    if reconcile_registry_views(registry_root, index):
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)
    if load_index(registry_root) != index:
        raise RegistryError("ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3)


def initialize_registry(*, registry_root: Path) -> Dict[str, Any]:
    validate_registry_root_path(registry_root)
    root_expectation = capture_directory_expectation(
        registry_root, "REGISTRY_ROOT_INVALID"
    )
    if root_expectation.existed:
        with registry_lock(registry_root, create=False):
            children = directory_children(registry_root)
            if children:
                child_names = {child.name for child in children}
                if {"index.json", "tracks"} - child_names:
                    raise RegistryError(
                        "ORPHANED_CLAIM_REVIEW_REQUIRED", exit_code=3
                    )
                index = load_index(registry_root)
                if reconcile_registry_views(registry_root, index):
                    raise RegistryError("PACKAGE_ARTIFACT_DRIFT", exit_code=3)
            else:
                index = create_empty_registry(registry_root)
                validate_initialized_registry(registry_root, index)
            return registry_ready_result(index)

    owned_root = secure_directory(
        registry_root,
        expectation=root_expectation,
        reason_code="REGISTRY_ROOT_INVALID",
    )
    if owned_root is None:
        raise RegistryError("REGISTRY_ROOT_INVALID", exit_code=3)

    committed = False
    index: Optional[Dict[str, Any]] = None
    try:
        with registry_lock(registry_root, create=False):
            index = create_empty_registry(registry_root)
            committed = True
            validate_initialized_registry(registry_root, index)
    except BaseException:
        if not committed:
            remove_owned_empty_directories((owned_root,))
        raise

    if index is None:
        raise RegistryError("REGISTRY_INITIALIZATION_INCOMPLETE", exit_code=3)
    return registry_ready_result(index)


def inspect(*, registry_root: Path, selector: Optional[str]) -> Dict[str, Any]:
    validate_registry_root_path(registry_root)
    if not registry_root.exists() and not registry_root.is_symlink():
        if selector is None:
            return {"schema_version": REGISTRY_SCHEMA_VERSION, "packages": []}
        raise RegistryError("PICKUP_NOT_FOUND")
    with registry_lock(registry_root, create=False):
        index = load_index(registry_root)
        reconcile_registry_views(registry_root, index)
        if selector is None:
            packages = []
            for track_id, track in sorted(index["tracks"].items()):
                if not isinstance(track, dict) or not isinstance(
                    track.get("packages"), dict
                ):
                    raise RegistryError("REGISTRY_INDEX_INVALID")
                for checkpoint_id, entry in sorted(track["packages"].items()):
                    if not isinstance(entry, dict):
                        raise RegistryError("REGISTRY_INDEX_INVALID")
                    coordinate = PackageCoordinate(track_id, checkpoint_id)
                    package_path = coordinate.package_path(registry_root)
                    package = load_verified_package(package_path, entry)
                    summary = package_summary(
                        package,
                        package_path,
                        state=entry.get("state"),
                        claim_active=(
                            isinstance(track.get("active_claim"), dict)
                            and track["active_claim"].get("checkpoint_id")
                            == checkpoint_id
                        ),
                    )
                    summary.pop("package_path")
                    packages.append(summary)
            return {"schema_version": REGISTRY_SCHEMA_VERSION, "packages": packages}
        coordinate = parse_selector(selector)
        package_path = coordinate.package_path(registry_root)
        track = index["tracks"].get(coordinate.track_id)
        if not isinstance(track, dict) or not isinstance(track.get("packages"), dict):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        package_entry = track["packages"].get(coordinate.checkpoint_id)
        if not isinstance(package_entry, dict):
            raise RegistryError("REGISTRY_INDEX_INVALID")
        package = load_verified_package(package_path, package_entry)
        return package_summary(
            package,
            package_path,
            state=package_entry.get("state"),
            claim_active=(
                isinstance(track.get("active_claim"), dict)
                and track["active_claim"].get("checkpoint_id")
                == coordinate.checkpoint_id
            ),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    publish = commands.add_parser("publish")
    publish.add_argument("--registry-root", default=None)
    publish.add_argument("--track-id", required=True)
    publish.add_argument("--resource-scope", action="append", required=True)
    publish.add_argument("--handoff", required=True)
    publish.add_argument("--checkpoint", required=True)
    publish.add_argument("--gitleaks-path", default=shutil.which("gitleaks") or "")
    publish.set_defaults(handler=handle_publish)

    initialize = commands.add_parser("initialize")
    initialize.add_argument("--registry-root", default=None)
    initialize.set_defaults(handler=handle_initialize)

    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("--registry-root", default=None)
    inspect_command.add_argument("--selector")
    inspect_command.set_defaults(handler=handle_inspect)

    claim = commands.add_parser("claim")
    claim.add_argument("--registry-root", default=None)
    claim.add_argument(
        "--compatibility-output", default=None
    )
    claim.add_argument("--selector")
    claim.add_argument("--workspace", required=True)
    claim.add_argument("--fresh-task", required=True)
    claim.add_argument("--freshness-basis", required=True)
    claim.add_argument("--invocation-mode", required=True)
    claim.add_argument("--model", required=True)
    claim.add_argument("--effort", required=True)
    claim.add_argument("--skill-file", required=True)
    claim.add_argument("--gitleaks-path", default=shutil.which("gitleaks") or "")
    claim.set_defaults(handler=handle_claim)

    advance = commands.add_parser("advance")
    advance.add_argument("--registry-root", default=None)
    advance.add_argument(
        "--compatibility-output", default=None
    )
    advance.add_argument("--track-id", required=True)
    advance.add_argument("--checkpoint-id", required=True)
    advance.add_argument("--receipt-id", required=True)
    advance.add_argument("--expected-revision", type=int, required=True)
    advance.add_argument("--expected-receipt-sha256", required=True)
    advance.add_argument("--gate", required=True)
    advance.add_argument("--evidence-file")
    advance.add_argument("--gitleaks-path", default=shutil.which("gitleaks") or "")
    advance.set_defaults(handler=handle_advance)

    complete = commands.add_parser("complete")
    complete.add_argument("--registry-root", default=None)
    complete.add_argument(
        "--compatibility-output", default=None
    )
    complete.add_argument("--track-id", required=True)
    complete.add_argument("--checkpoint-id", required=True)
    complete.add_argument("--receipt-id", required=True)
    complete.add_argument("--expected-revision", type=int, required=True)
    complete.add_argument("--expected-receipt-sha256", required=True)
    complete.add_argument("--status", required=True)
    complete.add_argument("--drift", required=True)
    complete.add_argument("--current-phase")
    complete.add_argument("--next-phase")
    complete.add_argument("--reason-code")
    complete.add_argument("--reason")
    complete.add_argument("--gitleaks-path", default=shutil.which("gitleaks") or "")
    complete.set_defaults(handler=handle_complete)

    release = commands.add_parser("release")
    release.add_argument("--registry-root", default=None)
    release.add_argument(
        "--compatibility-output", default=None
    )
    release.add_argument("--track-id", required=True)
    release.add_argument("--checkpoint-id", required=True)
    release.add_argument("--receipt-id", required=True)
    release.add_argument("--expected-revision", type=int, required=True)
    release.add_argument("--expected-receipt-sha256", required=True)
    release.add_argument("--gitleaks-path", default=shutil.which("gitleaks") or "")
    release.set_defaults(handler=handle_release)
    return parser


def coordinates_from_args(args: argparse.Namespace) -> RunCoordinates:
    return RunCoordinates(
        track_id=args.track_id,
        checkpoint_id=args.checkpoint_id,
        receipt_id=args.receipt_id,
        revision=args.expected_revision,
        receipt_sha256=args.expected_receipt_sha256,
    )


def handle_publish(args: argparse.Namespace) -> Dict[str, Any]:
    return publish_checkpoint(
        registry_root=Path(args.registry_root),
        track_id=args.track_id,
        handoff_path=Path(args.handoff),
        checkpoint_path=Path(args.checkpoint),
        resource_scopes=args.resource_scope,
        gitleaks_path=args.gitleaks_path,
    )


def handle_initialize(args: argparse.Namespace) -> Dict[str, Any]:
    return initialize_registry(registry_root=Path(args.registry_root))


def handle_inspect(args: argparse.Namespace) -> Dict[str, Any]:
    return inspect(registry_root=Path(args.registry_root), selector=args.selector)


def handle_claim(args: argparse.Namespace) -> Dict[str, Any]:
    return claim_checkpoint(
        registry_root=Path(args.registry_root),
        compatibility_output=Path(args.compatibility_output),
        selector=args.selector,
        invocation=InvocationContext(
            workspace=Path(args.workspace),
            fresh_task=args.fresh_task,
            freshness_basis=args.freshness_basis,
            mode=args.invocation_mode,
            model=args.model,
            effort=args.effort,
            skill_file=Path(args.skill_file),
        ),
        gitleaks_path=args.gitleaks_path,
    )


def handle_advance(args: argparse.Namespace) -> Dict[str, Any]:
    return transition_run(
        registry_root=Path(args.registry_root),
        compatibility_output=Path(args.compatibility_output),
        coordinates=coordinates_from_args(args),
        gate=args.gate,
        evidence_file=(
            Path(args.evidence_file) if args.evidence_file is not None else None
        ),
        gitleaks_path=args.gitleaks_path,
    )


def handle_complete(args: argparse.Namespace) -> Dict[str, Any]:
    return complete_run(
        registry_root=Path(args.registry_root),
        compatibility_output=Path(args.compatibility_output),
        coordinates=coordinates_from_args(args),
        status=args.status,
        drift=args.drift,
        current_phase=args.current_phase,
        next_phase=args.next_phase,
        reason_code=args.reason_code,
        reason=args.reason,
        gitleaks_path=args.gitleaks_path,
    )


def handle_release(args: argparse.Namespace) -> Dict[str, Any]:
    return release_checkpoint(
        registry_root=Path(args.registry_root),
        compatibility_output=Path(args.compatibility_output),
        coordinates=coordinates_from_args(args),
        gitleaks_path=args.gitleaks_path,
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    workspace = Path(
        getattr(args, "workspace", None)
        or os.environ.get("PICKUP_HOME")
        or Path.home() / "Desktop" / "pickup_audit"
    ).expanduser()
    if args.registry_root is None:
        args.registry_root = str(workspace / "treasurepickup" / "pickups")
    if hasattr(args, "compatibility_output") and args.compatibility_output is None:
        _, output = registry_invocation_bindings(Path(args.registry_root))
        args.compatibility_output = str(output)
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        result = args.handler(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except RegistryError as exc:
        print(
            json.dumps({"reason_code": exc.reason_code}, sort_keys=True),
            file=sys.stderr,
        )
        return exc.exit_code
    except (OSError, RuntimeError, TypeError, ValueError):
        print(
            json.dumps({"reason_code": "FILESYSTEM_OPERATION_FAILED"}, sort_keys=True),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
