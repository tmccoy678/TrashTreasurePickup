# Trash Pickup

Close a finished phase and produce a handoff, checkpoint, and separate trash bag.

Use `$trashpickup` explicitly after finishing a work phase. Unfinished critical work returns `WAIT`.

Install both skills through the [Pickup project](https://github.com/tmccoy678/draft2staged-pickup). The installed names remain `trashpickup` and `treasurepickup`; both use Treasure’s shared tools.

[First use](references/first-use.md) · [Setup](references/macos-setup.md) · [Update and recovery](references/lifecycle.md) · [Support](references/support.md)

Checks depend on available access. Unavailable checks remain `UNKNOWN` or `NOT RUN`; actual failures keep their result. Model output requires inspection. Completion does not authorize subsequent work.

[Operational instructions](SKILL.md) · [Security](SECURITY.md) · [MIT License](LICENSE)
