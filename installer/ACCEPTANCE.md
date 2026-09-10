# Installer acceptance — 2026-09-10

Implemented for draft2 tickets [#2](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/2) and [#3](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/3). Family trial instructions were removed at the user's request. This is implementation evidence, not authorization for public publication.

## Checks

| Check | Observed result |
| --- | --- |
| Full regression suite | **248 passed**, 106.473 seconds, using managed Python 3.12.14. |
| Installer boundary | Seven tests cover default installation, custom location/configuration precedence, replacement declined/accepted, checksum failure, failed download and retry, the single command bundle, and closed terminal output after activation. External downloads use fixture tools in these tests. |
| Real tool installation | Passed on Apple Silicon, macOS 26.6.2, into disposable user homes with spaces in their paths. The command bundle ran with an empty inherited environment and standard macOS tool paths. Python and Git were supplied by the locked environment. This was an isolated installation on the existing host, not a new physical Mac. |
| Actual managed versions | Python **3.12.14**, Git **2.55.0**, Gitleaks **8.30.1**; Pixi bootstrap pinned to **0.80.0**. Git initialized a temporary repository successfully. |
| Installed operational helper | A complete publish, claim, gate progression, and Markdown receipt check passed using the installed helper and managed Python. Configured-workspace behavior also passed. These checks used the existing test scanner. |
| Scanner availability | Real Gitleaks version and supported command interface ran. **Real secret scanning remains deferred under the user's waiver**, not passed. |
| Syntax and package integrity | Shell parsing and Python compilation passed. Embedded payload hashes and every bundled source-file hash matched the source checkouts. The bundle excludes generated machine configuration, Git history, audit data, and local planning documents. |
| Other Macs | Intel assets and package resolution are pinned. **Native Intel and older macOS installation execution remain unverified**. macOS 12 is the configured runtime floor, not evidence of a test on that version. |

The real-download bundle installation exercised source at `081e9e3`. The subsequent small cleanup correction at `88afabd` was verified by the new failing-then-passing installer regression and the full suite. The final bundle embeds Trash source `0458597` and Treasure source `88afabd`; both source trees were clean when it was built. Its file SHA-256 is `86bc9b960a895fc8c383da271b46c93f21c90d96f46eebc621b398419517ae7b`.

## Standards

No hard documented-standard violations or actionable baseline smells were found. The review identified one P2 correctness issue: a failure while printing the final result could delete the runtime after the new skills were installed. The public installer test reproduced it. Cleanup now retains a runtime as soon as an installed skill can reference it; successful rollback permits cleanup. The reviewer confirmed the issue resolved in `88afabd` with no residual actionable finding.

## Spec

Zero actionable findings against the parent specification and the two tickets, including the user's removal of family trial instructions. The existing operational Python helpers are unchanged. The access behavior, verification semantics, manual invocation, and completion-without-authorization contract remain intact. Unperformed native-platform and real-scanner checks remain explicitly unverified.

Final review: Standards — one correctness finding resolved, zero outstanding; Spec — zero actionable findings.
