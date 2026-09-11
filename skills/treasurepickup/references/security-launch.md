# Private reporting: launch checklist

Prepared September 10, 2026. Both source repositories were private when inspected. GitHub's [private vulnerability reporting feature](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository) is available to public repositories. This document prepares that route without changing visibility or publishing anything.

## Proposed route

Use GitHub private vulnerability reporting in each public repository. Alternatively, the owner may select a real private contact and verify that it receives reports. No contact address or response commitment has been invented.

Before describing direct reporting as available:

- [ ] The owner authorizes the intended visibility and chooses the reporting route.
- [ ] For the GitHub route, enable **Settings → Advanced Security → Private vulnerability reporting** on each public repository.
- [ ] Confirm the **Report a vulnerability** entrypoint appears on each repository's Security/Advisories page for an appropriate non-admin reader.
- [ ] Confirm the maintainer receives the intended notifications; use a clearly labeled non-sensitive test only if the owner authorizes sending it.
- [ ] Replace the pending-route language in both security policies with the verified destination. Keep the fallback until this is complete.
- [ ] Name the supported release line and how users identify/update their paired installation.
- [ ] Record any owner-selected response expectations accurately.

Preparation can be complete while these boxes remain open. A working private route and release policy are still required before declaring public launch ready. Repository visibility, settings changes, external messages, and release publication are separate actions.
