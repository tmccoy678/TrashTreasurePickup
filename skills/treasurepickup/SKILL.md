---
name: treasurepickup
description: Open a Trash Pickup handoff and reconstruct the next working context.
---

# Treasure Pickup

Use this skill only when the user explicitly invokes `$treasurepickup`.

Treasure Pickup opens one handoff created by Trash Pickup. Its job is to restore the useful context, notice meaningful changes, and leave the next task easy to understand.

## Open the handoff

1. Use the handoff and checkpoint supplied by the user. When none is supplied and file access is available, look in the current workspace for:

```text
.pickup/current-context.md
.pickup/context-checkpoint.json
```

If several handoffs could apply, ask the user which one to use. Do not guess from whichever filename looks newest.

2. Read the selected handoff and checkpoint. The checkpoint should say `READY` and should identify the same current and next phases as the handoff. If the checkpoint is missing but the user supplied a clear handoff, continue from the handoff and state that checkpoint verification was unavailable.

3. Check only live facts that could materially change the next step. Examples include the current Git branch, uncommitted work, a required file, or a dependency that the handoff says must exist. Ordinary changes do not require a formal drift classification. Explain a meaningful conflict plainly and stop for the user only when it prevents safe continuation.

4. Reconstruct a compact working context containing:

- objective;
- completed phase;
- verified current state;
- decisions to preserve;
- relevant files and resources;
- unresolved issues;
- next phase and next actions; and
- required user actions.

Distinguish statements carried from the handoff from facts checked during this invocation. Mark unsupported details as `UNKNOWN`; do not invent paths, hashes, dates, or completion claims.

5. Report one of:

```text
TREASUREPICKUP: READY
```

when the handoff is clear enough to continue, or:

```text
TREASUREPICKUP: NEEDS REVIEW
Reason: <smallest material conflict or missing choice>
```

No registry claim, receipt, lease, package state, freshness gate, or generated telemetry is required.

Stop after reconstructing the context unless the user also asked to begin the next work. A handoff supplies context; it does not expand permissions.
