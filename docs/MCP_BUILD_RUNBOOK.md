# MCP Build Runbook

> **READ THIS WHOLE FILE BEFORE BUILDING ANY MCP SERVER, MANAGED AGENT, OR CUSTOM CONNECTOR.**
>
> This applies to: building new MCPs, modifying existing ones, deploying managed agents, debugging MCP connection failures, or planning MCP architecture.
>
> This runbook captures every lesson from MCP builds so you never re-learn them. Every numbered lesson is load-bearing.

---

## PRE-FLIGHT CHECKLIST (run before every MCP build)

1. **Read this whole file.** Every skipped lesson costs 15-60 minutes.
2. **Check your tool-routing doc** before building. Does an existing paid tool already do this? (n8n, HubSpot, Apollo, etc.) Don't build custom when you can wire.
3. **Run the Optimization Pass** (see section below). Before writing a line of code, audit the spec for over-engineering and stack redundancy. This is mandatory, not optional.
4. **Verify FastMCP is installed:** `fastmcp version` (expect v3.2.3+). Install via `pipx install fastmcp`.
5. **Check `~/.claude.json`** for existing registrations. Don't create duplicates.
6. **Check Python dependencies:** `python3 -c "import fastmcp; print(fastmcp.__version__)"`. If import fails: `pip3 install --break-system-packages fastmcp`.
7. **Read at least one existing MCP server** to match established patterns before writing new ones.

---

## OPTIMIZATION PASS (mandatory before every build)

Run this audit on your spec before writing any code. The goal: build only what genuinely needs to be built, at the right complexity level.

### 1. Stack redundancy check

For every component in the spec, ask: does an existing paid tool handle this already?

| Spec says | Check this first |
|----------|-----------------|
| Dashboard / reporting UI | Native tool reporting, Google Sheets |
| Scheduling / cron | n8n workflows, Claude scheduled tasks |
| Email sending | Existing email tool sequences |
| CRM data | Already-connected CRM (HubSpot, etc.) |
| File classification | Rules-based Python — no Claude API needed |
| Web scraping | Playwright or existing browser plugin |
| Document storage | Vault files — no new DB needed |

### 2. Frontend complexity check

Most internal tools don't need a full React stack. Before building Next.js + a component library:

- **Is the only user you?** If yes: terminal output, a Google Sheet, or a simple HTML page is sufficient.
- **Is it purely internal operations?** A Slack bot or terminal output is often enough.
- **Does it need real-time updates?** If not, static HTML + a cron refresh is simpler.
- **Rule:** Next.js is justified only when the tool has external users, complex interactivity, or is being published publicly.

### 3. Database size check

Before reaching for Postgres/Supabase:
- Weekly snapshots for 90 days = 52 rows. That's SQLite.
- Contacts at typical scale = hundreds of rows. That's SQLite.
- Supabase/Postgres is justified only when: multi-user concurrent writes, >100k rows, or cross-service DB access.

### 4. LLM usage check

Not everything needs Claude. Flag and remove LLM calls where:
- The logic is purely rule-based (file classification, field mapping, regex extraction)
- The output is deterministic math (totals, calculations)
- The operation is just format conversion (JSON to markdown, YAML parsing)
- **Rule:** Claude API calls add latency and cost. Use only where the LLM is genuinely making a judgment call.

### 4b. Financial math goes in Excel — not Python, not LLM

Any agent that outputs money amounts (invoices, commissions, budgets, tax calculations) must generate an Excel file with formulas. Excel's engine does the math. Python only writes input values and formula strings.

- Use `openpyxl` — formula strings like `"=B3*0.11"` are written as cell values
- The spreadsheet is the auditable source of truth; JSON/dict output is a summary
- Add `openpyxl>=3.1.0` to any requirements.txt that handles financial output

### 5. Cross-agent shared code

When building multiple agents in the same session, look for shared patterns to extract:
- Anthropic client setup with prompt caching
- Error handling and retry logic
- Vault write helpers
- Common data models
- **Rule:** If two agents share >20 lines of logic, extract to a shared `utils.py`.

### 6. Integration with existing MCPs

Check if a new agent should call an already-built MCP instead of re-implementing:
- **Rule:** Agents and MCPs should compose, not duplicate.

### Document your optimization decisions

In your build log entry, note:
- What you simplified vs the spec
- What you decided NOT to build (and why)
- Any shared code extracted

---

## ARCHITECTURE RULES

### MCP Server Pattern (FastMCP)

```python
from fastmcp import FastMCP

mcp = FastMCP("your-server-name")

@mcp.tool()
def your_tool(param: str) -> dict:
    """Tool description shown to Claude."""
    return {"result": param}

if __name__ == "__main__":
    mcp.run()
```

- **Framework:** FastMCP v3.2.3+ (Python, decorator-based)
- **Transport:** stdio (registered in `~/.claude.json`)
- **Location:** `~/Desktop/{name}-mcp/` (each server gets its own directory)
- **Files:** `server.py` (main), `requirements.txt`, `config.yaml` (if needed)

### Managed Agent Pattern (Anthropic SDK)

```python
import anthropic
import os

MODEL = "claude-sonnet-4-6"
_client = None

def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return None  # return None, don't crash
        _client = anthropic.Anthropic(api_key=key)
    return _client
```

Key rules:
- **Always lazy-initialize** the Anthropic client — never at module level
- **Always stub gracefully** when no API key is set — return a hardcoded example, don't crash
- **Use prompt caching** on system prompts: `{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}`
- **Model:** `claude-sonnet-4-6` unless you need a cheaper/faster option

### Registration

```bash
# Register MCP server (user-level, loads everywhere including worktrees)
claude mcp add your-server-name -s user -- python3 /path/to/server.py

# Verify registration
cat ~/.claude.json | python3 -c "import json,sys; print(list(json.load(sys.stdin).get('mcpServers',{}).keys()))"
```

After registration: **restart Claude Code** to load new MCP tools.

### Data Patterns

- **SQLite** for queryable structured data (contacts, logs, events)
- **Vault files** as source of truth for Obsidian content — use `python-frontmatter` to read
- **os.walk(followlinks=True)** for vault traversal — never `Path.rglob()` (see Lesson #10)
- **Wikilinks:** Always bare filenames, never path-form: `[[Note Name]]` not `[[folder/Note Name]]`

---

## COMMON PITFALLS

### datetime.utcnow() is deprecated

```python
# WRONG — deprecated in Python 3.12, removed in 3.14
from datetime import datetime
datetime.utcnow()

# CORRECT
from datetime import datetime, timezone
datetime.now(timezone.utc)
```

### Dict access on external data

```python
# WRONG — crashes if key missing
f['rating']

# CORRECT — safe with fallback
f.get('rating', 'N/A')
```

### Module-level Anthropic client crashes when no API key

```python
# WRONG — crashes at import time if no key
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# CORRECT — lazy init, graceful if missing
_client = None
def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return None
        _client = anthropic.Anthropic(api_key=key)
    return _client
```

### macOS symlinks silently skipped by rglob

```python
# WRONG — silently misses symlinked directories (e.g. team vault symlinks)
for f in Path(vault_root).rglob("*.md"):
    ...

# CORRECT
import os
def _walk_md_files(root):
    for dirpath, _, filenames in os.walk(str(root), followlinks=True):
        for fname in filenames:
            if fname.endswith(".md"):
                yield Path(dirpath) / fname
```

---

## LESSONS LOG

### Lesson #1: Background agents can't get interactive permission approvals
**Rule:** Never use background agents for tasks that require file creation (Bash, Write). Build directly in the main session. Background agents work for read-only research but not for builds.

### Lesson #2: Worktree isolation blocks MCP access
**Rule:** Don't use worktree isolation for MCP builds. Each MCP lives in its own directory outside the repo anyway. Use regular agents or build directly.

### Lesson #3: Embed context in agent prompts, don't reference external tools
**Rule:** When delegating to agents, embed ALL needed context directly in the prompt. Never tell an agent to "go read X from MCP Y." Pre-read it and paste the relevant sections.

### Lesson #4: Agents with vault access produce better servers than rushed direct builds
**Rule:** When an agent CAN get permissions (foreground, non-worktree), let it read the actual data. It will produce context-aware code. For background builds, build directly since permissions block.

### Lesson #5: Install dependencies system-wide before testing
**Rule:** After creating server files, immediately install all requirements and run an import test: `python3 -c "import server; print('OK')"`. Don't wait to discover import errors.

### Lesson #6: Agent-built servers may use different dependencies than specified
**Rule:** After an agent builds/modifies a server, re-read requirements.txt and verify the import test still passes.

### Lesson #7: Register MCPs in ~/.claude.json for universal loading
**Rule:** Use `claude mcp add name -s user -- python3 /path/to/server.py` to register at the user level. This loads in all sessions including worktrees. Project-level `.mcp.json` may not load in worktree sessions.

### Lesson #8: Always run the Optimization Pass before writing code
**Rule:** Before writing any code, run the Optimization Pass. Kill unnecessary frontends for internal-only tools. Use SQLite until Postgres is genuinely needed. Remove LLM calls from deterministic operations.

### Lesson #9: Never use Python or LLM for financial math — use Excel formulas
**Rule:** Any agent that produces financial output must generate an Excel file using `openpyxl` with formulas in the cells. Excel's formula engine does the math. Python only writes input values and formula strings.

### Lesson #10: macOS symlinks are silently skipped by Python's rglob
**Rule:** Never use `Path.rglob()` on directories that may contain symlinks. Use `os.walk(root, followlinks=True)`.

### Lesson #11: Always check actual frontmatter field values before writing filters
**Rule:** Before writing any frontmatter filter config, sample actual values from the vault to verify they match what you expect.

### Lesson #12: Verify vault folder paths exist before referencing them
**Rule:** Before adding any path to a sync rule or config, verify it exists with `ls`.

### Lesson #13: Wire agents to real data sources — don't ship stubs
**Rule:** When building an agent that depends on data from an already-built MCP, read that MCP's source and wire to it directly. Stubs are acceptable only for services not yet built. Flag all stubs with `# STUB — replace with {service name}`.

---

## SELF-TEST PROTOCOL

Every MCP server and managed agent must pass a self-test before being considered done:

```python
# At the bottom of server.py or agent.py
if __name__ == "__main__":
    # If called directly (not via MCP), run self-test
    import inspect
    if "mcp" in inspect.signature(mcp.run).parameters:
        mcp.run()
    else:
        self_test()
```

Self-test requirements:
1. Must not crash when `ANTHROPIC_API_KEY` is not set (graceful stub output)
2. Must exercise every tool/function at least once
3. Must print clear pass/fail indicators
4. Must end with `print("Self-test complete.")` and exit 0

---

## POST-BUILD: GITHUB PUBLISHING CHECKLIST

Once an MCP is tested and working, publish it as a standalone GitHub repo:

1. **Strip personal data.** Remove: vault paths, contact names, company-specific config, API tokens, personal anecdotes. Replace with generic examples and env var placeholders.
2. **Create GitHub repo:** `gh repo create yourusername/{name}-mcp --public --description "..."`
3. **Standard files:** README.md, LICENSE (MIT), requirements.txt, server.py or agent.py, .env.example
4. **README must include:** one-line description, install instructions, Claude Code registration snippet, tool list with descriptions, config examples
5. **Test install from scratch:** clone into a temp dir, install deps, run import test, register in .claude.json, verify tools appear in Claude Code
6. **Tag a release:** `git tag v1.0.0 && git push --tags`

---

## WHICH AGENTS ARE WORTH PUBLISHING?

Publish if: the core logic is universal (not company-specific), it composes with common tools (Obsidian, Google Drive, HubSpot), and the config is externalizable via env vars.

| Agent type | Publish? | Notes |
|-----------|---------|-------|
| Vault file classifier/syncer | Yes | Anyone with Google Drive + Obsidian wants this |
| Meeting action item extractor | Yes | Generalize owner list to config file |
| Knowledge graph auto-tagger | Yes | Companion to graphify — same audience |
| Graph State of the Union | Yes | Useful to anyone running graphify quarterly |
| Invoice generator (with local tax law) | No | Tax rules are country-specific |
| Business-specific pipeline | No | Too narrow without heavy reconfiguration |
