default:
    @just --list

# Install / refresh deps
sync:
    uv sync

# Lint: ruff + mypy (strict via pyproject)
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy vsc

# Auto-fix lint issues
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Run tests
test *args:
    uv run pytest {{args}}

# Run tests with coverage
test-cov:
    uv run pytest --cov=vsc --cov-report=term-missing

# Smoke-run the CLI
vsc *args:
    uv run vsc {{args}}

# Serve docs locally (preview only)
docs:
    uv run zensical serve

# Build docs (strict — fails on broken links / missing anchors)
docs-build:
    uv run zensical build --strict
