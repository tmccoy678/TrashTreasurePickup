#!/bin/bash
set -euo pipefail
umask 077

bundle=$(cd "$1" && pwd)
shift
if [[ ! -d "$bundle/trashpickup" && -d "$bundle/skills/trashpickup" ]]; then
    bundle="$bundle/skills"
fi

skills_dir="$HOME/.agents/skills"
assume_yes=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes)
            assume_yes=1
            shift
            ;;
        --skills-dir)
            [[ $# -ge 2 ]] || { echo 'Missing value for --skills-dir.' >&2; exit 2; }
            skills_dir=$2
            shift 2
            ;;
        --help|-h)
            echo 'Usage: pickup-install.command [--yes] [--skills-dir PATH]'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

skills_dir=${skills_dir/#\~/$HOME}
if [[ $skills_dir != /* ]]; then
    skills_dir="$PWD/$skills_dir"
fi

for name in trashpickup treasurepickup; do
    for relative in SKILL.md README.md LICENSE SECURITY.md agents/openai.yaml; do
        path="$bundle/$name/$relative"
        [[ -f "$path" && ! -L "$path" ]] || {
            echo "Installer is missing a regular file: $name/$relative" >&2
            exit 1
        }
    done
done

echo "Skills directory: $skills_dir"
if [[ $assume_yes -eq 0 ]]; then
    read -r -p 'Install Trash Pickup and Treasure Pickup here? [Y/n] ' answer
    case "$answer" in ''|y|Y|yes|YES) ;; *) echo 'Installation cancelled.'; exit 1;; esac
fi

existing=()
for name in trashpickup treasurepickup; do
    [[ -e "$skills_dir/$name" || -L "$skills_dir/$name" ]] && existing+=("$name")
done
if [[ ${#existing[@]} -gt 0 ]]; then
    if [[ $assume_yes -eq 1 ]]; then
        echo 'Existing Pickup skills were preserved. Run without --yes to review replacement.' >&2
        exit 1
    fi
    read -r -p 'Replace the existing Pickup pair and keep a backup? [y/N] ' answer
    case "$answer" in y|Y|yes|YES) ;; *) echo 'Existing Pickup skills were preserved.'; exit 1;; esac
fi

mkdir -p "$skills_dir"
stage=$(mktemp -d "$skills_dir/.pickup-install.XXXXXXXX")
backup=''
installed=()
cleanup() {
    status=$?
    if [[ $status -ne 0 ]]; then
        for path in "${installed[@]}"; do
            [[ -e "$path" || -L "$path" ]] && rm -rf "$path"
        done
        if [[ -n "$backup" && -d "$backup" ]]; then
            for name in trashpickup treasurepickup; do
                [[ -e "$backup/$name" || -L "$backup/$name" ]] && mv "$backup/$name" "$skills_dir/$name"
            done
        fi
    fi
    [[ -d "$stage" ]] && rm -rf "$stage"
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

for name in trashpickup treasurepickup; do
    mkdir -p "$stage/$name/agents"
    cp "$bundle/$name/SKILL.md" "$stage/$name/SKILL.md"
    cp "$bundle/$name/README.md" "$stage/$name/README.md"
    cp "$bundle/$name/LICENSE" "$stage/$name/LICENSE"
    cp "$bundle/$name/SECURITY.md" "$stage/$name/SECURITY.md"
    cp "$bundle/$name/agents/openai.yaml" "$stage/$name/agents/openai.yaml"
done

if [[ ${#existing[@]} -gt 0 ]]; then
    backup=$(mktemp -d "$skills_dir/.pickup-backup.XXXXXXXX")
    for name in "${existing[@]}"; do
        mv "$skills_dir/$name" "$backup/$name"
    done
fi

for name in trashpickup treasurepickup; do
    [[ ! -e "$skills_dir/$name" && ! -L "$skills_dir/$name" ]] || {
        echo "Installation destination changed: $skills_dir/$name" >&2
        exit 1
    }
    mv "$stage/$name" "$skills_dir/$name"
    installed+=("$skills_dir/$name")
done

trap - EXIT HUP INT TERM
rmdir "$stage"
echo "Pickup installed: $skills_dir"
[[ -n "$backup" ]] && echo "Previous skills retained: $backup"
echo 'Invoke $trashpickup to close a completed phase and $treasurepickup in the fresh task.'
