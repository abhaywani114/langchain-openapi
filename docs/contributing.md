# Contributing Guidelines

Thank you for considering contributing to `langchain-openapi`!

---

## Development Environment Setup

1. **Clone repository**:
   ```bash
   git clone https://github.com/abhaywani114/langchain-openapi.git
   cd langchain-openapi
   ```

2. **Sync virtual environment with `uv`**:
   ```bash
   uv sync --extra dev
   ```

3. **Install pre-commit hooks**:
   ```bash
   uv run pre-commit install
   ```

---

## Code Quality Standards

Before submitting a PR, ensure all checks pass:

- **Formatting**: `uv run ruff format .`
- **Linting**: `uv run ruff check .`
- **Type Checking**: `uv run mypy langchain_openapi tests examples`
- **Tests**: `uv run pytest`

---

## Pull Request Checklist

- [ ] Clear title describing the change.
- [ ] Added or updated unit tests for new functionality.
- [ ] Updated docstrings and relevant documentation in `docs/`.
- [ ] Ruff and MyPy pass cleanly without errors.
