# Contributing

Thanks for contributing to BeeAGI.

## Local setup

1. Backend
   - `cd backend`
   - `python -m pip install -e ".[dev]"`
   - `pytest tests -q`
2. Desktop
   - `cd desktop`
   - `npm install`
   - `npm run build`

## Branch and PR rules

1. Create a feature branch from `main`.
2. Keep PRs focused and small.
3. Include tests for behavior changes.
4. Explain user impact and risks in PR description.

## Commit style (recommended)

- `feat: ...`
- `fix: ...`
- `refactor: ...`
- `docs: ...`
- `test: ...`

## Quality checklist

- Backend tests pass.
- Desktop build passes.
- No secrets committed.
- API changes are documented in README.
