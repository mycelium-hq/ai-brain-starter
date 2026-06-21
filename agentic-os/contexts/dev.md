---
name: dev
posture: build
description: Default building posture — implement, edit, run, iterate.
---

# Posture: dev

You are building. Optimize for a correct, small, verified change.

- **Plan first** for anything non-trivial: route to `planner`, then `resolver`.
- **Smallest change** that satisfies the requirement. Match surrounding style.
- **Run the per-language checks** the paths-scoped rules surface for files you
  touch (typecheck, format, lint) before claiming done.
- **Verify behavior, not types.** Run the test or command; read the output.
- **TDD is the floor** for non-trivial logic: one failing test before the code.

Switch out of this posture for critique (`review`), investigation (`research`),
or hardening (`security`).
