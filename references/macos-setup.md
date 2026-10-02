# Setup

## Install the pair

Download [pickup-install.command](https://github.com/tmccoy678/TrashTreasurePickup/raw/refs/heads/main/dist/pickup-install.command), then run:

```bash
bash "$HOME/Downloads/pickup-install.command"
```

The command contains both skills. It makes no additional network download and does not install a separate runtime.

The default destination is `~/.agents/skills`. Use another compatible location with:

```bash
bash "$HOME/Downloads/pickup-install.command" --skills-dir "$HOME/path/to/skills"
```

The installer asks before replacing an existing pair and retains accepted replacements in a `.pickup-backup-*` folder beside the active skills. It does not create a handoff or invoke either skill.

After installation, refresh the agent host or start a fresh task so it discovers the new skill files.

## Handoff location

Pickup uses the current project by default:

```text
<workspace>/.pickup/current-context.md
<workspace>/.pickup/context-checkpoint.json
<workspace>/.pickup/archive/
```

No computer-specific username or fixed home-directory path is required.
