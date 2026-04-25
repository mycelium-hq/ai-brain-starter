---
type: runbook
---

# Build Standards

> Read this BEFORE any artifact-specific build runbook. Applies to all build types: MCPs, skills, routines, API integrations, scripts, managed agents.
>
> The MCP Build Runbook (`docs/MCP_BUILD_RUNBOOK.md`) extends this for MCP-specific patterns and lessons. Skills, routines, and other artifact types inherit these rules directly.

---

## PRE-BUILD CHECKLIST

Run before every new build, regardless of artifact type.

1. **Check what you already own.** Scan your skills directory, your MCPs, and any connected SaaS tools (CRM, email, analytics, workflow). Don't build custom when you can wire. Many "features" are a single config change in a tool you already pay for.
2. **Search for existing implementations first.** Before writing a single line, search GitHub for `"{service/concept} {artifact type} GitHub"`. Audit the top 3-5 candidates: coverage, language, auth, stars/activity, gotchas. Fork if a repo is already 90%+ of what you need. See the MCP Build Runbook for the audit template.
3. **Read the official API/docs end-to-end.** Existing repos only expose what their builders cared about. Go to the official reference and scan every section. List every endpoint or feature your use case could benefit from, including ones no existing repo exposes.
4. **Run the Optimization Pass** (see section below). Mandatory before writing any code.
5. **Document-heavy builds: pre-extract the spec.** If the spec is >500 words of PRD/API docs, run it through a cheap extractor model first and feed the structured output to your main build model. Saves tokens and keeps focus on architecture.

---

## OPTIMIZATION PASS (mandatory before every build)

Run this audit on the spec/PRD before writing any code. The goal: build only what genuinely needs to be built, at the right complexity level.

### 1. Stack redundancy check
For every component in the spec, ask: does an existing tool handle this already?

| Spec says | Check this first |
|-----------|-----------------|
| Dashboard / reporting UI | Your CRM's native reporting, Google Sheets, or your analytics tool's built-in dashboards |
| Scheduling / cron | Workflow tools (n8n, Zapier, Make), Claude scheduled tasks |
| Email sending | Your CRM's sequences, Gmail MCP |
| CRM data | Your existing CRM — don't build a second one |
| File classification | Rules-based Python — no LLM API needed |
| Web scraping | Playwright plugin |
| Document storage | Vault files — no new DB needed |
| Analytics | Whatever analytics tool you already have |

### 2. Frontend complexity check
Most internal tools don't need a full React stack. Before building Next.js + a component library:
- **Is the only user you?** If yes: FastAPI + Jinja2 template, or just a Google Sheet, is sufficient.
- **Is it purely internal operations?** A Slack bot or terminal output is often enough.
- **Does it need real-time updates?** If not, static HTML + a cron refresh is simpler.
- **Rule:** Next.js is justified only when the tool has external users, complex interactivity, or is being published publicly.

### 3. Database size check
Before reaching for Postgres/Supabase:
- Weekly snapshots for 90 days = 52 rows. That's SQLite.
- Hundreds to low thousands of rows = SQLite.
- Supabase/Postgres is justified only when: multi-user concurrent writes, >100k rows, or cross-service DB access.

### 4. LLM usage check
Not everything needs an LLM. Flag and remove LLM calls where:
- The logic is purely rule-based (file classification, field mapping, regex extraction)
- The output is deterministic math (invoice totals, commission calculations)
- The operation is just format conversion (JSON to markdown, YAML parsing)
- **Rule:** LLM API calls add latency and cost. Use only where the LLM is genuinely making a judgment call.

### 4a. Structured-signal-first audit (mandatory before any LLM batch over vault files)

Before iterating an LLM over a folder of files, audit what structured signal already exists in those files. Past automation passes (extractors, mappers, prior LLM runs) almost always leave extracted fields, wikilinks, themes, or numeric tags behind. Reaching for the LLM as the first tool when existing signal already covers 60%+ of the judgment burns hours and dollars for no gain.

The pre-batch audit (≤5 minutes, mandatory):

1. **Frontmatter scan.** Read 5-10 sample files and list every field. Look especially for: `concepts_extracted`, `themes`, `tags`, `entities`, anything with `_extracted`, `_score`, or `_confidence`. These are usually prior LLM output already on disk.
2. **Wikilink density.** Count `[[X]]` references per file. If the body links to the concepts you're about to classify, the wikilinks ARE the classification — count them, don't re-derive them.
3. **Cross-reference against the question.** Ask: "If I just used this existing signal, what % of files would resolve unambiguously?" If ≥60%, build a Python heuristic FIRST, then LLM only the residual ambiguous cases.
4. **LLM as tiebreaker, not first pass.** The LLM call should be last-resort, not default. Pure-Python over structured signal is seconds and free; LLM over the same files is hours and dollars.

**Failure mode this prevents:** A "classify N files against schema X" task goes straight to an LLM batch at ~10s per call × 2,000 files = ~5 hours and significant API spend. The frontmatter and body of each file already contained the schema labels in machine-readable form, but the audit wasn't run, so the existing signal was re-derived. A high-precision Python pass (only flag cases where existing signal is overwhelming, punt the residual ambiguous tail to LLM) handles 80%+ of cases in under a minute, with LLM reserved for the genuinely contextual cases. Skipping the audit costs orders of magnitude more time and money than running it.

**Codification:** When a build calls for "iterate an LLM over N files in folder X," the pre-build checklist MUST include a frontmatter sample + wikilink count + a one-paragraph "what existing signal covers" before code is written. If the audit shows ≥60% existing-signal coverage, the build is Python-first with LLM as tiebreaker.

### 4b. Financial math goes in Excel — not Python, not LLM
Any build that outputs money amounts (invoices, commissions, budgets, tax calculations) must generate an Excel file with formulas. Excel's engine does the math. Python only writes input values and formula strings.
- Use `openpyxl` — formula strings like `"=B3*0.11"` are written as cell values
- The spreadsheet is the auditable source of truth; JSON/dict output is a summary
- Regulated financial output (tax, payroll, invoicing in many jurisdictions) requires traceable calculation methodology — Excel provides it
- Add `openpyxl>=3.1.0` to any requirements.txt that handles financial output

### 5. Cross-artifact shared code
When building multiple agents/scripts in the same session, look for shared patterns to extract:
- LLM client setup with prompt caching
- Error handling and retry logic
- Vault write helpers
- Notification senders (Slack, email)
- Common data models
- **Rule:** If two artifacts share >20 lines of logic, extract to a shared `utils.py` in a common directory.

### 6. Integration with existing MCPs and tools
Check if a new build should call an already-built MCP instead of re-implementing:
- Scheduling features should call your calendar MCP, not reimplement it
- Any vault read/write should go through a single vault helper
- **Rule:** Agents and MCPs should compose, not duplicate.

### Document your optimization decisions
In the build log entry, add an "Optimizations applied" row noting:
- What you simplified vs the spec/PRD
- What you decided NOT to build (and why)
- Any shared code extracted

---

## GENERAL BUILD RULES

These rules apply to every artifact type.

- **Embed context in agent prompts.** When delegating to sub-agents, paste the relevant content directly. Never tell an agent to "go read X from MCP Y" — it won't have access. Pre-read and include.
- **Wire to real data, not stubs.** Before shipping, check if a dependency already has a live DB, API, or endpoint. Stubs are only acceptable for services not yet built. Flag all stubs with `# STUB: replace with {service name}` so they're never accidentally shipped.
- **Financial math goes in Excel.** Any output involving money amounts must use openpyxl with formula strings, not Python arithmetic. See section 4b above.
- **Glob before Write in any directory you didn't just create.** A prior session or sub-agent may have already written files there. Read before overwriting.
- **Verify file paths and config values exist before referencing them.** A path in a config that doesn't exist silently matches zero files. Confirm with `ls` or `Glob` first.

---

## BUILD ONLY WHAT YOU DON'T ALREADY OWN

Before building any component, do a one-minute audit: what already exists in your stack that covers this? Common coverage areas include workflow orchestration, CRM, contact enrichment, analytics, deployment, issue tracking, scheduling, web scraping, and library documentation. If an existing tool covers 80% of the need, wire it up and only build the remaining 20%.

Skip any build step where the "custom" implementation would just be a thin wrapper over a capability you already pay for.
