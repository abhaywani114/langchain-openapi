# Contributing to `langchain-openapi`

Thank you for your interest in contributing to `langchain-openapi`! We welcome contributions from the community.

---

## Development Setup

We use [`uv`](https://github.com/astral-sh/uv) for fast, reliable Python environment and dependency management.

### 1. Prerequisites

* Python 3.11 or higher
* `uv` installed (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 2. Clone the Repository

```bash
git clone https://github.com/your-username/langchain-openapi.git
cd langchain-openapi
```

### 3. Set Up Virtual Environment & Dependencies

Create the virtual environment and install all development dependencies:

```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync --all-extras --dev
```

### 4. Install Pre-commit Hooks

Setting up pre-commit hooks ensures all code formatting and lint checks pass before creating a commit:

```bash
uv run pre-commit install
```

---

## Quality & Testing Commands

Before submitting a pull request, verify that your code adheres to project formatting, typing, and test standards.

### Running Tests

We use `pytest` for unit testing:

```bash
uv run pytest
```

### Running Code Formatting & Linting

We use `Ruff` for linting and formatting:

```bash
# Check for linting errors
uv run ruff check .

# Check formatting compliance
uv run ruff format --check .

# Automatically fix lint issues and format files
uv run ruff check --fix .
uv run ruff format .
```

### Running Type Verification

We use `MyPy` for strict static type checking:

```bash
uv run mypy langchain_openapi tests
```

---

## Commit & PR Guidelines

### Commit Expectations

* **Clear & Concise Messages**: Write commit summaries in imperative mood (e.g., `Add OpenAPI spec validation module`).
* **Atomic Commits**: Keep changes focused on a single feature or bugfix per commit.
* **Pass Pre-commit Hooks**: Ensure pre-commit hooks run cleanly prior to committing.

### Pull Request Workflow

1. **Create a Feature Branch**: Branch off `main` using descriptive names (e.g., `feature/openapi-loader` or `fix/schema-parser`).
2. **Implement Changes**: Write code, tests, and documentation.
3. **Verify Locally**: Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy langchain_openapi tests`.
4. **Open Pull Request**: Provide a clear title and description explaining the changes, context, and motivation.
5. **CI Pipeline**: All checks in GitHub Actions must pass before PR approval and merge.

Thank you for contributing!
