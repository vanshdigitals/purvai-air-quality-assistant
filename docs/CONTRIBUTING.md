# Contributing (owner of workflow)

Documentation first, small changes, tests with every change. Challenge code is built inside Google Antigravity (required). Setup: [README.md](README.md#install-and-run), then `pre-commit install` (ruff, ruff-format, eslint, prettier, gitleaks).

## Branches and commits
During the challenge, commit to `main` only (reported single-branch rule, unverified). Tag `phase-1` to `phase-7`. Afterwards use `feat/`, `fix/`, `docs/` branches, squash-merged. Conventional Commits, for example `feat(rules): escalate sensitive members one level`, with `Refs FR-04` in the body.

## Standards
- Python 3.12: ruff, mypy strict, type hints, Pydantic at boundaries, no bare `except`, snake_case.
- TypeScript strict: no `any`, function components, PascalCase components, camelCase functions.
- Components: one per file, tokens only, native inputs in styled labels, follow the [design system](design/PURVAI_DESIGN_SYSTEM.md).
- API changes update [API.md](API.md) and tests together; breaking changes need `/v2`. DB changes need a migration, [DATABASE.md](DATABASE.md) update and an export schema bump if shape changes.

## Before submitting and review
Run `pytest`, `npm test`, `npm run build`, `npx playwright test`. Update only the owning document. Checklist: verdict logic unchanged or tests justified; no secrets or personal data in logs or prompts; accessible names, focus, contrast checked; new services listed in [TRD.md](TRD.md#external-services). Report security issues privately to Vansh Gupta.
