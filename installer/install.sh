#!/bin/bash
# Bootstrap with macOS tools; Python and Git come from the pinned environment.
set -euo pipefail
umask 077
bundle=$(cd "$1" && pwd)
shift
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
[[ $(uname -s) == Darwin ]] || { echo 'Pickup requires macOS.' >&2; exit 1; }
[[ $(sw_vers -productVersion | cut -d. -f1) -ge 12 ]] || { echo 'Pickup requires macOS 12 or newer.' >&2; exit 1; }
machine=$(uname -m)
case "$machine" in arm64|x86_64) ;; *) echo 'Unsupported Mac architecture.' >&2; exit 1;; esac
mkdir -p "$HOME/Library/Application Support/Pickup"
runtime=$(mktemp -d "$HOME/Library/Application Support/Pickup/runtime.XXXXXXXX")
finished=false
cleanup() { if [[ $finished == false ]]; then rm -rf "$runtime"; fi; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
mkdir "$runtime/tools"
while IFS=$'\t' read -r arch name url expected; do
    [[ $arch == "$machine" ]] || continue
    case "$name" in pixi|gitleaks) ;; *) echo 'Invalid runtime asset.' >&2; exit 1;; esac
    curl -qfsSL --retry 2 --connect-timeout 20 --proto '=https,file' --proto-redir '=https' "$url" -o "$runtime/$name.download"
    actual=$(shasum -a 256 "$runtime/$name.download" | cut -d' ' -f1)
    [[ $actual == "$expected" ]] || { echo "Download checksum mismatch: $name" >&2; exit 1; }
    if [[ $name == pixi ]]; then
        mv "$runtime/$name.download" "$runtime/tools/pixi"
        chmod 700 "$runtime/tools/pixi"
    else
        tar -xzf "$runtime/$name.download" -C "$runtime/tools"
        rm "$runtime/$name.download"
    fi
done < "$bundle/installer/assets.tsv"
[[ -x "$runtime/tools/pixi" && -x "$runtime/tools/gitleaks" ]] || { echo 'Required runtime assets are missing.' >&2; exit 1; }
cp "$bundle/installer/pixi.toml" "$bundle/installer/pixi.lock" "$runtime/"
cp "$bundle/installer/PIXI-LICENSE" "$bundle/installer/GITLEAKS-LICENSE" "$bundle/installer/THIRD_PARTY.md" "$runtime/"
echo 'Installing the tools used by Pickup…'
export PIXI_CACHE_DIR="$runtime/cache"
"$runtime/tools/pixi" install --no-config --locked --manifest-path "$runtime/pixi.toml"
"$runtime/.pixi/envs/default/bin/python3" "$bundle/installer/setup.py" "$bundle" "$runtime" "$@"
finished=true
