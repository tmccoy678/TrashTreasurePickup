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


def render(files, manifest):
    """Render a deterministic command file, including its recorded provenance."""
    members = {**files, "source-manifest.json": json.dumps(manifest, indent=2).encode() + b"\n"}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(("/pickup", ".sh")) else 0o644
            archive.addfile(info, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0, filename="") as archive:
        archive.write(stream.getvalue())
    payload = compressed.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    script = '''#!/bin/bash
set -euo pipefail
umask 077
work=$(mktemp -d "${TMPDIR:-/tmp}/pickup-install.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 1' HUP INT TERM
base64 -D > "$work/payload.tar.gz" <<'PICKUP_PAYLOAD'
''' + base64.encodebytes(payload).decode() + "PICKUP_PAYLOAD\n"
    return script + f'''[[ $(shasum -a 256 "$work/payload.tar.gz" | cut -d' ' -f1) == {digest} ]] || {{ echo 'Installer payload checksum mismatch.' >&2; exit 1; }}
tar -xzf "$work/payload.tar.gz" -C "$work"
case "$0" in bash|/bin/bash) export PICKUP_STREAMED_INSTALL=1;; esac
/bin/bash "$work/installer/install.sh" "$work" "$@"
'''


def verify(output, files):
    """Read the payload as data; never execute or extract an installer to verify it."""
    script = output.read_text()
    encoded = script.split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
    payload = base64.b64decode("".join(encoded.splitlines()), validate=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        names = [item.name for item in members]
        if len(names) != len(set(names)) or any(not item.isfile() for item in members):
            raise ValueError("Bundle contains duplicate or non-regular members")
        bundled = {item.name: archive.extractfile(item).read() for item in members}
    manifest = json.loads(bundled.pop("source-manifest.json"))
    if set(bundled) != set(files):
        raise ValueError("Bundle file set differs from required sources")
    for name, data in files.items():
        if bundled[name] != data:
            raise ValueError(f"Distributed source differs: {name}")
    expected = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    if manifest["sha256"] != expected:
        raise ValueError("Bundle source manifest hashes differ")
    if script != render(files, manifest):
        raise ValueError("Installer script or payload encoding differs from the builder")
    return manifest


def revision(root):
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode or Path(result.stdout.strip()).resolve() != root.resolve():
        return {"commit": None, "modified": None}
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    modified = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip())
    return {"commit": commit, "modified": modified}


def check_sources(manifest, files, roots, pins):
    """Match every shipped byte to its declared Git commit, including installer inputs."""
    for name, root in roots.items():
        recorded = manifest["sources"][name]["commit"]
        pin = pins[name]
        if pin is not None and recorded != pin:
            raise ValueError(f"Source identity differs from declared commit: {name}")
        if recorded is None:
            if pin is not None or revision(root)["commit"] is not None:
                raise ValueError(f"Missing declared commit: {name}")
            continue  # Unversioned fixture builds are not release evidence.
        for path, data in files.items():
            if path.startswith(name + "/"):
                relative = path.split("/", 1)[1]
            elif name == "treasurepickup" and path.startswith("installer/"):
                relative = path
            else:
                continue
            source = subprocess.run(["git", "-C", str(root), "show", f"{recorded}:{relative}"], capture_output=True)
            if source.returncode or source.stdout != data:
                raise ValueError(f"Distributed file differs from declared commit: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trash", type=Path, required=True)
    parser.add_argument("--treasure", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--installer", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true", help="Verify an existing output without executing it")
    parser.add_argument("--trash-commit", help="Exact 40-character reviewed Trash commit")
    parser.add_argument("--treasure-commit", help="Exact 40-character reviewed Treasure commit")
    args = parser.parse_args()
    pins = {"trashpickup": args.trash_commit, "treasurepickup": args.treasure_commit}
    if any(pins.values()) and not all(pins.values()):
        parser.error("Supply both source commits together")
    for pin in pins.values():
        if pin is not None and (len(pin) != 40 or any(c not in "0123456789abcdef" for c in pin)):
            parser.error("Source commits must be full lowercase SHA-1 identities")
    roots = {"trashpickup": args.trash, "treasurepickup": args.treasure}
    files = {}
    for name, root in (("trashpickup", args.trash), ("treasurepickup", args.treasure)):
        selected = [root / path for path in (
            "SKILL.md", "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md",
            "agents/openai.yaml", "references/macos-setup.md",
            "references/pickup-registry.md", "references/first-use.md",
            "references/comparison.md", "references/author-note.md",
            "references/lifecycle.md", "references/support.md", "references/security-launch.md",
        )]
        selected += sorted((root / "references").glob("*.md")) + sorted((root / "agents").glob("*.yaml"))
        if name == "treasurepickup":
            selected += [root / "scripts" / path for path in ("pickup", "pickup_registry.py", "treasurepickup_receipt.py")]
        for path in selected:
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"Missing regular required file: {name}/{path.relative_to(root)}")
            files[f"{name}/{path.relative_to(root)}"] = path.read_bytes()
    for name in ("install.sh", "setup.py", "assets.tsv", "pixi.toml", "pixi.lock", "PIXI-LICENSE", "GITLEAKS-LICENSE", "THIRD_PARTY.md"):
        if not (args.installer / name).is_file() or (args.installer / name).is_symlink():
            raise ValueError(f"Missing regular required file: installer/{name}")
        files["installer/" + name] = (args.installer / name).read_bytes()
    manifest = {"sources": {"trashpickup": revision(args.trash), "treasurepickup": revision(args.treasure)},
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if args.verify:
        recorded = verify(args.output, files)
        check_sources(recorded, files, roots, pins)
        print(f"Verified {args.output}: {len(files)} distributed files match")
        return
    if all(pins.values()):
        for name, pin in pins.items():
            manifest["sources"][name]["commit"] = pin
        check_sources(manifest, files, roots, pins)
    script = render(files, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script)
    args.output.chmod(0o755)
    print(f"Built {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, tarfile.TarError) as error:
        raise SystemExit(f"Bundle validation failed: {error}")
