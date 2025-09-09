# Gemini Agent Development

This document outlines the development process for this Gemini agent, including setup, code style, and testing procedures.

## Getting Started

### Prerequisites

- Python 3.10+
- `make`
- `uv`

### Setup

```bash
make install
```

## Code Quality

To maintain a clean and consistent codebase, we use automated tools for linting and formatting.

### Checking Code Style

Before committing code, run `make check` command to ensure your code adheres to the project's style guidelines. This includes pyright, ruff, and some extra linters across all files. See `.pre-commit-config.yaml` for details.

## Testing

We use `pytest` for our test suite. All tests must pass before code is merged. Run `make check` in order to run all pytest tests. Add the tests in the `tests/` directory.

For tests we can assume we have credentials to a test instance of Jira.

### Writing Tests


All new functionality, including new tools or modifications to the agent's logic, must be accompanied by corresponding tests.

-   Tests should be placed in the `tests/` directory.
-   Test files should follow the `test_*.py` naming convention.
-   Ensure your tests cover both success and failure cases for the new functionality.

By following these guidelines, we can ensure the agent remains robust, reliable, and easy to maintain.
