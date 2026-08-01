import langchain_openapi


def test_import() -> None:
    assert langchain_openapi is not None
    assert langchain_openapi.__version__ == "1.0.0"
