# Trash Pickup

**Start the next session with a handoff you can inspect.**

Carry the decisions that matter into your next AI session. Trash Pickup captures the current state, unresolved issues, and next steps in a readable handoff and structured checkpoint. It assesses whether the phase can close and returns `WAIT` when important work is still unfinished.

Its companion, [Treasure Pickup](https://github.com/tmccoy678/draft2staged-treasurepickup), checks the supplied artifacts in a fresh task and reports what was verified. “Trash” means stale context; your project files stay in place.

## Install the pair

The supported installer supplies **both skills and their tools**. Download [pickup-install.command](https://github.com/tmccoy678/draft2staged-treasurepickup/blob/main/dist/pickup-install.command) using your authorized GitHub access, then run:

```bash
bash "$HOME/Downloads/pickup-install.command"
```

Accept the defaults or choose your locations. Internet access is required; separate Python, Git, Gitleaks, or jq setup is unnecessary. This is a development snapshot, not a versioned release. Contributors testing this branch must build its matching source pair using the maintainer instructions; the main-branch download retains its own source identity.

**Tested scope:** the existing installer was exercised on Apple Silicon with macOS 26.6.2. Native Intel, older macOS, and other agent hosts remain unverified; macOS 12 is a configured floor, not a tested-support claim. See [macOS setup](references/macos-setup.md) for paths, replacement backups, and access behavior.

## First use

1. Explicitly select **trashpickup** after finishing a work phase. It produces a Markdown handoff and JSON checkpoint, or `WAIT` if important work is unfinished.
2. In the **first substantive message of a fresh task**, explicitly select **treasurepickup** and supply the handoff/checkpoint and any confirmed package selector.
3. Read the reconstructed context and receipt, then decide whether to begin the next phase.

In Codex, type `$trashpickup` or `$treasurepickup` and select the named skill. The [complete first-use example](references/first-use.md) includes sample inputs, a WAIT case, and a restricted-access receipt.

## Why choose Pickup?

- **Close at a clear boundary.** Keep decisions, unresolved issues, and the next phase in a record you can inspect.
- **Check what carried forward.** With the required access, the saved workflow checks package identity and hashes, then relevant live state for changes affecting the next phase.
- **See the limits.** With restricted access, conversation delivery reports unavailable checks as `UNKNOWN` or `NOT RUN`. An actual failure still requires resolution.
- **Keep the next step yours.** Treasure reconstructs and reports, then stops. Completion does not authorize subsequent work.

Hashes establish consistency with a recorded baseline; they do not prove authorship or the truth of a handoff. Compaction, branches, and lightweight summaries remain useful for their own jobs. See [the short comparison and evidence map](references/comparison.md).

## From the author

Read [A note from Taylor](references/author-note.md) about the project's origins, the context problems that motivated it, and the invitation to improve its structure.

## Help and license

[Setup and access](references/macos-setup.md) · [Update, recovery, and removal](references/lifecycle.md) · [Support](references/support.md) · [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md)

The project uses the [MIT License](LICENSE). Bundled tools have their [own notices](https://github.com/tmccoy678/draft2staged-treasurepickup/blob/main/installer/THIRD_PARTY.md).
