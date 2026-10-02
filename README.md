# Trash Pickup + Treasure Pickup

Two small, manual Codex skills for carrying useful context into a fresh task.

- **Trash Pickup** closes a completed phase into a readable Markdown handoff and a small JSON checkpoint.
- **Treasure Pickup** opens that pair, checks only the live facts that matter, and reconstructs the next working context.

The default pair follows the project's original simple design. It does not require a registry, receipt service, lease, package state machine, secret scanner, managed Python, or managed Git.

## Install

Download [pickup-install.command](https://github.com/tmccoy678/TrashTreasurePickup/raw/refs/heads/main/dist/pickup-install.command) and run:

```bash
bash "$HOME/Downloads/pickup-install.command"
```

The installer contains both skills and works without another network download. It installs to `~/.agents/skills` by default, preserves existing copies when replacement is declined, and keeps a backup when replacement is accepted. No GitHub sign-in is required.

To install from a cloned checkout instead:

```bash
bash installer/install.sh "$PWD"
```

Use `--skills-dir PATH` for another compatible skills directory.

## Use

At a natural stopping point, explicitly select `$trashpickup`. When file access is available, it writes:

```text
<workspace>/.pickup/current-context.md
<workspace>/.pickup/context-checkpoint.json
```

Open a fresh task in that workspace and explicitly select `$treasurepickup`. You may also paste or attach the two files. Treasure reconstructs the context and reports any material conflict it actually observes.

See the [first-use walkthrough](references/first-use.md) and [setup guide](references/macos-setup.md).

## Scope

Pickup carries context; it does not grant permissions or prove that every statement in a handoff is true. Agents should label unsupported details and inspect current state when it can change the next action.

Git history retains the former experimental multi-pickup registry and its acceptance records. The current tree stays focused on the small, single-handoff pair.

## Help and license

[Update or remove Pickup](references/lifecycle.md) · [Support](references/support.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

Pickup is available under the [MIT License](LICENSE).
