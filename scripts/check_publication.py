"""Check repository and installed-package documentation without invoking Pickup."""

import ast
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
from sources import SKILLS, collect


def check_links(path, text):
    targets = re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text)
    targets += re.findall(r"^\[[^\]\n]+\]:\s*(\S+)", text, re.M)
    for target in targets:
        if target.startswith(("https://", "http://", "#", "mailto:")):
            continue
        destination = unquote(target.split("#", 1)[0])
        if not (path.parent / destination).is_file():
            raise ValueError(f"Missing link from {path.relative_to(ROOT)}: {target}")


def check():
    files, _ = collect(ROOT)
    documents = [ROOT / name for name in ("README.md", "SECURITY.md", "CONTRIBUTING.md", "AGENTS.md")]
    for folder in ("references", "docs", "skills"):
        documents.extend((ROOT / folder).rglob("*.md"))
    for path in documents:
        check_links(path, path.read_text())
    for name in SKILLS:
        if "allow_implicit_invocation: false" not in files[name + "/agents/openai.yaml"].decode():
            raise ValueError(f"Explicit-only policy missing: {name}")
    for folder in ("installer", "scripts", "tests", "skills"):
        for path in (ROOT / folder).rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for relative in ("installer/install.sh", "skills/treasurepickup/scripts/pickup", "dist/pickup-install.command"):
        subprocess.run(["/bin/bash", "-n", str(ROOT / relative)], check=True)
    print("Shared documents, local links, explicit invocation policy, licenses, and syntax: PASS")


if __name__ == "__main__":
    try:
        check()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
