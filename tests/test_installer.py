"""Exercise the instruction-only Pickup installer."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
NAMES = ("trashpickup", "treasurepickup")
FILES = ("SKILL.md", "README.md", "LICENSE", "SECURITY.md", "agents/openai.yaml")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pickup install ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.skills = self.home / ".agents" / "skills"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        }

    def install(self, *args, input_text="", expected=0):
        result = subprocess.run(
            ["/bin/bash", str(REPO / "installer/install.sh"), str(REPO), *args],
            input=input_text,
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def assert_installed_pair(self, root=None):
        root = root or self.skills
        for name in NAMES:
            for relative in FILES:
                installed = root / name / relative
                source = REPO / "skills" / name / relative
                self.assertTrue(installed.is_file(), installed)
                self.assertEqual(installed.read_bytes(), source.read_bytes())

    def test_default_install_is_self_contained_and_has_no_runtime(self):
        result = self.install("--yes")
        self.assert_installed_pair()
        self.assertIn("$trashpickup", result.stdout)
        self.assertIn("$treasurepickup", result.stdout)
        self.assertFalse((self.home / "Library/Application Support/Pickup").exists())
        self.assertFalse((self.home / ".pickup").exists())
        for name in NAMES:
            self.assertFalse((self.skills / name / "scripts").exists())
            self.assertFalse((self.skills / name / "references").exists())

    def test_yes_never_replaces_an_existing_skill(self):
        self.install("--yes")
        custom = self.skills / "trashpickup/SKILL.md"
        custom.write_text("personal customization")
        result = self.install("--yes", expected=1)
        self.assertIn("preserved", result.stderr)
        self.assertEqual(custom.read_text(), "personal customization")

    def test_accepted_replacement_keeps_backup_and_unrelated_skill(self):
        self.install("--yes")
        custom = self.skills / "trashpickup/SKILL.md"
        custom.write_text("personal customization")
        unrelated = self.skills / "other-skill/SKILL.md"
        unrelated.parent.mkdir()
        unrelated.write_text("leave me alone")

        result = self.install(input_text="\ny\n")

        self.assert_installed_pair()
        backup = next(self.skills.glob(".pickup-backup.*/trashpickup/SKILL.md"))
        self.assertEqual(backup.read_text(), "personal customization")
        self.assertEqual(unrelated.read_text(), "leave me alone")
        self.assertIn("Previous skills retained", result.stdout)

    def test_custom_skills_directory(self):
        custom = self.root / "custom skills"
        self.install("--yes", "--skills-dir", str(custom))
        self.assert_installed_pair(custom)
        self.assertFalse(self.skills.exists())

    def test_missing_required_source_file_stops_before_installation(self):
        bundle = self.root / "broken"
        shutil.copytree(REPO / "skills", bundle / "skills")
        (bundle / "skills/trashpickup/SKILL.md").unlink()
        result = subprocess.run(
            ["/bin/bash", str(REPO / "installer/install.sh"), str(bundle), "--yes"],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing a regular file", result.stderr)
        self.assertFalse(self.skills.exists())


if __name__ == "__main__":
    unittest.main()
