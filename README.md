**Trash Pickup and Treasure Pickup**

**"Summarize this entire conversation so that I can continue this work in another chat. No mistakes."
**
The early versions of these skills were built for myself, these are the "softened" versions of context-movement skills that I used to joke, "could have launched a rocket" with their checks and acceptance gates. 

I have tested the skills contained in this repository myself on my Mac computer with Codex agents only. 

I do not claim that these skills will be able to be used on your Windows 11 home system or something. My apologies for that, and I would be grateful for the skills to be returned to me if someone adapts and tests them on a computer running Windows or Linux. 

Thank you, 

Taylor 

The original implementations of these skills were created as a way for me to capture and transport accurate context from large context windows. Broadly, my goals were to eliminate drift, maintain audibility, and capture hallucinations honestly. Additionally, I wanted to stop needing to write: "summarize this conversation in detail, no mistakes" since it was not very reproducible and it placed no responsibility for accuracy on me nor the agent collecting the context and writing the summary. 

# Trash Pickup + Treasure Pickup

[![Pickup checks](https://github.com/tmccoy678/TrashTreasurePickup/actions/workflows/paired-checks.yml/badge.svg)](https://github.com/tmccoy678/TrashTreasurePickup/actions/workflows/paired-checks.yml)

Two small, manual Codex skills for carrying useful context into a fresh task.

- **Trash Pickup** closes a completed phase into a readable Markdown handoff and a small JSON checkpoint.
- **Treasure Pickup** opens that pair, checks only the live facts that matter, and reconstructs the next working context.

The default pair follows the project's original simple design. It does not require a registry, receipt service, lease, package state machine, secret scanner, managed Python, or managed Git.

## Install

Download [pickup-install.command](https://github.com/tmccoy678/TrashTreasurePickup/raw/refs/heads/main/dist/pickup-install.command) and run:

```bash
bash "$HOME/Downloads/pickup-install.command"
```

The installer contains both skills and works without another network download. It installs to `~/.agents/skills` by default, preserves existing copies when replacement is declined, and keeps a backup when replacement is accepted. No GitHub sign-in is required.

The bundle carries a manifest of the exact reviewed source bytes and a source
commit reachable from public history. Its wrapper verifies the embedded payload's
SHA-256 before extraction; repository checks independently verify the manifest
against the committed sources.

To install from a cloned checkout instead:

```bash
bash installer/install.sh "$PWD"
```

Use `--skills-dir PATH` for another compatible skills directory.

## Use

At a natural stopping point, explicitly select `$trashpickup`. When file access is available, it writes:

```text
<workspace>/.pickup/current-context.md
<workspace>/.pickup/context-checkpoint.json
```

Open a fresh task in that workspace and explicitly select `$treasurepickup`. You may also paste or attach the two files. Treasure reconstructs the context and reports any material conflict it actually observes.

See the [first-use walkthrough](references/first-use.md) and [setup guide](references/macos-setup.md).

## Scope

Pickup carries context; it does not grant permissions or prove that every statement in a handoff is true. Agents should label unsupported details and inspect current state when it can change the next action.

Git history retains the former experimental multi-pickup registry and its acceptance records. The current tree stays focused on the small, single-handoff pair.

## Independent review

[Nova (Muse Spark, Meta) — code review, 2026-10-05](docs/reviews/2026-10-05-nova.md): source-code-only review of the installer builder. 11/11 tests passing; the commit-pinning and pre-extraction checksum chain verified by reading. No defects found; one minor note on implicit path anchoring in `sources.py`.

## Help and license

[Update or remove Pickup](references/lifecycle.md) · [Support](references/support.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

Pickup is available under the [MIT License](LICENSE).
