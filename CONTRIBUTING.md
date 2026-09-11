# Contributing to the Pickup pair

Start with a small issue describing the user outcome, evidence, and affected skill. Shared changes are tracked in [Treasure Pickup issues](https://github.com/tmccoy678/draft2staged-treasurepickup/issues); linked pull requests in both repositories keep the implementation trail together. Publication Tickets [01](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/4), [02](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/5), [03](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/6), [04](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/7), and [05](https://github.com/tmccoy678/draft2staged-treasurepickup/issues/8) record the current work.

## Compatible checkouts

Clone the two repositories as siblings named `draft2staged-trashpickup` and `draft2staged-treasurepickup`. Select the exact Treasure revision under review, then check out the full Trash commit recorded in Treasure's `.github/paired-source.json`. Access to both repositories is required while private. Recheck the pair after changing distributed inputs.

Use Python 3.12 and macOS for the full suite. The installer downloads its own user runtime; contributors running tests from source supply their test Python and Git. There is no separate static typechecker configuration.

From the Treasure source checkout:

```bash
python3 -m unittest discover -s tests -p test_bundle.py -v
python3 -m unittest discover -s tests -p test_installer.py -v
python3 scripts/check_publication.py --trash ../draft2staged-trashpickup
python3 -m unittest discover -s tests -v
```

Run focused tests while editing, then the full suite once at the end. Reuse equivalent results until a new change invalidates them. Test code behavior through the installer, bundle, and registry/receipt CLIs. External download/scanner fixtures are not real scanner coverage. Host scenarios are maintained separately in the source checkout's `docs/acceptance/host-scenarios.md`; helper tests cannot prove instruction-following.

For builds and strict verification, follow the Treasure source checkout's `installer/README.md`. Its pre-artifact source commit may differ from the commit adding the generated bundle when all distributed bytes match.

## Review standards

Preserve explicit-only invocation, freshness checks, normal required authorized persistence, restricted-access reporting, exact status meanings, failure precedence, and the stop before next-phase work. The approved verifier and trash-bag renderer stay unchanged unless a later task explicitly changes their contract.

Keep human persuasion in the README and operational instructions in the skills/references. Put conditions beside their actions, preserve one authoritative status definition, and update duplicated references identically in both repositories. Source comparative claims and qualify access/host limits. Keep project MIT texts and all applicable third-party notices intact.

For behavior changes, add a failing test at an agreed public boundary, make it pass, and review the diff against both these standards and the issue's acceptance criteria. Prose needs relevant walkthroughs and link/consistency checks, not sentence snapshot tests. Preserve user data in disposable lifecycle tests.

Use small commits that reference the originating issue and include validation in the PR. Keep cross-repository issues open until both sides are integrated; do not auto-close a shared issue after only one PR merges. Report unrun checks and pending launch decisions explicitly. For security reports, use the [security policy](SECURITY.md).

