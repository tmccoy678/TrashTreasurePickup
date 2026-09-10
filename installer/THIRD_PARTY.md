# Managed tools

Pickup uses Pixi 0.80.0 to install the exact Python and Git packages recorded in the lockfile, including their supporting libraries. Gitleaks 8.30.1 comes from its upstream macOS release. The installer verifies the bootstrap and scanner downloads against the SHA-256 values in the asset list; Pixi verifies and installs locked packages.

- [Pixi source and license](https://github.com/prefix-dev/pixi/tree/v0.80.0): BSD 3-Clause, included as `PIXI-LICENSE`.
- [Gitleaks source and license](https://github.com/gitleaks/gitleaks/tree/v8.30.1): MIT, included as `GITLEAKS-LICENSE` and in the downloaded archive.
- [Conda-forge Git recipe](https://github.com/conda-forge/git-feedstock) and [Python recipe](https://github.com/conda-forge/python-feedstock): package locations and integrity hashes are pinned in the lockfile. Their own licenses apply, including Git's GPL-2.0-only license and Python's license.

The installed runtime retains the downloaded package cache, including package license files under each package's `info/licenses` directory, and package records in the environment. The Pickup pair's MIT license does not replace third-party licenses. The installer bundle contains the pair and installation instructions; tools are downloaded directly from their distribution sources.

Runtime assets target Apple Silicon and Intel Macs on macOS 12 or newer. Treat this as the configured compatibility floor, not proof of testing on every supported Mac. Record actual installation evidence separately.
