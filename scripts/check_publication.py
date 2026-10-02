"""Run the inexpensive checks required for the public Pickup repository."""

import ast
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
from sources import SKILLS, collect


def check_links(path):
    text = path.read_text()
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
    for path in ROOT.rglob("*.md"):
        if ".git" not in path.parts:
            check_links(path)
    for name in SKILLS:
        metadata = files[f"{name}/agents/openai.yaml"].decode()
        if "allow_implicit_invocation: false" not in metadata:
            raise ValueError(f"Explicit-only policy missing: {name}")
        for shared in ("LICENSE", "SECURITY.md"):
            packaged = ROOT / "skills" / name / shared
            if packaged.read_bytes() != (ROOT / shared).read_bytes():
                raise ValueError(f"Stale package copy: {packaged.relative_to(ROOT)}")
    for folder in ("installer", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for relative in ("installer/install.sh", "dist/pickup-install.command"):
        subprocess.run(["/bin/bash", "-n", str(ROOT / relative)], check=True)
    forbidden = ("/Users/" + "taylor", "~/AI-" + "Workspace", "PRIVATE " + "VAULT")
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.suffix in {".md", ".py", ".sh", ".yaml", ".yml"}:
            text = path.read_text(errors="replace")
            if any(value in text for value in forbidden):
                raise ValueError(f"Private machine path in {path.relative_to(ROOT)}")
    print("Links, metadata, source files, shell syntax, and portability: PASS")


if __name__ == "__main__":
    try:
        check()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
