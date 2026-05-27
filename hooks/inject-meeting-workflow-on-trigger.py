#!/usr/bin/env python3
"""
UserPromptSubmit hook: detect "I just had a meeting" (and bilingual / phrasing
variants), then inject the user's meeting-workflow.md rule as additionalContext
so the full post-meeting cascade fires automatically.

Pre-fix bug class: ARTIFACT-WITHOUT-AUTOMATION-WIRING. The rule existed in the
user's vault at `⚙️ Meta/rules/meeting-workflow.md` and README/POWER_TOOLS.md
promised "the rule fires" — but no hook surfaced the rule on the trigger
phrase. Claude had only a one-time SessionStart bullet to remember it. Users
reported "I said 'I just had a meeting' and nothing happened" — the cascade
silently no-op'd because the rule was never in context at the moment of need.

Pattern: inject-best-of-best-on-consulting.py + inject-love-language-context.py.
UserPromptSubmit -> regex prompt -> read vault rule -> inject additionalContext
-> exit 0 always (never block).

Vault root auto-detection (in order):
  1. VAULT_ROOT env var
  2. Walk up from cwd looking for `⚙️ Meta/Current Priorities.md`
     (canonical marker) or any `⚙️ Meta/` / `Meta/` folder
  3. Silent exit if not found

Rule file lookup order (first hit wins):
  1. <vault>/⚙️ Meta/rules/meeting-workflow.md (canonical, emoji folder)
  2. <vault>/Meta/rules/meeting-workflow.md (no-emoji fallback)
  3. ~/.claude/skills/ai-brain-starter/templates/rules/meeting-workflow.md
     (template fallback — only fires if the user never ran Phase 4)
  4. Embedded minimal summary (last-resort, keeps the cascade non-silent)

Bypass: set env var MEETING_WORKFLOW_BYPASS=1 (or include the literal token
in the prompt) to suppress the injection on a single prompt.

Wire into settings.json under hooks.UserPromptSubmit:
    {
      "type": "command",
      "command": "python3 ~/.claude/skills/ai-brain-starter/hooks/inject-meeting-workflow-on-trigger.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
    }
"""
import json
import os
import re
import sys
import unicodedata
from typing import Optional

MAX_RULE_CHARS = 8000  # truncate very large customized rules
BYPASS_ENV = "MEETING_WORKFLOW_BYPASS"
BYPASS_TOKENS = ["MEETING_WORKFLOW_BYPASS=1", "ignore meeting workflow"]

# Trigger regexes. Each requires a temporal "just / done / ended / finished"
# anchor so generic mentions of "meeting" (future / past-week / planning) do
# NOT fire. English first, then Spanish — the public starter is bilingual.
#
# Modifier slot `(?:\w+\s+){0,4}` allows compound noun phrases — "discovery
# call", "kickoff meeting", "team sync", "my client interview" — without
# admitting cross-sentence false positives, because punctuation breaks \w+.

# Noun lists. Hyphens kept inside the compound-modifier slot (so "all-hands",
# "kick-off", "stand-up" survive as a single token). After strip_accents,
# "reunión" → "reunion", "sesión" → "sesion".
NOUN_EN = (
    r"meeting(?:s)?|call(?:s)?|sync(?:s)?|standup(?:s)?|stand-?up(?:s)?|"
    r"1[:\- ]on[:\- ]1|1[:\- ]1|one[:\- ]?on[:\- ]?one|"
    r"interview(?:s)?|huddle(?:s)?|conversation(?:s)?|chat(?:s)?|catch[\-\s]?up(?:s)?|"
    r"check[\-\s]?in(?:s)?|session(?:s)?|demo(?:s)?|kickoff(?:s)?|kick[\-\s]?off(?:s)?|"
    r"retro(?:s)?|retrospective(?:s)?|review(?:s)?|briefing(?:s)?|workshop(?:s)?|"
    r"offsite(?:s)?|alignment(?:s)?|all-?hands"
)
NOUN_ES = (
    r"reunion(?:es)?|llamada(?:s)?|sync(?:s)?|standup(?:s)?|stand-?up(?:s)?|"
    r"entrevista(?:s)?|conversacion(?:es)?|charla(?:s)?|junta(?:s)?|reu|"
    r"demo(?:s)?|kickoff(?:s)?|sesion(?:es)?|check[\-\s]?in(?:s)?|taller(?:es)?|"
    r"meeting(?:s)?|call(?:s)?"  # bilingual users mix EN/ES in the same sentence
)

# Determiner classes. Required after a "I just <verb>" anchor so verb-of-action
# usages (e.g. "I just had to call the bank") cannot match — no det between
# "had" and the noun → no fire. Modifier slot uses `[\w\-]+` so hyphenated
# compounds like "all-hands" / "kick-off" / "one-on-one" count as one token.
DET_EN = r"a|an|the|my|our|your|today'?s|that|this|some|another"
DET_ES = r"una|la|mi|nuestra|el|este|esa|esta|nuestro|otro|otra"
MOD = r"(?:[\w\-]+\s+){0,3}"  # 0-3 hyphen-aware adjective tokens

TRIGGERS_EN = [
    # "I just <verb> <det> [adj×0-3] <noun>" — the standard form.
    rf"\bi\s+just\s+(?:had|finished|wrapped(?:\s+up)?|got\s+out\s+of|came\s+out\s+of|ended|got\s+off)\s+"
    rf"(?:{DET_EN})\s+{MOD}({NOUN_EN})\b",
    # "Just <verb> <det> [adj×0-3] <noun>" — terse, no "I".
    rf"\bjust\s+(?:had|finished|wrapped(?:\s+up)?|got\s+out\s+of|came\s+out\s+of|ended|got\s+off)\s+"
    rf"(?:{DET_EN})\s+{MOD}({NOUN_EN})\b",
    # "<det> [adj×0-3] <noun> [with X×1-5] just (ended|wrapped|finished|is done)"
    rf"\b(?:{DET_EN})\s+{MOD}({NOUN_EN})\s+(?:with\s+(?:[\w\-]+\s+){{1,5}})?(?:just\s+)?"
    rf"(?:ended|wrapped(?:\s+up)?|finished|is\s+done|was\s+done|is\s+over)\b",
    # "<noun> [with X×1-5] just (ended|wrapped|...)"  — no det, e.g. "meeting just ended"
    rf"\b({NOUN_EN})\s+(?:with\s+(?:[\w\-]+\s+){{1,5}})?(?:just\s+)?"
    rf"(?:ended|wrapped(?:\s+up)?|is\s+done|was\s+done|is\s+over)\b",
    # "[name]'s [adj×0-2] <noun> (is done|just ended|...)"
    rf"\b[\w\-]+(?:'s|s')\s+(?:[\w\-]+\s+){{0,2}}({NOUN_EN})\s+"
    rf"(?:is\s+done|just\s+ended|ended|wrapped|finished)\b",
    # "done|finished with <det> [adj×0-3] <noun>"
    rf"\b(?:done|finished)\s+with\s+(?:{DET_EN})\s+{MOD}({NOUN_EN})\b",
    # "wrapped (up) <det> [adj×0-3] <noun>"
    rf"\bwrapped(?:\s+up)?\s+(?:{DET_EN})\s+{MOD}({NOUN_EN})\b",
    # "Pull|process|file|save|capture|extract [det] [adj×0-3] (notes|transcript|...)"
    # Artifact list — pull/process targeting the meeting artifact.
    rf"\b(?:pull|process|file|save|capture|extract)\s+(?:{DET_EN}|all)?\s*"
    rf"{MOD}(?:notes?|transcripts?|recordings?|granola|action\s+items?|to-?dos)\b",
    # "Pull|process|file|... <det> [adj×0-3] <noun>" — det REQUIRED so verb-of-
    # action usages can't match ("pull request review" has no det after "pull"
    # → no fire). "process today's meeting" / "file the standup note" → fire.
    rf"\b(?:pull|process|file|save|capture|extract)\s+(?:{DET_EN})\s+"
    rf"{MOD}({NOUN_EN})\b",
    # "I just got off the phone (with X)" — phone-call end signal.
    r"\b(?:i\s+just\s+)?got\s+off\s+the\s+phone\b",
]

TRIGGERS_ES = [
    # "acabo de (tener|terminar|salir del?|colgar) [det] [adj×0-3] <noun>"
    rf"\bacabo\s+de\s+(?:tener|terminar|salir\s+del?|colgar)\s+"
    rf"(?:(?:{DET_ES})\s+)?{MOD}({NOUN_ES})\b",
    # "(la|mi|...) [adj×0-3] <noun> [con X] (ya|recien) (termino|acabo|...)"
    rf"\b(?:{DET_ES})\s+{MOD}({NOUN_ES})\s+(?:con\s+(?:[\w\-]+\s+){{1,5}})?"
    rf"(?:ya\s+)?(?:recien\s+)?"
    rf"(?:termino|acabo|se\s+acabo|se\s+termino|fue|ya\s+acabo|ya\s+termino|acabo\s+de\s+terminar)\b",
    # "<noun> con X [ya] (termino|acabo|...)"
    rf"\b({NOUN_ES})\s+con\s+(?:[\w\-]+\s+){{1,5}}"
    rf"(?:ya\s+)?(?:termino|acabo|se\s+acabo|ended|ya\s+termino|ya\s+acabo)\b",
    # "ya (termine|acabe|sali de) [det] [adj×0-3] <noun>"
    rf"\bya\s+(?:termine|acabe|sali\s+del?)\s+(?:(?:{DET_ES})\s+)?{MOD}({NOUN_ES})\b",
    # "trae|saca|pull|... [det] (notas|transcript|...) [de [det] [adj×0-3] <noun>]"
    rf"\b(?:trae|saca|pull|busca|consigue|extrae)\s+(?:las|los|mis|el|la|todas?|todos?)?\s*"
    rf"{MOD}(?:notas|transcript|transcripcion|grabacion|granola|to-?dos|tareas|pendientes)"
    rf"(?:\s+del?\s+(?:(?:{DET_ES})\s+)?{MOD}({NOUN_ES}))?\b",
]


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize(s: str) -> str:
    return strip_accents(s).lower()


def matches_trigger(prompt: str) -> Optional[str]:
    """Return the matched substring if any trigger fires, else None."""
    p = normalize(prompt)
    for regex in TRIGGERS_EN + TRIGGERS_ES:
        m = re.search(regex, p)
        if m:
            return m.group(0)
    return None


def find_vault_root() -> Optional[str]:
    """Walk up from cwd looking for the canonical Current Priorities marker
    or a Meta/ folder. VAULT_ROOT env var wins if set."""
    env_root = os.environ.get("VAULT_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root
    cur = os.getcwd()
    for _ in range(8):
        # Canonical marker
        for meta in ("⚙️ Meta", "Meta"):
            if os.path.isfile(os.path.join(cur, meta, "Current Priorities.md")):
                return cur
            if os.path.isdir(os.path.join(cur, meta, "rules")):
                return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def find_rule_file(vault_root: Optional[str]) -> Optional[str]:
    """Locate meeting-workflow.md. First the vault's installed copy
    (preferred — carries Phase 11 per-tool customization), then the
    ai-brain-starter template as a fallback."""
    if vault_root:
        for meta in ("⚙️ Meta/rules", "Meta/rules"):
            path = os.path.join(vault_root, meta, "meeting-workflow.md")
            if os.path.isfile(path):
                return path
    template = os.path.expanduser(
        "~/.claude/skills/ai-brain-starter/templates/rules/meeting-workflow.md"
    )
    if os.path.isfile(template):
        return template
    return None


def read_rule(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""
    if len(content) > MAX_RULE_CHARS:
        content = content[:MAX_RULE_CHARS] + "\n...[truncated — read full file at " + path + "]"
    return content


FALLBACK_SUMMARY = """[meeting-workflow fallback — vault rule file not found]

The user just signaled a meeting ended. Run the standard post-meeting
cascade WITHOUT asking for clarification:

1. Find the transcript. Check Granola (~/Library/Application Support/
   com.granola.granola/), Google Meet+Gemini transcripts in Drive,
   Otter/Fireflies/Zoom export folders, or the Meeting Notes/ folder
   in the vault — whichever tool the user configured. Search the LAST
   24 HOURS in parallel.
2. Read the transcript in full. Never skim. Verbatim transcript wins
   over post-processed summaries.
3. Enrich the meeting note in the vault: TL;DR, decisions table,
   action items, verbatim quotes, meta-observations. Wikilink every
   named person to their CRM file.
4. Cascade to canonical docs. Update strategy/vision/target docs
   the meeting changed. Rule-consistency scan after rule edits.
5. Update Decision Log. One entry per high-stakes decision: What/
   Why/Floor/Stakes/Speed.
6. Update each attendee's CRM file: meeting notes wikilink, refreshed
   last_interaction / next_step. Read 2 adjacent CRM files first to
   confirm the pattern. Preserve dataview blocks.
7. Update to-dos. Business -> team to-do file. Personal -> personal
   to-do file. Never duplicate. Default personal when ambiguous.
8. Humanizer pass on any external-facing prose written.
9. Verify with backlinks: open the CRM file, confirm the meeting
   note shows up. Open the to-do file, confirm team embeds render.
10. Report every file changed, flag what the user should eyeball,
    state which sources were read with byte counts as evidence.

If no transcript or notes file is found in step 1, SAY SO immediately
— do not invent a meeting note from chat context.
"""


def main() -> int:
    if os.environ.get(BYPASS_ENV) == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = payload.get("prompt", "") or ""
    if not prompt.strip():
        return 0
    for token in BYPASS_TOKENS:
        if token in prompt:
            return 0

    match = matches_trigger(prompt)
    if not match:
        return 0

    vault_root = find_vault_root()
    rule_path = find_rule_file(vault_root)
    if rule_path:
        rule_body = read_rule(rule_path)
        if rule_body:
            header = (
                "[meeting-workflow auto-injected — trigger matched: "
                f"{match!r}]\n"
                "The user just signaled a meeting ended. Run the FULL cascade "
                "below WITHOUT asking for clarification. Source rule: "
                f"{rule_path}\n"
            )
            body = header + "\n" + rule_body
        else:
            body = FALLBACK_SUMMARY
    else:
        body = FALLBACK_SUMMARY

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": body,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
