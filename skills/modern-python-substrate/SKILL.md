---
name: modern-python-substrate
description: Modern Python toolchain substrate. uv for installs and venvs, ruff for lint and format, ty for typecheck, pytest for tests, hypothesis for property-based tests, src/ layout, pyproject.toml as single source of truth, pre-commit hooks. Plus LLM-stack patterns when the codebase calls anthropic, openai, tiktoken, or similar SDKs (prompt caching, retries, streaming, token counting). Use when the user says /python-setup, "set up Python project", "modern Python toolchain", "switch from poetry to uv", "ruff config", "ty migration from mypy", "configure pytest", or starts a new Python codebase. Covers Python 3.11+ idioms.
---

## /modern-python-substrate

Modern Python toolchain substrate built by reading every comparable skill and incorporating the strongest piece from each into one opinionated reference. Targets Python 3.11+ on Linux/macOS, with Windows parity called out where it matters.

## Source comparison (everything-comparison build)

| Source | What got incorporated | What was left out |
|---|---|---|
| [trailofbits/skills/modern-python](https://github.com/trailofbits/skills/tree/main/skills/modern-python) (CC-BY-SA-4.0) | The uv + ruff + ty + pytest core stack; src/ layout default; pre-commit pattern | Security-firm framing (security defaults belong in a separate skill); patterns reimplemented clean per CC-BY-SA-4.0 license-hygiene |
| [Astral docs](https://docs.astral.sh/) (uv, ruff, ty official guidance) | Authoritative invocation patterns; correct config field names; latest behavior in 2026 | Docs are reference; the substrate teaches the workflow not the API |
| [pytest official docs](https://docs.pytest.org/) | Fixtures, parametrize, marker patterns, conftest hierarchy | Plugin ecosystem catalogue (out of scope) |
| Anthropic SDK + tiktoken patterns (covered in detail by `claude-api` skill) | LLM-stack integration: prompt caching, streaming, retries, token counting (mentioned + linked here, full content stays in `claude-api`) | The full SDK docs (read `claude-api` skill for that) |
| [trailofbits/skills/property-based-testing](https://github.com/trailofbits/skills/tree/main/skills/property-based-testing) (CC-BY-SA-4.0) | Hypothesis pattern for invariants on top of example-based tests | Smart-contract specifics |
| Established practice (cross-team norms) | src/ layout default; no implicit relative imports; no wildcard imports; one logger per module; typed-everything; narrow exception types | n/a |

No source was forked verbatim. The patterns were extracted, merged, and re-expressed in caveman-form.

## When to use

- User says `/python-setup`, "set up Python project", "modern Python toolchain"
- User says "switch from poetry to uv" or "migrate from pip-tools to uv"
- User says "ruff config", "configure ruff", "format settings"
- User says "ty migration from mypy" or "set up Python type checking"
- User says "configure pytest", "set up pytest", "pytest fixtures"
- User starts a new Python codebase from scratch
- User asks "what's the current best Python setup"

Do NOT use for:
- Pure data-science notebooks (the toolchain is overkill for one-shot scripts; use `pip install ...` directly)
- Legacy Python 2 codebases (out of scope; modern Python means 3.11+)
- Bash + venv only setups (these are valid but not the "modern" target this skill teaches)

## Core stack (one toolchain, four tools)

| Tool | Replaces | Why |
|---|---|---|
| **uv** | pip + pip-tools + virtualenv + pyenv + poetry + pipenv | 10-100x faster, single-binary, manages Python versions + venvs + deps + lockfile in one |
| **ruff** | flake8 + black + isort + pyupgrade + many smaller linters | Single binary, sub-second on most repos, near-100% rule coverage of the Python lint ecosystem |
| **ty** | mypy + pyright (for typecheck only) | Astral's typechecker, 10x+ faster than mypy on large codebases. mypy still works; ty is the migration target. |
| **pytest** | unittest | Industry standard; fixtures, parametrize, plugin ecosystem |

Why not use `requirements.txt` + `pip` + `mypy` directly? They work, but the inner-loop speed delta (uv installs in 1s where pip takes 30s; ruff lints in 0.1s where flake8 takes 5s; ty typechecks in 1s where mypy takes 30s on the same codebase) compounds across thousands of inner-loop runs over a project's life. The faster toolchain stops being a luxury and becomes a productivity floor.

## pyproject.toml (single source of truth)

```toml
[project]
name = "yourproject"
version = "0.1.0"
description = "..."
requires-python = ">=3.11"
authors = [{name = "..."}]
dependencies = [
    "anthropic>=0.34",
    "fastapi>=0.110",
    "pydantic>=2.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "hypothesis>=6.100",
    "ty>=0.1",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "UP",   # pyupgrade
    "SIM",  # flake8-simplify
    "RUF",  # ruff-specific rules
    "S",    # flake8-bandit (security)
    "PTH",  # flake8-use-pathlib
]
ignore = [
    "E501",  # line-too-long (handled by formatter)
    "S101",  # assert-used (pytest needs assertions)
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.ty]
strict = true
exclude = ["tests/fixtures/", ".venv/"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers --strict-config"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external services",
]
```

## Standard project layout (src/ layout)

```
yourproject/
├── pyproject.toml
├── README.md
├── .gitignore
├── .python-version          # uv reads this for the Python version
├── src/
│   └── yourproject/
│       ├── __init__.py
│       ├── main.py
│       └── ...
├── tests/
│   ├── conftest.py          # shared fixtures
│   ├── test_main.py
│   └── ...
└── .venv/                   # uv-managed, .gitignored
```

Why src/ layout (not flat layout)?
- Imports like `from yourproject.main import foo` work in both editable and installed modes
- Tests cannot accidentally import from the source via implicit relative paths
- Packaging via `hatch build` or `uv build` is unambiguous about what gets shipped

## uv workflow

### One-time setup per machine
```bash
# Install uv (single binary, no Python pre-required)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or on macOS via Homebrew
brew install uv
```

### Per-project setup
```bash
# Initialize a new project
uv init yourproject
cd yourproject

# Or in an existing project, sync deps from pyproject.toml
uv sync

# Pin Python version (writes .python-version)
uv python pin 3.11

# Add a dep
uv add fastapi pydantic anthropic

# Add a dev-only dep
uv add --dev pytest hypothesis

# Run something inside the venv
uv run python script.py
uv run pytest tests/
uv run ruff check src/
uv run ty check src/
```

### Lockfile + reproducibility
- `uv.lock` is committed to the repo; locks every dep version + transitive
- `uv sync` installs from the lockfile reproducibly
- `uv lock --upgrade` to refresh; `uv lock --upgrade-package <name>` for one dep

## ruff workflow

```bash
# Lint (read-only)
uv run ruff check src/ tests/

# Lint + auto-fix
uv run ruff check --fix src/ tests/

# Lint + auto-fix (including unsafe transformations like type-annotation upgrades)
uv run ruff check --fix --unsafe-fixes src/ tests/

# Format
uv run ruff format src/ tests/

# Check formatting (CI mode)
uv run ruff format --check src/ tests/
```

The ruff config in `pyproject.toml` enables a sensible default ruleset (E + W + F + I + B + C4 + UP + SIM + RUF + S + PTH). Add or remove rules per project; do not delete the entire `select` and start over.

## ty workflow (migration from mypy)

```bash
# Typecheck
uv run ty check src/

# Strict mode (recommended for new codebases)
uv run ty check --strict src/

# Watch mode during development
uv run ty check --watch src/
```

Migration from mypy:
1. Install ty alongside mypy (do not delete mypy yet).
2. Run `ty check` and `mypy` in CI in parallel for one week.
3. Compare error counts. ty often finds errors mypy misses (and vice versa for some legacy patterns).
4. Migrate the config: `[tool.mypy]` → `[tool.ty]`. Most options have direct equivalents.
5. Once both pass cleanly, remove mypy from CI.

ty is faster than mypy by 10x+ on large codebases. The migration cost is one-time; the speed dividend compounds.

## pytest workflow

```bash
# Run all tests
uv run pytest tests/ -v

# Run one file
uv run pytest tests/test_invoice.py -v

# Run one test
uv run pytest tests/test_invoice.py::test_sums_line_items -vv

# Last-failed iteration (huge inner-loop win)
uv run pytest --lf -v

# Parallel (requires pytest-xdist)
uv run pytest tests/ -n auto

# With coverage
uv run pytest tests/ --cov=src/yourproject --cov-report=term-missing
```

### Fixtures (`conftest.py`)

```python
# tests/conftest.py
import pytest
from yourproject.config import Config


@pytest.fixture
def config():
    """Test config with safe defaults."""
    return Config(env="test", db_url="sqlite:///:memory:")


@pytest.fixture
def sample_invoice_items():
    """Sample invoice items used across multiple tests."""
    return [
        {"description": "service A", "amount": 100, "tax_rate": 0.10},
        {"description": "service B", "amount": 200, "tax_rate": 0.07},
    ]
```

Tests in any file under `tests/` automatically receive these fixtures by parameter name.

### Parametrize

```python
import pytest


@pytest.mark.parametrize("amount,tax_rate,expected", [
    (100, 0.10, 110),
    (200, 0.07, 214),
    (0, 0.10, 0),
])
def test_per_line_tax(amount, tax_rate, expected):
    assert apply_tax(amount, tax_rate) == expected
```

### Markers (slow tests, integration tests)

```python
import pytest


@pytest.mark.slow
def test_full_pipeline_end_to_end():
    """Takes 30 seconds; skip in inner loop with `-m 'not slow'`."""
    ...
```

Run only fast tests in inner loop: `pytest -m "not slow"`. Run all in CI: `pytest`.

## Property-based testing (hypothesis)

For pure functions where the input space is too large to enumerate:

```python
from hypothesis import given, strategies as st


@given(st.lists(st.dictionaries(
    keys=st.sampled_from(["description", "amount", "tax_rate"]),
    values=st.one_of(st.text(), st.floats(min_value=0), st.floats(min_value=0, max_value=1)),
    min_size=3,
    max_size=3,
)))
def test_total_is_non_negative_for_valid_inputs(items):
    """Total is always >= 0 for inputs with non-negative amounts."""
    valid_items = [i for i in items if isinstance(i.get("amount"), float) and i["amount"] >= 0]
    if not valid_items:
        return
    assert calculate_invoice_total(valid_items) >= 0
```

Properties to test commonly: idempotency, commutativity, associativity, identity, inverse, bounds. See `tdd-substrate` skill for the full property-based testing pattern.

## LLM-stack patterns (anthropic, openai, tiktoken)

When the Python codebase calls LLM SDKs, full guidance lives in the `claude-api` skill (auto-loads when relevant). Quick highlights:

### Prompt caching with anthropic
```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "<long static system prompt that does not change run-to-run>",
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[{"role": "user", "content": "..."}],
)
# Subsequent calls reuse the cached system prompt for ~90% of input tokens.
```

### Token counting with tiktoken (OpenAI-compatible)
```python
import tiktoken

encoding = tiktoken.get_encoding("cl100k_base")
tokens = encoding.encode("hello world")
print(f"{len(tokens)} tokens")
```

For Anthropic-specific token counting, use the `client.messages.count_tokens()` API instead.

### Retry pattern with exponential backoff
```python
import anthropic
from anthropic import APIError, RateLimitError
import time


def call_with_retry(client, messages, model, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.messages.create(model=model, messages=messages, max_tokens=1024)
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt + (e.retry_after or 0)
            time.sleep(wait)
        except APIError as e:
            if e.status_code in (500, 502, 503, 504):
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
            else:
                raise
```

(Full LLM-stack patterns: see `claude-api` skill.)

## Pre-commit hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/astral-sh/ty-pre-commit
    rev: v0.1.0
    hooks:
      - id: ty
        args: [--strict, src/]

  - repo: local
    hooks:
      - id: pytest-fast
        name: pytest (fast tests)
        entry: uv run pytest -m "not slow" -q
        language: system
        pass_filenames: false
        stages: [commit]
```

Install: `pre-commit install`. Now every `git commit` runs ruff + ty + fast pytest before the commit lands.

## CI matrix (GitHub Actions example)

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check src/ tests/
      - run: uv run ruff format --check src/ tests/
      - run: uv run ty check --strict src/

  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ matrix.python-version }}
      - run: uv sync
      - run: uv run pytest tests/ -v --cov=src
```

## Idioms (typed-everything, narrow imports, src layout)

| Idiom | Why |
|---|---|
| Type-annotate every public function signature | ty catches mismatches at import time, not at runtime |
| `from collections.abc import Iterable, Mapping` (not `from typing`) | Modern Python prefers the abstract base classes from `collections.abc` |
| `dict[str, int]` not `Dict[str, int]` | Python 3.9+ supports built-in generic types |
| `str | None` not `Optional[str]` | Python 3.10+ union-syntax is canonical |
| One logger per module: `logger = logging.getLogger(__name__)` | Lets per-module log-level config work; named-logger hierarchy is searchable |
| Narrow except clauses: `except ValueError as e` not `except Exception` | Bare `except Exception` swallows logic bugs disguised as KeyboardInterrupt |
| `pathlib.Path` not `os.path` | Object-API > string-mangling-API |
| `dataclass` or `pydantic.BaseModel` for value objects, not bare dicts | Type-checker catches typos in field names |

## Anti-patterns

| Anti-pattern | Fix |
|---|---|
| Mixing `pip` and `uv` in the same project | Pick one (uv); commit `uv.lock`; remove `requirements.txt` |
| Editable install via `pip install -e .` instead of `uv pip install -e .` | Use `uv` directly; the `pip` wrapper is for compatibility, not the daily path |
| Wildcard imports (`from yourproject import *`) | Explicit imports; ruff catches this |
| Bare `print()` for logging | One `logger = logging.getLogger(__name__)` per module |
| `os.path.join` instead of `pathlib.Path` | Migrate; ruff has a rule for this (`PTH`) |
| Untyped public function signatures | ty's `--strict` catches; CI gate fails |
| Tests in the same package as source (`yourproject/test_main.py`) | Move to `tests/test_main.py` (src/ layout) |
| pytest fixtures defined in test files instead of `conftest.py` | Move shared fixtures to conftest; one source of truth |

## Output format

When invoked, the skill responds:

```
## Modern Python setup: <project name or scope>

### Toolchain choices
- Python: <version>
- Package manager: uv
- Linter + formatter: ruff (rules: <selected>)
- Typechecker: ty (strict: yes/no, migration from mypy: yes/no)
- Test runner: pytest (with hypothesis for property-based tests)
- Pre-commit: yes/no
- CI matrix: <OSes + Python versions>

### Files to create / modify
- pyproject.toml (full content above)
- .python-version (pin)
- src/yourproject/ (or migration plan)
- tests/conftest.py (shared fixtures)
- .pre-commit-config.yaml (if adopting)
- .github/workflows/ci.yml (if adopting)

### Migration steps (if not greenfield)
<numbered list>

### First inner-loop test
<one specific command the user runs to verify the setup>
```

## Cross-references

- `tdd-substrate` — TDD discipline; pairs with this skill (use TDD inside the toolchain set up here)
- `claude-api` — full LLM-stack patterns (anthropic SDK, prompt caching, streaming, citations, model migration)
- trailofbits-skills bundle — complementary security-focused Python skills (insecure-defaults, sharp-edges, static-analysis)

## Async testing (asyncio + pytest-asyncio)

For Python services that ship `async def` code (FastAPI, httpx clients, async DB drivers):

```python
import pytest


@pytest.mark.asyncio
async def test_async_function_returns_value():
    result = await my_async_function()
    assert result == "expected"


@pytest.fixture
async def async_client():
    """Async fixture using async generator pattern."""
    client = AsyncClient()
    yield client
    await client.close()
```

Configure in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # auto-mark async tests; opt-out with @pytest.mark.asyncio(mode="strict")
```

For testing async code that hits real services, use `pytest-httpx` to mock httpx calls or `respx` for `httpx`-specific routing.

## Structured logging (loguru OR structlog OR stdlib logging)

For LLM-stack apps especially: structured logging is required for production debugging because LLM call latency / tokens / errors / retries need correlation.

```python
# Recommended for new projects: loguru (one import, sane defaults)
from loguru import logger

logger.add("app.log", rotation="100 MB", retention="30 days", serialize=True)  # JSON output
logger.info("call_start", model="claude-sonnet-4-5", input_tokens=1234)
logger.error("rate_limit", retry_after=10.0, attempt=2)
```

Or stdlib + structlog if the team prefers explicit configuration. Either way, output should be:
- One log entry per event (not concatenated multi-line)
- JSON when serialized (greppable, parseable)
- Has correlation IDs for multi-step requests
- Captures context (user_id, request_id, model, retry count) at the call site, not later

## Mocking (pytest-mock + unittest.mock)

```python
def test_external_api_call(mocker):
    """pytest-mock wraps unittest.mock with cleaner pytest integration."""
    mock_response = mocker.Mock(status_code=200, json=lambda: {"key": "value"})
    mocker.patch("httpx.get", return_value=mock_response)

    result = call_external_api()

    assert result == {"key": "value"}
```

Mock at the BOUNDARY (HTTP, database, file I/O), not at internal calls. If you find yourself mocking your own internal methods, the test is testing the wrong layer.

## Eng-discipline cycle (Python-specific cross-references)

Python toolchain hygiene + TDD + debugging + verification form one cycle. Each step has its own substrate or upstream skill:

| Step | Iron Law | Substrate / source |
|---|---|---|
| 1. Design before code | NO IMPLEMENTATION ACTION UNTIL DESIGN APPROVED | `obra:brainstorming` |
| 2. Toolchain set up correctly | THIS SKILL — uv + ruff + ty + pytest configured per pyproject.toml | This skill (`modern-python-substrate`) |
| 3. Test before code | NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST | `tdd-substrate` (Vitest + pytest dual-runtime; this skill is the Python toolchain that hosts the pytest side) |
| 4. Root cause before fix | NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST | `obra:systematic-debugging` |
| 5. Evidence before completion | NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE | `obra:verification-before-completion` |

The toolchain (this skill) is necessary but not sufficient. The cycle is the discipline.

## Source comparison (everything-comparison build, revised)

| Source | What got incorporated | What was left out |
|---|---|---|
| [trailofbits/skills/modern-python](https://github.com/trailofbits/skills/tree/main/skills/modern-python) (CC-BY-SA-4.0) | The uv + ruff + ty + pytest core stack; src/ layout default; pre-commit pattern | Security-firm framing (security defaults belong in a separate skill); patterns reimplemented clean per CC-BY-SA-4.0 license-hygiene |
| [Astral docs](https://docs.astral.sh/) (uv, ruff, ty official) | Authoritative invocation patterns; correct config field names; latest 2026 behavior | Docs are reference; this skill teaches the workflow not the API |
| [pytest official docs](https://docs.pytest.org/) | Fixtures, parametrize, markers, conftest hierarchy | Plugin ecosystem catalogue (would bloat) |
| Anthropic SDK + tiktoken patterns (linked via `claude-api`) | LLM-stack integration: prompt caching, streaming, retries, token counting | Full SDK docs (handled by claude-api skill) |
| [trailofbits/skills/property-based-testing](https://github.com/trailofbits/skills/tree/main/skills/property-based-testing) (CC-BY-SA-4.0) | Hypothesis pattern for invariants on top of example-based tests | Smart-contract specifics |
| **pytest-asyncio + httpx async patterns (newly added)** | Async test patterns, fixture usage, asyncio_mode config | Niche async libraries (trio, anyio) |
| **Structured logging (loguru / structlog) (newly added)** | When and why structured logging matters for LLM-stack apps | Distributed tracing (OpenTelemetry, separate concern) |
| **pytest-mock + unittest.mock (newly added)** | Mock at the boundary, not internal calls | Specific mock-libraries-as-DB-replacements |
| **obra eng-discipline cycle cross-references (newly added)** | Brainstorming + TDD + systematic-debugging + verification as the surrounding discipline | Each individual obra skill stays at upstream |
| Established practice (cross-team norms) | src/ layout default, no implicit relative imports, no wildcard imports, one logger per module, typed-everything, narrow exception types | n/a |

**Audit gap closed 2026-05-10.** v1 cited 5 sources. v2 adds async testing, structured logging, mocking, and the obra eng-discipline cycle cross-references — these were genuine missing capabilities.

## Source attribution

Source-comparison build per the repo-evaluation runbook "build with everything-comparison" rule. Patterns from CC-BY-SA-4.0 sources (trailofbits/skills/modern-python, trailofbits/skills/property-based-testing) were reimplemented clean per the license-hygiene rule.
