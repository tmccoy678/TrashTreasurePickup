# Pickup Registry Protocol

Use this protocol automatically when the explicit skill invocation has sufficient authorized access for the normal file and helper operations. It governs every actual claim, receipt transition, and Trash package publication; saving and runtime checks remain required without another opt-in. With limited or no access, follow the invoked skill's supplied-content flow instead: unavailable helper reads and registry operations are not prerequisites for reconstruction and a conversation receipt. The registry, package, claim, and receipt identities are durable; window, task, session, thread, process, and title identities are not.

Unavailable checks remain `UNKNOWN` or `NOT RUN`. A failed check, corrupt registry, or interrupted transaction cannot be relabeled as limited access to claim success. Report the last confirmed and incomplete operations if access is lost; do not invent claim closure or consumption. Implementation regression checks remain required, separately from the runtime gates below.

## Locate the installed helper

Before using any command below, complete [macOS setup](macos-setup.md). Use the selected `pickup_workspace`, `pickup_registry_root`, and `treasurepickup_skill` paths from that setup. `pickup_registry` must point to `scripts/pickup_registry.py` inside that exact installed Treasure Pickup directory. Trash Pickup calls this shared helper; it does not contain a second registry implementation.

The command examples below are invocation templates. Replace every placeholder with verified values and follow the manual skill's gates before running an operation.

## Storage and identity

The default authoritative root is:

```text
$pickup_workspace/treasurepickup/pickups
```

Each package selector is `<track-id>@<checkpoint-id>`. A track is one stable line of work. A checkpoint is one immutable handoff/checkpoint revision. A receipt is one claim/opening attempt.

New receipt IDs combine their UTC creation second with 128 random bits. Allocation occurs under the registry lock and retries until the candidate is absent from both the global receipt index and every track receipt namespace. Historical receipt IDs with the former 32-bit suffix remain readable.

The registry owns these mutable views:

- `index.json`;
- `tracks/<track-id>/track.json`;
- `tracks/<track-id>/claim.json`; and
- `$pickup_workspace/treasurepickup/context-resume.json`, which is compatibility telemetry only.

Package files, quarantine events, and versioned receipt files are immutable. Do not hand-edit any registry file.

## Inspect and select

List packages without claiming them:

```bash
PYTHONDONTWRITEBYTECODE=1 "$pickup_python" \
  "$pickup_registry" inspect \
  --registry-root "$pickup_registry_root"
```

Inspect one exact selector with `--selector <track-id>@<checkpoint-id>`.

Each summary includes `state` and the sanitized boolean `claim_active`. `CLAIMED` and `OPENING` are active states. `CONSUMED` means a successful opening run is complete and the package cannot be claimed again.

When the user supplies a selector, preserve it exactly. When no selector is supplied, let `claim` select only if exactly one package is `AVAILABLE`. `PICKUP_SELECTION_REQUIRED`, `NO_AVAILABLE_PICKUP`, `PICKUP_SUPERSEDED`, `ALREADY_CLAIMED`, `RESOURCE_SCOPE_CONFLICT`, and `ORPHANED_CLAIM_REVIEW_REQUIRED` are terminal stops for the invocation. Never guess, choose the newest package, or take over a claim.

## Publish a closed context

Trash Pickup publishes only after its handoff/checkpoint pair passes its own closure and artifact validation:

Choose a stable `track_id` of 1-63 lowercase kebab-case characters. Empty segments and consecutive hyphens are invalid; the bound leaves room for protocol suffixes within a filesystem path component.

```bash
PYTHONDONTWRITEBYTECODE=1 "$pickup_python" \
  "$pickup_registry" publish \
  --registry-root "$pickup_registry_root" \
  --track-id <stable-kebab-case-track-id> \
  --resource-scope <absolute-owned-resource-path> \
  --handoff <validated-current-handoff> \
  --checkpoint <validated-checkpoint>
```

Repeat `--resource-scope` for each independently owned path. Use the narrowest complete write scope for the next phase. Scope identity resolves physical path aliases, collapses multiple leading separators, and on macOS compares Unicode-normalized paths without case distinctions. Therefore `/var` and `/private/var`, APFS firmlink aliases such as `/Users` and `/System/Volumes/Data/Users`, symlink aliases, case aliases, and `//` cannot evade root rejection or an ancestor conflict; the macOS Data volume root itself is also too broad. The checkpoint's optional `pickup.track_id` and `pickup.resource_scopes`, when present, must exactly match these canonical values.

Publishing captures each source once, then parses, hashes, scans, and copies those captured bytes into a new immutable package. It rechecks the live sources before committing the package and installs the final directory without replacing any object that appeared during scanning. Each manifest links to the preceding checkpoint and package-manifest SHA-256, forming one immutable publication chain. Its initial candidate scan includes deterministic quarantine-event templates and seals their SHA-256 values in the manifest. A later package on the same unclaimed track supersedes older revisions. Exact repeat publication rescans the stored package and rehashes both sources immediately before reporting success. A failed candidate scan removes only its identity-bound private scaffolding so the exact publication can be retried safely after any independently created destination object is removed. Foreign data that appears in staging is preserved and produces `TRANSACTION_ROLLBACK_FAILED`, never recursive deletion. A failed stored-package secret scan appends the matching prevalidated immutable event at `tracks/<track-id>/quarantines/<checkpoint-id>.json`; the package entry hash-anchors that evidence and derives `NEEDS_REVIEW` from it. Artifact drift discovered anywhere during a mutation, including drift first exposed by a terminal receipt scan, joins one iterative closure pass and is quarantined before scanner-dependent receipt telemetry. A scanner failure therefore cannot return the package to `AVAILABLE`. A later clean scan or restored artifact does not silently clear a quarantine, and current artifact corruption still fails closed rather than being summarized from an unverified manifest. Publication while that track has an active claim fails before creating the package.

## Claim a package

Start a new opening run before reading package contents:

```bash
PYTHONDONTWRITEBYTECODE=1 "$pickup_python" \
  "$pickup_registry" claim \
  --registry-root "$pickup_registry_root" \
  [--selector <track-id>@<checkpoint-id>] \
  --workspace "$pickup_workspace" \
  --fresh-task <YES|NO|UNKNOWN> \
  --freshness-basis <FIRST_SUBSTANTIVE_USER_TURN|PRIOR_TASK_CONTENT|UNVERIFIED> \
  --invocation-mode <MANUAL_SKILL_SELECTOR|SLASH_COMMAND> \
  --model <current-model-or-UNKNOWN> \
  --effort <current-effort-or-UNKNOWN> \
  --skill-file "$treasurepickup_skill/SKILL.md"
```

Registry claims require `YES / FIRST_SUBSTANTIVE_USER_TURN`. Any other pair fails without consuming a package. Preserve from the JSON result:

- `pickup.track_id`;
- `pickup.checkpoint_id`;
- `pickup.selector`;
- `receipt_id`;
- `revision`;
- `receipt_sha256`; and
- the four artifact paths under `artifacts`: deployed skill, package manifest, handoff, and checkpoint.

Every mutation must use the latest returned revision and receipt hash. A stale or mismatched value fails without mutation.

## Advance one verified gate

After independently completing one gate, append its receipt revision:

```bash
PYTHONDONTWRITEBYTECODE=1 "$pickup_python" \
  "$pickup_registry" advance \
  --registry-root "$pickup_registry_root" \
  --track-id <exact-track-id> \
  --checkpoint-id <exact-checkpoint-id> \
  --receipt-id <exact-receipt-id> \
  --expected-revision <latest-revision> \
  --expected-receipt-sha256 <latest-receipt-sha256> \
  --gate <CANONICAL_PAIR_VERIFIED|LIVE_STATE_VERIFIED> \
  --evidence-file <sanitized-gate-evidence.json>
```

The evidence file must be a JSON object with this shape:

```json
{
  "schema_version": 1,
  "gate": "<the exact --gate value>",
  "status": "PASS",
  "observed_at": "<RFC3339 timestamp>",
  "checks": [
    {
      "name": "<sanitized check name>",
      "status": "PASS",
      "detail": "<optional sanitized result>"
    }
  ]
}
```

Use exactly the shown top-level fields and, for each check, exactly `name`, `status`, and optional string `detail`; extra fields fail closed. Use at least one independently completed check. The timestamp must use an uppercase `T` separator and either `Z` or an explicit numeric UTC offset. Arbitrary-length nonempty fractional seconds and RFC 3339 `:60` leap-second syntax are accepted; the calendar date itself must be valid, and the helper does not consult an external leap-second table. Do not include session, thread, task, process, window, credential, or private-identifier fields. Forbidden-key detection is insensitive to case, camelCase, spaces, hyphens, and other separators. The helper validates and embeds the evidence object in the new immutable receipt; it does not persist the evidence-file path.

Evidence check names are at most 100 printable characters and details are at most 500. Invocation model and effort labels are at most 80 and 40 printable characters, respectively. Current/next phase labels are at most 200 printable characters. These are persistence bounds, not truncation rules: overlong or nonprintable input fails closed.

Advance the gates in exactly that order. Missing, malformed, mismatched, non-passing, or forbidden evidence fails without changing the run. `TELEMETRY_VALIDATED` is owned by terminal completion and cannot be advanced directly. Use the new revision and hash returned by every successful call.

## Complete a run

Finalize the exact run with the same status/drift contract as the prior receipt helper:

```bash
PYTHONDONTWRITEBYTECODE=1 "$pickup_python" \
  "$pickup_registry" complete \
  --registry-root "$pickup_registry_root" \
  --track-id <exact-track-id> \
  --checkpoint-id <exact-checkpoint-id> \
  --receipt-id <exact-receipt-id> \
  --expected-revision <latest-revision> \
  --expected-receipt-sha256 <latest-receipt-sha256> \
  --status <READY|BLOCKED|REVIEW_REQUIRED|STOP|ABORTED> \
  --drift <NONE|EXPECTED|BENIGN|MATERIAL|SECURITY|UNKNOWN> \
  [verified result fields]
```

For `READY`, supply `--current-phase` and `--next-phase`. `READY` requires `LIVE_STATE_VERIFIED` and drift `NONE`, `EXPECTED`, or `BENIGN`.

For another terminal result, add a sanitized `--reason-code` and `--reason`. The code is 1-64 uppercase ASCII letters, digits, or underscores and starts with a letter. The reason is trimmed, printable text of at most 500 characters; the receipt secret scan still applies. Use `BLOCKED / UNKNOWN`, `REVIEW_REQUIRED / MATERIAL|UNKNOWN`, `STOP / SECURITY`, or `ABORTED / UNKNOWN`. Artifact drift is terminalized automatically as `REVIEW_REQUIRED / MATERIAL`. If scanning fails or exposes additional package drift while closing an already-claimed artifact-drift run, the helper may append only a deterministic terminal derived from the preceding scanned receipt plus fixed drift constants. That receipt is labeled `validation.secret_scan: PREVALIDATED_DERIVED_TERMINAL`; this exception never accepts new user-supplied receipt content, and newly exposed drift still joins the same iterative closure pass.

Completion clears the active claim. A successful package becomes `CONSUMED`; any other result becomes `NEEDS_REVIEW`. No result authorizes phase work.

Each `COMPLETED` event also saves one user-facing Markdown receipt containing that terminal JSON's recorded checks. The helper returns `markdown_receipt_path`, located in `receipts/` beside the compatibility output, outside the internal registry namespace. It uses the same transaction and protected write mechanism; an unsuccessful Markdown save cannot report successful completion. The presentation adds only fixed text and the already validated JSON bytes, preserving the JSON's exact scan result, including any prevalidated-derived status. This Markdown is a presentation copy; the existing JSON history remains the registry evidence. Do not hand-edit either to claim different checks.

## Release an explicitly abandoned package

Only after the current user explicitly chooses to make an `ABORTED` package available again, use the exact terminal receipt coordinates:

```bash
PYTHONDONTWRITEBYTECODE=1 "$pickup_python" \
  "$pickup_registry" release \
  --registry-root "$pickup_registry_root" \
  --track-id <exact-track-id> \
  --checkpoint-id <exact-checkpoint-id> \
  --receipt-id <exact-receipt-id> \
  --expected-revision <latest-revision> \
  --expected-receipt-sha256 <latest-receipt-sha256>
```

Release appends an immutable `RELEASED` receipt revision. It never rewrites or resumes the abandoned run. `READY`, `BLOCKED`, `REVIEW_REQUIRED`, and `STOP` packages cannot be released by this command, and no package with immutable quarantine evidence can be released without a separately designed and explicitly authorized quarantine-resolution protocol.

## Safety contract

- Every new receipt is schema v4, SHA-256 linked, mode `0600`, and has immutable `scope.phase_authorized: false`.
- Persisted registry views, claims, package manifests, quarantine events, receipts, and embedded evidence are schema-closed. Boolean values are never accepted as integer schema versions or revisions.
- JSON parsing rejects duplicate object members and nonstandard numeric constants such as `NaN` or infinity. JSON serialization likewise rejects non-finite values.
- Registry directories are mode `0700`; registry files are mode `0600`; mode drift and artifact or receipt symlinks fail closed.
- Cross-window concurrency is a cooperative-writer protocol. Every Treasure Pickup or Trash Pickup process that writes the private registry must use this helper and hold its fenced registry-root lock. A same-UID process deliberately bypassing both the mode-`0700` boundary and advisory lock is outside this coordinator threat model.
- The held registry lock fences the root directory's identity and mode throughout an operation and around descendant descriptor acquisition. A root replacement or mode change cannot redirect an in-flight command into another directory.
- Before publication, claim, or a later run transition mutates authoritative registry state, every mutable output is schema-validated, serialized, and durably staged on its destination filesystem. Temporary directories and files, immutable links, exchanges, removals, and owned-directory cleanup are performed relative to verified parent-directory descriptors. Each existing mutable destination must retain the exact regular-file identity, mode, parent identity, and hash captured before scanning; creation, deletion, replacement, or symlink substitution fails without authoritative mutation. Immutable installs and transaction-created directories remain guarded by captured filesystem identity, mode, parent identity, and content through every mutable-view commit and cleanup boundary. An in-process commit or cleanup fault restores already committed mutable views and removes only immutable files and empty directories still proven to belong to that transaction; a foreign replacement or addition observed before cleanup is preserved and forces review. Final descriptor-relative pathname removal relies on the cooperative-writer boundary above; it is not represented as inode-conditional deletion against a malicious same-UID lock bypass.
- Each transaction inventories the whole registry namespace and permits only its declared additions. An unrelated path or foreign child that appears during commit is preserved and causes `TRANSACTION_ROLLBACK_FAILED`; it is never adopted or recursively removed.
- Secret scans are scoped to the candidate package or receipt and redact output.
- Claims never expire automatically. Inconsistent claim evidence requires review.
- Before every mutation, the helper inventories and reconciles the index, track, claim, package directories, quarantine events, receipt files, package state, and complete SHA-256-linked receipt history. Missing, unindexed, corrupt, or contradictory evidence fails closed.
- Each track points to the verified head of its immutable package-publication chain, and each package points to the head of its immutable cross-run receipt lifecycle chain plus any hash-anchored immutable quarantine event. Legal supersession and package state are derived from that evidence rather than trusted from matching mutable views.
- Every intact package manifest must agree with its indexed track, checkpoint, selector, artifact hashes, resource scopes, publication predecessor, strict timestamps, copied checkpoint identity and phase metadata, canonical handoff, and sealed quarantine templates before selection or resource-conflict decisions.
- Every recorded quarantine must have exactly one regular, mode-constrained immutable event whose identity, reason, packaged artifact hashes, prevalidated template hash, and event SHA-256 reconcile with the immutable manifest and both mutable views. An unindexed, missing, or changed quarantine event fails closed.
- Different active tracks are allowed only when their resource scopes do not overlap.
- Deployed-skill drift already present when a mutation begins closes each affected active run as `REVIEW_REQUIRED / MATERIAL` under a guard for the exact observed skill state. Any further skill change during that closure fails the transaction.
- Persisted workspace, skill, handoff, checkpoint, manifest, receipt, and compatibility-output paths must use their exact canonical absolute strings; a different lexical spelling of the same resolved path is rejected rather than normalized into authority.
- Schema-v2 and schema-v3 `context-resume.json` files remain historical telemetry. They are historical telemetry: any JSON object with integer `schema_version: 2` is legacy with freshness `UNKNOWN`, while schema v3 is checked against the receipt helper's contract, including missing, non-regular, and unsupported-checkpoint telemetry. Never reinterpret either form as a registry claim.
