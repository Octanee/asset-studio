# Contributing

- The project uses **GitHub Flow**:
  1. Create a short-lived branch from the latest `main`: `feature/*`, `fix/*`, `docs/*`, `chore/*` or `ci/*`.
  2. Open a pull request to `main` early; one topic per pull request.
  3. Wait for the required checks; merge with **squash** (default) or **rebase**. Merge commits are disabled.
  4. The branch is deleted automatically after the merge. Start the next change from the updated `main`.
- Do not stack pull requests on top of each other. If `main` moves, use **Update branch** on the pull request (or rebase locally).
- Nothing is pushed directly to `main`.
- Solo-maintainer mode: no approving review is required. In an emergency (a broken external service in CI, a false-positive alert), the maintainer can merge a pull request with **bypass rules**. Direct pushes to `main` stay blocked even then. Record every bypass in the PR description.
- Every PR follows the **Definition of Done** (`docs/09-Project-Management/Documentation-Rules.md`, brief §20):
  - tests pass;
  - lint and type checks pass;
  - the docs in `docs/` are updated;
  - requirements stay traceable to tests.
- Approved requirements, UI and architecture change only with an approved decision (see `docs/09-Project-Management/Decision-Log.md`).
- Never commit secrets, `.env`, model files or machine-specific data.

## Conduct and security

- Be respectful — see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Report security problems privately, never in a public issue — see [SECURITY.md](SECURITY.md).
- `main` is protected by a ruleset: pull request required, review threads resolved, squash or rebase merge only (linear history). Details: `docs/08-Operations/Repository-Security.md`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, `ci:` …).

### Pre-commit hooks

Install once per clone:

```bash
uv tool install pre-commit   # or: pipx install pre-commit
pre-commit install
```

The hooks block commits with secrets (gitleaks), private keys, files over 1 MB, merge-conflict markers and direct commits to `main`.

If a secret is committed by accident, treat it as leaked: rotate it first, then remove it from history and tell the maintainer.

### Dependencies

- Every new dependency needs a reason in the PR description and a licence compatible with Apache-2.0 — no GPL code linked into the application (`docs/04-Architecture/Security-Architecture.md`).
- Lock files (`uv.lock`, `pnpm-lock.yaml`) are always committed.
- Dependabot PRs are reviewed like any other change.

## License

By contributing you agree that your contributions are licensed under the Apache License 2.0 (see [LICENSE](LICENSE)).
