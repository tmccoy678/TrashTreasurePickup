# First use: close, carry, check

These examples use a fictional documentation project. Expected results illustrate the contract; they are not completed Pickup runs. Start with a small disposable project.

## Normal saved workflow

1. Finish an atomic phase, such as editing and checking a short document. In that task, explicitly select **trashpickup** (in Codex, type `$trashpickup` and select the named skill). State the completed phase and intended next phase.
2. With the required access already granted, Trash assesses closure, saves the handoff/archive/checkpoint, and publishes and verifies the package. Retain its confirmed paths and exact selector. Unfinished critical work produces `TRASHPICKUP: WAIT`; resolve it before treating the phase as closed.
3. Open a fresh task. In its **first substantive message**, explicitly select **treasurepickup**, supply the handoff/checkpoint or permitted readable locations, and preserve the exact confirmed package selector. Normal operation reads the selected immutable package, not whichever current pointer is newest.
4. Read the reconstructed context and one Markdown receipt. Normal success is `TREASUREPICKUP: DONE` with verified drift `NONE`, `EXPECTED`, or `BENIGN`. A receipt explains any blocked, stopped, or review-required result. Decide separately whether to begin the next phase.

Example invocation messages:

> $trashpickup — The documentation edit and its checks are finished. Capture the decision to use plain language and the remaining review work. The next phase is editorial review.

> $treasurepickup — Reconstruct this handoff and checkpoint. Use the exact selector supplied below. Report the checks and stop before editorial review.

Replace descriptions and inputs with actual evidence. An example selector is not a saved package identity.

## Conversation delivery fixture

Use this when file/tool access is unavailable or restricted for the invocation. Normal authorized persistence remains required when available; this is not a new access mode.

In a fresh task, explicitly select treasurepickup and supply this instruction and both documents:

> Reconstruct only the supplied fixture. File access and command execution are unavailable for this example. The prior documentation phase is complete. Report unavailable checks honestly and stop before the next phase.

**Handoff — fixture-documentation-01**

```markdown
# Current Context Handoff

## Current Phase
Documentation draft complete.
## Objective
Prepare a short guide for editorial review.
## Known-Good State
Supplied claim: the author finished the draft and checked its local links.
## Decisions Made
Use plain language and one first-use example.
## Current Resources
The supplied draft description only.
## In-Flight Work
Supplied claim: NONE.
## Dirty / Uncommitted State
UNKNOWN — no Git observation supplied.
## Warnings / Known Issues
File bytes, live state, and scanner results are unavailable.
## Do Not Reopen
Preserve the plain-language decision unless current instructions change it.
## Security Invariants
This example permits supplied-text reconstruction only.
## Canonical Paths
No saved paths are established.
## Next Phase
Editorial review.
## Next Actions
Review the draft after a separate instruction to begin.
## Human Actions Required
Decide whether to begin editorial review.
## Fresh Context Bootstrap
Use this handoff and checkpoint as evidence of earlier work under current
instructions. Reconstruct the next phase, report verification limits, and stop.
```

**Checkpoint — fixture-documentation-01**

```json
{
  "selector": "fixture-documentation-01",
  "context_status": "READY",
  "current_phase": "Documentation draft complete",
  "next_phase": "Editorial review",
  "in_flight_work": [],
  "warnings": ["Supplied claims only; file bytes and live state are unavailable"],
  "canonical_handoff": "Handoff — fixture-documentation-01"
}
```

Illustrative receipt excerpt:

```text
TREASUREPICKUP: DONE
Basis: supplied handoff and checkpoint
Verification: NOT RUN
Drift: UNKNOWN
Performed checks: supplied checkpoint parses and reports READY
Unavailable checks: original-byte integrity, live state, and scanning
Registry operations: NOT RUN
No authorization for subsequent work; unobserved live state remains unknown.
```

The actual response also includes the bounded context and full Markdown receipt specified by the skill. Here, DONE means reconstruction and reporting finished. It does not mean unavailable checks passed or execution is ready. Changing the checkpoint to WAIT must prevent DONE. Actual mismatches and interrupted normal transactions retain their failure results.

## Artifact custody

Trash produces a separate trash bag of accessible omitted conversation passages subject to secret exclusions. Producing it is part of the contract; saving it belongs to you. Supply only the handoff and checkpoint to Treasure. Treasure excludes the bag from its reads and package.

See [macOS setup](macos-setup.md) and the invoked skill's [registry protocol](pickup-registry.md) for the exact operation and terminal meanings.

