# Implementation acceptance

Completed 2026-09-10 against [ticket 01](issues/01-complete-pickup-from-supplied-artifacts.md). The parent specification remains unchanged.

## Executed checks

- TDD: the new CLI lifecycle test first failed because no Markdown receipt was returned. It passed after the existing receipt transaction was extended to save that presentation. No new command, mode selector, registry schema, or replacement implementation was added.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests`: **241 tests passed** in 107.726 seconds. Three added tests cover one saved Markdown receipt matching the terminal JSON, interrupted Markdown persistence leaving an active incomplete claim with owned output cleanup, and an aborted receipt that cannot claim `DONE`.
- Existing verifier coverage passed for matching identity and bytes, identity/integrity mismatch, missing hashes/bytes, malformed field values, and failure taking precedence over missing evidence. Existing registry, secret-handling, transaction, receipt-history, and workspace regressions also passed.
- An isolated copy of the installed pair exercised setup directory creation, preservation of the prior handoff archive, matching current/archive saves, checkpoint storage, publish, claim, artifact checks, live fixture checks, completion, and consumed-state inspection. The saved Markdown contained the same JSON as the terminal record and preserved `phase_authorized: false`.
- The already-started isolated validation used the real Gitleaks scanner successfully for package, receipt, and installed-source checks. No further real-scanner run was performed after the owner waived it. Owned scan temporary storage was empty after success and after a separately injected scanner rejection.
- All Python source and test files parsed with the supported Python 3.9 syntax. No configured static type-checker was available; syntax checking is not represented as type checking.

## Restricted-access walkthroughs

These are instruction-level acceptance checks, independently reviewed by the Spec reviewer. They were not autonomous restricted-model executions or invocations on user work.

Both cases use a first-turn explicit invocation and a supplied handoff/checkpoint identifying `fixture-handoff`, a safely closed `Definition` phase, and `Implementation` as the next phase.

| Available access | Shared reconstruction and receipt result |
| --- | --- |
| Supplied conversation content; no file or command access; no original bytes or digest | Use the shared ten reconstruction headings, identify supplied claims, and return one Markdown receipt. Reconstruction can be `DONE`; the verifier and registry operations are `NOT RUN`, with integrity, scanning, and live-observation limits explicit. No helper inspection, writes, invented paths, or registry coordinates are required. |
| Permitted exact-byte reads and helper execution; no persistence; digest missing | The unchanged verifier reports identity `PASS`, integrity `UNKNOWN`, status `BLOCKED`, drift `UNKNOWN`, live state `UNKNOWN`, and `phase_authorized: false`. Preserve this result unchanged within the one Markdown receipt while reconstruction can be `DONE`. No claim, gate transition, or persistence is required. |

The shared instructions preserve actual mismatch/secret/corruption failures and disclose interrupted operations; they cannot be reclassified as access limitations to obtain success. Unestablished safe closure still requires review. Artifact custody belongs to the user; the tools remain responsible for reporting checks accurately, and neither result authorizes subsequent work.

## Review and scope

- Standards review: **0 findings**, worst severity none.
- Spec review: **0 findings**, worst severity none.
- The fixed point was the exact pre-edit artifact snapshot. Both repositories have unborn HEAD, so no commit comparison or commit creation was used. Two independent review agents inspected the pinned nonempty before/after diff. Temporary review copies were removed after review.
- The trash-bag block and approved `verify_handoff()` source remain exactly unchanged. Both copies of setup and registry guidance agree.
- Changes are confined to the draft2 skills, readmes, setup/protocol references, Treasure's display description, existing registry helper and tests, plus this ticket's completion evidence. The first staged pair, other systems, licenses, Git state, and parent specification are preserved. No live user audit data was used or mutated. No commit or publication was performed.
