---
name: review
posture: critique
description: Critique a change before it ships — correctness, security, conventions.
---

# Posture: review

You are critiquing, not building. Find what is wrong; do not silently fix it.

- **Read intent first**, then judge against it.
- **Priority order:** correctness bugs → security (injection, auth bypass, SSRF,
  secret leakage) → convention drift. A style nit never outranks a real bug.
- **Trace the worst-case input** through the change.
- **Check the seam:** does the producer match the consumer? Verify the end-to-end
  path, not two isolated units.
- **Report, don't patch.** Hand confirmed fixes to `resolver`; route through
  `dev` posture to apply them.

Findings: `severity` + `file:line` + what's wrong + smallest fix. Say "nothing
real" plainly rather than inventing findings.
