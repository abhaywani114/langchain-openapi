# Installation

## Prerequisites

- Python **3.11** or higher.
- `uv` (recommended) or `pip`.

---

## Package Naming & Installation

The PyPI distribution package name is **`langchain-openapi-tools`**, whereas the Python import module name is **`langchain_openapi`**.

### Installing via uv (Recommended)

```bash
uv add langchain-openapi-tools
```

### Installing via pip

```bash
pip install langchain-openapi-tools
```

> **Note on Package Naming:**
> The PyPI distribution name differs from the Python import name. This is common in Python packages (e.g. `beautifulsoup4` → `import bs4`, `opencv-python` → `import cv2`).

---

## Importing in Python

```python
from langchain_openapi_tools import OpenAPIToolkit, OpenAPIToolkitConfig
```

### Migration Note

```python
# Old (deprecated):
from langchain_openapi import OpenAPIToolkit

# New (recommended):
from langchain_openapi_tools import OpenAPIToolkit
```

---

## Verifying Installation

Run a quick Python command to verify that `langchain-openapi` is correctly installed:

```bash
python -c "import langchain_openapi_tools; print(langchain_openapi.__version__)"
```

---

## Optional Dependencies

If you plan to contribute to `langchain-openapi` or run the documentation server locally, install dev dependencies:

```bash
uv sync --extra dev
```
