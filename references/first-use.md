# First use

Start with a small disposable project.

1. Finish a natural phase of work.
2. Explicitly select `$trashpickup` and name the completed and next phases.
3. Read the generated handoff and checkpoint. Correct anything unsupported.
4. Open a fresh task in the same workspace.
5. Explicitly select `$treasurepickup`.
6. Review the reconstructed context, then separately decide whether to begin the next work.

Example closing request:

> $trashpickup — The documentation draft and its checks are complete. Preserve the decision to use plain language. The next phase is editorial review.

A minimal checkpoint looks like:

```json
{
  "context_status": "READY",
  "current_phase": "Documentation draft complete",
  "next_phase": "Editorial review",
  "workspace": "/path/to/project",
  "canonical_handoff": ".pickup/current-context.md",
  "warnings": []
}
```

Example opening request:

> $treasurepickup — Open the handoff in this workspace and reconstruct the next context.

If files cannot be shared, paste the handoff and checkpoint into the fresh task. Treasure may continue from a clear handoff when the checkpoint is unavailable, but it must state that limitation.
