# Security Policy

## Reporting a vulnerability

Please do not open public issues for security vulnerabilities.

Send details privately to project maintainers with:

- affected component and version
- reproduction steps
- potential impact
- suggested mitigation (if known)

Maintainers will acknowledge within 72 hours and work on a fix and disclosure plan.

## Hardening notes

- Prefer enabling `APP_CONTROL_PLANE_API_KEY` in non-local environments.
- Do not commit `.env` files or API keys.
- Keep dependencies updated and run tests before release.
