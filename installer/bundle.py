"""Build one portable installer from the reviewed pair; no private runtime state."""

import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


def revision(root):
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode or Path(result.stdout.strip()).resolve() != root.resolve():
        return {"commit": None, "modified": None}
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    modified = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip())
    return {"commit": commit, "modified": modified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trash", type=Path, required=True)
    parser.add_argument("--treasure", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--installer", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = {}
    for name, root in (("trashpickup", args.trash), ("treasurepickup", args.treasure)):
        selected = [root / path for path in ("SKILL.md", "README.md", "LICENSE", "SECURITY.md")]
        selected += sorted((root / "references").glob("*.md")) + sorted((root / "agents").glob("*.yaml"))
        if name == "treasurepickup":
            selected += [root / "scripts" / path for path in ("pickup", "pickup_registry.py", "treasurepickup_receipt.py")]
        for path in selected:
            if path.is_file():
                files[f"{name}/{path.relative_to(root)}"] = path.read_bytes()
        if f"{name}/SKILL.md" not in files:
            raise ValueError(f"Missing {name} skill")
    for name in ("install.sh", "setup.py", "assets.tsv", "pixi.toml", "pixi.lock", "PIXI-LICENSE", "GITLEAKS-LICENSE", "THIRD_PARTY.md"):
        files["installer/" + name] = (args.installer / name).read_bytes()
    manifest = {"sources": {"trashpickup": revision(args.trash), "treasurepickup": revision(args.treasure)},
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["source-manifest.json"] = json.dumps(manifest, indent=2).encode() + b"\n"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(("/pickup", ".sh")) else 0o644
            archive.addfile(info, io.BytesIO(data))
    payload = gzip.compress(stream.getvalue(), mtime=0)
    digest = hashlib.sha256(payload).hexdigest()
    script = '''#!/bin/bash
set -euo pipefail
umask 077
work=$(mktemp -d "${TMPDIR:-/tmp}/pickup-install.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 1' HUP INT TERM
base64 -D > "$work/payload.tar.gz" <<'PICKUP_PAYLOAD'
''' + base64.encodebytes(payload).decode() + "PICKUP_PAYLOAD\n"
    script += f'''[[ $(shasum -a 256 "$work/payload.tar.gz" | cut -d' ' -f1) == {digest} ]] || {{ echo 'Installer payload checksum mismatch.' >&2; exit 1; }}
tar -xzf "$work/payload.tar.gz" -C "$work"
case "$0" in bash|/bin/bash) export PICKUP_STREAMED_INSTALL=1;; esac
/bin/bash "$work/installer/install.sh" "$work" "$@"
'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script)
    args.output.chmod(0o755)
    print(f"Built {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
