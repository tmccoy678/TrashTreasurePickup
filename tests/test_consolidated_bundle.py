"""Exercise single-repository distribution through its public command line."""

import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class ConsolidatedBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pickup one checkout ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        shutil.copytree(REPO, self.source, ignore=shutil.ignore_patterns(
            ".git", ".scratch", "dist", "__pycache__", ".pixi"))
        self.output = self.root / "pickup-install.command"

    def bundle(self, *args):
        return subprocess.run([
            sys.executable, str(self.source / "installer/bundle.py"),
            "--source-root", str(self.source), "--output", str(self.output), *args,
        ], capture_output=True, text=True)

    def payload(self):
        script = self.output.read_text()
        encoded = script.split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(encoded)), mode="r:gz") as archive:
            return {item.name: archive.extractfile(item).read() for item in archive.getmembers()}

    def commit_source(self):
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.source), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture"], check=True)
        return subprocess.check_output(["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True).strip()

    def rewrite_manifest(self, change):
        script = self.output.read_text()
        encoded = script.split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
        payload = base64.b64decode(encoded)
        stream = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as original, tarfile.open(fileobj=stream, mode="w") as altered:
            for member in original.getmembers():
                data = original.extractfile(member).read()
                if member.name == "source-manifest.json":
                    manifest = json.loads(data)
                    change(manifest)
                    data = json.dumps(manifest, indent=2).encode() + b"\n"
                    member.size = len(data)
                altered.addfile(member, io.BytesIO(data))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0, filename="") as archive:
            archive.write(stream.getvalue())
        replacement = compressed.getvalue()
        script = script.replace(encoded, base64.encodebytes(replacement).decode().rstrip("\n"))
        script = script.replace(hashlib.sha256(payload).hexdigest(), hashlib.sha256(replacement).hexdigest())
        self.output.write_text(script)

    def test_one_checkout_bundles_both_named_skills_and_shared_tools(self):
        result = self.bundle()
        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.payload()
        for name in ("trashpickup", "treasurepickup"):
            self.assertEqual(files[name + "/SKILL.md"], (self.source / "skills" / name / "SKILL.md").read_bytes())
            self.assertEqual(files[name + "/references/first-use.md"], (self.source / "references/first-use.md").read_bytes())
        self.assertIn("treasurepickup/scripts/pickup", files)
        manifest = json.loads(files["source-manifest.json"])
        self.assertEqual(manifest["format"], "pickup-single-repository-v1")
        self.assertEqual(manifest["source_paths"]["trashpickup/SKILL.md"], "skills/trashpickup/SKILL.md")
        self.assertEqual(manifest["source_paths"]["treasurepickup/references/first-use.md"], "references/first-use.md")
        self.assertEqual(self.bundle("--verify").returncode, 0)

    def test_legacy_source_options_are_not_silently_ignored(self):
        result = self.bundle("--treasure", str(self.root / "wrong source"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_required_inputs_cannot_be_omitted(self):
        for relative in ("skills/trashpickup/SKILL.md", "skills/treasurepickup/SKILL.md",
                         "skills/trashpickup/agents/openai.yaml", "SECURITY.md", "LICENSE",
                         "CONTRIBUTING.md", "references/first-use.md", "installer/GITLEAKS-LICENSE"):
            with self.subTest(missing=relative):
                path = self.source / relative
                data = path.read_bytes()
                path.unlink()
                result = self.bundle()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(relative, result.stderr)
                self.assertFalse(self.output.exists())
                path.write_bytes(data)

    def test_declared_commit_binds_the_distributed_bytes(self):
        commit = self.commit_source()
        built = self.bundle("--source-commit", commit)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(self.bundle("--verify", "--source-commit", commit).returncode, 0)
        path = self.source / "skills/trashpickup/SKILL.md"
        path.write_text(path.read_text() + "\nUncommitted change\n")
        result = self.bundle("--source-commit", commit)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("declared commit", result.stderr)
        self.assertNotEqual(self.bundle("--verify").returncode, 0)

    def test_recorded_mapping_and_commit_cannot_be_substituted(self):
        self.commit_source()
        self.assertEqual(self.bundle().returncode, 0)
        original = self.output.read_bytes()
        mutations = (
            ("immutable", lambda value: value["source"].update(commit="HEAD")),
            ("mapping", lambda value: value["source_paths"].update({"trashpickup/LICENSE": "../LICENSE"})),
            ("not a commit", lambda value: value["source"].update(commit="0" * 40)),
        )
        for expected, change in mutations:
            with self.subTest(expected=expected):
                self.output.write_bytes(original)
                self.rewrite_manifest(change)
                result = self.bundle("--verify")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_manifest_without_new_format_is_not_reinterpreted(self):
        self.assertEqual(self.bundle().returncode, 0)
        self.rewrite_manifest(lambda value: value.pop("format"))
        result = self.bundle("--verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("historical paired checkout", result.stderr)

    def test_shared_non_markdown_reference_is_copied_and_shipped(self):
        relative = "references/example.txt"
        (self.source / relative).write_text("Portable reference fixture")
        synced = subprocess.run([sys.executable, str(self.source / "scripts/sync_skill_docs.py")], capture_output=True, text=True)
        self.assertEqual(synced.returncode, 0, synced.stderr)
        self.assertEqual(self.bundle().returncode, 0)
        files = self.payload()
        for name in ("trashpickup", "treasurepickup"):
            self.assertEqual(files[name + "/" + relative], b"Portable reference fixture")

    def test_document_sync_refuses_a_symlinked_destination_directory(self):
        references = self.source / "skills/trashpickup/references"
        outside = self.root / "outside"
        references.rename(outside)
        sentinel = outside / "first-use.md"
        sentinel.write_text("Keep outside content")
        references.symlink_to(outside, target_is_directory=True)
        result = subprocess.run([sys.executable, str(self.source / "scripts/sync_skill_docs.py")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "Keep outside content")

    def test_clean_pinned_rebuild_has_identical_bytes(self):
        commit = self.commit_source()
        self.assertEqual(self.bundle("--source-commit", commit).returncode, 0)
        first = self.output.read_bytes()
        self.assertEqual(self.bundle("--source-commit", commit).returncode, 0)
        self.assertEqual(self.output.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
