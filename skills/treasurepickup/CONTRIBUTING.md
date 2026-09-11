# Contributing to the Pickup pair

Start with a small issue describing the user outcome, evidence, and affected skill. Shared changes use [project issues](https://github.com/tmccoy678/draft2staged-treasurepickup/issues) and linked pull requests in this repository. Publication Tickets [01](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/4), [02](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/5), [03](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/6), [04](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/7), and [05](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/8) record the current work.

## One checkout

Clone this repository with its history. Both skills live in the skills collection; no companion checkout or submodule is required. Use Python 3.12 and macOS for the full suite. Contributors supply Python and Git; the user installer supplies its managed runtime. There is no separate static typechecker configuration.

From the repository root:

```bash
python3 scripts/sync_skill_docs.py --check
python3 scripts/check_publication.py
python3 -m unittest discover -s tests -p test_consolidated_bundle.py -v
python3 -m unittest discover -s tests -p test_installer.py -v
python3 -m unittest discover -s tests -v
```

Run focused tests while editing, then the full suite at the end. Reuse equivalent results until new changes invalidate them. Tests use the installer, bundle, and registry/receipt command lines. Download/scanner fixtures are not real scanner coverage; host instruction observations are recorded separately.

Shared policies and references are maintained at the repository root. Run `python3 scripts/sync_skill_docs.py` after editing them, and commit their regular-file package copies. Those copies let hosts read either skill directly. The builder maps both distributed copies back to the one declared source and rejects stale copies.

After committing every distributed input, use the maintainer build instructions in the repository's installer documentation. Source commits may precede the generated-artifact commit when all shipped bytes match. The maintained host scenario runner and acceptance records live in the repository's acceptance documentation.

## Review standards

Preserve explicit-only invocation, freshness checks, normal required authorized persistence, restricted-access reporting, exact status meanings, failure precedence, and the stop before next-phase work. The approved verifier and trash-bag renderer stay unchanged unless a later task explicitly changes their contract.

Keep human persuasion in the README and operational instructions in the skills/references. Put conditions beside their actions, preserve one authoritative status definition, and update duplicated references identically in both repositories. Source comparative claims and qualify access/host limits. Keep project MIT texts and all applicable third-party notices intact.

For behavior changes, add a failing test at an agreed public boundary, make it pass, and review the diff against both these standards and the issue's acceptance criteria. Prose needs relevant walkthroughs and link/consistency checks, not sentence snapshot tests. Preserve user data in disposable lifecycle tests.

Use small commits that reference the originating issue and include validation in the PR. Close an implementation issue only after its complete acceptance criteria and integration evidence are recorded. Report unrun checks and pending launch decisions explicitly. For security reports, use the [security policy](SECURITY.md).
