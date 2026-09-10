# Standalone Pickup pair

Status: resolved

## Problem Statement

The public pair still requires an external system's policy metadata and execution lanes to close and reopen an ordinary handoff.

## Solution

Use the existing handoff identity, hashes, immutable packages, verification evidence, and receipts independently. Remove policy-specific code, setup, gates, fields, and instructions from both draft2 repositories. Preserve the first staged pair.

## User Stories

1. As a Mac user, I want to close and reopen a handoff without configuring another system.
2. As a user, I want the selected handoff and its bytes verified so that a different or changed artifact cannot pass unnoticed.
3. As a user, I want unavailable checks reported accurately so that missing evidence is never represented as verification.
4. As a user, I want receipts to contain only the checks and metadata the pair actually uses.
5. As a user, I want completion to grant no authorization for later work.
6. As the owner, I want the first staged pair preserved so that I can develop integrations separately.

## Implementation Decisions

- Reuse the shared registry, approved handoff verifier, receipt helper, and existing transaction protections.
- Keep package selection, safe-closure status, timestamps, canonical pairing, hashes, live-state evidence, secret scanning, and human authority boundaries.
- Remove the checkpoint version-2 requirement and all external policy metadata, execution-lane fields, and policy verification gates.
- Keep internal receipt statuses compatible with the existing command vocabulary; successful user-facing Treasure completion remains DONE.
- Use one configurable Pickup location and ordinary Trash/Treasure subdirectories; explicit paths retain precedence.
- Remove unused policy assets and commands. Add no opt-in mode, activation switch, or placeholder audit fields.

## Testing Decisions

- Use the existing command-line lifecycle tests as the main acceptance seam: publish, claim, verify, complete, inspect, and release.
- Update policy-specific fixtures and expectations while retaining tests for drift, missing evidence, strict metadata types, secret scans, concurrency, immutable history, and rollback.
- Test the approved verifier for exact identity, unchanged bytes, mismatch, unavailable inputs, and failure precedence.
- Exercise a fresh temporary installation with the real scanner and no external policy data.
- Compare final file hashes against the starting inventory to confirm all work stays inside the draft2 pair.

## Out of Scope

Publishing, changes to the first staged pair or other systems, automatic integration, Windows support, new access modes, and changes to the trash-bag renderer.

## Further Notes

The owner will adapt other systems to consume the standalone pair later. Existing audit records are not migrated or rewritten by this work.

## Comments

Implemented on 2026-09-09. Validation: all 238 tests passed. A fresh copied installation completed the fixture lifecycle without a checkpoint version or external policy data, using real Gitleaks scans for packages and receipts; the installed source scan also passed. File-hash comparison confirmed changes stayed inside draft2, with the first staged pair, other repositories, licenses, and Git metadata unchanged. The approved handoff verifier and trash-bag block were preserved.
