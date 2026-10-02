# Update, roll back, or remove Pickup

## Update

Download the current installer and run it with the same skills directory. When an existing pair is found, the installer asks before replacement and keeps the previous pair in a `.pickup-backup-*` folder.

## Roll back

Close active agent tasks that use Pickup. Move the active `trashpickup` and `treasurepickup` folders aside, then move the matching pair from the chosen backup into their place. Start a fresh host task and confirm both skills appear.

## Remove

Move the two active skill folders outside the skills directory:

```bash
pickup_skills="$HOME/.agents/skills"
pickup_retired="$HOME/Downloads/pickup-retired"
mkdir -p "$pickup_retired"
mv "$pickup_skills/trashpickup" "$pickup_retired/"
mv "$pickup_skills/treasurepickup" "$pickup_retired/"
```

This leaves project handoffs under `.pickup/`, backups, and unrelated skills untouched. Deleting those retained files is a separate user decision.
