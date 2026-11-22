# Security Policy

Asset Studio is a local-first application. Security issues are taken seriously,
even before the first release.

## Supported versions

| Version | Supported |
|---|---|
| `main` (pre-release) | yes |
| older commits / forks | no |

Once releases exist, only the latest minor release receives security fixes.

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a security problem.**

Report it privately through GitHub:
**Security → Advisories → "Report a vulnerability"**
(<https://github.com/Octanee/asset-studio/security/advisories/new>).

Please include:

- a description of the issue and its impact;
- steps to reproduce or a proof of concept;
- the affected commit, version or component (API, worker, MCP server, host agent, frontend);
- any suggested fix.

## What to expect

| Step | Target time |
|---|---|
| Acknowledgement | 7 days |
| Initial assessment | 14 days |
| Fix or mitigation plan | 90 days, or sooner for critical issues |

You will be credited in the advisory unless you ask otherwise. Please give us a
reasonable time to fix the issue before disclosing it publicly.

## Scope

In scope: code in this repository and its documented default configuration
(see `docs/04-Architecture/Security-Architecture.md`).

Out of scope: third-party tools run as separate processes (ComfyUI, kohya,
custom nodes), model weights, and issues that need an already compromised
local machine or account.

## Secrets

If you find a secret (token, key, password) committed to this repository,
report it the same way. Never test whether a leaked secret works.
