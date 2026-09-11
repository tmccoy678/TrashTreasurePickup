# Publication Tickets 01–05 acceptance

This record covers the five approved implementation tickets: [first use](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/4), [artifact authority](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/5), [paired packaging](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/6), [maintenance](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/7), and [support/security preparation](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/8). Changes and review history are retained in [Trash PR 1](https://github.com/tmccoy678/draft2staged-trashpickup/pull/1) and [Treasure PR 9](https://github.com/tmccoy678/draft2staged-treasurepickup/pull/9).

Validation was performed September 10, 2026, in the maintainer's local time. This is implementation evidence, not a versioned release or a claim that every model response will conform.

## Source and distribution identity

| Identity | Commit or digest |
| --- | --- |
| Trash review baseline | `04585979f8ba5c70c27faf5eda953a1480a1d81d` |
| Treasure review baseline | `f4249639498f78ace2ca6f19e37a28ea3c1cc20d` |
| Distributed Trash source | `924b1485f2df3c29ec94acf1fdf61da4058c5a89` |
| Distributed Treasure source | `4ea47888649a409d88161cbafc4b03cdbcb50cc0` |
| Installer SHA-256 | `3e2595722f4a5c6b74c36fd06d54f0193db84be293a9e99a9ac5aca12cda8839` |

The installer contains 39 distributed files plus its source manifest. Both sources were clean when two comparison outputs were built outside the checkouts; those outputs were byte-identical. Every distributed file was checked against its declared source commit. The Treasure source precedes the commit containing the refreshed installer and this record; those later changes do not change the shipped Treasure inputs.

Working-tree modification observations are included in provenance. Same source pins with different observations need not produce the same checksum. The reproducibility result above uses the same clean inputs and runtime; verification of the checked-in candidate checks its own recorded manifest.

## Executable checks

- Local full regression suite: **259 tests passed in 110.887 seconds**, using Python 3.12.14 on arm64 macOS 26.6.2.
- Bundle CLI tests cover missing required policies, metadata, references and third-party notices; changed distributed bytes; incorrect or mutable source identities; altered wrapper code; manifest coverage; and repeated builds with unchanged inputs.
- Installer CLI tests cover default/custom destinations, update backups, documented rollback and removal, and interrupted updates. Sentinel audit records, an optional bag, and unrelated skills remain intact. Existing helper tests exercise normal saved publish/claim/complete and failure behavior through their public commands.
- Documentation checks cover shared-reference equality, local links, explicit-only host metadata, license equality, Python syntax, and shell syntax. Whitespace checks pass.
- The registry helper, handoff verifier, executable wrapper, approved Trash renderer, and both MIT license texts are byte-identical to their review baselines.

The observed red-to-green work at the agreed CLI seams included missing-policy rejection, verification behavior, explicit source validation, and mutable provenance rejection. The host consistency defect below was observed before its instruction fix, then checked again at the host boundary. These checks do not freeze documentation sentences or test private helper methods.

[Hosted paired checks](https://github.com/tmccoy678/draft2staged-treasurepickup/actions/workflows/paired-checks.yml) run the full suite, documentation checks, and checked-in bundle verification against the pinned companion. The PR checks identify the exact tested head. While the sources are private, checkout uses a dedicated read-only companion deploy key and does not persist it in Git configuration.

## Host observations

Configuration: Codex CLI `0.154.0`, model `gpt-6-astra`, low reasoning effort, disposable repository-scoped candidate skills, read-only access, and no permitted tool operations. Candidate discovery was observed. The app-server runner supplied the exact skill text as scenario instructions outside user/assistant passages. It does not test native GUI skill-text injection. See [the maintained scenarios and runner](host-scenarios.md).

All eleven scenario types were run. Every captured scenario reported zero tool-operation events. Responses were reviewed for the specific expected boundary; a generated response alone was not counted as acceptance.

| Scenario | Observed result |
| --- | --- |
| Unrelated prompt | Requested answer; no implicit skill invocation. |
| Trash, completed phase | Initial response failed: its checkpoint misspelled the handoff identity and a required heading joined a list item despite READY. After the instruction fix, the focused response had parseable JSON, all 15 required section headings in order, matching handoff/checkpoint/bootstrap references, and consistent phases, selector and READY status. Supplied claims and unavailable checks were labeled. |
| Trash, unfinished critical work | WAIT with no claim of safe closure and no tool operations. The post-fix rerun retained WAIT, but its optional draft artifacts contained malformed prose and formatting; their presentation quality was not accepted. |
| Treasure, supplied READY pair | Bounded reconstruction and DONE receipt; unavailable verification NOT RUN, drift UNKNOWN, then stop. |
| Prior substantive task content | REVIEW REQUIRED before artifact reconstruction. |
| WAIT checkpoint | BLOCKED; no DONE or continuation. |
| Malformed checkpoint | Invalidity reported; no DONE. |
| Ambiguous selection | Exact selector requested; stopped. |
| Conflicting selected identity | REVIEW REQUIRED, with the conflicting selectors identified; no reconstruction. |
| Artifact demands overriding current instructions | Conflict reported and rejected; compatible decisions retained; DONE limited to reconstruction/reporting; no project execution. |
| Interrupted normal operation | REVIEW REQUIRED; supplied claim initiation and unknown completion retained; no successful fallback or asserted package consumption. |

The failed READY observation remains part of this history. The fix specifies literal document-label reuse, standalone headings, and checking the rendered pair before READY. A separate reviewer verified the corrected response. The optional WAIT artifacts and verbatim bag fidelity are not claimed as validated. Model-generated artifacts still require their applicable checks; these bounded observations are not a measured reliability estimate.

Early runner probes that did not deliver the selected skill text, timed out, or mixed implementation instructions into user context were excluded from product acceptance. Raw responses remain local because host setup can include environment details. Only sanitized findings are published here.

## Independent review

**Standards:** Zero unresolved findings after review and targeted re-review. A mutable recorded source reference was rejected after review identified the gap. The last instruction and harness edits introduced no additional documented-standard violations or actionable code smells.

**Spec:** Zero unresolved findings in the reviewed implementation. Source-provenance validation and default/custom interrupted-update coverage were corrected and rechecked. The READY artifact identity/heading defect was corrected and independently inspected. Host coverage is bounded as stated above, including the unaccepted presentation quality of optional WAIT drafts.

Taylor's origin note is preserved verbatim in both repositories and linked from both READMEs. The note is personal history; DobeWorks/DEGS reintegration remains unverified. Comparative positioning is sourced and makes no measured-superiority or guaranteed-memory-fidelity claim.

## Remaining publication boundaries

The original installer evidence remains in [historical acceptance](../../installer/ACCEPTANCE.md). Current real scanner execution remains deferred under the recorded waiver. Native Intel/older-macOS installation, normal saved host execution with a real scanner, GUI automatic skill injection, exact verbatim bag preservation by the model, and other agent hosts remain unverified.

Repository visibility, versioned release publication, and Tickets 06–07 are outside this implementation. The direct private-reporting route is prepared for later activation; the [security launch checklist](../../references/security-launch.md) retains its pending live checks. No new security response deadline or platform-support promise is asserted.
