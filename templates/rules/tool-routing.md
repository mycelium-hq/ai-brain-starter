# Tool Routing

You likely have paid plans or free tiers on many tools. **Don't burn Claude tokens when another tool is better.**

| Task | Route to | Not here |
|------|----------|----------|
| Quick research / "what is X" / market data | **Perplexity** or similar research tool | Don't search the web here |
| Deep autonomous research + deliverables (investor lists, competitor analysis, one-pagers, outbound emails, pitch decks, ROI calculators, account proposals, pricing models, SOPs, KPI dashboards) | **Manus AI** or similar research agent | Don't spend 30min on research or produce sales/ops deliverables here |
| Meeting transcription + notes | **Granola**, **Otter.ai**, or similar meeting tool | Don't manually transcribe |
| Product specs / PRDs / feature docs | **ChatPRD** or similar PRD tool (MCP if available) | Don't write PRDs here |
| Image generation | **Gemini Pro** (API), **DALL-E**, or **Canva** | Route to whichever you have access to |
| Website building / landing pages | **Framer**, **Webflow**, or similar | Don't build HTML sites here |
| UI/UX design reference | **Mobbin** or similar pattern library | Don't describe UI patterns verbally |
| Product analytics / user tracking | **PostHog**, **Mixpanel**, or similar | Don't build analytics manually |
| Workflow automation (connect APIs, auto-import) | **n8n**, **Zapier**, or **Make** | Don't script one-off automations |
| Sprint planning / issue tracking | **Linear**, **Jira**, or similar | Don't track sprints in markdown |
| CRM / sales pipeline | **HubSpot**, **Salesforce**, or similar | Don't build pipeline trackers in Obsidian |
| Design prototyping | **Figma** or similar | Don't describe mockups in text |
| Code editing / AI pair programming | **Cursor**, **Windsurf**, or similar | Use Claude Code for vault/orchestration work |
| Cloud deployment | **Railway**, **Vercel**, or similar | Don't write deploy scripts here |
| Sales prospecting / enrichment | **Apollo**, **ZoomInfo**, or similar | Don't manually research contacts |
| Productivity data / time tracking | **RescueTime** (MCP if connected, read-only) | Don't estimate time manually. Pull live data via MCP during weekly reviews. Session time logged auto to Time Tracking file. See POWER_TOOLS.md for setup. |
| Building custom MCP servers | **FastMCP** | 10-line Python servers with decorators; use for any custom connector |
| Browser testing / regression suites / form validation | **Playwright** | Don't use Claude in Chrome or Computer Use for repeatable tests |
| Web scraping / structured data extraction from pages | **Playwright** (headless, lower tokens) | Don't screenshot + OCR when DOM access works |

**When to redirect:** *"This is a [tool] task, do it there, paste the result here if you need me to process it."*

**Proactive routing rule:** Don't just check this table when you're about to *do* work. Also check it when you're *planning* work. If a planning conversation produces a list of things to build, spec, research, or design, scan every item against this table BEFORE offering to do it yourself. The redirect should happen at the planning stage, not after you've already started.

**When to stay here:** Vault operations, multi-tool orchestration (Gmail + Calendar + Slack + Drive), writing narrative/pitch content, complex analysis across vault files, bulk edits, theme/plugin work.

### Browser tool routing
| Need | Tool | Why |
|------|------|-----|
| Repeatable test suite (forms, flows, regression) | **Playwright** | Headless, assertions, pass/fail reports, cross-browser |
| Scrape structured data from a URL | **Playwright** | DOM access without rendering screenshots, lowest token cost |
| Interactive one-off checking ("does this page look right?") | **Claude in Chrome** | Real-time AI reasoning about what it sees |
| Cross-app desktop workflows (native apps) | **Computer Use** | Only tool that works outside the browser |
| Dev server preview during coding | **Claude Preview** | Purpose-built for local dev verification |

### In-vault search routing
| Need | Tool | Why |
|------|------|-----|
| Keyword/exact match | `obsidian search` or Grep | Fastest for known terms |
| Structural neighbors ("what links to X?") | graphify graph.json query | Explicit relationships, communities |
| Semantic similarity ("what else talks about themes like X?") | Smart Connections sidebar in Obsidian | Finds conceptually related notes even without shared links or keywords |
| Visual graph exploration | Neo4j Browser or Juggl in Obsidian | Cypher queries, visual cluster browsing |
