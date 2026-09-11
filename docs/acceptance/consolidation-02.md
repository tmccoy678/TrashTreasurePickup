# Consolidation 02 acceptance — one project home

Recorded 2026-09-11 for issue 13. The root README presents both roles and one installer. Portable skill READMEs preserve local operational and support links. The first-use and lifecycle instructions retain WAIT, fresh-task Treasure invocation, unavailable-check reporting, update/rollback/removal, and the stop before subsequent work.

The owner-edited author note remains byte-identical to `cb82e326861ca68a1020fdd48dbc93bc21c36e57`; the truncated comparison row is repaired without restoring removed sections. Original MIT and third-party notices remain unchanged. Security guidance targets one maintained root policy with synchronized distributed copies. Public reporting is still pending.

## Validation

- Full suite: **269 tests passed in 121.401 seconds**, Python 3.12.14, Apple Silicon/macOS 26.6.2. This includes disposable installation and historical update/recovery scenarios.
- Documentation, Python/shell syntax, metadata, local/installed Markdown references, policy equality, and whitespace checks pass.
- GitHub's GFM renderer returned the root and both package READMEs and comparison document successfully. Inspected rendered structure has one title per page; both comparison tables have complete rows (30 body cells total), and installer/first-use/support links remain present. This is rendered HTML structure/content inspection, not a visual accessibility audit.
- Distribution source: `4eb8951` (full immutable ID is recorded in the payload manifest). Two clean builds outside the checkout match. All **39 files** verify against their declared source mappings.
- Installer SHA-256: `0ec873e55b08645200aa5a56618ae8cb66fa84bfee1eb284f98388efed0d9d52`.

[Successor draft PR 16](https://github.com/tmccoy678/draft2staged-treasurepickup/pull/16) retains all eleven added figure/source files byte-for-byte from the original Treasure PR10 and Trash PR2. Its consolidation manifest lists both source commits and SHA-256 values. PDFs, accessible HTML alternatives, source qualifications, and provenance remain intact. Its new shared assets synchronize into both skill packages and its draft bundle verifies 51 files. The original reviews were closed as superseded, with links to the successor; their discussions and branches remain. The successor remains unaccepted and unmerged. Original rendering and citation reviews remain historical observations, not repeated certification during this port.

## Standards

The initial review found outdated two-repository instructions in the active security-launch checklist. Those instructions were corrected to the surviving project and synchronized root policy. Final review is recorded in the implementing PR.

## Spec

Zero findings in the implementation review. Pending draft preservation and rendered-document checks are recorded above; hosted checks are attached to the implementing PR. Naming and archive changes belong to issue 14.

## Limits carried forward

Model formatting and exact reproduction still require inspection. Real-scanner execution, normal saved-host end-to-end operation, native GUI discovery, Intel/older macOS, and other hosts remain unverified. [The first consolidation record](consolidation-01.md) contains the bounded CLI observations. No runtime or skill instructions changed in this ticket; those observations remain applicable to the unchanged instruction bytes.
