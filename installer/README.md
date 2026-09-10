# Maintaining the installer

The user downloads the single command file, runs it, and accepts or changes the locations. The installer supplies the pair and its tools. User instructions live in the repositories' README and macOS setup reference.

To rebuild from reviewed source checkouts, run from Treasure:

```bash
python3 installer/bundle.py --trash ../draft2staged-trashpickup --output dist/pickup-install.command
```

The builder embeds only the allowlisted skill/support files and installer inputs. Its source manifest records each input's SHA-256 plus source commits and whether their working trees were modified. Build from clean, reviewed checkouts and inspect this evidence before distributing a new bundle. Generated machine configuration, repository history, audit records, and local planning documents are excluded.

The asset list pins Pixi and Gitleaks URLs and hashes. The manifest and lockfile pin Python, Git, and supporting packages for both Mac architectures. Maintainers resolve and validate updates; installation uses the locked environment and never asks the user for dependency choices. See [third-party notices](THIRD_PARTY.md).

Use `--yes` for automated installations into a disposable home; it accepts defaults and refuses replacement. `--skills-dir` and `--audit-dir` allow explicit destinations. The interactive guide handles replacement with a retained backup. These are installer options, not new pickup modes.

Run `python3 -m unittest discover -s tests -v` for the existing suite and installer boundary tests. The focused installer tests use fixture downloads; [acceptance evidence](ACCEPTANCE.md) distinguishes those from real downloads and runtime checks. Installing or testing an artifact does not publish it publicly.
