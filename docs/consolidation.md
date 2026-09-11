# Pickup consolidation and retained work

The project is one home for `trashpickup` and `treasurepickup`. The installed skill names, shared helper commands, default/custom destinations, and audit records retain their existing meaning. One checkout supplies one installer. See [source/build documentation](../installer/README.md) and [one-checkout acceptance](acceptance/consolidation-01.md).

## Source history

Treasure's repository is the surviving project. Trash history through `bb44f27c5ab367c3ef0148457ad61977f99690d8` was imported without squashing into `skills/trashpickup/`; the original source commits remain in the Git ancestry. Treasure's pre-consolidation revision is `cb82e326861ca68a1020fdd48dbc93bc21c36e57`. Its latest owner-edited author note is preserved byte-for-byte. Only the visibly incomplete comparison row is repaired; previously removed editorial passages remain removed.

Git source import does not transfer GitHub discussions. [Trash's original PR 1](https://github.com/tmccoy678/draft2staged-trashpickup/pull/1) and the original repository remain the history of that review. The surviving project's issues and PRs remain attached to its repository identity.

## Pending illustrations

The accessible illustration and engineering-reference work remains a **draft**, outside the installed main-branch payload until accepted. Original reviews:

- [Treasure draft PR 10](https://github.com/tmccoy678/draft2staged-treasurepickup/pull/10), source `4dbf7ce217a907919c7aad90f4bdb9617146ece4`.
- [Trash draft PR 2](https://github.com/tmccoy678/draft2staged-trashpickup/pull/2), source `faeb9afd8857046f5022e25a826e48e1f5f61c68`.

Their eleven added files are identical across the two drafts: `.gitattributes`, the figure README, provenance JSON, HTML and PDF overview, HTML and PDF foundation references, citation notes, Crossref metadata, verification report, and verified-entry JSON. The four-line README addition from each draft links the figure and its accessible HTML alternative; those destinations remain part of the retained draft. Latest author-note and comparison edits are separate owner changes and are not overwritten with the older Trash copy.

[Successor draft PR 16](https://github.com/tmccoy678/draft2staged-pickup/pull/16) carries these files into the consolidated layout with original bytes and provenance intact. Its PR links both original discussions. Review must still decide whether to accept the illustrations, validate the accessible editions and citations, and refresh the installer for any accepted shared-reference assets. Preserving the draft does not certify PDF/UA accessibility or accept its source claims.

## Canonical-name cutover

The canonical project is [draft2staged-pickup](https://github.com/tmccoy678/draft2staged-pickup). It retains Treasure's repository identity and GitHub issues/PRs. [Cutover evidence and recovery](acceptance/consolidation-03.md) records exact identities, redirect checks, the old Trash entrypoint, and credential retirement.

The root installer link is relative. Active support, contribution, skill-home, and tracker links use the canonical name. Historical evidence links retain their original identities. GitHub does not redirect references to repository-hosted actions; this project uses pinned official actions and exposes no repository-hosted action or reusable workflow. Keep the old Treasure name unused to preserve ordinary redirects.

Publication Tickets 06–07 must use the final single-repository revision and manifest. Public visibility, a versioned release, and private-reporting activation remain separate work.
