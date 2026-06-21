---
name: typescript
paths: ["**/*.ts", "**/*.tsx"]
description: Quality rules applied automatically to TypeScript files on edit.
---

# TypeScript rules

These apply automatically when you edit a `.ts` / `.tsx` file — the
`paths_scoped_rules` hook matches the glob above and surfaces this block. No
per-file wiring.

- **Types must check.** `tsc --noEmit` passes — no type errors, no new `any`.
- **Format.** `prettier --check` (or your formatter) on touched files.
- **No `console.log`** in committed code — use the project logger.
- **No `// @ts-ignore`** without a one-line reason on the same line.
- **Imports resolve.** No unused imports; no deep relative `../../../` when an
  alias exists.

Tune this list to your stack. The glob (`paths:`) decides which files it governs;
edit the glob, not the wiring.
