"""Public command-line path configuration, without running operational commands."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry = load_script("pickup_registry")
receipt = load_script("treasurepickup_receipt")


class WorkspacePathTests(unittest.TestCase):
    def claim_args(self, *paths):
        return registry.parse_args([
            "claim", "--workspace", "/example/explicit workspace",
            "--fresh-task", "YES", "--freshness-basis", "FIRST_SUBSTANTIVE_USER_TURN",
            "--invocation-mode", "MANUAL_SKILL_SELECTOR", "--model", "UNKNOWN",
            "--effort", "UNKNOWN", "--skill-file", "/example/SKILL.md", *paths,
        ])

    def test_registry_default_follows_configured_workspace_at_invocation(self):
        with mock.patch.dict(os.environ, {"PICKUP_HOME": "/example/custom workspace"}):
            args = registry.parse_args(["inspect"])
        self.assertEqual(
            args.registry_root,
            "/example/custom workspace/treasurepickup/pickups",
        )

    def test_claim_explicit_workspace_controls_dependent_defaults(self):
        with mock.patch.dict(os.environ, {"PICKUP_HOME": "/example/unused"}):
            args = self.claim_args()
        self.assertEqual(args.registry_root, "/example/explicit workspace/treasurepickup/pickups")
        self.assertEqual(args.compatibility_output, "/example/explicit workspace/treasurepickup/context-resume.json")

    def test_registry_discovers_scanner_on_path_unless_explicit(self):
        with tempfile.TemporaryDirectory(prefix=".path-test-", dir=SCRIPTS.parent) as temporary:
            scanner = Path(temporary) / "gitleaks"
            scanner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            scanner.chmod(0o700)
            with mock.patch.dict(os.environ, {"PATH": temporary}):
                self.assertEqual(self.claim_args().gitleaks_path, str(scanner))
                self.assertEqual(self.claim_args("--gitleaks-path", "/example/scanner").gitleaks_path, "/example/scanner")

    def test_legacy_expected_workspace_controls_files_but_keeps_observed_workspace(self):
        with mock.patch.dict(os.environ, {"PICKUP_HOME": "/example/unused"}):
            args = receipt.parse_args([
                "start", "--workspace", "/example/observed",
                "--expected-workspace", "/example/configured",
                "--fresh-task", "YES", "--freshness-basis", "FIRST_SUBSTANTIVE_USER_TURN",
            ])
        self.assertEqual(args.workspace, "/example/observed")
        self.assertEqual(args.expected_workspace, "/example/configured")
        self.assertEqual(args.output, "/example/configured/treasurepickup/context-resume.json")
        self.assertEqual(args.handoff, "/example/configured/trashpickup/current-context.md")
        self.assertEqual(args.checkpoint, "/example/configured/trashpickup/context-checkpoint.json")

    def test_unconfigured_commands_default_to_current_users_home(self):
        with mock.patch.dict(os.environ, {"PICKUP_HOME": ""}), mock.patch.object(Path, "home", return_value=Path("/example/user")):
            self.assertEqual(registry.parse_args(["inspect"]).registry_root, "/example/user/Desktop/pickup_audit/treasurepickup/pickups")
            self.assertEqual(receipt.parse_args(["summary"]).output, "/example/user/Desktop/pickup_audit/treasurepickup/context-resume.json")

    def test_explicit_registry_and_output_override_workspace_defaults(self):
        with mock.patch.dict(os.environ, {"PICKUP_HOME": "/example/unused"}):
            args = self.claim_args("--registry-root", "/example/other/treasurepickup/pickups", "--compatibility-output", "/example/explicit-output.json")
        self.assertEqual(args.registry_root, "/example/other/treasurepickup/pickups")
        self.assertEqual(args.compatibility_output, "/example/explicit-output.json")

    def test_explicit_registry_controls_default_compatibility_location(self):
        args = self.claim_args("--registry-root", "/example/other/treasurepickup/pickups")
        self.assertEqual(args.compatibility_output, "/example/other/treasurepickup/context-resume.json")

    def test_custom_registry_layout_preserves_workspace_binding(self):
        args = self.claim_args("--registry-root", "/example/other/storage/pickups")
        self.assertEqual(args.compatibility_output, "/example/other/treasurepickup/context-resume.json")

    def test_legacy_explicit_files_override_workspace_defaults(self):
        with mock.patch.dict(os.environ, {"PICKUP_HOME": "/example/configured"}):
            args = receipt.parse_args([
                "start", "--workspace", "/example/observed", "--output", "/example/receipt.json",
                "--handoff", "/example/handoff.md", "--checkpoint", "/example/checkpoint.json",
                "--fresh-task", "YES", "--freshness-basis", "FIRST_SUBSTANTIVE_USER_TURN",
            ])
        self.assertEqual(args.expected_workspace, "/example/configured")
        self.assertEqual((args.output, args.handoff, args.checkpoint), ("/example/receipt.json", "/example/handoff.md", "/example/checkpoint.json"))

    def test_legacy_observed_workspace_default_remains_current_directory(self):
        args = receipt.parse_args(["start", "--fresh-task", "YES", "--freshness-basis", "FIRST_SUBSTANTIVE_USER_TURN"])
        self.assertEqual(args.workspace, os.getcwd())


if __name__ == "__main__":
    unittest.main()
