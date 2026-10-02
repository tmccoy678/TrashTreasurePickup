"""Verify the downloadable installer contains only the simple public pair."""

import base64
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pickup bundle ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        shutil.copytree(
            REPO,
            self.source,
            ignore=shutil.ignore_patterns(".git", ".scratch", "dist", "__pycache__"),
        )
        self.output = self.root / "pickup-install.command"

    def bundle(self, *args):
        return subprocess.run(
            [
                sys.executable,
                str(self.source / "installer/bundle.py"),
                "--source-root",
                str(self.source),
                "--output",
                str(self.output),
                *args,
            ],
            text=True,
            capture_output=True,
        )

    def payload(self):
        text = self.output.read_text()
        encoded = text.split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(encoded)), mode="r:gz") as archive:
            return {member.name: archive.extractfile(member).read() for member in archive.getmembers()}

    def commit_source(self):
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(
            [
                "git", "-C", str(self.source), "-c", "user.name=Fixture",
                "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture",
            ],
            check=True,
        )
        return subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True
        ).strip()

    def test_bundle_contains_only_two_instruction_skills_and_installer(self):
        result = self.bundle()
        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.payload()
        expected = {"source-manifest.json", "installer/install.sh"}
        for name in ("trashpickup", "treasurepickup"):
            expected.update(
                {
                    f"{name}/SKILL.md",
                    f"{name}/README.md",
                    f"{name}/LICENSE",
                    f"{name}/SECURITY.md",
                    f"{name}/agents/openai.yaml",
                }
            )
        self.assertEqual(set(files), expected)
        self.assertFalse(any("scripts/" in name or "references/" in name for name in files))
        manifest = json.loads(files["source-manifest.json"])
        self.assertEqual(manifest["format"], "pickup-single-repository-v1")
        self.assertEqual(self.bundle("--verify").returncode, 0)

    def test_bundled_command_installs_the_pair(self):
        self.assertEqual(self.bundle().returncode, 0)
        home = self.root / "home"
        home.mkdir()
        result = subprocess.run(
            ["/bin/bash", str(self.output), "--yes"],
            env={**os.environ, "HOME": str(home)},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("trashpickup", "treasurepickup"):
            installed = home / ".agents/skills" / name
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertFalse((installed / "scripts").exists())

    def test_missing_or_symlinked_input_is_rejected(self):
        path = self.source / "skills/trashpickup/SKILL.md"
        original = path.read_bytes()
        path.unlink()
        missing = self.bundle()
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(self.output.exists())
        outside = self.root / "outside.md"
        outside.write_bytes(original)
        path.symlink_to(outside)
        symlink = self.bundle()
        self.assertNotEqual(symlink.returncode, 0)
        self.assertIn("regular", symlink.stderr)

    def test_clean_commit_binds_the_distributed_bytes(self):
        commit = self.commit_source()
        built = self.bundle("--source-commit", commit)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(self.bundle("--verify", "--source-commit", commit).returncode, 0)
        skill = self.source / "skills/trashpickup/SKILL.md"
        skill.write_text(skill.read_text() + "\nchanged\n")
        changed = self.bundle("--source-commit", commit)
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("declared commit", changed.stderr)

    def test_repeated_build_is_identical(self):
        self.assertEqual(self.bundle().returncode, 0)
        first = self.output.read_bytes()
        self.assertEqual(self.bundle().returncode, 0)
        self.assertEqual(self.output.read_bytes(), first)

    def test_changed_wrapper_is_rejected_without_execution(self):
        self.assertEqual(self.bundle().returncode, 0)
        with self.output.open("a") as stream:
            stream.write("\nexit 0\n")
        verified = self.bundle("--verify")
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("script", verified.stderr)


if __name__ == "__main__":
    unittest.main()
