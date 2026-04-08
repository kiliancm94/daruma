# Contributing to Daruma

Thanks for your interest in contributing!

## Getting Started

```bash
# Fork and clone
git clone https://github.com/<your-username>/daruma.git
cd daruma

# Install dependencies
uv sync --all-extras

# Verify everything works
source .venv/bin/activate
pytest
```

## Development Workflow

1. Create a branch from `main`
2. Write tests for your changes
3. Implement the feature or fix
4. Lint and format before committing:

```bash
uvx ruff check --fix .
uvx ruff format .
```

5. Open a pull request

## Commit Messages

Use [conventional commits](https://www.conventionalcommits.org/):

| Prefix | Use for |
|--------|---------|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation only |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance, dependencies, CI |

## Pull Requests

- Describe **what** changed and **why**
- Reference related issues (`Fixes #123`)
- Keep scope small — one concern per PR
- Ensure all tests pass (`pytest`)

## Project Structure

See [CLAUDE.md](CLAUDE.md) for architecture details and code conventions. The short version:

```
app/
  models/    → SQLAlchemy ORM (one model per file)
  schemas/   → Pydantic schemas (one file per domain)
  crud/      → Data access (plain functions, session as first param)
  routers/   → FastAPI routers (one per resource)
  services.py → Business logic
  runner.py  → Claude CLI subprocess wrapper
```

## Reporting Bugs

Open a [GitHub Issue](https://github.com/kiliancm94/daruma/issues) with:

- Steps to reproduce
- Expected vs actual behavior
- Environment: OS, Python version, Claude CLI version
