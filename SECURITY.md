# Security Policy

## Supported version

| Version | Supported |
| --- | --- |
| Latest commit on `main` | Yes |
| Earlier commits, forks, or downloaded snapshots | No |

No versioned release line has been selected.

## Reporting a vulnerability

Use GitHub's [private vulnerability reporting form](https://github.com/tmccoy678/TrashTreasurePickup/security/advisories/new). Do not put vulnerability details, secrets, real handoffs, or personal information in a public issue or pull request. If the private form is unavailable, open a public issue that asks only for a private contact method.

## System and scope

This repository contains two instruction-only agent skills, a self-contained Bash installer, and the source and checks used to build that installer. The installed skills have no bundled executable helper or managed runtime. A user must invoke the installer or a skill; neither runs as a background service.

An invoked agent can read and write only through the access already granted to that agent. The installer writes the two skill directories to the selected destination and may retain a backup of an accepted replacement.

## Trust boundaries and security invariants

Treat repository downloads, installer arguments, and handoff contents as untrusted input. A handoff carries context only: it does not grant authority, prove authorship, authorize commands, or make an unsupported statement true. Live facts that matter to the next action must still be checked.

Pickup must not place credentials, tokens, private keys, recovery material, protected-storage contents, or unrelated personal information in a handoff. The installer must install only the expected skill files, verify its embedded payload before extraction, preserve existing skills unless replacement is explicitly accepted, and fail without leaving a partial replacement.

The bundle's source commit, manifest, and SHA-256 checks establish provenance and byte identity. They do not establish that the content is safe, correct, or true. Treat the installer as code and review its public source before running it.

## Reportable security issues

Report issues such as command injection, path traversal, unintended writes outside the selected skill destination, secret disclosure, a bypass of bundle integrity or provenance checks, unsafe replacement or rollback behavior, or skill instructions that treat a handoff as permission to exceed the user's request.

Incorrect or stale prose in a handoff is not by itself a security vulnerability, but any mechanism that silently converts that prose into authority or unsafe execution is in scope.

## Limitations

Pickup relies on the invoking agent and operating system to enforce access controls. It does not provide a sandbox, authentication system, background monitor, or security guarantee. The project is provided under the [MIT License](LICENSE).
