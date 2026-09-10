# Pickup using the access the user allows

Status: ready-for-agent

## Problem Statement

The draft2 pair's normal handoff, storage, and registry workflow depends on filesystem and helper access. Users who grant sufficient access should retain that automation. Users who grant limited or no access still need to carry Trash's supplied handoff into Treasure and receive an accurate result.

## Solution

Use the access already authorized for the invocation. With sufficient access, create required folders, save artifacts, run the registry helpers and their checks, and finish normally without another storage or registry opt-in. With insufficient access, work from the supplied handoff in the conversation, bypass unavailable filesystem and helper operations, and return a Markdown receipt with accurate limitations. Saving is optional only in that limited-access fallback.

Both use the same handoff content and reconstruction logic. The access decision controls available operations; it does not require duplicated implementations or a user-facing mode selector.

## User Stories

1. As a user, I want explicit invocation to start either skill so that I control when pickup occurs.
2. As a user granting sufficient access, I want required folders created automatically so that I do not need an extra setup step.
3. As a user granting sufficient access, I want Trash to save its handoff, archive, and checkpoint normally so that the durable record is preserved.
4. As a user granting sufficient access, I want the registry used automatically so that I retain the existing package and receipt history.
5. As a user, I want normal helper verification retained so that automation preserves its established checks.
6. As a user denying AI file access, I want to supply Trash's content directly so that Treasure can reconstruct it without reading my filesystem.
7. As a user granting limited access, I want only permitted reads and writes performed so that the fallback respects my boundaries.
8. As a user, I want one shared handoff flow so that access differences do not require another transfer step.
9. As a user, I want existing permission grants honored so that I am not asked repeatedly to authorize normal operations.
10. As a user, I want unavailable checks distinguished from passed checks so that limited access does not create false assurance.
11. As a user, I want actual verification failures disclosed so that they cannot be hidden by switching to the fallback.
12. As a user, I want one Markdown receipt that can include existing JSON receipt details so that I can understand the result.
13. As a user, I want secret checking and temporary processing confined to permitted material so that unrelated data is not searched.
14. As a user, I want artifact custody and execution authority stated accurately so that pickup completion does not authorize further work.
15. As the owner, I want relevant regression checks to remain required so that supporting limited access does not weaken normal pickup.
16. As the owner, I want work confined to draft2 so that the first staged pair remains intact for separate integration work.

## Implementation Decisions

- Determine whether the invocation has sufficient authorized access for the existing file and helper operations. Use known permissions and capabilities; no separate registry opt-in is required. Preserve the shared flow and put the access condition around operations that require it.
- With sufficient access, proceed as normal automatically: create required folders, save and archive Trash's handoff and checkpoint, publish and verify its registry package, and use Treasure's claim, verification, receipt, and completion operations. Saving and applicable runtime checks remain required for this normal workflow.
- Use the configured Pickup location, including its existing Desktop audit default when no override is supplied and access covers it. A user-created folder works identically. Do not ask again for permissions already granted; applicable platform permission controls and explicit user restrictions still apply.
- With insufficient access, use the exact handoff and checkpoint already supplied by Trash through readable attachments, pasted content, or permitted file reads. Do not require registry claims, returned registry paths, package copies, disk saves, or examining unavailable helpers. Deliver the reconstructed context and receipt in the conversation. The user may retain them manually; any permitted saving in this fallback remains optional.
- Reuse the approved handoff verifier unchanged when its inputs and execution are available. Preserve its check outcomes and failure precedence. In the fallback, unavailable hashes, original bytes, execution, or live observations remain UNKNOWN or NOT RUN as appropriate and do not prevent reconstruction of supplied content. Never invent a digest or claim exact-byte continuity after silently altering the supplied text.
- Preserve normal failure handling when checks run. A failed integrity check, secret finding, corrupt registry, or interrupted transaction must not be relabeled as an access limitation to obtain success. If access is lost during a run, report incomplete registry operations accurately; do not claim a claim was closed or an artifact saved without evidence.
- Return one user-facing Markdown receipt in either case, incorporating relevant JSON receipt details when available. Normal operation retains its existing internal JSON records and saves the Markdown receipt as part of authorized output. The fallback may return the Markdown solely in the conversation. Identify performed checks, unavailable checks, failures, and scope limits; distinguish stored evidence from current observations and never fabricate registry state.
- For normal operation, keep existing successful-completion conditions. In the fallback, DONE means the supplied context was reconstructed and reporting completed, with its verification limits explicit. Neither outcome authorizes the next phase or proves unobserved machine state.
- Preserve normal secret-scanning requirements. Limited access does not require opening unavailable helpers or producing temporary files. Where temporary processing is permitted, restrict it to the relevant artifact or receipt material and clean up owned temporary files after success or failure. Report unavailable scanning accurately and preserve the existing credential exclusions.
- Preserve manual invocation, safe-boundary reporting, the current trash-bag behavior, and the prohibition on Treasure using trash bags. The user controls custody of retained outputs; the tools remain responsible for reporting their checks accurately.
- Keep the existing registry implementation and its regression coverage. Update the pair's instructions, output presentation, and access-dependent connections with the smallest changes needed; do not build a replacement registry or duplicate the pickup logic.

## Testing Decisions

- Use the complete Trash-to-Treasure handoff as the primary acceptance seam. Reuse the existing command-line lifecycle, verifier, artifact, and secret-handling tests; add no new framework.
- With sufficient authorized access, verify automatic directory creation, normal artifact and archive saves, package publication, claims, verification, receipt history, and completion without a separate opt-in. Exercise the real scanner in an isolated installation.
- With limited or no access, exercise supplied content through the same reconstruction flow. Confirm no unauthorized writes or attempts to inspect unavailable helpers, no required registry transaction, and delivery of the Markdown receipt despite unavailable checks. Cover partial access, including readable artifacts without permission to persist outputs.
- Cover exact matches, identity and integrity mismatches, missing hashes or bytes, unavailable execution, and access loss. Confirm that actual failures are not hidden by fallback and that incomplete operations remain visible.
- Verify one Markdown receipt in both cases: normally saved with available JSON details, or returned in the conversation when access is restricted. Confirm honest verification status and no phase authorization.
- Relevant regression checks remain required acceptance gates for implementation, including the retained registry helpers and the normal file workflow. These development checks are distinct from the runtime helper checks; the limited-access invocation is not required to inspect or execute inaccessible helpers or their test suite.
- Validate temporary-file cleanup on success and failure, agreement between both skills and their documentation, and the exact changed-file scope. Use isolated fixtures and leave existing user audit data untouched. State which behaviors were executed and which were reviewed from instructions.

## Out of Scope

Implementation during this planning step; publishing or committing; changes to the first staged pair, DobeWorks, or DEGS; Windows support; replacing or broadly rewriting the registry; a new access-mode selector; new retention policies; trash-bag changes; mutation of live user registries during implementation or testing; and guarantees beyond the evidence actually checked.

## Further Notes

This extends the completed [standalone-pair specification](../standalone-pickup/spec.md) with a fallback for insufficient access while retaining its normal file and registry workflow. External governance requirements remain removed.

Sufficient access means permission for the relevant operations and locations, not unrestricted access to the entire computer. Restricted access does not require broader permission just to return a handoff and receipt. A supplied hash establishes consistency with its supplied baseline, not independent authorship. Closing a context does not itself delete disk files or retained conversation history.

Ready-for-agent records specification readiness. Implementation awaits the owner's next approved step.
