# Update, recover, and remove Pickup

This guide uses the existing installer. Keep the pair together: Trash uses Treasure's shared tools. Installation and maintenance do not invoke either skill.

## Find your installation

The default skills folder is `~/.agents/skills`. A custom folder selected during setup replaces that default. The generated `treasurepickup/scripts/pickup-env.sh` records tool paths and the saved audit location; it applies only to the invoked command/shell and does not edit shell startup files.

Use the installed command to view its effective configuration:

```bash
pickup_skills="$HOME/.agents/skills" # Replace if you selected another folder.
"$pickup_skills/treasurepickup/scripts/pickup" config
```

The audit location follows explicit helper paths, then `PICKUP_HOME`, then the saved setup location, whose default is `~/Desktop/pickup_audit`. Installer `--skills-dir` and `--audit-dir` set installation destinations; interactive answers can replace the proposed values. On an update, supply your existing custom destinations again. The installer does not discover all previous custom installations.

Each installation provisions a separate runtime under `~/Library/Application Support/Pickup/runtime.*`. Keep old runtimes while any active or backed-up skill references them.

## Update the pair

1. Obtain the intended installer and its source identity/checksum from the maintainer. Versioned releases are not yet available; identify development snapshots by commit and bundle digest.
2. Confirm your current skills/audit locations. Run the downloaded command, select those same locations, and accept replacement when desired. `--yes` accepts defaults but **refuses replacement**; interactive confirmation is needed for an existing pair.
3. Setup keeps the previous skills in a unique `.pickup-backup-*` folder inside the selected skills directory. Record the exact path printed by setup. Existing audit data is retained.
4. Check the new command's `config` and `registry --help` outputs. Begin actual Pickup work only in its appropriate task and phase.

Setup initially downloads and checks tools before replacement. A failed download or checksum leaves the installed pair intact. A replacement failure attempts to restore the prior pair; inspect the actual result if the process was interrupted. Do not infer success from a partially printed message.

## Roll back without losing records

Stop using the installed pair while changing it. Select the exact backup from the update you intend to undo, and retain both its skill folders and referenced runtime.

Move the current `trashpickup` and `treasurepickup` folders to a new holding folder **outside every configured skill directory**. Copy both folders from the selected backup back to their original active locations, ensuring those destination names are empty first. Keep the backup until the restored `pickup config` and `pickup registry --help` work. Open a fresh host task so it discovers the restored instructions.

This restores skill/configuration files. It does not rewind or rewrite audit history, registry claims, or receipts created since the backup. Resolve any interrupted Pickup operation from its last confirmed state using the normal protocol; restoring binaries cannot complete a claim.

## Remove active skills and preserve your data

Move just the two active skill folders to a holding folder outside every configured skill directory, or remove those two folders only after retaining any desired customizations. For a reversible default-location removal:

```bash
(
set -e
pickup_skills="$HOME/.agents/skills" # Replace if your installation is elsewhere.
# Confirm both expected directories before moving either.
test -d "$pickup_skills/trashpickup" && test ! -L "$pickup_skills/trashpickup"
test -d "$pickup_skills/treasurepickup" && test ! -L "$pickup_skills/treasurepickup"
pickup_retired=$(mktemp -d "$HOME/Downloads/pickup-retired.XXXXXXXX")
mv "$pickup_skills/trashpickup" "$pickup_retired/"
mv "$pickup_skills/treasurepickup" "$pickup_retired/"
)
```

Run the move commands only if both checks succeed. Choose a different holding location if Downloads is a configured skill directory. Refresh the host or start a fresh task; an already-open task may retain loaded instructions.

Leave audit/registry records, receipts, trash bags you chose to save, `.pickup-backup-*` folders, unrelated skills, and runtimes in place. They are not removed by these steps. Runtime cleanup and deletion of retained records are separate destructive choices; no broad cleanup command is provided.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Permission or wrong-path error | Confirm the selected destinations and permitted access; choose an authorized folder if needed. |
| Download failed | Keep the installed pair, restore network access, and retry the same intended installer. |
| Checksum mismatch | Stop using that download; obtain a fresh artifact and compare the maintainer's digest. Do not bypass verification. |
| Existing skills preserved | Interactive replacement was declined or `--yes` refused it. Run the guided installer when you intend to replace them. |
| Partial installation or closed terminal | Inspect active folders, backup, and the command's config/help. Preserve the last confirmed state; do not assume tools were removed or setup completed. |
| Claim/receipt interrupted | Report the last confirmed operation and sanitized reason; follow the [protocol](pickup-registry.md). Do not hand-edit state or use conversation fallback to declare success. |

For ordinary support, share the release/commit, operating system and architecture, expected behavior, and sanitized error. Keep secrets, raw handoffs, and private audit contents out of reports. See [support](support.md) and [security policy](../SECURITY.md).

