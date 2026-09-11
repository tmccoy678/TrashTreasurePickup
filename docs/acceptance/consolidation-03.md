# Consolidation 03 — canonical repository cutover

Recorded 2026-09-11 for issue 14. Taylor approved consolidation tickets 01–03. The scope is a private repository consolidation, not public launch.

## Identities recorded before mutation

| Item | Identity |
| --- | --- |
| Surviving repository | GitHub ID `1364652040`, previously `tmccoy678/draft2staged-treasurepickup` |
| Canonical name | `tmccoy678/draft2staged-pickup` |
| Historical Trash repository | GitHub ID `1364651906`, `tmccoy678/draft2staged-trashpickup` |
| Imported Trash source | `bb44f27c5ab367c3ef0148457ad61977f99690d8` |
| Treasure owner baseline | `cb82e326861ca68a1020fdd48dbc93bc21c36e57` |
| Accepted main before rename | `73838b5e4708c410fe391e5fd75ac44df2cb782f` |
| Accepted documentation PR head | `598853727b2b1f16c91820c24d0e289f63593fec` |
| Pre-rename bundle source | `4eb8951b1daa4d79a24ba026a1a03df585280ad4` |
| Pre-rename bundle SHA-256 | `0ec873e55b08645200aa5a56618ae8cb66fa84bfee1eb284f98388efed0d9d52` |

Both repositories were private, without Pages or webhooks. The surviving project had no Actions variables. The new name returned authenticated 404 before rename. PR17 passed [CI 34651732447](https://github.com/tmccoy678/draft2staged-pickup/actions/runs/34651732447); its merge tree was identical to the reviewed head. A clean worktree verified the 39-file distribution before rename. Both source baselines were verified as ancestors. Earlier one-checkout merge [CI 34651668186](https://github.com/tmccoy678/draft2staged-pickup/actions/runs/34651668186) passed too.

## Observed cutover

Renaming the existing repository retained ID `1364652040`, issues, PRs, and PRIVATE visibility. Its description now describes the pair. The local origin remote uses the canonical Git URL. No replacement repository was created, and the previous Treasure name was not reused.

Authenticated API requests through the old Treasure repository, issue 11, and PR9 endpoints returned the canonical URLs with the same repository/resource identities. Old and new Git URLs both returned main `73838b5e4708c410fe391e5fd75ac44df2cb782f`. Downloads through both authenticated contents endpoints returned the same pre-rename installer digest above. A fresh canonical clone verified that bundle and passed all **10 installer lifecycle tests in 14.255 seconds**, using disposable default/custom destinations and fixture tool downloads. User audit records were not touched.

A signed-out in-app browser returned GitHub's private-repository 404 for the old issue URL. Authenticated browser navigation is therefore unverified; the successful observations above are authenticated API/Git checks, not a claim about every historical HTTP URL. Public anonymous downloads are not supported while the repository is private.

[GitHub's rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository) explains ordinary redirects and exceptions. Inspected active workflows use pinned official `actions/checkout` and `actions/setup-python`, contain no self-hosted action references or reusable-workflow calls, and require no companion checkout. No repository action manifest was present. Pages and webhooks remain absent; external consumers outside visible repository settings are unknown.

[Trash PR3](https://github.com/tmccoy678/draft2staged-trashpickup/pull/3) merged the prominent canonical pointer at `188f5c114e14a01fb132e671bbfedf70ea2b7640`. Only its README changed. The repository was then archived, retaining ID `1364651906`, PRIVATE visibility, source/history, issues, and reviews. No repository was deleted.

Pending illustrations remain in [canonical draft PR16](https://github.com/tmccoy678/draft2staged-pickup/pull/16). Both originals link there and are closed as superseded. The successor retains the original eleven added files and provenance. It is not an accepted main-branch product change.

## Companion credential retirement

The main workflow, completed consolidation branches, and retained successor draft use the single-checkout workflow. Historical `DW/accessible-figures` and `codex/publication-1-5` branches still contain the old workflow text, but their PRs are closed and they are not active automation. Modernize those branches before any manual rerun; historical workflow files do not justify retaining live credentials. No old workflow run was in progress at removal.

Removed only `PICKUP_COMPANION_SSH_KEY` from the canonical repository and matching read-only Trash deploy key ID `162936604` (title `Pickup paired checks (read-only)`). Post-removal lists are empty; no unrelated credential was removed. [Post-removal CI run 34652121124](https://github.com/tmccoy678/draft2staged-pickup/actions/runs/34652121124) passed on main after both credentials were removed. The final canonical-documentation checks are recorded in PR18.

## Recovery

Unarchive Trash through repository settings if maintenance is necessary. Preserve both repository IDs and source history. If the rename itself must be reversed and the old Treasure name remains free, rename this same surviving repository back, update remotes and active links through reviewed commits, and rebuild a matching installer. Do not reset shared history or create a replacement under the old name.

The retired private key is not recoverable. Reactivating historical paired CI would require a newly provisioned dedicated read-only key and secret after reviewing the intended access. Current one-checkout CI does not require it. Repository rollback does not restore or modify installed skills, audit records, registry state, or receipts; use the normal lifecycle/protocol for those operations.

## Final distribution

The canonical-documentation payload declares source `d4f9fb7e8d506de7a9738bda1d88807593b7c32c`, with artifact commit `2195a3dd4f0a4a99d95bd11032fd2f3af167458e`. Its format is `pickup-single-repository-v1`, with explicit source mappings and SHA-256 values for all 39 distributed files. Two clean builds with matching inputs/runtime are byte-identical. Installer SHA-256: `23bcc907df4336042df1c0e19eb10c27fe7348a45f191db693d013dd4a91f9bd`.

Operational SKILL files, the three shared runtime helpers, the latest owner author note, original MIT text, and third-party notices were byte-compared with the pre-consolidation sources and remain unchanged. Final branch and integration CI are linked from [PR18](https://github.com/tmccoy678/draft2staged-pickup/pull/18); this record does not predict their result.

## Standards

Zero findings. The independent review verified canonical/private repository identity, private archived Trash identity, successful post-removal CI, documentation checks, 39-file verification, and unchanged operational/license/author bytes.

## Spec

Zero findings. Independent live checks verified the rename, API redirects, README-only Trash change and archive, retained draft PR16, active URLs, empty dedicated-credential lists, source manifest/digest, and publication handoff. The final-head CI and merge remain completion evidence recorded on PR18. Historical acceptance records remain unchanged.

## Handoff to publication Tickets 06–07

Use the final canonical source commit, `pickup-single-repository-v1` manifest, and installer checksum recorded with this cutover. The old paired manifest/checksum is historical evidence only. Assemble a candidate from the final canonical checkout; decide separately whether to accept draft PR16 before building that candidate. Preserve its accessible alternatives/provenance if accepted.

Tickets 06–07 still own coordinated candidate assembly, discovery/launch review, supported release-line selection, and any separately authorized visibility/release/private-reporting activation. They were not published as standalone GitHub issues during the earlier planning; this tracked cutover record is their new source handoff. Existing unrelated parent issue 1 and completed publication issues 4–8 remain unchanged.

Model formatting and exact reproduction still require inspection. Real-scanner execution, normal saved-host end-to-end operation, native GUI discovery, Intel/older macOS, and other hosts remain unverified. No public release, visibility change, vulnerability-reporting activation, or runtime contract change occurred.
