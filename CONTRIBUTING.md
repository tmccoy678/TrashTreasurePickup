# Contributing

Keep Pickup easy to understand and easy to remove. A normal user should need only two skill folders and no managed runtime.

Clone the public repository:

```bash
git clone https://github.com/tmccoy678/TrashTreasurePickup.git
cd TrashTreasurePickup
```

Open an issue describing the user-visible problem before a behavioral change. Preserve manual-only invocation, concise handoffs, honest `UNKNOWN` values, existing user files, and the rule that Pickup does not authorize the next phase.

Run from the repository root:

```bash
python3 scripts/check_publication.py
python3 -m unittest discover -s tests -v
```

Build the downloadable installer only from a clean committed source:

```bash
pickup_source_commit=$(git rev-parse HEAD)
python3 installer/bundle.py --source-commit "$pickup_source_commit" --output dist/pickup-install.command
python3 installer/bundle.py --source-commit "$pickup_source_commit" --output dist/pickup-install.command --verify
```

The declared source commit must remain reachable from the public default branch.
Do not squash-merge a change that pins the installer to a feature-branch commit:
the squash would replace that identity and leave a fresh clone unable to verify
the bundle. For a change to bundled skill files or `installer/install.sh`, first
merge the reviewed sources, then use a small follow-up pull request that rebuilds
the installer against the new `main` commit. Documentation-only changes do not
require a new bundle when the bundled inputs are unchanged.

The installer must remain self-contained, back up accepted replacements, avoid unrelated skill folders, and install the exact reviewed skill bytes.
