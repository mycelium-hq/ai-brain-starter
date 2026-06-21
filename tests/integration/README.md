---
type: integration-tests
last_verified: 2026-06-21
freshness_days: 90
---

# Integration tests

Integration tests verify that shipped components compose correctly across contract boundaries.

## What lives here

Tests are added when a feature ships that involves two or more pieces working together. Each test exercises a contract between components, not a single script in isolation.

## Running

```bash
# Run all integration tests (Python-based)
python3 tests/integration/<test_name>.py

# Run all shell-based tests
bash tests/integration/<test_name>.sh
```

Stdlib + PyYAML only for Python tests. No pytest or external mocks.

## Adding a new test

1. Name it `test_<what_it_proves>.py` or `test_<what_it_proves>.sh`.
2. Provision a fresh temp directory for vault state; tear it down on exit.
3. Exit 0 on pass, 1 on first failure with the step name and the assertion that broke.
4. Document the step table in this README.
