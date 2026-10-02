"""Build or verify the self-contained Pickup installer."""

import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

from sources import collect


FORMAT = "pickup-single-repository-v1"


def git(root, *args, text=False):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=text
    )


def current_commit(root):
    result = git(root, "rev-parse", "--show-toplevel", text=True)
    if result.returncode or Path(result.stdout.strip()).resolve() != root.resolve():
        return None
    return git(root, "rev-parse", "HEAD", text=True).stdout.strip()


def source_manifest(root, files, mapping, commit=None):
    return {
        "format": FORMAT,
        "source_commit": commit if commit is not None else current_commit(root),
        "source_paths": mapping,
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }


def render(files, manifest):
    members = {
        **files,
        "source-manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n",
    }
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as archive:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(".sh") else 0o644
            archive.addfile(info, io.BytesIO(data))
    zipped = io.BytesIO()
    with gzip.GzipFile(fileobj=zipped, mode="wb", mtime=0, filename="") as archive:
        archive.write(tar_stream.getvalue())
    payload = zipped.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    encoded = base64.encodebytes(payload).decode()
    return f'''#!/bin/bash
set -euo pipefail
umask 077
work=$(mktemp -d "${{TMPDIR:-/tmp}}/pickup-install.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 1' HUP INT TERM
if base64 --decode </dev/null >/dev/null 2>&1; then
    decoder=(base64 --decode)
else
    decoder=(base64 -D)
fi
"${{decoder[@]}}" > "$work/payload.tar.gz" <<'PICKUP_PAYLOAD'
{encoded}PICKUP_PAYLOAD
if command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 "$work/payload.tar.gz" | cut -d' ' -f1)
else
    actual=$(sha256sum "$work/payload.tar.gz" | cut -d' ' -f1)
fi
[[ $actual == {digest} ]] || {{ echo 'Installer payload checksum mismatch.' >&2; exit 1; }}
tar -xzf "$work/payload.tar.gz" -C "$work"
/bin/bash "$work/installer/install.sh" "$work" "$@"
'''


def read_bundle(output):
    script = output.read_text()
    encoded = script.split("<<'PICKUP_PAYLOAD'\n", 1)[1].split("\nPICKUP_PAYLOAD\n", 1)[0]
    payload = base64.b64decode("".join(encoded.splitlines()), validate=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        if len({item.name for item in members}) != len(members):
            raise ValueError("Bundle contains duplicate members")
        if any(not item.isfile() for item in members):
            raise ValueError("Bundle contains a non-regular member")
        return script, {
            item.name: archive.extractfile(item).read() for item in members
        }


def validate_commit(root, commit, files, mapping):
    if commit is None:
        if current_commit(root) is not None:
            raise ValueError("Versioned sources require a source commit")
        return
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Source commit must be a full lowercase Git identity")
    resolved = git(root, "rev-parse", "--verify", f"{commit}^{{commit}}", text=True)
    if resolved.returncode or resolved.stdout.strip() != commit:
        raise ValueError("Source commit does not resolve exactly")
    for bundled_name, source_path in mapping.items():
        recorded = git(root, "show", f"{commit}:{source_path}")
        if recorded.returncode or recorded.stdout != files[bundled_name]:
            raise ValueError(f"Distributed file differs from declared commit: {bundled_name}")


def verify(output, root, files, mapping, expected_commit=None):
    script, bundled = read_bundle(output)
    manifest = json.loads(bundled.pop("source-manifest.json"))
    if manifest.get("format") != FORMAT:
        raise ValueError("Unexpected bundle format")
    if manifest.get("source_paths") != mapping or set(bundled) != set(files):
        raise ValueError("Bundle file set or source mapping differs")
    if any(bundled[name] != data for name, data in files.items()):
        raise ValueError("Distributed bytes differ from the source tree")
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    if manifest.get("sha256") != hashes:
        raise ValueError("Bundle hashes differ")
    commit = manifest.get("source_commit")
    if expected_commit is not None and commit != expected_commit:
        raise ValueError("Bundle source differs from requested commit")
    validate_commit(root, commit, files, mapping)
    if script != render(files, manifest):
        raise ValueError("Generated installer script wrapper differs")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="repository checkout")
    parser.add_argument("--source-commit", help="full commit containing every bundled input")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = (args.source_root or Path(__file__).resolve().parents[1]).resolve()
    files, mapping = collect(root)
    if args.verify:
        verify(args.output, root, files, mapping, args.source_commit)
        print(f"Verified {args.output}: {len(files)} distributed files match")
        return
    manifest = source_manifest(root, files, mapping, args.source_commit)
    validate_commit(root, manifest["source_commit"], files, mapping)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(files, manifest))
    args.output.chmod(0o755)
    print(f"Built {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, tarfile.TarError) as error:
        raise SystemExit(f"Bundle validation failed: {error}")
