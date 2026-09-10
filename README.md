# Trash Pickup

Download [pickup-install.command](https://github.com/tmccoy678/draft2staged-treasurepickup/blob/main/dist/pickup-install.command) through your authorized GitHub access, then run:

```bash
bash "$HOME/Downloads/pickup-install.command"
```

Accept the setup defaults or choose your locations. This installs **both skills and their required tools**. Internet access is needed; no manual folder copying or separate Python, Git, Gitleaks, or jq setup is required. See [macOS setup](references/macos-setup.md) for details.

Trash Pickup is a manual-only skill for closing a work phase at a safe boundary. It reconstructs the available evidence into a Markdown handoff and checkpoint JSON, or returns `WAIT` when the phase cannot close safely. Supply that handoff and checkpoint with an explicit Treasure Pickup invocation in the next fresh context. A completed close supports transfer; readiness never authorizes later work.

With sufficient authorized access, required folders, handoff and archive saves, checkpoint storage, registry publication, and package verification happen automatically. Existing permissions need no additional storage or registry opt-in. Saving remains required in this normal workflow.

With limited or no access, the same content is delivered in the conversation using supplied evidence and permitted reads. No disk save, extra registry package, or inaccessible helper is required. Optional permitted saves and manual retention are the user's choice. Unavailable checks remain `UNKNOWN` or `NOT RUN`; actual failures still require resolution. The user controls artifact custody, and the tools remain responsible for accurately reporting their checks.

For normal storage, `PICKUP_HOME` defaults to `~/Desktop/pickup_audit`, with separate `trashpickup/` and `treasurepickup/` folders. An authorized user-created folder works identically. Explicit paths take precedence. Follow [macOS setup](references/macos-setup.md) and the bundled [Pickup Registry protocol](references/pickup-registry.md) when access permits their use. [SKILL.md](SKILL.md) defines both access cases and the unchanged optional retention of the separate trash bag.
