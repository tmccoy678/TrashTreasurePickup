"""Check distribution integrity through the bundle command-line interface."""

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
TRASH = REPO / "skills" / "trashpickup"


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pickup bundle ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.trash = self.root / "trash"
        self.treasure = self.root / "treasure"
        for source, target in ((TRASH, self.trash), (REPO / "skills/treasurepickup", self.treasure)):
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(
                ".git", ".scratch", "dist", "__pycache__", ".pixi"))
        shutil.copytree(REPO / "installer", self.treasure / "installer")
        self.output = self.root / "pickup-install.command"

    def bundle(self, *args):
        return subprocess.run([
            sys.executable, str(REPO / "installer" / "bundle.py"),
            "--trash", str(self.trash), "--treasure", str(self.treasure),
            "--installer", str(self.treasure / "installer"),
            "--output", str(self.output), *args,
        ], capture_output=True, text=True)

    def test_missing_security_policy_prevents_distribution(self):
        (self.trash / "SECURITY.md").unlink()
        result = self.bundle()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECURITY.md", result.stderr)
        self.assertFalse(self.output.exists())

    def test_verify_rejects_changed_distributed_source(self):
        built = self.bundle()
        self.assertEqual(built.returncode, 0, built.stderr)
        verified = self.bundle("--verify")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        (self.trash / "README.md").write_text("Changed after packaging")
        result = self.bundle("--verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trashpickup/README.md", result.stderr)

    def test_declared_source_pair_must_match_distributed_bytes(self):
        commits = []
        for root in (self.trash, self.treasure):
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture"], check=True)
            commits.append(subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip())
        pins = ["--trash-commit", commits[0], "--treasure-commit", commits[1]]
        built = self.bundle(*pins)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(self.bundle("--verify", *pins).returncode, 0)
        (self.trash / "README.md").write_text("Uncommitted distributed change")
        result = self.bundle(*pins)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("declared commit", result.stderr)

    def test_missing_third_party_notice_prevents_distribution(self):
        (self.treasure / "installer" / "GITLEAKS-LICENSE").unlink()
        self.assertNotEqual(self.bundle().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_verify_rejects_mutable_recorded_source_references(self):
        for root in (self.trash, self.treasure):
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture"], check=True)
        self.assertEqual(self.bundle().returncode, 0)
        script = self.output.read_text()
        encoded = script.split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
        payload = base64.b64decode(encoded)
        archive_bytes = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as original, tarfile.open(fileobj=archive_bytes, mode="w") as changed:
            for member in original.getmembers():
                data = original.extractfile(member).read()
                if member.name == "source-manifest.json":
                    manifest = json.loads(data)
                    for source in manifest["sources"].values():
                        source["commit"] = "HEAD"
                    data = json.dumps(manifest, indent=2).encode() + b"\n"
                    member.size = len(data)
                changed.addfile(member, io.BytesIO(data))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0, filename="") as stream:
            stream.write(archive_bytes.getvalue())
        altered = compressed.getvalue()
        script = script.replace(encoded, base64.encodebytes(altered).decode().rstrip("\n"))
        script = script.replace(hashlib.sha256(payload).hexdigest(), hashlib.sha256(altered).hexdigest())
        self.output.write_text(script)
        result = self.bundle("--verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("immutable", result.stderr)

    def test_missing_host_metadata_and_support_reference_are_rejected(self):
        for relative in ("agents/openai.yaml", "references/pickup-registry.md"):
            path = self.trash / relative
            data = path.read_bytes()
            path.unlink()
            result = self.bundle()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(relative, result.stderr)
            path.write_bytes(data)

    def test_changed_script_is_rejected_without_execution(self):
        self.assertEqual(self.bundle().returncode, 0)
        sentinel = self.root / "executed"
        with self.output.open("a") as stream:
            stream.write(f'\ntouch "{sentinel}"\n')
        result = self.bundle("--verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("script", result.stderr)
        self.assertFalse(sentinel.exists())

    def test_repeated_build_has_identical_bytes(self):
        self.assertEqual(self.bundle().returncode, 0)
        first = self.output.read_bytes()
        self.assertEqual(self.bundle().returncode, 0)
        self.assertEqual(self.output.read_bytes(), first)

    def test_bundle_manifest_hashes_cover_exact_payload(self):
        self.assertEqual(self.bundle().returncode, 0)
        encoded = self.output.read_text().split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(encoded)), mode="r:gz") as archive:
            files = {item.name: archive.extractfile(item).read() for item in archive.getmembers()}
        manifest = json.loads(files.pop("source-manifest.json"))
        self.assertEqual(set(files), set(manifest["sha256"]))
        for path, data in files.items():
            self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["sha256"][path])


if __name__ == "__main__":
    unittest.main()
