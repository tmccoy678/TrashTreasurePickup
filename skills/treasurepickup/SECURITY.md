# Security Policy

## Supported versions

No versioned releases are published. Fixes target the latest commit on `main`; earlier commits, forks, and modified copies are outside the current support policy. Identify a development installation by its source commit and installer digest, then compare with the maintainer's current source.

| Version | Security fixes |
| --- | --- |
| Latest `main` | Yes |
| Earlier commits, forks, or modified copies | No |
| Future versioned release line | Not selected yet |

Before a versioned release, the maintainer must name the supported release line and update this table and the coordinated release instructions. No response-time commitment is currently promised.

## Private vulnerability reports

Keep vulnerability details out of issues and pull requests.

Contact [@tmccoy678](https://github.com/tmccoy678) through a private channel already established with the owner. If none exists, open an issue containing **only a request for a private security contact**, without reproduction details, affected private artifacts, or secrets.

After private contact is established, include the affected source/release, impact, sanitized reproduction, and any known mitigation.

A direct GitHub private-reporting route is planned for public launch, **not currently advertised as enabled**. The maintainer's [activation checklist](references/security-launch.md) records the remaining steps. The existing contact-request fallback stays in place until that route is verified.

## Scope and limitations

Pickup's checks report available evidence under their documented access conditions. Hash consistency is not authorship or proof that a handoff's statements are true. Limited access may leave checks UNKNOWN or NOT RUN; actual failures retain their result. Real scanner execution remains deferred in the current acceptance evidence. See the skill and its [protocol](references/pickup-registry.md) for the operation's boundaries.

The project is [MIT licensed](LICENSE). Its dependencies retain their own applicable license terms; project licensing does not imply a security guarantee.

## Sources

- [GitHub: security policies](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/add-security-policy)
- [GitHub: private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
