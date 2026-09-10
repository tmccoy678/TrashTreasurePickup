# macOS setup for the Pickup pair

Use this setup for the normal file and registry workflow when the invocation has sufficient authorized access. Existing grants activate that workflow automatically; no additional storage or registry opt-in is needed. With limited or no access, follow the supplied-content instructions in the invoked `SKILL.md` without requiring installation, commands, or inaccessible helper reads. The handoff and receipt may be delivered in the conversation; saving is optional only in that fallback.

Manually copy the complete `trashpickup/` and `treasurepickup/` directories into `~/.agents/skills/`. Keep `SKILL.md`, `agents/`, `references/`, and Treasure Pickup's `scripts/` intact. Both skills remain manually invoked.

Trash Pickup uses Treasure Pickup's shared registry helper for inspection and package publication. That helper also contains the handoff identity and integrity verifier. Each skill includes the same [Pickup Registry protocol](pickup-registry.md). The older receipt helper remains available for existing receipt commands; new runs use the registry.

## Prerequisites for the normal file workflow

- macOS with Python 3.9 or newer available as `python3`. The helpers use the standard library; there are no pip dependencies.
- Gitleaks through `PATH`, supporting `detect --no-git --source` and the helper's redaction/output flags. An explicit `--gitleaks-path` may select its executable. A missing scanner blocks registry writes.
- Git when reviewing repository state. Trash Pickup also uses `jq` to check checkpoint JSON.

## Select the Pickup location

Use an explicitly selected location first; otherwise use `PICKUP_HOME`, defaulting to `~/Desktop/pickup_audit`. This location stores the pair's artifacts. Preserve the current project's source paths in the handoff. Expand a leading `~`, use resolved absolute paths, and quote them.

The following shell setup uses the sibling installation above. If Treasure Pickup lives elsewhere, set `treasurepickup_skill` to that exact installed directory.

```bash
export PICKUP_HOME="${PICKUP_HOME:-$HOME/Desktop/pickup_audit}"
pickup_workspace="$PICKUP_HOME"
treasurepickup_skill="$HOME/.agents/skills/treasurepickup"
pickup_registry="$treasurepickup_skill/scripts/pickup_registry.py"
pickup_registry_root="$pickup_workspace/treasurepickup/pickups"
```

When existing access covers storage at this location, automatically create these directories as part of the normal invocation, then perform the required artifact saves and registry operations:

```bash
mkdir -p "$pickup_workspace/trashpickup/context-archive" "$pickup_workspace/treasurepickup"
```

A directory created by the user works the same way once access is permitted. Respect platform controls and explicit restrictions. Denied access permits conversation delivery without requesting broader access. An actual failed check or interrupted normal transaction must still be reported as such.

The protocol passes `--registry-root` explicitly so every operation addresses the same registry. `claim --workspace` must match the registry's workspace binding: two parent directories above the registry. The default compatibility output is `treasurepickup/context-resume.json` beneath that location. Terminal completion automatically creates its sibling `receipts/` folder and saves one Markdown receipt there while retaining internal JSON records. Explicit `--compatibility-output` retains the helper's binding checks and determines that receipt folder. `--skill-file` must identify the deployed `SKILL.md` beside the running helper's `scripts/` directory.

## Confirm the supporting files

Confirm the installed Treasure Pickup `SKILL.md`, `scripts/pickup_registry.py`, this package's `references/pickup-registry.md`, and the commands required for the invocation.

The checkpoint shape is embedded in Trash Pickup's `SKILL.md`; gate evidence is defined in the [registry protocol](pickup-registry.md). Package, receipt, and quarantine validation remain inside Treasure Pickup's scripts. No separately downloaded schema or template is needed. Replace placeholders with verified facts.

Setup supplies locations and supporting files. Each manually invoked skill still checks its inputs and reports its results. Completion never authorizes the next phase.

Use permitted temporary storage only for the relevant artifact or receipt material; the helpers use the system temporary directory (or a permitted `TMPDIR`). Clean up owned temporary files on success or failure. If that processing is unavailable because of access restrictions, report the unavailable checks and follow the skill's fallback. A missing or failing scanner in an otherwise authorized normal run remains a failure, not a passed or skipped normal check.
