# Security Policy

## Supported versions

We follow [semantic versioning](https://semver.org/). Security fixes land
on the latest minor release of the most recent major version. Older
majors receive fixes for **critical** issues at maintainer discretion.

| Version | Supported |
|---------|-----------|
| 2.x     | ✅        |
| 1.x     | ❌ (please upgrade — see [docs/migration.md](docs/migration.md)) |
| < 1.0   | ❌        |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Use GitHub's [Private Vulnerability Reporting](https://github.com/TexasCoding/kalshi-python-sdk/security/advisories/new)
to disclose privately. Reports go directly to maintainers and are not
visible until a coordinated disclosure.

When reporting, please include:

- A description of the issue and its potential impact.
- Steps to reproduce (minimal proof-of-concept preferred).
- Affected versions and environment (Python version, OS).
- Suggested mitigation, if known.

### Response timeline

We aim for:

- **Acknowledgement** within 72 hours.
- **Triage + severity assessment** within 7 days.
- **Fix or mitigation plan** within 30 days for high/critical issues.

Reporters who follow this process and request credit will be named in
the CHANGELOG entry for the fix release, unless they prefer anonymity.

## Scope

In scope:

- Credential or PII leakage from `KalshiError` / log output.
- Unsafe deserialization or remote code execution paths.
- Auth-bypass / signing-bypass in `kalshi.auth`.
- Supply-chain compromise vectors in the build, release, or
  spec-sync pipelines.

Out of scope:

- Vulnerabilities in upstream dependencies — please report those to the
  affected project. We track upstream CVEs via Dependabot security
  updates and `pip-audit`.
- Issues in the Kalshi API itself — please contact
  [Kalshi support](https://kalshi.com/support).
- DoS via legitimate API rate limits (the SDK respects `Retry-After`).

## Security measures in this repo

- Secret scanning + push protection enabled on this repository.
- Dependabot version updates (weekly) + security updates (CVE-triggered).
- Nightly `pip-audit` workflow against the resolved dev environment.
- `release.yml` uses [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
  with [sigstore attestations](https://docs.pypi.org/attestations/) —
  no API tokens, no manual upload step.
- Spec-sync workflow runs with `contents: read` only; it cannot push,
  open PRs, or execute upstream-derived Python.
- Third-party Actions SHA-pinned in workflows that hold elevated
  permissions (release, spec-sync, claude review).
- RSA-PSS request signing with timestamp; signatures rejected if
  clock-skew exceeds the API's tolerance.

If you spot a gap in these controls, please report via the channel above.
