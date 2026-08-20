# Contributing to Marg

Thank you for contributing to Marg! Please follow these steps before submitting any code.

## First-Time Setup

```powershell
git clone https://github.com/your-org/marg.git
cd marg
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# REQUIRED: Install pre-commit hooks
pre-commit install
```

The pre-commit hooks will run automatically on every `git commit` and include:
- **`detect-secrets`** — blocks accidental commits of API keys, tokens, or credentials
- **`ruff`** — Python linting and formatting
- **`check-added-large-files`** — prevents committing OSM data files or large binaries

## Environment Variables

Copy `.env.example` to `.env` and fill in your values. **Never commit `.env` or any file containing real credentials.**

If the secrets scanner flags a false-positive (e.g. a test fixture UUID), add it to `.secrets.baseline`:
```powershell
detect-secrets audit .secrets.baseline
```

## Running Tests

```powershell
pytest -v
```

## Dependency Vulnerability Check

Before opening a PR:
```powershell
marg audit
```

Or manually:
```powershell
pip-audit --strict
```

## Code Standards

- No hardcoded coordinates, API keys, or DB credentials in source
- All new endpoints must validate India bounding box for any coordinate input
- Error responses must never include stack traces or internal file paths
- New routing/geocoding logic must be deterministic — no LLM or non-deterministic fallbacks
