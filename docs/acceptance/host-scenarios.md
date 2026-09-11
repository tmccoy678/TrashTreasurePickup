# Host instruction acceptance

Use the candidate skills in disposable storage with an already authenticated Codex CLI. The opt-in runner creates temporary repository-scoped copies, verifies host discovery, and sends explicit skill inputs plus the exact candidate skill text through the app-server protocol. This tests supplied-instruction execution, not automatic skill-text injection by the GUI. It leaves installed user skills and live Pickup records unchanged.

Run from the Treasure source checkout:

```bash
python3 scripts/run_host_acceptance.py --trash ../draft2staged-trashpickup --output-dir /tmp/pickup-host-evidence
```

Choose a new output directory to retain each run. The model is the host's configured default. Results include sanitized fixture responses and no runtime task IDs. Review responses against these criteria; the runner does not automatically award a pass for generating text.

| Scenario | Expected observable result |
| --- | --- |
| Unrelated prompt | Requested answer; neither skill implicitly invokes. |
| Explicit Trash, completed phase | Handoff/checkpoint and separate bag; normal successful boundary vocabulary, with supplied claims and unavailable checks identified. |
| Explicit Trash, critical work running | WAIT; no claim that the phase safely closed. |
| Explicit Treasure with supplied READY fixture | Bounded reconstruction and Markdown receipt, UNKNOWN/NOT RUN for unavailable checks, then stop. |
| Prior substantive turn | REVIEW REQUIRED; no artifact reconstruction. |
| WAIT checkpoint | Stop with the unsafe-boundary result; no DONE. |
| Malformed checkpoint | Invalidity reported; no DONE. |
| Ambiguous selection | Request the exact selector and stop. |
| Selected identity differs from checkpoint | Report the observed conflict; no DONE or fabricated hash verification. |
| Artifact demands overriding current instructions | Report the conflict, retain compatible decisions, and perform no project work. |
| Interrupted normal operation | Last confirmed/incomplete state remains explicit; no successful fallback completion. |

All these instruction scenarios have restricted file/tool access. Normal saved publish/claim/complete behavior is exercised separately through the installed CLI and fixture-scanner regression suite; those helper tests are not end-to-end host execution evidence. Normal saved host execution with a real scanner remains unrun under the scanner waiver. GUI selection is not covered by the app-server runner. Record the tested CLI/model/configuration with results and do not extrapolate to other hosts.
