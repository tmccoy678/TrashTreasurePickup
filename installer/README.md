# Maintaining the installer

One checkout supplies both instruction-only skills. User instructions are in the project README and setup reference.

## Build and verify

Use a clean checkout with full history and commit every distributed input first. With Python 3.12 and Git available, run from the repository root:

```bash
pickup_source_commit=$(git rev-parse HEAD)
python3 installer/bundle.py --source-commit "$pickup_source_commit" --output dist/pickup-install.command
python3 installer/bundle.py --source-commit "$pickup_source_commit" --output dist/pickup-install.command --verify
shasum -a 256 dist/pickup-install.command
```

The default source is this repository. `--source-root` selects another checkout. `--source-commit` is the full commit containing every distributed input. The generated installer can be committed afterward.

## What validation proves

The manifest records one source revision, explicit source paths, and SHA-256 hashes. The payload contains the two skill files, their small metadata files, shared license and security files, and the Bash installer. Every input must be a regular file.

`--verify` reads the installer as data. It checks the exact file set, bytes, source mapping, hashes, Git source bytes, and generated wrapper without executing the candidate.

## Tests and evidence

Run `python3 scripts/check_publication.py` and `python3 -m unittest discover -s tests -v`. The tests exercise the bundle and installer in disposable directories, including a real bundled install.

`--yes` accepts the default destination but preserves an existing pair. `--skills-dir` selects another destination. Interactive replacement retains a backup.
