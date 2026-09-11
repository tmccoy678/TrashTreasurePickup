# Why choose Pickup?

Pickup fits a transition where you want deliberate phase closure, an inspectable transfer record, and a report of what was checked before you decide to continue.

| Need | Useful approach | When Pickup adds value |
| --- | --- | --- |
| Make room in an active conversation | Native compaction | Separate handoff/checkpoint artifacts and a receipt. |
| Explore another direction with history intact | A conversation fork or branch | Bounded reconstruction into a fresh task. |
| Send a concise summary to another agent or person | A lightweight handoff | Closure assessment and, with sufficient access, package and live-state checks. |
| Pause/resume inside a planning framework | Its paired workflow | A focused close/check/reconstruct/report contract. |

These tools can coexist. Pairing is an established pattern. This comparison does not measure which tool retains more context or uses fewer tokens.

## Inspected alternatives

- [Matt Pocock's handoff](https://github.com/mattpocock/skills/blob/d28dfdc39beadc3142a33359b5cfa4765dcbd0bc/skills/productivity/handoff/SKILL.md) specifies a portable summary, artifact references, and redaction.
- GSD's [pause](https://github.com/gsd-build/get-shit-done/blob/bdcaab2c752d9a33a1a1ca9acf3a3c81fb991815/get-shit-done/workflows/pause-work.md) and [resume](https://github.com/gsd-build/get-shit-done/blob/bdcaab2c752d9a33a1a1ca9acf3a3c81fb991815/get-shit-done/workflows/resume-project.md) include structured handoffs, incomplete-work/Git-divergence checks, and state-writing and execution-routing behavior. The cited repository was archived when inspected September 10, 2026.
- [Codex context commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli) and [Claude Code sessions](https://code.claude.com/docs/en/sessions) describe native compaction and branching.

## Claim-to-evidence map

| Claim | Inspected source | Scope |
| --- | --- | --- |
| Capture current state, decisions, and next steps | [Trash handoff structure][trash] | Selected relevant information, not guaranteed lossless memory. |
| Assess closure and return WAIT | [Trash boundary rules][trash] | Available evidence; unavailable observations remain explicit. |
| Check identity, hashes, and relevant live-state drift | [Treasure verification][treasure] and [registry protocol](pickup-registry.md) | Normal authorized workflow. A hash establishes consistency, not authorship or truth. |
| Return a receipt and stop before project work | [Treasure completion rules][treasure] | Skill instructions, not an OS-enforced guarantee. |
| Deliver through conversation with restricted access | [Trash][trash] and [Treasure][treasure] access rules | UNKNOWN/NOT RUN stays visible; actual failures retain their result. |
| Coordinate packages and retain receipt history | [Registry protocol](pickup-registry.md) | Its documented cooperative-writer threat model, not a universal security/concurrency guarantee. |

Sources pin the designs inspected September 10, 2026. Live product documentation can change. No comparative runtime, recall, performance, or security benchmark was conducted. Current skill instructions control their operation. The [author's note](author-note.md) is personal experience, not comparative test evidence.

[trash]: https://github.com/tmccoy678/draft2staged-trashpickup/blob/04585979f8ba5c70c27faf5eda953a1480a1d81d/SKILL.md
[treasure]: https://github.com/tmccoy678/draft2staged-treasurepickup/blob/f4249639498f78ace2ca6f19e37a28ea3c1cc20d/SKILL.md
