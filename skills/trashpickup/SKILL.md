---
name: trashpickup
description: Close a completed work phase into a concise handoff for a fresh context.
---

# Trash Pickup

Use this skill only when the user explicitly invokes `$trashpickup`.

Trash Pickup preserves the useful state of a completed phase so a fresh task can continue without depending on the old conversation. “Trash” means stale context, never user data.

## Close the phase

1. Decide whether the current phase has reached a safe stopping point. Check only the evidence needed to answer that question. Do not interrupt running work or declare an unfinished operation complete.

2. If important work is still active, report:

```text
TRASHPICKUP: WAIT
Reason: <the unfinished work>
```

Do not create a ready checkpoint.

3. Use the current project or the workspace named by the user. Prefer project files, Git state, completed results, and direct observations over recollection from the conversation. Mark anything unsupported as `UNKNOWN`.

4. Write a concise Markdown handoff with the sections that are useful for this project. Include:

- the objective and phase just completed;
- the verified current state;
- decisions worth preserving;
- changed or important files;
- unresolved issues and warnings;
- the next phase and concrete next actions; and
- any action that still requires the user.

Do not pad the handoff with routine conversation, repeated policy text, or facts the next task does not need.

5. When file access is available, save the pair under the current workspace:

```text
.pickup/current-context.md
.pickup/context-checkpoint.json
```

Before replacing an existing handoff, preserve it under `.pickup/archive/` with a unique name. Do not overwrite the only copy. If file access is unavailable, return both documents in the conversation instead.

Use a small checkpoint:

```json
{
  "context_status": "READY",
  "current_phase": "...",
  "next_phase": "...",
  "workspace": "...",
  "canonical_handoff": ".pickup/current-context.md",
  "warnings": []
}
```

Add a field only when it helps the next task. A timestamp, hash, registry entry, package, receipt, or secret scanner is not required.

6. Keep credentials, tokens, private keys, recovery material, protected-storage contents, and unrelated personal information out of both files. Preserve existing permissions and leave unrelated files untouched.

7. Check that the handoff and checkpoint agree about the completed and next phases. When they do, report:

```text
TRASHPICKUP: READY FOR FRESH CONTEXT
Handoff: <saved path or conversation document>
Checkpoint: <saved path or conversation document>
Next phase: <phase>
```

Stop after delivering the pair. The handoff carries context; it does not authorize unrelated work.
