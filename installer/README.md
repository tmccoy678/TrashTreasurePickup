# Maintaining the installer

One checkout supplies both skills and their tools. User instructions are in the project README and macOS setup reference.

## Build and verify

Use a clean checkout with full history and commit every distributed input first. With Python 3.12 and Git available, run from the repository root:

```bash
pickup_source_commit=$(git rev-parse HEAD)
python3 scripts/sync_skill_docs.py --check
python3 installer/bundle.py --source-commit "$pickup_source_commit" --output dist/pickup-install.command
python3 installer/bundle.py --source-commit "$pickup_source_commit" --output dist/pickup-install.command --verify
shasum -a 256 dist/pickup-install.command
```

The default source is this repository. `--source-root` selects a disposable or alternate checkout. `--source-commit` is a full immutable commit. Every distributed input must match that commit. The generated installer can be committed afterward; its source commit remains valid when the distributed inputs agree.

For checksum comparisons, build twice with the same source revision, runtime, and provenance inputs, writing both outputs outside the checkout. Working-tree observations are part of the manifest, so unrelated uncommitted changes can change the artifact checksum. Verification uses the candidate's recorded observations.

## What validation proves

The manifest format `pickup-single-repository-v1` records one source revision, explicit source paths for every distributed file, and SHA-256 hashes. Both portable packages receive shared policies and references from one maintained source. Required skill files, metadata, runtime helpers, policies, references, and third-party notices must be regular files; stale package copies fail clearly. All files in the shared reference collection are included, including non-Markdown assets.

`--verify` reads the installer as data. It checks the exact file set, distributed bytes, source mapping, manifest hashes, recorded Git source bytes, and generated wrapper. It does not run the installer or extract files to disk. Unversioned fixture builds carry null provenance and are not release evidence.

The legacy `--trash`, `--treasure`, `--installer`, and paired commit options remain an explicit separate mode for historical fixtures. For historical versioned verification, use the matching paired source revisions and historical builder. Legacy artifacts keep their original manifest and checksum; the consolidated verifier does not reinterpret them as the new format.

## Tests and evidence

Run focused bundle/installer tests while editing, then `python3 -m unittest discover -s tests -v`. The suite preserves the registry and receipt command-line regressions and checks the one-checkout build, provenance rejection, update/rollback/removal, and interrupted operations in disposable storage.

The retained previous installer fixture is hash-checked before its payload is used for upgrade tests. Only external download locations are replaced in the disposable extracted copy; old installer and skill code remain unchanged. This is fixture-scanner evidence. [Historical acceptance](ACCEPTANCE.md) and [publication acceptance](../docs/acceptance/publication-1-5.md) remain records of their original sources and limitations.

CI uses one checkout and no companion-repository secret. The dedicated companion credential is retired during the recorded repository cutover. Historical branches retain old workflow text and require modernization before manual reruns. Current real scanner execution remains deferred.

The installer retains its existing user interface: `--yes` accepts defaults and refuses replacement; `--skills-dir` and `--audit-dir` set explicit locations. Interactive replacement retains a backup. [Third-party notices](THIRD_PARTY.md) cover the pinned tools separately from the project's MIT license.
