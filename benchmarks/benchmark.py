"""Performance benchmark suite for langchain-openapi."""

import time
from typing import Any

from langchain_openapi import (
    OpenAPILoader,
    OpenAPIParser,
    OpenAPIToolkit,
    SchemaConverter,
)


def run_benchmarks() -> None:
    """Execute benchmark measurements and print report."""
    print("==================================================")
    print("       langchain-openapi Performance Benchmark     ")
    print("==================================================")

    spec_dict: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Benchmark API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            f"/endpoint_{i}": {
                "get": {
                    "operationId": f"getEndpoint_{i}",
                    "summary": f"Benchmark operation {i}",
                    "parameters": [
                        {
                            "name": f"param_{i}",
                            "in": "query",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
            for i in range(100)
        },
    }

    # Benchmark 1: Spec Parsing
    t0 = time.perf_counter()
    spec = OpenAPILoader.from_dict(spec_dict).load()
    parser = OpenAPIParser(spec)
    operations = parser.parse()
    t1 = time.perf_counter()
    parse_time = (t1 - t0) * 1000
    print(f"1. Spec Parsing (100 operations): {parse_time:.2f} ms")

    # Benchmark 2: Dynamic Schema Conversion
    t0 = time.perf_counter()
    converter = SchemaConverter()
    for op in operations:
        converter.to_pydantic(op)
    t1 = time.perf_counter()
    convert_time = (t1 - t0) * 1000
    print(f"2. Dynamic Schema Conversion (100 models): {convert_time:.2f} ms")

    # Benchmark 3: Tool Factory Generation
    t0 = time.perf_counter()
    toolkit = OpenAPIToolkit.from_dict(spec_dict)
    tools = toolkit.get_tools()
    t1 = time.perf_counter()
    toolkit_time = (t1 - t0) * 1000
    print(f"3. Toolkit Tool Generation ({len(tools)} tools): {toolkit_time:.2f} ms")

    print("==================================================")


if __name__ == "__main__":
    run_benchmarks()
