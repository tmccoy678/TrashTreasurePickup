"""Exercise the installer CLI; downloaded tool distributions are test fixtures."""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
TRASH = REPO.parent / "draft2staged-trashpickup"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pickup installation ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        for name, source in (("trashpickup", TRASH), ("treasurepickup", REPO)):
            target = self.bundle / name
            target.mkdir()
            for item in ("SKILL.md", "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "agents", "references", "scripts"):
                origin = source / item
                if origin.is_dir():
                    shutil.copytree(origin, target / item, ignore=shutil.ignore_patterns("__pycache__"))
                elif origin.exists():
                    shutil.copy2(origin, target / item)
        shutil.copytree(REPO / "installer", self.bundle / "installer")
        # These replace external download services, not Pickup implementation.
        pixi = self.root / "pixi"
        python = shlex.quote(sys.executable)
        git = shlex.quote(shutil.which("git"))
        pixi.write_text('#!/bin/sh\nwhile [ "$1" != "--manifest-path" ]; do shift; done\n'
                        'shift\nprefix="$(dirname "$1")/.pixi/envs/default/bin"\n'
                        'mkdir -p "$prefix"\n'
                        f'ln -s {python} "$prefix/python3"\nln -s {git} "$prefix/git"\n')
        pixi.chmod(0o700)
        scanner = self.root / "gitleaks"
        scanner.write_text("#!/bin/sh\nexit 0\n")
        scanner.chmod(0o700)
        archive = self.root / "gitleaks.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(scanner, arcname="gitleaks")
        self.assets = self.bundle / "installer" / "assets.tsv"
        self.assets.write_text("".join(
            f'{platform.machine()}\t{name}\t{path.as_uri()}\t{hashlib.sha256(path.read_bytes()).hexdigest()}\n'
            for name, path in (("pixi", pixi), ("gitleaks", archive))
        ))
        self.env = {**os.environ, "HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PICKUP_HOME": "", "PYTHONDONTWRITEBYTECODE": "1"}
        self.skills = self.home / ".agents" / "skills"

    def install(self, *args, input="", expected=0):
        result = subprocess.run(["/bin/bash", str(REPO / "installer" / "install.sh"), str(self.bundle), *args],
                                input=input, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def pickup(self, *args, input=None, expected=0, extra_env=None):
        result = subprocess.run([str(self.skills / "treasurepickup" / "scripts" / "pickup"), *args],
                                input=input, env={**self.env, **(extra_env or {})}, text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_defaults_install_a_usable_pair_without_user_tool_configuration(self):
        result = self.install("--yes")
        self.assertIn("Pickup installed", result.stdout)
        for name in ("trashpickup", "treasurepickup"):
            self.assertTrue((self.skills / name / "SKILL.md").is_file())
        self.pickup("registry", "--help")
        self.pickup("python", "-m", "json.tool", input='{"checkpoint": true}')
        self.pickup("git", "init", str(self.root / "project"))
        config = json.loads(self.pickup("config").stdout)
        self.assertEqual(config["pickup_home"], str(self.home / "Desktop" / "pickup_audit"))
        self.assertFalse((self.home / "Desktop").exists(), "Installation must not create pickup history")

    def test_failed_download_can_retry_without_changing_existing_data(self):
        audit = self.home / "Desktop" / "pickup_audit"
        audit.mkdir(parents=True)
        retained = audit / "handoff.md"
        retained.write_text("Preserve this handoff")
        original = self.assets.read_text()
        fields = original.splitlines()[0].split("\t")
        fields[2] = (self.root / "missing-download").as_uri()
        self.assets.write_text("\t".join(fields) + "\n" + original.splitlines()[1] + "\n")
        failed = subprocess.run(["/bin/bash", str(REPO / "installer" / "install.sh"), str(self.bundle), "--yes"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertNotIn("Pickup installed", failed.stdout)
        self.assertFalse(self.skills.exists())
        self.assertEqual(retained.read_text(), "Preserve this handoff")
        self.assets.write_text(original)
        self.install("--yes")
        self.assertEqual(retained.read_text(), "Preserve this handoff")

    def test_checksum_mismatch_preserves_the_installed_pair(self):
        self.install("--yes")
        skill = self.skills / "trashpickup" / "SKILL.md"
        skill.write_text("Custom skill")
        self.assets.write_text(self.assets.read_text().replace(hashlib.sha256((self.root / "pixi").read_bytes()).hexdigest(), "0" * 64))
        result = self.install("--yes", expected=1)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertEqual(skill.read_text(), "Custom skill")
        self.pickup("registry", "--help")

    def test_guide_saves_custom_locations_and_environment_still_overrides(self):
        self.skills = self.home / "My skills"
        audit = self.home / "My audit"
        audit.mkdir()
        self.install(input=f"n\n{self.skills}\n{audit}\n")
        self.assertEqual(json.loads(self.pickup("config").stdout)["pickup_home"], str(audit))
        other = str(self.home / "override")
        self.assertEqual(json.loads(self.pickup("config", extra_env={"PICKUP_HOME": other}).stdout)["pickup_home"], other)
        self.pickup("registry", "inspect")

    def test_existing_skill_is_preserved_until_replacement_is_accepted(self):
        self.install("--yes")
        custom = self.skills / "trashpickup" / "SKILL.md"
        custom.write_text("My custom skill")
        self.install(input="\nn\n", expected=1)
        self.assertEqual(custom.read_text(), "My custom skill")
        result = self.install(input="\ny\n")
        self.assertIn("Previous skills retained", result.stdout)
        self.assertIn("# Trash Pickup", custom.read_text())
        self.assertTrue(any(path.read_text() == "My custom skill" for path in self.skills.glob(".pickup-backup-*/trashpickup/SKILL.md")))
        self.pickup("registry", "--help")

    def test_single_command_bundle_installs_the_pair(self):
        output = self.root / "pickup-install.command"
        build = subprocess.run([sys.executable, str(REPO / "installer" / "bundle.py"),
                                "--trash", str(self.bundle / "trashpickup"),
                                "--treasure", str(self.bundle / "treasurepickup"),
                                "--installer", str(self.bundle / "installer"),
                                "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr)
        result = subprocess.run(["/bin/bash", str(output), "--yes"], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.pickup("registry", "--help")

    def test_closed_output_does_not_delete_tools_after_installation(self):
        process = subprocess.Popen(["/bin/bash", str(REPO / "installer" / "install.sh"), str(self.bundle), "--yes"],
                                   env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertIn(b"Installing", process.stdout.readline())
        process.stdout.close()
        process.stderr.read()
        process.stderr.close()
        process.wait(timeout=30)
        self.pickup("registry", "--help")

    def test_update_rollback_and_documented_removal_preserve_records(self):
        for custom in (False, True):
            with self.subTest(custom_locations=custom):
                self.skills = self.home / ("Custom skills" if custom else ".agents/skills")
                audit = self.home / ("Custom audit" if custom else "Desktop/pickup_audit")
                audit.mkdir(parents=True)
                record = audit / "retained-handoff.md"
                record.write_text("User-owned record")
                bag = audit / "retained-bag.md"
                bag.write_text("User-retained omitted content")
                self.skills.mkdir(parents=True, exist_ok=True)
                unrelated = self.skills / "unrelated"
                unrelated.mkdir()
                (unrelated / "SKILL.md").write_text("Keep this skill")
                options = ("--skills-dir", str(self.skills), "--audit-dir", str(audit))
                self.install(*options, "--yes")
                old_skill = self.skills / "trashpickup" / "SKILL.md"
                old_skill.write_text("User customization before update")
                self.install(*options, input="\ny\n")
                backup = next(self.skills.glob(".pickup-backup-*"))
                self.assertEqual((backup / "trashpickup/SKILL.md").read_text(), "User customization before update")
                parked = self.root / ("parked-custom" if custom else "parked-default")
                parked.mkdir()
                for name in ("trashpickup", "treasurepickup"):
                    shutil.move(str(self.skills / name), parked / name)
                    shutil.copytree(backup / name, self.skills / name)
                self.pickup("registry", "--help")
                self.assertEqual(old_skill.read_text(), "User customization before update")
                (self.home / "Downloads").mkdir(exist_ok=True)
                guide = (REPO / "references/lifecycle.md").read_text()
                removal = re.findall(r"```bash\n(.*?)```", guide, re.S)[-1]
                removal = removal.replace('pickup_skills="$HOME/.agents/skills"', "pickup_skills=" + shlex.quote(str(self.skills)))
                result = subprocess.run(["/bin/bash"], input=removal, env=self.env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.skills / "trashpickup").exists())
                self.assertFalse((self.skills / "treasurepickup").exists())
                self.assertTrue(backup.is_dir())
                self.assertEqual(record.read_text(), "User-owned record")
                self.assertEqual(bag.read_text(), "User-retained omitted content")
                self.assertEqual((unrelated / "SKILL.md").read_text(), "Keep this skill")


if __name__ == "__main__":
    unittest.main()
