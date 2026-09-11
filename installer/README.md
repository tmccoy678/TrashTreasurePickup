# Maintaining the installer

The user downloads the single command file, runs it, and accepts or changes the locations. The installer supplies the pair and its tools. User instructions live in the repositories' README and macOS setup reference.

Use compatible sibling checkouts as described in [Contributing](../CONTRIBUTING.md). After committing every distributed input, build from the Treasure checkout using both full source identities:

```bash
pickup_trash_commit=$(git -C ../draft2staged-trashpickup rev-parse HEAD)
pickup_treasure_commit=$(git rev-parse HEAD)
python3 installer/bundle.py --trash ../draft2staged-trashpickup \
  --trash-commit "$pickup_trash_commit" --treasure-commit "$pickup_treasure_commit" \
  --output dist/pickup-install.command
python3 installer/bundle.py --trash ../draft2staged-trashpickup \
  --trash-commit "$pickup_trash_commit" --treasure-commit "$pickup_treasure_commit" \
  --output dist/pickup-install.command --verify
shasum -a 256 dist/pickup-install.command
```

The builder requires both skills, their readmes/policies/licenses, host metadata, the named support references, shared runtime code, and installer inputs/notices. Other Markdown references and host YAML metadata are included. It rejects missing or symlinked required files. Its source manifest records every payload file's SHA-256 plus both source commits and working-tree modification observations. With explicit commits, every distributed byte must match those commits; unversioned fixture builds are not release evidence.

`--verify` reads the existing installer as data without running or extracting it to disk. It checks the exact payload file set, file bytes, manifest hashes, declared Git source bytes, and generated shell wrapper. A changed script fails even if its archive is intact. Generated machine configuration, repository history, audit records, and local planning documents are excluded.

Commit the generated bundle after source validation. Its recorded Treasure source may be the preceding commit: that is valid when all distributed files agree. Rebuild whenever a shipped input changes. Keep `.github/paired-source.json` aligned with the reviewed Trash commit so contributor and CI checkouts agree. Updating a bundle is preparation, not a versioned release.

The asset list pins Pixi and Gitleaks URLs and hashes. The manifest and lockfile pin Python, Git, and supporting packages for both Mac architectures. Maintainers resolve and validate updates; installation uses the locked environment and never asks the user for dependency choices. See [third-party notices](THIRD_PARTY.md).

Use `--yes` for automated installations into a disposable home; it accepts defaults and refuses replacement. `--skills-dir` and `--audit-dir` allow explicit destinations. The interactive guide handles replacement with a retained backup. These are installer options, not new pickup modes.

Run `python3 -m unittest discover -s tests -v` for the full suite. The bundle tests exercise rejection of missing required inputs, changed source bytes, incorrect source identity, and shell-wrapper changes. Installer tests use fixture downloads and include documented update/rollback/removal with retained user records. [Historical acceptance](ACCEPTANCE.md) distinguishes prior real downloads/runtime checks from fixture tests; [current acceptance](../docs/acceptance/publication-1-5.md) records this implementation.

Hosted paired checks use a full pinned companion commit and a dedicated read-only deploy key stored as the Treasure Actions secret `PICKUP_COMPANION_SSH_KEY` while Trash is private. The key cannot write Trash and is not persisted by checkout. Fork pull requests do not receive this secret: maintainers must review them before running private-companion checks from a trusted branch. Once both sources are public, the public checkout can run without that secret. No real scanner test is added to CI under the current waiver.
