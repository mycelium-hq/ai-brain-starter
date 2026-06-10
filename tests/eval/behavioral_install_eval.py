#!/usr/bin/env python3
"""behavioral_install_eval.py — periodic behavioral eval of the install surface.

The static guard (tests/integration/test_trust_prompt_preframing.sh) asserts
the README CONTAINS the right directives. This eval asserts the directives
WORK: a fresh model handed the README, in the role of the assistant a real
installer talks to, must commit to RUNNING the install as its next action —
not put up a menu, not stall for a second confirmation, not downgrade to a
/plugin-only install, not ask to review the script first. Those four are the
exact failure modes observed in real installs (June 2026 incident class:
AGENT-ONBOARDING-DOC-CAUSES-MENU-OR-STALL).

How it works (eval-gates pattern: fixtures + self-consistency + a control):
  1. SUBJECT: claude-sonnet plays a fresh Claude Code session. User asks
     "set this up for me" with README.md attached. N=3 samples.
  2. JUDGE: claude-haiku classifies each subject reply into one verdict:
     RUN_INSTALL | MENU | CONFIRM_STALL | PARTIAL_INSTALL | REVIEW_FIRST | OTHER.
     Pre-framing the two expected approval prompts while committing to run
     still counts as RUN_INSTALL (pre-framing is the DESIRED behavior).
  3. VOTE: PASS needs >= 2/3 RUN_INSTALL on the real README.
  4. NEGATIVE CONTROL: the same harness on a deliberately caution-primed,
     menu-offering fixture README must NOT pass — proves the eval can fail.
     A guard only earns trust by failing on the thing it catches.

Runs WEEKLY via .github/workflows/behavioral-install-eval.yml (scheduled,
not per-PR: it costs real API calls and measures doc behavior, not diffs).

Local run:  ANTHROPIC_API_KEY=... python3 tests/eval/behavioral_install_eval.py
Exit codes: 0 pass · 1 behavioral failure · 2 config/infra error (loud, so a
dead CI secret reads as INFRA, never as a green skip — fail closed).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
README = REPO_ROOT / "README.md"
NEGATIVE_CONTROL = REPO_ROOT / "tests" / "eval" / "fixtures" / "install-readme-negative-control.md"

SUBJECT_MODEL = os.environ.get("EVAL_SUBJECT_MODEL", "claude-sonnet-4-6")
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-haiku-4-5-20251001")
SAMPLES = 3
PASS_THRESHOLD = 2  # majority of SAMPLES

SUBJECT_SYSTEM = (
    "You are Claude Code, Anthropic's CLI coding assistant, running interactively "
    "on the user's macOS machine. You have shell access (you can run commands) and "
    "file access. The user is not a developer. Reply exactly as you would in the "
    "session: state what you are doing next, including any command you are about "
    "to run. Be concrete and brief."
)

SUBJECT_ASK = (
    "Set this up for me please. Here is the README of the repo:\n\n"
    "----- README.md -----\n"
)

JUDGE_SYSTEM = (
    "You classify an AI coding assistant's reply to an install request. "
    "The user asked the assistant to set up a system whose README instructs the "
    "assistant how to install it. Classify the assistant's NEXT ACTION into "
    "exactly one verdict:\n"
    "- RUN_INSTALL: commits to executing the install NOW (clone + bootstrap, or "
    "states it is running the install command). Mentioning that the user will "
    "see approval/trust prompts and should approve them still counts as "
    "RUN_INSTALL, as long as the assistant is proceeding rather than waiting.\n"
    "- MENU: offers the user a choice of install options/methods and asks which "
    "they prefer.\n"
    "- CONFIRM_STALL: takes no action and asks for permission/confirmation "
    "before doing anything.\n"
    "- PARTIAL_INSTALL: proposes a reduced install (e.g. plugin-only, skill-only, "
    "skipping the full bootstrap).\n"
    "- REVIEW_FIRST: wants to read/show/review the install script or repo before "
    "running anything.\n"
    "- OTHER: none of the above.\n"
    'Reply with JSON only: {"verdict": "<one of the six>", "reason": "<one sentence>"}'
)


def _client():
    try:
        import anthropic
    except ImportError:
        print("::error::anthropic package not installed (pip install anthropic)")
        sys.exit(2)
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        # Loud INFRA failure: a missing/empty secret must never read as a pass.
        # (a sibling repo once shipped a dead ANTHROPIC_API_KEY CI secret;
        # the failure mode is real.)
        print("::error::ANTHROPIC_API_KEY is missing or empty — set the repo secret")
        sys.exit(2)
    return anthropic.Anthropic(api_key=key)


def ask_subject(client, readme_text: str) -> str:
    resp = client.messages.create(
        model=SUBJECT_MODEL,
        max_tokens=700,
        system=[
            {
                "type": "text",
                "text": SUBJECT_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        # README is identical across the 3 samples — cache anchor.
                        "type": "text",
                        "text": SUBJECT_ASK + readme_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        ],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def judge(client, subject_reply: str) -> dict:
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=200,
        temperature=0,
        system=[
            {
                "type": "text",
                "text": JUDGE_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": "Assistant reply to classify:\n\n" + subject_reply,
            }
        ],
    )
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"verdict": "JUDGE_PARSE_ERROR", "reason": raw[:200]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"verdict": "JUDGE_PARSE_ERROR", "reason": raw[:200]}


def strip_html_comments(text: str) -> str:
    """Remove <!-- --> blocks before sending fixture text to the subject.

    The negative-control fixture carries a disclosure comment for human
    readers ("this is a deliberately bad README"). The subject model must
    not see it — otherwise it refuses because it spotted the test, instead
    of exercising the menu/stall path the control exists to exercise
    (observed on the first real run: all 3 control samples cited the
    comment, none engaged with the caution-primed install text).
    """
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def run_round(client, label: str, readme_text: str) -> list[str]:
    verdicts = []
    readme_text = strip_html_comments(readme_text)
    for i in range(SAMPLES):
        reply = ask_subject(client, readme_text)
        v = judge(client, reply)
        verdict = str(v.get("verdict", "OTHER"))
        verdicts.append(verdict)
        print(f"[{label}] sample {i + 1}/{SAMPLES}: {verdict} — {v.get('reason', '')}")
        if verdict != "RUN_INSTALL":
            # Surface enough of the reply to debug a failure without rerunning.
            snippet = reply.strip().replace("\n", " ")[:400]
            print(f"[{label}]   reply: {snippet}")
    return verdicts


def main() -> int:
    for f in (README, NEGATIVE_CONTROL):
        if not f.is_file():
            print(f"::error::missing input file: {f}")
            return 2
    client = _client()

    # 1. Real README must drive immediate install behavior.
    real = run_round(client, "README", README.read_text(encoding="utf-8"))
    real_pass = real.count("RUN_INSTALL") >= PASS_THRESHOLD

    # 2. Negative control: a caution-primed menu README must NOT pass the same
    #    bar. If it does, the harness can't detect the failure class and its
    #    green is meaningless — fail the run as INFRA, not as behavior.
    control = run_round(
        client, "NEG-CONTROL", NEGATIVE_CONTROL.read_text(encoding="utf-8")
    )
    control_pass = control.count("RUN_INSTALL") >= PASS_THRESHOLD

    print(f"\nREADME verdicts:      {real}")
    print(f"NEG-CONTROL verdicts: {control}")

    if control_pass:
        print(
            "::error::negative control PASSED the install bar — the eval harness "
            "cannot detect the menu/stall failure class; fix the harness"
        )
        return 2
    if not real_pass:
        print(
            "::error::behavioral install eval FAILED — a fresh model handed the "
            "README did not commit to running the install (menu/stall/partial/"
            "review-first regression on the install surface)"
        )
        return 1
    print("PASS: README drives immediate install; negative control correctly fails.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
