# Treasure Pickup

Read the selected handoff/checkpoint, reconstruct the next phase, and return a receipt of performed and unavailable checks.

Use `$treasurepickup` explicitly in the first substantive message of a fresh task. Read the receipt, then decide separately whether to begin subsequent work.

Install both skills through the [Pickup project](https://github.com/tmccoy678/draft2staged-pickup). The installed names remain `trashpickup` and `treasurepickup`; both use Treasure’s shared tools.

[First use](references/first-use.md) · [Setup](references/macos-setup.md) · [Update and recovery](references/lifecycle.md) · [Support](references/support.md)

Checks depend on available access. Unavailable checks remain `UNKNOWN` or `NOT RUN`; actual failures keep their result. Model output requires inspection. Completion does not authorize subsequent work.

[Operational instructions](SKILL.md) · [Security](SECURITY.md) · [MIT License](LICENSE)
