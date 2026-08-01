# Installation

## Prerequisites

- Python **3.11** or higher.
- `uv` (recommended) or `pip`.

---

## Installing via uv (Recommended)

```bash
uv add langchain-openapi
```

## Installing via pip

```bash
pip install langchain-openapi
```

---

## Verifying Installation

Run a quick Python command to verify that `langchain-openapi` is correctly installed:

```bash
python -c "import langchain_openapi; print(langchain_openapi.__version__)"
```

---

## Optional Dependencies

If you plan to contribute to `langchain-openapi` or run the documentation server locally, install dev dependencies:

```bash
uv sync --extra dev
```
