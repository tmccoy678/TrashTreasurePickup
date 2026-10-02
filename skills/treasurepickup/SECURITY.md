# Security Policy

## Supported version

Security fixes target the latest commit on `main`. No versioned release line has been selected.

## Reporting a vulnerability

Keep vulnerability details and secrets out of public issues and pull requests. Contact [@tmccoy678](https://github.com/tmccoy678) through an established private channel. If none exists, open an issue that asks only for a private contact method.

## Security boundaries

The installed pair is instruction-only and has no bundled executable helper or managed runtime. A user-invoked agent may read and write the handoff files allowed by that agent's existing access.

Pickup must not place credentials, tokens, private keys, recovery material, protected-storage contents, or unrelated personal information in a handoff. A handoff records prior work; it does not grant authority, prove authorship, or make an unsupported statement true.

The project is provided under the [MIT License](LICENSE), without a security guarantee.
