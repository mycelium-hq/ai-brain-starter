---
name: warn-dev-repo-shared-checkout
enabled: true
event: bash
action: warn
conditions:
  - field: command
    operator: regex_match
    pattern: cd\s+(?:~|\$HOME|/Users/[^/]+|/home/[^/]+)/dev/(your-shared-repo-1|your-shared-repo-2|your-shared-repo-3)(?=[/\s;&|]|$)
---

**You're cd'ing to a shared `~/dev/<repo>` checkout.** Multiple concurrent Claude sessions running against the same physical checkout collide on the single `.git/HEAD` pointer + index + working tree. Symptoms observed in prior sessions: commits land on a sibling session's branch by accident, sibling reverts edits mid-build, stash-vs-untracked recovery wastes 5+ tool calls.

If this session is going to **write** code to this repo (commit, push, edit), switch to a per-session worktree FIRST:

```bash
# At session start
claude-dev-worktree start your-shared-repo-1 my-task-slug
cd ~/dev/your-shared-repo-1-my-task-slug
# all work happens here — isolated HEAD, no collision with sibling sessions
```

At session close (after PR merges):

```bash
claude-dev-worktree cleanup your-shared-repo-1 my-task-slug
```

If this session is **read-only** (`git log`, `git diff`, `cat`, `grep`, audit-only) — the main checkout is fine. No need to worktree for read-only access.

If you've already created a worktree but cd'd back to the main checkout by mistake, switch back:

```bash
cd ~/dev/<repo>-<slug>
```

## Customize the repo list

Edit the `(your-shared-repo-1|your-shared-repo-2|your-shared-repo-3)` capture group in this file's frontmatter `pattern` to match the repos in your environment where you've observed concurrent Claude sessions. Examples that would belong on the list:

- A monorepo that multiple feature work-streams hit simultaneously
- A repo where you frequently run parallel Claude sessions on different Linear issues
- Any repo where you've experienced HEAD-drift corruption before

A repo with a single concurrent-session ceiling (e.g. a personal tool only one session ever touches) does NOT need to be on the list — the warn would be noise.

## Bypass

`DEV_WORKTREE_BYPASS=1 <command>` when you've verified there's no sibling session active (rare — typically only solo audit work where the warn would be noise).

## Lineage

Full rule + wrapper script + lineage in the parent skill `dev-repo-worktrees/SKILL.md`. Bug class: `CONCURRENT-SESSION-HEAD-DRIFT`.
