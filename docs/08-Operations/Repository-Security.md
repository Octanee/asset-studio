---
title: Repository Security
type: operations
status: draft
created: 2026-11-22
updated: 2026-11-22
tags:
  - operations
  - security
  - governance
---

# Repository Security

How the repository itself is protected. Application-level controls are in [[Security-Architecture]]; the supply-chain row of its threat model is implemented here.

## Policies

| File | Purpose |
|---|---|
| `SECURITY.md` | private vulnerability reporting via GitHub Security Advisories, response times, scope |
| `CONTRIBUTING.md` | pull-request workflow, Conventional Commits, Definition of Done, what must never be committed |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1 |
| `.github/CODEOWNERS` | required reviewer for every path |
| `.github/pull_request_template.md` | security and docs checklist on every pull request |

## Automated controls

| Control | Where | When |
|---|---|---|
| Secret scan (gitleaks) | `.github/workflows/security.yml` | every push to `main`, every pull request, weekly |
| Dependency review (blocks high-severity vulnerable dependencies) | `.github/workflows/security.yml` | every pull request |
| CodeQL (`security-extended`) | `.github/workflows/codeql.yml` | every push to `main`, every pull request, weekly; languages: GitHub Actions, Python, JavaScript/TypeScript |
| Dependabot version updates | `.github/dependabot.yml` | weekly: GitHub Actions, `uv` (`backend/`, `host-agent/`), `npm`/pnpm (`frontend/`) |
| Pre-commit hooks (gitleaks, private keys, large files, no commits to `main`) | `.pre-commit-config.yaml` | on every local commit |
| `.gitignore` for `.env`, keys, model weights | `.gitignore` | always |

Workflows run with read-only `GITHUB_TOKEN` permissions by default and do not persist checkout credentials.

## Repository settings (GitHub)

These live in GitHub settings, not in files. State as of 2026-11-22:

| Setting | State |
|---|---|
| Ruleset "Protect main" (default branch) | active: pull request required, review threads must be resolved, stale reviews dismissed, squash or rebase only, linear history, no force pushes, no deletion, no bypass; required checks: `Secret scan (gitleaks)`, `Dependency review`, `Analyze (actions)`, `Analyze (python)`, `Analyze (javascript-typescript)`, `backend`, `frontend`, `host-agent`, `compose`, `docs` |
| Private vulnerability reporting | enabled |
| Secret scanning and push protection | enabled |
| Dependabot alerts and security updates | enabled |
| Secret scanning for generic patterns, validity checks | not available (need a GitHub Secret Protection licence) |

### Planned tightening

- **Required approvals and code-owner review** stay at 0 while the project has a single maintainer, because GitHub does not let authors approve their own pull requests. Raise both to 1 when a second maintainer joins.
- When a CI job is renamed or added, update the required checks in the ruleset too; a required check that never reports blocks every pull request.

## Licence check

The dependency review does not enforce licences automatically yet. Licence compatibility with Apache-2.0 is checked in review (see `CONTRIBUTING.md`).
