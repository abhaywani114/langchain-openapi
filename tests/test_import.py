import langchain_openapi_tools


def test_import() -> None:
    assert langchain_openapi_tools is not None
    assert langchain_openapi_tools.__version__ == "1.0.2"
