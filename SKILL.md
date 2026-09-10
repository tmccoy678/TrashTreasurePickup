---
name: treasurepickup
description: Reconstruct one supplied pickup handoff in a fresh context, using authorized checks and reporting verification limits.
---

# Treasure Pickup

This is a manual-only fresh-context opening operation. Proceed only after the current user explicitly invokes `/treasurepickup` or selects `treasurepickup` through an explicit skill selector. Never initiate this workflow implicitly.

`trashpickup` closes a context by delivering its handoff and checkpoint; `treasurepickup` opens the next context by checking the supplied artifacts and reconstructing bounded context. Sufficient access retains the normal saved package and registry workflow. Limited access permits the same content to travel through the conversation.

Use the selected handoff and checkpoint as the reconstruction baseline, with stored claims distinguished from current observations. Read, verify what access allows, reconstruct, then stop. Do not begin the next phase or modify project files. Writes are confined to authorized pickup telemetry and receipts.

## Access for this invocation

Use known permissions and capabilities before opening helpers or resolving filesystem paths. Sufficient access means permission for the relevant operations and locations, not unrestricted computer access. Honor existing grants and user-created folders without another storage or registry opt-in; do not add a mode selector.

- With sufficient access, automatically create required folders within the configured Pickup location and follow the bundled [Pickup Registry protocol](references/pickup-registry.md). Package selection, claims, verification gates, JSON records, the Markdown receipt save, and completion remain required.
- With limited or no access, use the exact handoff and checkpoint supplied with this invocation through pasted content, readable attachments, or permitted file reads. Skip unavailable filesystem and helper operations, including inspecting inaccessible helpers, making package copies, claims, and registry transitions. Return the same reconstructed context and one Markdown receipt in the conversation. Permitted saving is optional only in this fallback; no broader access is needed just to deliver it.

Unavailable evidence or execution is `UNKNOWN` or `NOT RUN`. An actual integrity mismatch, secret finding, corrupt registry, or interrupted operation retains its failure result; do not switch to the fallback to claim success. If access is lost after a claim or write starts, report incomplete operations and the last confirmed state. Never claim closure, a saved path, or consumption without evidence.

Proceed only when the explicit invocation is the first substantive user turn in this task. If prior substantive work exists or freshness is unknown, report `TREASUREPICKUP: REVIEW REQUIRED` in a Markdown receipt and stop. Do not read, hash, store, or print runtime session, thread, task, or process IDs or window titles. Preserve an explicit handoff selector exactly and never choose among ambiguous supplied handoffs.

## Workspace paths when access permits

Before using the registry, follow [macOS setup](references/macos-setup.md) to resolve `pickup_workspace` and locate the bundled registry helper. The Pickup location default is:

```bash
export PICKUP_HOME="${PICKUP_HOME:-$HOME/Desktop/pickup_audit}"
```

Use absolute paths. Explicit command-line paths take precedence. Registry `claim --workspace` supplies the observed workspace and the default registry location; an explicit `--registry-root` wins. The default compatibility output follows the registry's existing workspace binding: two parent directories above the registry, then `treasurepickup/context-resume.json`. `--compatibility-output` overrides that default. Existing workspace and output binding checks still apply. Other registry commands use `PICKUP_HOME` when `--registry-root` is omitted.

The legacy receipt helper keeps `--workspace` as the observed invocation directory, defaulting to the current directory. Its `--expected-workspace` selects the configured workspace, defaulting to `PICKUP_HOME`, and supplies default handoff, checkpoint, and receipt paths. Explicit `--handoff`, `--checkpoint`, and `--output` win. The observed and expected workspaces must still agree.

Supply `--gitleaks-path` for an explicit scanner executable; otherwise the helpers find `gitleaks` through `PATH`.

## 0. Select the handoff

In the fallback, select the handoff supplied by the user and continue to section 1 without a registry claim. If selection is ambiguous, ask for the exact handoff and stop. Do not search for alternatives or create a package.

With sufficient access, inspect and claim through the registry protocol before reading canonical state. Preserve an explicitly supplied selector exactly; never choose among multiple available packages. Use `fresh-task: YES` with `freshness-basis: FIRST_SUBSTANTIVE_USER_TURN` only when established by the shared freshness rule above.

Use only durable coordinates returned by the helper for later protocol operations.

If claim reports `PICKUP_SELECTION_REQUIRED`, list only entries returned by `inspect` whose state is exactly `AVAILABLE`, ask the current user to choose one selector, and stop. Do not present `CLAIMED`, `OPENING`, `SUPERSEDED`, `CONSUMED`, or `NEEDS_REVIEW` packages as choices. For any other claim failure, report `TREASUREPICKUP: REVIEW REQUIRED` with the sanitized reason code and stop. Never overwrite, take over, or repair a claim.

After a claim succeeds, finalize it through `complete` before every normal stop path. Leave it at `VERIFYING` only when the helper cannot safely append a terminal revision; report that incomplete telemetry explicitly rather than claiming a terminal result.

## 1. Read the selected handoff and checkpoint

For limited access, read only the supplied handoff/checkpoint and any supplied manifest metadata. Preserve original bytes when available; pasted text alone does not establish the original file bytes. Reuse the bundled `verify_handoff(metadata, selected, handoff_bytes)` unchanged if permitted execution and helper access are available. Use the supplied `selector` and `handoff_sha256` metadata, the explicitly selected identity, and actual original bytes or `None`; do not hash reformatted text and claim continuity. If execution is unavailable, report the verifier as `NOT RUN` and identify any direct content comparisons separately.

Preserve the verifier's returned status, drift, checks, and failure precedence verbatim. Missing identity, hashes, bytes, or execution do not prevent reconstruction in the fallback; record their limits. An actual mismatch requires review and prevents `DONE`. Missing disk paths, a registry manifest, or registry-specific metadata must not block supplied-content reconstruction. If the supplied checkpoint is malformed or says `WAIT`, report the invalidity or unsafe closure and stop; an unestablished safe boundary requires review. No registry gate is required for this fallback.

For normal operation, read exactly the four artifact paths returned by the claim:

- the selected package's `package.json` manifest;
- the selected package's `handoff.md`;
- the selected package's `checkpoint.json`; and
- the deployed Treasure Pickup `SKILL.md` fingerprinted by the receipt.

Validate that all four files are regular non-symlink files, the package selector matches the claimed track/checkpoint IDs, both copied artifact hashes match the manifest and receipt, the checkpoint parses as JSON, and the checkpoint's `canonical_handoff` matches the manifest's recorded source handoff. Treat semantic checkpoint invalidity, such as an invalid timestamp or an unpaired canonical handoff, as blocked/unknown. Treat a missing or changed sealed package artifact as artifact drift and report the helper's durable `REVIEW_REQUIRED / MATERIAL` result.

Do not substitute `$PICKUP_HOME/trashpickup/current-context.md` or `$PICKUP_HOME/trashpickup/context-checkpoint.json` for the selected package. Those mutable current pointers may belong to another track or later checkpoint. Inspect them only when the selected handoff makes their live state relevant.

Normal operation requires a valid checkpoint `generated_at` timestamp and the matching `canonical_handoff`. The registry's shared `verify_handoff()` checks the selected identity and handoff bytes against the recorded SHA-256; it does not verify the handoff's claims or live state. Missing required normal metadata is `UNKNOWN`: complete blocked telemetry when possible and stop.

The checkpoint must say that the prior context closed safely. If its `context_status` is not `READY`, complete the run as `BLOCKED / UNKNOWN`, report exactly:

```text
TREASUREPICKUP: BLOCKED
Reason: previous context was not safely closed
```

For any semantic package/checkpoint invalidity that is not artifact or hash drift, complete sanitized blocked telemetry when possible and report:

```text
TREASUREPICKUP: BLOCKED
Reason: missing or invalid pickup package
```

In normal operation, after the immutable package is valid and the prior context is safely closed, append `CANONICAL_PAIR_VERIFIED` through the registry protocol and preserve the returned revision/hash.

In either case, use the handoff and checkpoint as the reconstruction baseline. Load an additional file only when permitted and explicitly required by the handoff for the bootstrap or verification. Use existence or metadata checks when sufficient. Do not recursively ingest the workspace, historical handoffs, audits, logs, repositories, credential stores, or backup media. Never reference, read, search, or use a trash bag; retrieval from it belongs entirely to the user.

## 2. Derive the minimum verification surface

From the checkpoint and the handoff's `Next Phase`, `Next Actions`, `Canonical Paths`, `Security Invariants`, `Current Resources`, `Current Warnings`, and `Fresh Context Bootstrap`, identify only the live facts whose drift could change whether or how the next phase should run.

Verify only the relevant, permitted subset of:

- current user, hostname, and canonical workspace;
- every security invariant stated in the handoff;
- protected-storage mount state when relevant;
- provider health required by the next phase;
- relevant running jobs or atomic operations;
- the active Git repository, branch, and dirty or uncommitted state;
- required files and directories;
- external-disk presence when the next phase depends on that disk; and
- machine, authority, or configuration state required by the next phase.

Use the cheapest read-only check that can disprove the checkpoint. Stop checking a branch when further evidence cannot change its classification or next-phase decision.

In the fallback, unavailable live observations stay `UNKNOWN` and do not prevent reconstructing supplied content. Do not require access to unavailable helpers or their regression tests. Development regression checks remain required acceptance gates for changes to the skills; they are distinct from invocation-time verification.

Maintain the authority captured in the checkpoint. Do not elevate permissions, expand agent authority, start providers, launch work, reconcile configuration, mount protected storage, connect a missing disk, clean a worktree, or repair drift during this workflow.

Keep commands and outputs free of keys, tokens, passwords, `auth.json` contents, recovery material, full serial numbers, and sensitive backup filenames. Read neither credential values nor protected storage contents. Report only sanitized state such as present/absent, healthy/unhealthy, expected/unexpected, or permissions pass/fail.

Normal registry secret checks remain required. Restrict permitted temporary processing to the relevant artifacts or receipt material and clean up owned temporary files on success or failure. Restricted access does not require running a scanner or creating temporary files; report unavailable scanning as `NOT RUN`. A missing or failing scanner in an otherwise authorized normal run remains a normal failure. Never repeat a discovered secret in the context or receipt.

## 3. Classify every relevant difference

Classify each checked fact against the canonical baseline as exactly one of:

- `EXPECTED`: the handoff explicitly anticipated the difference and it remains within the stated safety boundary.
- `BENIGN`: the difference is explained and cannot change security, correctness, or the next phase.
- `MATERIAL`: the difference can change readiness, correctness, or the next phase.
- `SECURITY`: the difference weakens or contradicts an authority, isolation, credential, permission, or other security invariant.
- `UNKNOWN`: a required fact cannot be verified or a relevant difference cannot be explained safely.
- `NONE`: no relevant difference exists.

Examples of `SECURITY` drift include protected storage being unexpectedly mounted, user-granted permissions changing unexpectedly, or credential/config permissions being weaker than the verified baseline. Security drift takes precedence over every other classification. Write stopped telemetry when possible, report:

```text
TREASUREPICKUP: STOP
Reason: security drift
Drift: SECURITY
```

Do not reconstruct a resumable context or resume work.

An unexpected Git branch, unexplained uncommitted changes, a required disconnected disk, or material provider/machine disagreement is `MATERIAL` unless the evidence instead requires `SECURITY` or `UNKNOWN`. Actual material differences and unexplained observed differences require human review in both cases. Normal operation also requires review for unavailable required evidence. In the fallback, evidence unavailable solely because of limited access remains `UNKNOWN` in the receipt and permits reconstruction; it is not a passed check. Write review telemetry when available and report actual failures:

```text
TREASUREPICKUP: REVIEW REQUIRED
Drift: MATERIAL
```

or:

```text
TREASUREPICKUP: REVIEW REQUIRED
Drift: UNKNOWN
```

State the smallest sanitized evidence needed for review, then stop. Never choose a convenient explanation for unresolved drift.

When multiple differences exist, use this precedence for the aggregate drift: `SECURITY`; then `UNKNOWN`; then `MATERIAL`; then `EXPECTED`; then `BENIGN`; then `NONE`. A state is verified only when every relevant difference is `NONE`, `EXPECTED`, or `BENIGN`.

In normal operation, when the complete required live-state surface has been checked and classified—even when the verified result is `SECURITY` or `MATERIAL`—append `LIVE_STATE_VERIFIED` through the registry protocol and preserve the returned revision/hash.

Do not advance this gate when a required fact remains unverified; complete the normal run as `REVIEW_REQUIRED` with drift `UNKNOWN` instead. The fallback makes no gate transition.

## 4. Reconstruct the bounded resume context

After normal verification passes, or after fallback checks find no actual failure and supplied evidence establishes safe closure, reconstruct the context under exactly these headings:

```markdown
## Objective
## Current Phase
## Known-Good State
## Security Invariants
## Decisions To Preserve
## Relevant Resources
## Current Warnings
## Next Phase
## Next Actions
## Human Actions Required
```

Use the same content selection in either case. Keep verified facts, supplied claims, current observations, and inferences distinct. Label handoff claims that were not rechecked. Mark unsupported values `UNKNOWN`; normal verification requires review when an unknown affects safe execution. Fallback reconstruction may finish with explicit verification limits, but it does not establish execution readiness.

Treat the handoff's `Do Not Reopen` section as binding. Preserve its decisions as constraints and do not present disproven approaches or obsolete paths as options.

## 5. Complete the schema-v4 pickup run

This section applies only to an actual registry run. The fallback proceeds directly to the Markdown receipt in section 6. A partially completed registry run must disclose incomplete state and cannot report `DONE` by skipping this section.

Classify the outcome from the verification rules above, then complete the run through the registry protocol. For successful completion (`DONE` in the user report, `READY` in the registry), supply the verified current and next phases. For another result, provide the matching classification plus an uppercase reason code and the smallest bounded printable sanitized reason. If source wording may contain unsafe material, replace it with an accurate generic sanitized reason; never omit the mandatory reason fields.

The registry protocol is the single source for terminal status/drift pairs, required fields, transition order and evidence, artifact-drift handling, exact correlation, claim closure, and immutable receipt mechanics. Never hand-edit its files or compatibility telemetry. Only an explicit instruction from the current user may release an abandoned package; this opening workflow never assumes that authority.

## 6. Report completion and stop

Normal `DONE` requires valid canonical inputs, safe prior closure, verified relevant facts, reconstructed context, validated terminal JSON, and the saved Markdown receipt returned as `markdown_receipt_path`. The helper saves one Markdown presentation of the same JSON checks in `receipts/` beside the compatibility output, using the existing transaction. It retains internal JSON history. If the save or transaction fails, report the failure and incomplete state; do not claim `DONE`.

Report normal success as:

```text
TREASUREPICKUP: DONE
Drift: NONE
```

Use `EXPECTED` or `BENIGN` instead of `NONE` when that is the aggregate verified drift. Include the bounded resume context and one Markdown receipt, with its saved path and confirmed selector, receipt ID, revision, JSON receipt path, and compatibility path. The Markdown contains the recorded JSON details; do not emit a separate JSON receipt document.

In the fallback, `DONE` means the supplied context was reconstructed and reporting completed. Return the bounded context and one Markdown receipt directly in the conversation with this content:

```markdown
# Treasure Pickup Receipt

TREASUREPICKUP: <DONE, BLOCKED, REVIEW REQUIRED, or STOP>
Basis: supplied handoff and checkpoint
Verification: <exact verifier status, or NOT RUN>
Drift: <observed classification, or UNKNOWN>
Performed checks: <checks actually performed and their results>
Unavailable checks: <UNKNOWN or NOT RUN, with the access or evidence limit>
Registry operations: <NOT RUN, or last confirmed and incomplete operations>
Limitations: <stored claims versus current observations; missing original bytes or scanning>

The user controls artifact custody. The tools remain responsible for reporting checks accurately.
No authorization for subsequent work; unobserved live state remains unknown.
```

Include the verifier's JSON result unchanged when available, even if it is `BLOCKED / UNKNOWN` while reconstruction is `DONE`. Do not claim original-byte integrity from pasted text, independent authorship from a supplied hash, or quality and validity after transfer beyond the evidence checked. Omit invented paths, hashes, claim IDs, revisions, and consume status. For early stops or errors without a durable receipt, use this same Markdown reporting shape with the actual failure and incomplete state; never fabricate successful registry completion.

`DONE` confirms completion within the reported access and verification limits and grants no authorization for subsequent work. Stop after reporting. Do not edit project files, delegate work, or perform the `Next Actions` during the treasurepickup workflow.
