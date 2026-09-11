"""Check paired documentation and syntax without invoking either Pickup skill."""

import argparse
import ast
from pathlib import Path
import re
import subprocess


def check(trash, treasure):
    references = []
    for root in (trash, treasure):
        references.append({p.name: p.read_bytes() for p in (root / "references").glob("*.md")})
        documents = [root / name for name in ("README.md", "SECURITY.md", "LICENSE", "CONTRIBUTING.md", "AGENTS.md", "SKILL.md")]
        documents += list((root / "references").glob("*.md")) + list((root / "docs").rglob("*.md"))
        for path in documents:
            text = path.read_text()
            for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text):
                if target.startswith(("https://", "http://", "#")):
                    continue
                destination = target.split("#", 1)[0]
                if not (path.parent / destination).is_file():
                    raise ValueError(f"Missing link from {path.relative_to(root)}: {target}")
        metadata = (root / "agents/openai.yaml").read_text()
        if "allow_implicit_invocation: false" not in metadata:
            raise ValueError(f"Explicit-only policy missing: {root.name}")
    if references[0] != references[1]:
        raise ValueError("Paired references differ")
    if (trash / "LICENSE").read_bytes() != (treasure / "LICENSE").read_bytes():
        raise ValueError("Paired project licenses differ")
    for folder in ("installer", "scripts", "tests"):
        for path in (treasure / folder).glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for relative in ("installer/install.sh", "scripts/pickup", "dist/pickup-install.command"):
        subprocess.run(["/bin/bash", "-n", str(treasure / relative)], check=True)
    print("Paired references, local links, explicit invocation policy, licenses, and syntax: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trash", type=Path, required=True)
    parser.add_argument("--treasure", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    check(args.trash.resolve(), args.treasure.resolve())


if __name__ == "__main__":
    main()

