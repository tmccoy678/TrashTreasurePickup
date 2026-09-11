# Consolidation 01 acceptance — one checkout

Recorded 2026-09-11 for consolidation issue 12 and PR 15. This record does not replace historical paired-publication evidence.

## Source and distribution

- Treasure baseline: `cb82e326861ca68a1020fdd48dbc93bc21c36e57`.
- Imported Trash baseline: `bb44f27c5ab367c3ef0148457ad61977f99690d8`.
- Import commit: `025ad24` uses an unsquashed second parent. Both original commits are ancestors of the implementation branch; integration must preserve this with a merge commit.
- Distribution source: `f809a382c1f50347daeb8cea0b9b6eb98dbae8a3`.
- Distribution artifact commit: `5bdf23ec64f91dbeb72ec7b5902e5fe0dd1eeaa2`.
- SHA-256: `a118709ed8e9316a890204b80a64da4d4a406f6520894bad88df7d1f116a7ac3`.
- Manifest: `pickup-single-repository-v1`, 39 distributed files. Two clean builds with the same source/runtime and outputs outside the checkout are byte-identical. Full verification checks source paths, declared commit bytes, payload, and wrapper.

Both skill instructions, the three Treasure runtime helpers, original MIT text, and latest owner author-note bytes remain unchanged. The approved verifier and trash-bag renderer remain unchanged. Shared root policies/references are materialized as checked regular files in both packages. Legacy artifacts retain their historical manifest interpretation.

## Local checks

Python 3.12.14 on Apple Silicon/macOS 26.6.2: **269 tests passed in 123.344 seconds** after review corrections. Documentation/local-link, metadata, shared-copy, Python/shell syntax, and whitespace checks passed. There is no separate typechecker configuration.

The one-checkout tests cover missing inputs, stale copies, symlinked destinations, immutable provenance, file mapping, payload tampering, explicit legacy arguments, and repeatable clean builds. CLI regressions cover registry and receipt semantics. The retained old installer fixture is digest-checked, then its extracted tool-download table is replaced only in disposable test storage. Both default/custom installations undergo interrupted update, completed update, backup verification, restoration, and documented removal. Audits, bags, backups, and unrelated skills remain intact. Tool downloads and scanner results in these tests are fixtures.

## Host observations

Codex CLI 0.154.0, gpt-6-astra with low reasoning, ephemeral read-only tasks. The runner discovers both relocated skill metadata entries and supplies the exact selected instructions in the developer channel. It does not prove native GUI automatic injection. A sandbox SQLite initialization failure was excluded; successful runs used the existing authorized CLI runtime.

| Scenario | Observed result | Qualification |
| --- | --- | --- |
| Supplied READY pair | DONE, verification NOT RUN, drift UNKNOWN; bounded reconstruction and receipt | No saved package or live-state claim |
| Unfinished critical operation | WAIT | Boundary correct; omitted conversation text was not reproduced exactly |
| Prior substantive work | REVIEW REQUIRED before reconstruction | Fresh-task requirement retained |
| Unrelated input | Exact response `orchard` | No unsolicited Pickup result |
| Completed fictional Trash phase | READY with consistent labels, JSON, standalone headings, and bootstrap | Supplied claims only; omitted conversation text showed substitutions/additions |

All five captured runs reported zero tool operations. READY identity and JSON were inspected directly. These are bounded observations, not evidence of guaranteed verbatim model output. Raw host output is retained privately because it includes host-provided configuration text. The separate trash bag still requires inspection; no runtime or skill behavior was altered to conceal this limitation.

Real scanner execution, normal saved-host end-to-end operation, native GUI discovery, Intel/older macOS, and other hosts remain unverified. A configured macOS floor is not a tested-support promise.

## Standards

Zero unresolved findings after correcting obsolete two-repository contribution guidance. The focused re-review found no additional documented-standard violation or actionable code smell.

## Spec

Zero unresolved findings after adding historical-installer interruption, rollback, and removal coverage. Remaining integration evidence is the merge ancestry and hosted checks linked from PR 15.

Hosted run [34650716037](https://github.com/tmccoy678/draft2staged-treasurepickup/actions/runs/34650716037) passed on the earlier implementation artifact. PR 15 records the final-head and merge checks separately. The workflow uses one checkout with no companion secret. Credential retirement belongs to consolidation issue 14.
