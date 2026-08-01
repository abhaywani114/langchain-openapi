name: Documentation Improvement
description: Suggest improvements or report errors in documentation.
title: "[DOCS]: "
labels: ["documentation"]
assignees: []
body:
  - type: textarea
    id: summary
    attributes:
      label: Summary
      description: What section of the documentation needs improvement?
    validations:
      required: true
  - type: textarea
    id: content
    attributes:
      label: Suggested Changes
      description: Describe the changes or corrections you would like to see.
    validations:
      required: true
