name: Bug Report
description: Create a report to help us fix a bug or unexpected behavior.
title: "[BUG]: "
labels: ["bug"]
assignees: []
body:
  - type: textarea
    id: description
    attributes:
      label: Bug Description
      description: Clear and concise description of what the bug is.
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior or code sample.
      placeholder: |
        from langchain_openapi import OpenAPIToolkit
        toolkit = OpenAPIToolkit.from_url("...")
    validations:
      required: true
  - type: textarea
    id: environment
    attributes:
      label: Environment
      description: Python version, OS, langchain-openapi version.
      placeholder: |
        - Python version: 3.11.0
        - OS: Linux / macOS / Windows
        - langchain-openapi version: 0.1.0
    validations:
      required: false
