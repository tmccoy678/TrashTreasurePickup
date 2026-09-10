---
name: trashpickup
description: Create a verified phase-boundary handoff and context checkpoint so work can continue safely in a fresh session.
---

# Trash Pickup

This is a manual-only phase-boundary operation. Proceed only after the current user explicitly invokes `/trashpickup` or selects `trashpickup` through an explicit skill selector. Never initiate this workflow implicitly.

Reconstruct the current state from the evidence available within the user's authorized access. Prefer canonical files, live observations, Git state, completed reports, and verified artifacts when accessible. Supplied conversation content can provide the handoff when access is limited; label its claims and unobserved state accurately. It never overrides conflicting verified evidence.

"Trash" means stale context, never user data.

## Access for this invocation

Use the permissions and capabilities already known for this invocation before opening helpers or resolving filesystem paths. Sufficient access means the relevant reads, writes, helper execution, and temporary processing are permitted; it does not mean unrestricted computer access. Do not add a mode selector or request an extra storage or registry opt-in.

- With sufficient access, resolve the workspace in section 2 and follow the publication section of the bundled [Pickup Registry protocol](references/pickup-registry.md). Automatically create required folders within that permitted location, save the handoff, archive, and checkpoint, and publish and verify the package. These saves and checks remain required. Trash never claims, opens, releases, or executes a package.
- With limited or no access, perform the same boundary assessment and content capture below using supplied content and permitted reads. Skip unavailable filesystem, registry, and command operations, including opening inaccessible helpers. Deliver the handoff and checkpoint in the conversation; optional permitted saves or manual retention belong to the user. Apply in-memory rendering instructions directly when command execution is unavailable. Do not seek broader access just to finish delivery.

Unavailable checks are `UNKNOWN` or `NOT RUN`, never `PASS`. An actual secret finding, integrity failure, registry inconsistency, or interrupted transaction keeps its failure result; do not switch to the fallback to claim success. If access is lost, report which saves or registry operations completed, failed, or remain unknown. Preserve incomplete state without claiming successful publication.

## 1. Gate on a valid phase boundary

Before writing anything, determine whether important work is still actively in progress. Inspect the smallest relevant evidence set, including when applicable:

- running agent and task state;
- unfinished commands, jobs, installers, or migrations;
- current handoffs;
- Git and workspace state;
- unresolved errors; and
- incomplete requested deliverables.

Do not terminate running work. Never encourage a fresh context during an atomic operation.

Classify the boundary:

- `READY` only when the current atomic phase is complete, no critical work is running, and the requested deliverables for that phase are complete.
- `WAIT` when the invocation is clearly mid-phase or a critical operation remains unfinished.

With sufficient access, inspect the intended track through the registry's sanitized package summaries. A summary with `claim_active: true`, or an inconsistency error, makes the boundary `WAIT`; preserve the existing canonical pair and package. With limited access, report unavailable boundary checks and assess the phase from supplied evidence. Known unfinished work still requires `WAIT`; if safe closure cannot be established, do not claim it.

For `WAIT`, explain the exact unfinished work and print `TRASHPICKUP: WAIT`. A checkpoint may still be useful, but label its Markdown handoff `NOT READY FOR FRESH CONTEXT` and set the checkpoint status to `WAIT`. Do not claim that a fresh context is safe.

## 2. Resolve the canonical workspace

Use the explicitly selected Pickup location when supplied. Otherwise use `PICKUP_HOME`, then the audit location saved by [macOS setup](references/macos-setup.md), defaulting to `~/Desktop/pickup_audit`. Expand a leading `~` in configured paths. An explicit command-line path takes precedence over its configured default.

This section's filesystem setup applies when access permits it. Follow [macOS setup](references/macos-setup.md) to locate the installed Treasure Pickup registry helper and automatically create the required folders. Existing grants and user-created folders need no new opt-in. In the commands below, `pickup_workspace` is the resolved Pickup location. Quote filesystem paths. Load the installed tool configuration described there. Use `"$pickup_python"` for Python, `"$pickup_git"` for repository checks, and `"$pickup_gitleaks"` for scanning; an explicit helper `--gitleaks-path` overrides scanner discovery.

Preserve the current project's source paths and established handoff conventions. The Pickup location stores the pair's artifacts; it does not change the project being reviewed. In the fallback, name the supplied documents without inventing saved paths.

## 3. Read canonical state first

Inspect only permitted, relevant sources needed to reconstruct the current state. For the current project, consider:
- the newest relevant audits and handoffs;
- model and provider state;
- Git status for each relevant repository;
- machine status;
- relevant project documentation; and
- the latest completed reports.

Use this evidence priority:

1. canonical persisted artifacts;
2. directly observed system and Git state;
3. completed reports and audits;
4. supplied conversation context, with claims distinguished from verified state.

If sources conflict and the conflict cannot be resolved cheaply, mark the fact `UNKNOWN` and record the conflicting sources. Do not guess. Do not recursively ingest the workspace; stop when the smallest sufficient evidence set establishes the current state.

## 4. Enforce security boundaries

Keep checkpoint artifacts free of:

- API keys, passwords, tokens, and authentication material;
- `auth.json` contents;
- recovery keys;
- full hardware serial numbers;
- protected storage contents; and
- sensitive backup filenames unless they are essential to the next phase.

Respect the user's storage permissions. Leave protected storage and backups unchanged. Perform no destructive cleanup. Read credential stores neither for evidence nor for secret scanning.

## 5. Capture current state

Produce a concise Markdown handoff with this exact top-level structure:

```markdown
# Current Context Handoff

## Current Phase

## Objective

## Known-Good State

## Decisions Made

## Current Resources

## In-Flight Work

## Dirty / Uncommitted State

## Warnings / Known Issues

## Do Not Reopen

## Security Invariants

## Canonical Paths

## Next Phase

## Next Actions

## Human Actions Required

## Fresh Context Bootstrap
```

Populate the sections as follows:

- **Current Phase:** the phase that has just completed. For `WAIT`, state the incomplete phase and add `NOT READY FOR FRESH CONTEXT` immediately below the title.
- **Objective:** the larger project objective being pursued.
- **Known-Good State:** verified facts only. Include relevant architecture, security boundaries, machine roles, current configuration, agent roles, provider/model state, completed audits, and verified paths.
- **Decisions Made:** important architectural, product, and engineering decisions the next context must preserve; omit routine conversation detail.
- **Current Resources:** relevant machines, storage, RAM or compute findings, providers, models, agents, and repositories.
- **In-Flight Work:** every task or operation known to be running. Write `NONE` only when supported; otherwise identify the unobserved scope as `UNKNOWN`.
- **Dirty / Uncommitted State:** relevant Git and workspace state. Report it without cleaning it.
- **Warnings / Known Issues:** unresolved current issues only; omit obsolete warnings that are verified resolved.
- **Do Not Reopen:** significant superseded approaches or stale assumptions that a fresh context could accidentally resurrect.
- **Security Invariants:** verified current permission, storage, backup, and credential-handling boundaries relevant to the next phase.
- **Canonical Paths:** the minimal paths the next context needs.
- **Next Phase:** exactly one primary phase.
- **Next Actions:** ordered, concrete actions for that phase.
- **Human Actions Required:** actions that actually require the current user. Write `NONE` when none exists.
- **Fresh Context Bootstrap:** a short exact instruction in this form:

```text
Read:
<current handoff>
<checkpoint JSON>
<at most one additional required architecture document>

Treat those files as the source of truth.
Do not reconstruct state from earlier chat history.
Continue from NEXT PHASE.
```

Omit the optional architecture document when it is not required. In the fallback, identify the handoff and checkpoint delivered in this conversation as the inputs to supply with the next explicit Treasure invocation. Missing file access must not add a transfer or registry-packaging step. The bootstrap preserves the next phase; it does not authorize executing it.

### Trash bag

After selecting the handoff contents, collect all accessible omitted conversation passages in original order as `(role, text)` pairs named `omitted_passages`. Use each visible message's original `user` or `assistant` role. Preserve its text subject to the existing secret exclusions; do not summarize it again, reconstruct missing history, or infer a speaker.

```python
from datetime import datetime


def build_trash_bag(omitted_passages):
    """Render omitted passages using their original conversation roles."""
    speaker_labels = {
        "user": "human generated",
        "assistant": "AI generated",
    }
    sections = []

    for role, text in omitted_passages:
        if role not in ("user", "assistant"):
            raise ValueError("An original user or assistant role is required.")

        if not isinstance(text, str):
            raise ValueError("Passage content must be text.")

        sections.append(f"## {speaker_labels[role]}\n\n{text}")

    filename = datetime.now().strftime(
        "trash_bag_%Y-%m-%d_%H-%M-%S.md"
    )
    markdown = "\n\n".join(sections)

    return filename, markdown
```

Execute this block in memory and call `build_trash_bag(omitted_passages)`. Present the returned filename and Markdown as one separate document in the current context, outside the terminal status block. Producing the bag is unconditional; saving it is entirely the user's choice. Create no bag file or temporary copy and run no bag scanner.

Keep bag contents and references out of the handoff, checkpoint, and Pickup package. Treasure Pickup must never reference, read, search, or use a trash bag. Finding, reviewing, and reusing its contents belong entirely to the user. Do not claim that closing the context deletes conversation history retained by the hosting app.

## 6. Deliver the artifacts

With limited access, deliver the section 5 handoff as archivable Markdown and the section 7 checkpoint JSON in the conversation. No disk copy, archive verification, or additional registry package is required. State any optional saves actually performed. The user controls custody of retained artifacts; the tools remain responsible for accurately reporting their checks.

With sufficient access, perform the following normal saves automatically; saving is required:

Beneath the resolved Pickup location, maintain:

- current handoff: `trashpickup/current-context.md`;
- archived handoffs: `trashpickup/context-archive/context-handoff-YYYYMMDD-HHMMSS.md`; and
- machine-readable checkpoint: `trashpickup/context-checkpoint.json`.

Use a single timestamp for the new handoff and checkpoint. Build new artifacts in temporary files on the same filesystem and atomically rename them into place when practical.

Before replacing `current-context.md`, preserve its prior known-good content. Verify that an identical archive already exists or create a collision-safe timestamped archive before replacement; never destroy the only copy. Then save an archived copy of the newly generated handoff and make it byte-identical to `current-context.md`.

For another project, use its established project-local handoff and checkpoint paths. Preserve the same current/archive/checkpoint roles and the same no-loss replacement rule.

Choose one stable 1-63 character lowercase kebab-case `pickup.track_id` for the durable line of work and the narrowest complete list of absolute `pickup.resource_scopes` the next phase may write. Preserve an established track ID across checkpoint revisions. If the stable track or scope is materially ambiguous, record the required human decision and return `WAIT` before writing.

Do not publish yet. First complete the prepublication checks in step 9A; step 9B owns publication and its postpublication acceptance checks.

## 7. Keep the checkpoint concise

Use this checkpoint shape as the baseline for normal storage:

```json
{
  "generated_at": "RFC3339 timestamp",
  "context_status": "READY",
  "current_phase": "...",
  "next_phase": "...",
  "workspace": "...",
  "in_flight_work": [],
  "warnings": [],
  "canonical_handoff": "...",
  "source_of_truth": true,
  "pickup": {
    "track_id": "<stable-1-to-63-character-kebab-case-track-id>",
    "resource_scopes": ["<absolute-owned-resource-path>"]
  }
}
```

Use `context_status: "WAIT"` when work remains active. Normal publication requires a valid timestamp, safe-closure status, matching canonical handoff, and the intended track and resource scopes. The registry records the selected package identity and SHA-256 hashes. Missing required facts remain `UNKNOWN`; do not invent them. The JSON is concise handoff metadata, not a transcript.

For conversation delivery, preserve the same phases, boundary status, and warnings. Include a `selector` that explicitly labels this handoff; `canonical_handoff` may name the supplied document. Omit filesystem-only `workspace`, `source_of_truth`, and `pickup` fields when unestablished. Include `handoff_sha256` only if computed from the exact delivered handoff bytes using permitted execution; otherwise omit it and report integrity `UNKNOWN`. A supplied digest proves consistency with that baseline, not independent authorship. Do not invent a timestamp, path, hash, or registry identity.

## 8. Check secret hygiene

For normal publication, retain the required registry scanner checks. Run available, permitted `gitleaks` checks only against the newly created handoff and checkpoint files or an isolated temporary directory containing only those files. Clean up owned temporary files after success or failure. Never scan credential stores or protected storage. Never print a discovered value.

With restricted access, keep the credential exclusions and report unavailable scanning as `NOT RUN`; neither inaccessible helpers nor temporary files are required. A missing or failing scanner in an otherwise authorized normal run remains a normal failure.

If a detector flags a possible secret:

1. remove or redact the value from the artifact;
2. report only the detector type and file path; and
3. keep the checkpoint at `WAIT` until the finding is resolved.

## 9. Validate and publish the checkpoint

In the fallback, check the supplied Markdown and JSON agree on phases, identity, and safe-closure status; preserve secret exclusions and boundary warnings. Check only available evidence. Filesystem-only acceptance criteria and registry publication below apply to the normal workflow. Do not represent skipped checks as passed.

### 9A. Validate the canonical pair before publication

Before invoking the registry, verify every applicable criterion:

- the Markdown current handoff exists;
- the new archived handoff exists and is byte-identical to the current handoff;
- the checkpoint parses with `"$pickup_python" -m json.tool <checkpoint-path>`;
- the checkpoint has a valid timestamp, says `READY`, and identifies the same canonical handoff;
- the Markdown and JSON records agree on the current and next phases;
- the current and archived handoffs state the same single next phase;
- no secret was intentionally included and any detector finding is resolved;
- no running critical task was ignored;
- reported Git/workspace dirt remains untouched; and
- no destructive operation occurred; and
- checkpoint pickup metadata exactly matches the intended publication arguments.

If any prepublication criterion fails, report `WAIT` or failure and do not publish.

### 9B. Publish and validate the immutable package

Only after step 9A passes, publish that exact handoff/checkpoint pair through the registry protocol with the validated track and resource-scope arguments. Then verify:

- the helper returned one selector;
- `inspect --selector <returned-selector>` reports `AVAILABLE`; and
- the copied package hashes match the canonical pair validated in step 9A.

The returned selector is part of the terminal result. Do not report `READY FOR FRESH CONTEXT` before all three postpublication checks pass.

If publication or a postpublication check fails, do not rewrite the pair or choose another track. Report `TRASHPICKUP: WAIT`, state that the canonical pair closed but its pickup package is unavailable, and include only the sanitized registry reason code. Exact repeat publication of the unchanged pair is the recovery path after the cause is resolved.

## 10. Print the terminal status

When the context is safe to replace, use this shape for normal successful publication:

```text
TRASHPICKUP: READY FOR FRESH CONTEXT

Current phase:
<phase>

Next phase:
<phase>

In-flight work:
NONE

Handoff:
<absolute path>

Checkpoint:
<absolute path>

Archive:
<absolute path>

Pickup:
<track-id>@<checkpoint-id>

Security:
PASS

Fresh-context bootstrap:
<one concise instruction>
```

For successful conversation delivery, use the same phase and bootstrap fields, identify `Handoff` and `Checkpoint` as delivered in the conversation, and omit uncreated archive and registry coordinates. Report performed checks and unavailable checks explicitly; use `Security: NOT FULLY VERIFIED` when scanning or relevant observations were unavailable. State that safe closure was assessed from the supplied evidence and that the user controls artifact custody. Do not print the normal template's `PASS` for an unperformed check.

When work remains active, print:

```text
TRASHPICKUP: WAIT

Reason:
<exact unfinished work>

Checkpoint:
<absolute path if one was created, otherwise NONE>
```

Never claim that a fresh context is safe after a `WAIT` result.
