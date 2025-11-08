# Sage Research-ToolKit - Task Runner
# Use `just --list` to see all available commands

# Set shell based on OS for cross-platform compatibility
# Windows uses PowerShell, Unix-like systems use sh
set windows-shell := ["pwsh.exe", "-NoLogo", "-Command"]
set shell := ["sh", "-cu"]

# Default recipe (runs when you just type `just`)
default:
    @just --list

# Install project dependencies with uv
install:
    uv sync

# Run all tests with pytest
test *ARGS:
    uv run pytest {{ARGS}}

# Run tests with coverage report
test-cov:
    uv run pytest --cov=sage --cov-report=term-missing --cov-report=html

# Run only unit tests
test-unit:
    uv run pytest -m unit

# Run only integration tests
test-integration:
    uv run pytest -m integration

# Run only contract tests
test-contract:
    uv run pytest -m contract

# Format code with ruff
format:
    uv run ruff format .

# Lint code with ruff
lint:
    uv run ruff check .

# Lint and auto-fix issues
lint-fix:
    uv run ruff check --fix .

# Run type checking with mypy (strict mode)
typecheck:
    uv run mypy src/sage --strict

# Run complexity analysis with xenon
complexity:
    uv run xenon src/sage --max-absolute B --max-modules B --max-average A

# Detailed complexity report
complexity-report:
    uv run xenon src/sage --max-absolute B --max-modules B --max-average A -a -m

# Run all quality checks (lint, typecheck, complexity)
check: lint typecheck complexity
    @echo "✅ All quality checks passed!"

# Run full CI pipeline (format, lint, typecheck, complexity, tests)
ci: format lint typecheck complexity test
    @echo "🎉 Full CI pipeline completed successfully!"

# Clean up cache and temporary files
clean:
    rm -rf __pycache__
    rm -rf .pytest_cache
    rm -rf .mypy_cache
    rm -rf .ruff_cache
    rm -rf htmlcov
    rm -rf .coverage
    rm -rf dist
    rm -rf build
    rm -rf *.egg-info
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete

# Show project version
version:
    @uv run python -c "import sage; print(sage.__version__)"

# Start interactive Python shell with project loaded
shell:
    uv run python

# Run the main application
run:
    uv run python main.py

# Watch mode for tests (requires pytest-watch)
watch:
    uv run ptw

# Generate a coverage badge (requires coverage-badge)
coverage-badge:
    uv run coverage-badge -o coverage.svg -f

# List all TODO/FIXME/NOTE comments in code
todos:
    @rg "TODO|FIXME|NOTE|HACK|XXX" src/sage/ tests/ --color=always || echo "No TODOs found! 🎉"

# Supabase stack helpers
supabase-up:
    docker compose -f docker/docker-compose.yml --env-file docker/.env up -d

supabase-down:
    docker compose -f docker/docker-compose.yml --env-file docker/.env down

supabase-pull:
    docker compose -f docker/docker-compose.yml --env-file docker/.env pull

supabase-logs *SERVICES:
    docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f {{SERVICES}}

launch-sage: supabase-up
    uv run python scripts/test_supabase_db.py
    @echo "✅ Supabase ready at postgresql://postgres:@127.0.0.1:5433/postgres"

shutdown-sage: supabase-down
    @echo "🛑 Supabase stack stopped."

