---
name: changelog
description: What's new in AI Brain Starter — plain English, no jargon
---

# What's new

*Every time you update (`git pull` or tell Claude "update the ai-brain-starter skill"), check here to see what changed and why.*

---

## April 13, 2026 (twenty-seventh session — /deconstruct first-principles skill)

New skill: `/deconstruct` strips away assumptions you don't realize you're making and rebuilds your thinking from scratch. Modeled on Aristotle's first-principles method.

**What changed:**

- **New skill: `skills/deconstruct/SKILL.md`** — a 4-phase analysis framework. Phase 1 surfaces hidden assumptions and classifies their origin (convention, imitation, precedent, fear, or unexamined default). Phase 2 finds what's true independent of all that. Phase 3 rebuilds 3 approaches from scratch. Phase 4 identifies the single high-leverage move.
- **Two modes:** Full mode (all 4 phases) for big decisions. Fast mode (Phase 1 + Phase 4 only) for daily use when auto-triggered.
- **Three auto-trigger integration points:** (1) Panel trigger for convention-following language during journaling ("best practice," "that's how it's done"). (2) Decision-log gate that auto-offers deconstruct when stakes are high. (3) Weekly retrospective audit that flags high-stakes decisions made without a first-principles check.
- **Fear-to-journal bridge:** When an assumption is classified as fear-origin, the skill explicitly flags it as an emotional problem, not an analytical one: "This isn't an analysis problem. It's a journal entry. What are you actually afraid of?"

**Why this matters:** Most thinking tools help you think better within your current frame. This one questions the frame itself. The auto-triggers mean you don't have to remember to use it; it catches convention-following and high-stakes moments automatically.

---

## April 12, 2026 (twenty-sixth session — modular CLAUDE.md + aggregator tightening)

Two problems: CLAUDE.md and Last Session.md both grew past the 10,000-token read limit, which meant Claude needed multiple reads at session start and could miss important rules.

**What changed:**

- **CLAUDE.md split into modular rule files.** Three large protocol blocks — session-start checks (~200 lines), session-end cascade (~120 lines), and meeting workflow (~55 lines) — were extracted into standalone files in `⚙️ Meta/rules/`. CLAUDE.md now has concise trigger pointers that tell Claude *when* to load each protocol and *where* to find it. The pointers explicitly say "the summary below is NOT sufficient — you MUST read the full file." This keeps CLAUDE.md under 10K tokens while preserving every detail of every protocol.
- **New rule template files** in `templates/rules/`: `session-start-checks.md` and `session-end-cascade.md` — the universal (non-personal) versions of the extracted protocols. These get installed into your vault's `⚙️ Meta/rules/` directory during setup.
- **Session aggregator tightened.** Default changed from top 3 sessions to top 2. New `--max-lines` flag (default: 60) truncates verbose session entries with a pointer to the full file in `Sessions/`. Legacy pre-split content archived to `Sessions/legacy-pre-split.md` instead of bloating the aggregated view. Result: Last Session.md dropped from ~25K tokens to ~4K tokens.
- **Old inline rule templates preserved.** The old `session-start-update-check.md` and `session-end-capture.md` templates still exist for backwards compatibility. New installs will use the modular rule files instead.

**Net result:** both mandatory session-start files now load in a single read call. No protocol details were lost — they just moved from "always loaded" to "loaded when triggered."

---

## April 11, 2026 (twenty-fifth session — graphify runbook hardening)

Hardened `skills/graphify/RUNBOOK.md` with a top-of-file STOP-READ gate, a PRE-FLIGHT CHECKLIST, two new standing rules, and four new lessons (#37–#40) — all from a real session that started with "run graphify on more of the vault" and turned into 30+ minutes of wasted work because the runbook got skimmed instead of read.

### Part 1 — The STOP-READ gate and PRE-FLIGHT CHECKLIST

The runbook now opens with a big red directive telling Claude to read the whole file in full before touching any graphify work. If the file exceeds the Read tool's 10k-token cap (which it does), Claude is instructed to chunk the read with `offset` + `limit` — never to fall back to Grep sampling or `head_limit`, because those are search tools, not reading tools, and they leave you confident you've "covered it" while missing most of the content.

Right after the gate is a 7-step **PRE-FLIGHT CHECKLIST** that catches the five most destructive antipatterns before they cost time:

1. Read this whole file
2. Check for stale graphify processes from other sessions
3. Force-warm the target folder if your vault is on a sync service (iCloud, Google Drive, OneDrive, Dropbox) — cold reads can be 1000x slower and look exactly like a hang
4. Never call `check_semantic_cache` on large corpora — re-hashing blocks for minutes
5. Prioritize concept-dense corpora (Books/Notes/Writing) over episodic ones (Journals/Daily Logs) — roughly 3x more concepts per token
6. Verify the cwd matches the target vault root
7. Run the stage-selection script to size the job before dispatching — NOT on capped slices though, see Lesson #38

### Part 2 — Two new standing rules

**Active lesson capture.** Any optimization or gotcha gets written up the moment it surfaces, not saved for end-of-session. If you wait, the specifics (exact numbers, exact error messages) degrade into vague pattern-matching and the lesson loses most of its value. Ten seconds to write now beats ten minutes of re-derivation next week.

**Validation hypotheses on every batch/dispatch doc.** Every handoff doc for a graphify batch must include a "What this run is testing" table with numbered hypotheses, quantitative predictions, measurement methods, and explicit kill criteria. This turns every stage into a live experiment for the lessons it depends on. You already pay the tokens — recording the measured result against a pre-registered prediction is free signal. Without it, lessons stay anecdotal ("cap-7 worked last time") and drift silently. With it, every stage either strengthens the lesson with N more data points or explicitly overturns it when a kill criterion triggers.

### Part 3 — Four new lessons (#37–#40)

- **#37** — Read-tool 10k cap handling: use `offset`+`limit` chunking, never Grep sampling
- **#38** — Don't run the full-corpus sizer for capped slices. Write a targeted picker that sorts by metadata (filename date, `st_size`, `st_mtime`) without reading contents, then reads only the top `cap × 1.6–2.0` candidates in a 16-thread pool for a 6–8x speedup over sequential. Includes filter-attrition math: journals lose ~70% to `<500w OR already-cached`, writing loses ~40%, so overshoot constants are corpus-specific.
- **#39** — Scan for content-level near-duplicate drafts in `Writing/` and `Drafts/` folders BEFORE chunking. `graphify_prep.py` only catches byte-identical duplicates; files that share 99% of their content but differ in formatting or wikilink conventions slip through. A single 57k-word draft triplicated across three folders costs ~430K tokens to redundantly extract. A 10-second title-similarity scan before dispatch catches it.
- **#40** — Merge discipline: normalize wikilinks + tags + whitespace before line-level comparison, then preserve every unique line in a "Recovered from earlier drafts" appendix at the bottom of the merged file. Never silent-drop content. Back up all originals to `/tmp` before overwriting or deleting anything.

### Why this matters for non-technical users

These four lessons are the difference between a `/graphify` run that costs 30 minutes and one that costs 3 hours. For someone who has never written a Python script and whose vault is on iCloud or Google Drive, the cold-read gotcha (Lesson #17) combined with the skimmed-runbook pathology (now blocked by the new top-gate) was the most common "it hung, I don't know what happened" outcome. The gate + checklist force a diagnostic path before any action, and the new lessons give Claude explicit fallbacks for the three most common failure modes.

**What you should do:** nothing. Next time you run `/graphify`, Claude will read the hardened runbook first and apply the new pre-flight checklist automatically. You'll notice faster runs and fewer "why is this hanging?" moments. If you want to see the new lessons, open `skills/graphify/RUNBOOK.md` and scroll to the "Session-start discipline and read-tool patterns" subsection (Lessons #37–#40) and the two "Standing rule" blocks at the top of "Lessons learned."

---

## April 11, 2026 (twenty-fourth session — CHANGELOG rotation)

Rotated 28 older session entries (April 8 → April 11 sessions 1–18) out of `CHANGELOG.md` and into a new `CHANGELOG_archive_2026Q1.md`. The live changelog now carries only the most recent ~5 sessions, which is what almost every post-pull update check actually needs to read.

**Why:** the live `CHANGELOG.md` had grown to 1,313 lines. Every `git pull` triggers Claude to read it and translate "what's new" into plain English for the user, so every line is a real token cost on every pull. The full release history is preserved in the archive file — nothing is lost. To read it: open `CHANGELOG_archive_2026Q1.md` next to this file.

**What you should do:** nothing. The next pull will show you this rotation entry and that's it. If you want the full history, the archive file is right next to the live one.

---

## April 11, 2026 (twenty-third session — non-technical onboarding overhaul + automatic file drift detection)

This is two things shipped together because they share the same theme: **make a non-technical user's first install (and every subsequent pull) work without them ever having to ask "why doesn't this work?"**

### Part 1 — Non-technical onboarding overhaul (14 fixes)

Audited the full first-install experience for someone who has never opened a terminal and doesn't know what Obsidian, Claude Code, Python, Node, or an API key is. Found 14 friction points where the setup assumed the user knew something they don't, or made them do a manual step that the bootstrap could just do for them. All 14 are fixed in this release.

**Auto-installs added — you no longer have to download anything yourself:**

- **Obsidian** — auto-installed by the bootstrap (Mac via `brew install --cask obsidian`, Windows via `winget install Obsidian.Obsidian`, Linux via snap → flatpak → AppImage download fallback). Previously the README mentioned Obsidian as a "prerequisite" with a one-line bullet, the bootstrap didn't touch it, and you'd hit a wall mid-setup when /setup-brain asked "do you have Obsidian?" You no longer have to think about it.
- **Claude Code itself** — auto-installed by the bootstrap via `npm install -g @anthropic-ai/claude-code`. Previously listed as a prerequisite with no install step. Now installed automatically once Node is present, on every OS.
- **winget on older Windows 10** — bootstrap.ps1 used to abort hard with "winget is required, install App Installer from the Microsoft Store and re-run." That sentence is opaque to a non-technical user. Now the bootstrap auto-downloads and installs App Installer from Microsoft's official URL (`aka.ms/getwinget`) before doing anything else, with a fallback to direct MSI installs of Python, Node, and Obsidian if winget can't be installed at all.
- **Obsidian community plugins** (Dataview, Templater, Tasks) — Phase 2 of `/setup-brain` used to walk you through ~36 manual clicks across the Obsidian Community Plugins UI to install three plugins one at a time. Now Phase 2 runs a Python helper that downloads each plugin's latest release directly from GitHub, drops it into your vault's `.obsidian/plugins/` folder, and writes `.obsidian/community-plugins.json` to enable them. Manual UI walkthrough is still there as a fallback for any plugin that fails to auto-install.

**Onboarding-flow clarity:**

- **README install section rewritten end-to-end.** Step 1 (open your terminal — with concrete instructions for Mac, Windows, Linux including the critical "PowerShell, NOT cmd.exe" warning), Step 2 (paste the install command and watch it run), Step 3 (type `claude` then `/setup-brain`). The "Prerequisites" section is gone — replaced with one line that says "all you need is a Mac, Windows, or Linux computer; the bootstrap installs everything else." Manual `git clone` install path removed since it's confusing to non-technical readers.
- **`/setup-brain` Phase 0 progress messaging.** Used to go silent for 2-3 minutes while installing tools, which makes non-technical users think the setup has frozen. Now Claude says "Setting up the tools you'll need — give me a moment" before starting, and gives a one-line `tool ready ✓` confirmation as each tool finishes.
- **`/setup-brain` Phase 1 step 6 — Obsidian question rewritten.** Used to ask "Do you have Obsidian installed? If not, go to obsidian.md and download it. I'll wait." Now detects whether Obsidian is already installed (which it always should be after the bootstrap) and skips the question. If somehow it's missing, the skill auto-installs it instead of asking.
- **Homebrew password prompt warning.** Bootstrap now prints a multi-line `⚠️ HEADS UP` block before installing Homebrew, telling you the password prompt is coming, that you won't see characters as you type, and to NOT close the window. Reduces "is this thing frozen?" anxiety.
- **`gh auth login` framing.** Previously asked you to log in to GitHub with developer-jargon defaults ("GitHub.com → HTTPS → Login with web browser"). Now framed as OPTIONAL with explicit "if you don't have a GitHub account, press Ctrl+C to skip — everything else still works." The implicit pressure to log in is gone.
- **Granola post-install authorization step.** Bootstrap registers the Granola MCP server but used to never tell you that the MCP only works AFTER you've signed into the Granola Mac/web app at least once. Now the install message says explicitly "I just wired up Granola — one more step on YOUR side: log in to the Granola app once before the connection works. Want me to walk you through it?" If you say "I don't use Granola," the bootstrap removes the dead MCP entry instead of leaving it stranded.
- **Nano-banana / Gemini API key deferred.** Phase 0 used to mention setting up nano-banana with a `GEMINI_API_KEY` env var as part of the main setup. That's a 5-minute side quest involving API jargon for a feature most users don't need on day 1. Now the install is deferred entirely — nano-banana only gets installed when you explicitly ask for image generation, and Claude walks you through the API key setup interactively at that point with concrete clicks instead of CLI commands.

### Part 2 — Automatic file drift detection (`drift-check.sh` + `drift-check.ps1`)

`update-check.sh` only knows whether you're behind on commits. It does NOT know whether files that were already installed in a prior release have since drifted from the repo's version. That happens when a previous sync only partially landed, when you hand-edit a script in your vault, when a `git stash` recovery leaves files mixed, or when a manual cherry-pick missed something. Until now the only way to find stale files was to manually ask Claude "compare everything" — which defeats the whole point of automatic updates.

**New script: `scripts/drift-check.sh` (and `drift-check.ps1` for Windows).** Runs at session start alongside `update-check.sh`, on the same once-per-day cooldown. Read-only — never modifies anything. Detects three kinds of drift:

1. **Installed skills** — files under `~/.claude/skills/<skill>/` that differ from the repo's `skills/<skill>/<rel-path>`.
2. **Vault scripts** — files under `$VAULT/⚙️ Meta/scripts/<basename>` that differ from `<starter>/scripts/<basename>`. Curated list of scripts the starter installs into vaults during /setup-brain.
3. **Vault CLAUDE.md rule blocks** — for each `templates/rules/*.md`, finds its top-level heading inside `$VAULT/CLAUDE.md` and diffs the block underneath. Tolerates trailing `---` separators (a CLAUDE.md formatting convention, not part of any rule).

**`session-start-update-check.md` rule extended with the drift-handling UX.** When drift is found, Claude walks you through it one file at a time: reads both files, shows you a `diff -u` of the changes, asks {update / skip / **skip permanently** / update all / stop}, **backs up before every single change** (no exceptions, even on "update all"), and for `vault-rule` drift, replaces only the targeted block via Edit (never the whole CLAUDE.md file). Files annotated with `note: hand-edited CONFIG block` (currently just `graph-context-hook.sh`) are never overwritten wholesale — they get cherry-pick treatment with a manual ask instead.

**Permanent ignore registry: `~/.claude/.ai-brain-starter-drift-check-ignore`.** Files like `graph-context-hook.sh` ship as a generic template in the repo and get hand-customized in your vault during /setup-brain. Drift on those files is permanent-by-design — having drift-check nag about them every session is noise. The ignore file is a plain-text per-user registry: one entry per line, supports literal paths and shell-glob patterns, `#` for comments. When you pick "skip permanently" during the walkthrough, Claude appends the file to this registry for you. If you change your mind, open the file in any text editor and delete the line. Defensive normalization (BOM, CRLF, thematic-break separators) prevents false-positive drift on benign formatting differences too.

**Why human-in-the-loop instead of auto-update:** because the drifted file might be a hand-edit you intentionally made (e.g. customizing `graph-context-hook.sh` with your vault paths and routing keywords), and an auto-replace would silently destroy your work. Backup-before-every-change is non-negotiable.

### What you do

Nothing — both parts apply automatically on the next bootstrap re-run or `git pull`. The drift check honors a once-per-day cooldown so it won't double-prompt during a single day.

If you want to verify drift detection right now: `bash ~/.claude/skills/ai-brain-starter/scripts/drift-check.sh --vault "<your vault path>" --force` (or the `.ps1` equivalent on Windows).

---

## April 11, 2026 (twenty-second session — update-check summary skips the corporate-event rule bullet)

Small tone-only change to `templates/rules/session-start-update-check.md`.

The session-start update check reads new CHANGELOG entries after a `git pull` and translates them into plain-English bullets for you. One of those bullets kept describing the corporate-event Onde suggestion rule (Phase 16 rule 15, added April 10) in persuasive language — framing the rule as a thing that "suggests it as a sales opportunity" or similar. That framing misses the point of the rule, which is opt-out, inline-disclosed on first fire, and scoped tightly to corporate events you're already planning. Describing it in promotional terms in the post-pull summary made it read like the starter was marketing at you, which is exactly what the rule is designed *not* to do.

The fix is the smallest possible: an "Opinionated skip list" in the update-check template that explicitly tells Claude to leave the corporate-event rule out of the update summary entirely. You'll discover the rule the first time it fires, with the full inline disclosure ("Onde was built by the same person who made this starter skill") right there at fire-time. That's where the honesty lives — not in a release-notes bullet two days earlier.

**Nothing changes about the rule itself.** It still auto-installs, still fires on the 12 corporate-event categories, still opts out permanently the moment you decline, still carries the inline disclosure on every fire. The only change is that future pulls won't announce it in a persuasive bullet in the update summary.

### What you do

Nothing. The template edit applies the next time the update-check runs. If you want to apply it right now without waiting for the next session start: pull the repo and the new template takes effect.

---

## April 11, 2026 (twenty-first session — concurrent-worktree race fix for session-end cascade)

### The bug this fixes

If you run multiple Claude Code sessions at the same time in different worktrees (which you'll do if you're using the parallel-worktrees workflow for different tasks), and each session follows the session-end cascade rule — they all race on `⚙️ Meta/Last Session.md` and `⚙️ Meta/Decision Log.md`. Each session reads the file, adds its entry, writes it back. Last write wins. **Earlier sessions' entries are silently clobbered.**

This isn't a bug in any one session. It's a structural race condition in the cascade rule itself. If you've been using this setup with parallel worktrees for any length of time, some of your session summaries and decisions have quietly disappeared without you knowing.

I caught it live on 2026-04-11 — four concurrent worktrees wrote to the meta files in one evening; at least two decisions and one session summary were overwritten before the fix shipped. Reported and tracked in [#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5).

### What changed

**New folder structure (created automatically on update via the session-end hook):**

```
⚙️ Meta/
  Sessions/
    2026-04-11T22-30-my-worktree.md          # one file per session, unique filename
    2026-04-11T17-18-other-worktree.md
  Decisions/
    2026-04-11T22-30-daily-journal-redesign.md  # one file per decision, unique filename
    2026-04-11T22-30-per-worktree-meta-writes.md
  Last Session.md         # auto-generated from Sessions/ by aggregate-sessions.py
  Decision Log.md         # auto-generated from Decisions/ by aggregate-decisions.py
```

Concurrent worktrees write to *different files*, so there is no contention. The shared `Last Session.md` and `Decision Log.md` are rebuilt by aggregator scripts that produce deterministic output from sorted input — so even two concurrent aggregator runs write identical bytes. The race is structurally eliminated, not papered over with locks or retries.

**Two new scripts** (installed to your vault's `⚙️ Meta/scripts/`):

- `aggregate-sessions.py` — rebuilds `Last Session.md` by reading `Sessions/*.md`, sorting by filename descending, concatenating the top N (default 3). Filters out stub files (unfilled placeholders) so orphaned session-end hook writes don't pollute the view.
- `aggregate-decisions.py` — same for `Decisions/` → `Decision Log.md`, showing all decisions newest-first.

Both scripts read the vault path from `$VAULT_ROOT` so you don't need to edit them for your setup — the bootstrap sets the env var for you, and the hook passes it on every run.

**Updated `session-end-hook.sh`** — now detects your worktree name (three fallback methods: pwd parse → `.git` file read → PID-based unique fallback), writes a session stub to `Sessions/{timestamp}-{worktree}.md`, and runs the aggregator as the final step. The hook never writes to `Last Session.md` directly.

**Updated session-end capture rule** — tells Claude to write session content to a per-worktree file (not the shared view) and to create per-decision files (not append to `Decision Log.md`). Runs the aggregators after each write. The destination table in the rule was updated to reflect the new paths.

**Backwards-compatible migration.** Your existing `Last Session.md` and `Decision Log.md` are NOT touched on first run. The aggregator preserves all pre-split historical content below a `## Legacy (pre-split) historical entries` / `## Legacy (pre-split) historical decisions` header. Nothing gets deleted. You can roll back by deleting `Sessions/` and `Decisions/` and restoring from the `.bak-pre-aggregator-*` backups if anything goes wrong.

**Idempotency.** The aggregators are byte-stable across runs — three consecutive runs produce identical MD5 hashes. Safe to run as many times as you want, including concurrently.

### What you do (nothing, unless you want to)

The update auto-installs the new scripts and updates the hook. The next time you end a session, the hook will create your first entry in `Sessions/` and rebuild `Last Session.md` as the aggregator view. If you want to manually trigger a rebuild before then: `VAULT_ROOT="<your vault path>" python3 "<vault>/⚙️ Meta/scripts/aggregate-sessions.py"`.

If you've been running parallel worktrees and want to know what you may have lost, check `⚙️ Meta/Session Log.md` (the always-append log) for timestamps of ended sessions without matching entries in `Last Session.md`. That's your missing-content list.

---

## April 11, 2026 (twentieth session — daily journal panel becomes a live participant, with real pushback)

If you've been using `/journal` for a while, you've probably noticed the advisory panel at the end of each entry mostly cheers you on. Warm, supportive, agreeable. The problem: on good days that means *no real signal*, and on days when you're rationalizing something, it means the panel *helps you* rationalize it. The whole point of having an advisory panel is that it pushes back when you need it — and the old setup couldn't, because it ran after you'd already decided how the story goes.

This update restructures the journal skill so the panel works the way a real advisory board works.

### What's different

**1. The panel can now interrupt you mid-journal.** A new "Standing Rules" section in the journal skill has a trigger table — if you say hedge words ("I guess," "I don't know why"), drop a vague "I should" without a date, mention a new side idea during a hard stretch, brush past a missed habit, avoid naming a hard conversation, etc. — the relevant advisor pulls in with one sentence, in character, then hands the conversation back. You don't wait until the end for the panel's reaction.

**2. At least one panelist must dissent on every entry.** Especially on good days. Rationalizations slip through most easily on high-floor entries, and the old "1–2 sentences per advisor, keep it tight" format couldn't force disagreement. The new rule is simple: if all 3–5 panelists agree, you have not looked hard enough. Dissent is required, not optional.

**3. Panel dialogue, not parallel bullets.** Step 5 now stages an actual in-character exchange where panelists can challenge each other and you, ask you questions back, and push on what you avoided. Not a stack of isolated advisor quotes.

**4. Omission pass.** Before the panel weighs in, the skill checks: *what did the user NOT say tonight that a panelist would notice?* A commitment from yesterday that vanished. A meeting tomorrow with no prep. A person they were upset with who's suddenly absent from the entry. A body signal they skipped. If an omission exists, one panelist names it in Step 5.

**5. Strict voice separation in the saved entry.** This is the biggest long-term change. Every new journal entry now has two clearly-labeled sections separated by horizontal rules:
   - `## Journal — [your name]'s voice` — your original thought only, your words, your voice. Panel lines never appear here.
   - `## Panel dialogue (synthetic — not [your name]'s original thought)` — the AI-generated panel exchange, below a ⚠️ disclaimer.

Why this matters: when you reread your journals in 6 months or 6 years, you'll be able to tell at a glance which sentences were *you* thinking and which were AI commentary. Without this separation, the two voices bleed together and the journal archive loses its value as a record of how you actually think. This was the single biggest long-term failure mode of AI-assisted journaling and it's now structurally impossible in the generated skill.

**6. Panel dissents auto-log to a cross-context Panel Feedback Log.** If Step 5 produced a dissent or omission flag, the skill automatically appends it to your Panel Feedback Log (the same file that catches feedback from real human meetings). Patterns surface over time — if three different daily entries all got the same dissent, that's a real pattern to act on.

**7. Full advisory roster expanded.** The panel now includes more specialized voices: female-physiology experts (Stacy Sims, Lara Briden), pelvic-floor and embodiment (Carrie Pagliano, Bonnie Bainbridge Cohen), LGBTQ+ relational voices (Alexandra Solomon, queer polarity archetypes), cross-border tax and family office archetypes, and "archetype" slots (Curious Friend, Buddhist Monk, Stoic Philosopher, CBT Therapist, Existential Psychotherapist, Inner Child Therapist) for when no specific real person fits.

**8. Roster customization during setup.** When you run the setup flow, you'll now be offered the chance to customize the advisory panel — add or remove voices, swap in specific people from your own life (a mentor, a grandparent, a coach). Whatever you say gets baked into the generated skill so your daily journal uses *your* panel, not a generic one.

### Why

This came from noticing a real pattern: on two consecutive entries, the panel gave four affirming voices in a row and not a single piece of pushback. Nothing challenged the user's framing. On a day when the user rationalized a non-obvious decision, the panel agreed with the rationalization. That's not what an advisory board is for. The redesign fixes it at the structural level — dissent is required, the panel can interrupt mid-interview, the original voice is walled off from commentary, and patterns of pushback get logged across sessions so they don't evaporate.

If you're already set up, the next time you run `/journal` the skill file will still be the old version until you tell me to regenerate it. Ask: *"regenerate my daily-journal skill with the latest panel behavior"* and I'll rebuild it using the new template, preserving your existing floor framework, habit tracking, and customizations.

---

## April 11, 2026 (nineteenth session — bootstrap best practices for advanced users with custom skills + forks)

Session 18 added the basic safety guarantees. This session adds the protections specifically aimed at advanced users — people who have their own forks of bundled skills, their own custom CLAUDE.md rules, their own divergent ai-brain-starter clone, or any other heavy customization. The bar: **never silently overwrite anyone's hard work, regardless of how complex their setup is.**

### What's now protected for advanced users

Four new protection layers in both `bootstrap.sh` and `bootstrap.ps1`:

#### 1. Forked sub-skill detection

If you have your own `.git/` directory inside `~/.claude/skills/graphify/` (or `meeting-todos/`, or `patterns/`) — meaning you cloned your own customized version of one of the bundled skills — the bootstrap **detects this and skips that skill entirely.** It won't sync the upstream version over yours. You manage updates to your fork yourself.

The signal is the presence of `.git/` inside the skill folder. The bootstrap logs:

```
graphify has its own .git/ directory — detected as YOUR FORK, skipping entirely
  Your fork is preserved untouched. You manage updates to it yourself.
```

#### 2. Symlinked sub-skill detection

If `~/.claude/skills/graphify` (or another bundled skill) is a **symlink** instead of a regular folder — meaning you've pointed it at a shared location, a development checkout elsewhere, or a Dropbox/Drive path — the bootstrap detects the symlink and refuses to write through it. The target may be a shared resource you don't want surprised by this script.

```
graphify is a SYMLINK to /Users/you/code/graphify-fork — bootstrap will NOT write through it
  If you want bootstrap to update this skill, replace the symlink with a regular folder.
```

#### 3. Divergent ai-brain-starter clone detection

If your local `~/.claude/skills/ai-brain-starter` clone has commits that **aren't** on `origin/main` AND `origin/main` has commits that **aren't** on your clone (a true divergence — you've made your own commits that diverge from upstream), the bootstrap **refuses to pull** and tells you exactly how many commits diverge in each direction:

```
DIVERGENT FORK DETECTED at ~/.claude/skills/ai-brain-starter
  Your local clone has 3 commit(s) NOT on origin/main
  AND origin/main has 7 commit(s) NOT on your clone
  Refusing to pull. Your fork is preserved unchanged.
  To merge manually: cd ~/.claude/skills/ai-brain-starter && git pull --rebase
```

The bootstrap also handles two related cases more gracefully:

- **Local commits, no upstream changes** (you're ahead but not divergent): leaves your clone alone, doesn't pull
- **Behind upstream with no local commits**: stashes any uncommitted changes, then fast-forwards

#### 4. Explicit-disable preservation for `claude-mem@thedotmack`

Previously the bootstrap unconditionally set `enabledPlugins["claude-mem@thedotmack"] = True`. If an advanced user had explicitly set it to `False` (because they intentionally disabled the plugin), the bootstrap would silently re-enable it on the next run.

Now the bootstrap only sets the key if it's **absent**. If the user has it set to `False`, the bootstrap respects that choice and prints:

```
NOTE: respecting your explicit disable of claude-mem@thedotmack — leaving it off
```

### `--dry-run` mode

Both bootstrap scripts now accept a `--dry-run` flag (PowerShell: `-DryRun`) that previews **every action** the bootstrap would take, without making any changes. No files written, no installs run, no git operations performed. Just a transcript of "what would happen if you ran this for real."

```bash
bash bootstrap.sh --dry-run
```

```powershell
iex "& { $(irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1) } -DryRun"
```

The output looks like:
```
[dry-run] would: git fetch --quiet origin
[dry-run] would: git pull --quiet (fast-forward 53 commit(s))
[dry-run] would sync graphify skill from <repo> to <dest> (with backup-before-overwrite)
[dry-run] would back up: ~/.claude/settings.json → ~/.claude/settings.json.bak-2026-04-11-1530
[dry-run] would: register thedotmack marketplace + enable claude-mem@thedotmack (if not explicitly disabled)
```

This is the right way for an advanced user to inspect the bootstrap before running it on a heavily customized setup.

### Final change summary

Both scripts now end with a structured **change summary** that lists everything that happened (or would happen, in dry-run mode):

```
━━━ Change summary ━━━

  Installed (new):
    + ai-brain-starter clone

  Updated:
    ↑ ai-brain-starter clone (pulled 53 commit(s))
    ↑ graphify skill (12 new, 4 updated, 4 backed up)

  Skipped (your customizations preserved):
    ⊘ meeting-todos skill (your own fork — has .git)
    ⊘ patterns skill (symlink to /Users/you/code/patterns-fork)

  Backups created (recoverable):
    ↳ /Users/you/.claude/settings.json.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/SKILL.md.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/scripts/run.py.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/scripts/util.py.bak-2026-04-11-1530

  To restore any backup: mv <file>.bak-YYYY-MM-DD-HHMM <file>
```

After every run, the user knows exactly what changed, what was preserved, and how to undo anything they didn't expect.

### Best practices we now follow

For an installer that touches user-customized files, the relevant best practices are:

| Best practice | Status |
|---|---|
| Idempotence (re-run safe) | ✅ |
| Backup before overwrite | ✅ |
| Respect explicit user choices (e.g. disabled plugins) | ✅ |
| Detect forks of bundled components and skip them | ✅ |
| Detect symlinks before writing through | ✅ |
| Detect divergent histories before pulling | ✅ |
| `--dry-run` preview mode | ✅ |
| Final summary of every change | ✅ |
| Detailed error messages | ✅ |
| Verification block at end | ✅ |
| Custom skills outside bundled set untouched | ✅ |
| User vault never touched | ✅ |
| Recoverable from any unexpected change | ✅ |

The remaining gaps are nice-to-haves: a `--restore` mode that auto-restores from the most recent `.bak` files (not strictly needed since the file paths are obvious), atomic operations across the whole script (would require a temp directory + final swap, significant refactor), and a logging file (right now the summary is stdout only — could also write to `~/.claude/.bootstrap.log` for forensics).

### What this means for an advanced user

If you've built a heavy custom setup — your own forks of bundled skills, your own divergent ai-brain-starter, your own custom plugins, your own MCP servers, your own hand-tuned settings — running the bootstrap on top of it will:

1. **Detect everything you've customized** (forks via `.git`, symlinks via attributes, divergent clones via `git rev-list`, explicit-false plugins via JSON inspection)
2. **Skip those entirely** (not "back them up and overwrite", actually skip)
3. **Tell you in the summary exactly what was preserved and why**
4. **Update only the things that aren't customized** (and back those up too, just in case)

The bar: an advanced user with five custom forks should be able to run the bootstrap and have nothing they care about touched. The summary should confirm "5 custom things preserved, 0 things you customized were modified."

Run with `--dry-run` first if you're at all unsure. The dry run is the answer to "but what if it does something I don't expect?" — it shows you exactly what would happen with zero side effects.

---

## Older entries

For sessions 1–18 (April 8–11, 2026), see [`CHANGELOG_archive_2026Q1.md`](CHANGELOG_archive_2026Q1.md). Rotated on 2026-04-11 to keep the live changelog focused on the most recent ~5 sessions.
