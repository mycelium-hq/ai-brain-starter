---
name: cowork-projects
description: How to create project-scoped CLAUDE.md files for Cowork projects
---

# Setting Up Cowork Projects

When you create a Cowork project scoped to a subfolder (e.g., your business folder, writing folder, or journals), Claude only loads the `CLAUDE.md` inside that folder, not the root vault `CLAUDE.md`. This means your project-specific sessions won't have access to vault-wide rules, tool routing, or personal context unless you create a project-scoped CLAUDE.md.

## The architecture

```
Your Vault/
├── CLAUDE.md                    ← root (full vault context, all rules)
├── Business/
│   └── CLAUDE.md                ← business project context
├── Writing/
│   └── CLAUDE.md                ← writing project context
├── Journals/
│   └── CLAUDE.md                ← journal/advisory panel context
└── ⚙️ Meta/
    └── rules/                   ← shared rules (referenced, not duplicated)
```

## What goes in a project CLAUDE.md

Each project-scoped file should include:

### 1. Context header with root reference
```markdown
> This file gives Claude context for the [Project] Cowork project.
> Full vault rules live in the root `/CLAUDE.md` — read that file first
> for operating constraints, session protocol, and tool routing.
```

### 2. Project-specific context
What this project IS, what's currently happening, who's involved, key files, key terms. The things Claude needs to know to be useful without asking you 10 setup questions every session.

### 3. Subset of vault rules
Don't duplicate everything from root CLAUDE.md. Include only:
- Rules that apply to this project's work (e.g., Obsidian rules if you edit vault files)
- Tool routing relevant to this project
- Voice/tone guidance if Claude will draft content

### 4. Vault pointers
Where related content lives outside the project folder (CRM, journals, templates, etc.).

## Template

```markdown
# [Project Name] — Project Context

> Full vault rules live in the root `/CLAUDE.md` — read that file first.

## What This Project Is
[One paragraph. What it does, why it matters, current state.]

## Current Priority
[What's THE thing right now? One sentence.]

## Key Files
- [[Hub Note]] — master index
- [[Key Document 1]] — what it is
- [[Key Document 2]] — what it is

## People
- **Name** — Role. Behavioral note if relevant
- **Name** — Role. Context Claude needs

## Key Terms
- **Term** — what it means in this project (disambiguation)

## Voice & Tone
[If Claude will draft content: how should it sound? What does the user reject?]

## Rules
[Subset from root CLAUDE.md. Only what applies here.]

## Vault Context
[Pointers to related folders outside this project.]
```

## Tips from real usage

**Iterate with Cowork feedback.** After creating your project CLAUDE.md, start a Cowork session and ask Claude: "What's missing from your context file? What would make you more useful here?" The feedback is specific and actionable. Common gaps:
- Product/project description too vague for drafting content
- Missing voice/tone guidance
- Tool routing that references tools not available in this environment
- Missing financial numbers or pipeline state for business projects
- Missing current context (who's been contacted, what's been decided)

**Split tool routing.** If you have connected MCP servers (Apollo, Linear, Gmail, etc.), split your tool routing into "Claude can do directly" (connected tools) vs. "go do this elsewhere" (external tools). Otherwise Claude may redirect you to tools it could actually use itself.

**Don't over-duplicate.** Reference the root `CLAUDE.md` and rules files rather than copying them. The project file should add context, not repeat it. If a rule applies vault-wide, it lives in root. If it's project-specific, it lives here.

**Keep it fresh.** Project context goes stale fast. Update your project CLAUDE.md when priorities shift, team changes, or key decisions get made. A context file from three months ago actively hurts more than it helps.
