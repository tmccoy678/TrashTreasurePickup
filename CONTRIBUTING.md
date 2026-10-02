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

The installer must remain self-contained, back up accepted replacements, avoid unrelated skill folders, and install the exact reviewed skill bytes.
