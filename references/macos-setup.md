# macOS setup for the Pickup pair

## Install both skills

Download `pickup-install.command` from the draft2 Treasure repository's `dist` folder using your authorized GitHub access, or use the copy supplied by the maintainer. Run:

```bash
bash "$HOME/Downloads/pickup-install.command"
```

Accept the displayed locations, or choose your own. The installer supplies both skills, Python, Git, and Gitleaks. Internet access is needed for its tool downloads. No separate prerequisite installation or folder copying is needed. Existing skills require a replacement decision and are backed up when replacement is accepted. Existing audit data is preserved.

The default skill destination is `~/.agents/skills`; the default audit location is `~/Desktop/pickup_audit`. An existing user-created audit folder works identically. Setup does not invoke the skills, create pickup history, or grant the assistant file access.

The repositories remain private. The downloaded command file is the current installation route; a public download command depends on the owner's later publication. The installer targets Apple Silicon and Intel with a macOS 12 minimum. Actual verification is recorded in Treasure's installer acceptance document; other configurations remain unverified until tested.

## Resolve commands when access permits

These steps are for the operator following the invoked skill, not extra setup for the user. Use the installed Treasure Pickup directory supplied by the host or installer. Both skills use its shared helper.

```bash
# Use the selected installation directory if it differs from the default.
treasurepickup_skill="$HOME/.agents/skills/treasurepickup"
treasurepickup_skill=$(cd "$treasurepickup_skill" && pwd -P)
source "$treasurepickup_skill/scripts/pickup-env.sh"
pickup_workspace=$("$pickup_python" -c 'import os; from pathlib import Path; print(Path(os.environ["PICKUP_HOME"]).expanduser().resolve())')
pickup_registry="$treasurepickup_skill/scripts/pickup_registry.py"
pickup_registry_root="$pickup_workspace/treasurepickup/pickups"
```

The generated configuration supplies the tool paths and saved audit location to this command or shell only. It does not change shell startup files. An explicit Pickup location takes precedence over `PICKUP_HOME`, which takes precedence over the saved location. Helper command-line paths retain their existing precedence. Quote all paths. Use `"$pickup_python"` for Python and checkpoint JSON validation, `"$pickup_git"` for repository checks, and `"$pickup_gitleaks"` for scanning. Scanner discovery through the configured command PATH still works, and `--gitleaks-path` overrides it.

For direct helper use, the installed `scripts/pickup` command also accepts `init`, `registry`, `receipt`, `python`, `git`, `gitleaks`, or `config`. It loads the same configuration and forwards arguments. Use the original helper gates and verified values, as described in the [registry protocol](pickup-registry.md).

## Storage and access

With sufficient authorized access, run the idempotent first-use operation during the normal skill invocation, before any registry command:

```bash
"$treasurepickup_skill/scripts/pickup" init
```

The command creates the required Trash and Treasure folders and a private empty schema-v1 registry when they are absent. On later invocations it validates the existing registry and reports package and active-claim counts without changing registry objects. It creates no package, claim, receipt, quarantine, compatibility output, or phase authorization.

Existing grants activate this workflow without an additional opt-in. Limited or no access retains conversation delivery using supplied evidence and permitted reads; unavailable installation files or helpers are not required for that workflow. Saving is optional only in that fallback. Denied access does not require a broader-access request. An actual failed check or interrupted normal transaction remains a failure, not a successful fallback result.

Registry `claim --workspace` must match the registry's existing workspace binding: two parent directories above the registry. The default compatibility output is `treasurepickup/context-resume.json` beneath that location. Completion saves a Markdown receipt in its sibling `receipts` folder while retaining internal JSON records. Explicit output paths retain the helper's binding checks. `--skill-file` identifies the deployed Treasure `SKILL.md` beside the running helper; use its resolved absolute path.

Preserve the current project's source paths in the handoff. Temporary processing is limited to relevant artifacts and receipts, using permitted temporary storage and cleaning up owned temporary files. A missing or failing scanner in an otherwise authorized normal run blocks required writes.

The checkpoint shape remains in Trash's skill; registry validation remains in the existing helpers. Completing installation or a pickup never authorizes the next work phase.
