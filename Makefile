.PHONY: sync test lint typecheck format docs benchmark all

sync:
	uv sync --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy langchain_openapi tests examples

format:
	uv run ruff format .

docs:
	uv run mkdocs build

benchmark:
	uv run python benchmarks/benchmark.py

all: format lint typecheck test docs benchmark
