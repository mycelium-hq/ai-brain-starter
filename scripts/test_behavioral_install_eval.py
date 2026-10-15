#!/usr/bin/env python3
"""Tests for tests/eval/behavioral_install_eval.py, with no network and no API key.

The eval costs real API calls and runs weekly, so a harness bug is found a week
late, or worse, reads as a result. This drives the real harness with a fake
client and checks what the harness itself does:

  1. the yes conversation runs T1 to T5 and the no conversation is a separate
     one that runs T1, T2 and T3n, with no yes anywhere in its history;
  2. an exception that is not a verdict (the SDK TypeError that kept the weekly
     run red for seven weeks) exits 2 with the exception printed, never 1;
  3. a README that fails at T3n or T5 exits 1, one that holds with both controls
     (the old contract and the June menu README) failing exits 0, one failing
     sample of three is tolerated, and a control that passes the bar exits 2;
  4. no Messages.create call passes `temperature`, and the workflow pins the
     anthropic package to an exact version.

Plain script, no pytest (the CI job runs scripts/test_*.py directly on 3.9).
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import os
import re
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVAL = REPO / "tests" / "eval" / "behavioral_install_eval.py"
WORKFLOW = REPO / ".github" / "workflows" / "behavioral-install-eval.yml"
# Phrases that are in a frozen control README and not in README.md.
MARKERS = {"old": "that paste **is** their authorization", "menu": "do not run any commands yet"}
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: object = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  -> {detail!r}"))
    if not cond:
        FAILURES.append(name)


spec = importlib.util.spec_from_file_location("behavioral_install_eval", EVAL)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


class Block:
    """A content block the way the SDK returns it."""
    def __init__(self, type_: str, **fields: object) -> None:
        self.type = type_
        self.__dict__.update(fields)


class Response:
    def __init__(self, content: list, stop_reason: str = "end_turn") -> None:
        self.content, self.stop_reason = content, stop_reason


def turn_of(names: list) -> str:
    """Which turn a judge call is for, from the verdicts it was asked to choose from."""
    for key, turn in ev.TURNS.items():
        if list(turn["verdicts"]) == names:
            return key
    raise AssertionError(f"no turn offers {names}")


class FakeClient:
    """Plays subject and judge. `fails(kind, turn, nth)` says whether the judge
    gives the turn a failing verdict; kind is "readme", "old" or "menu" (the
    README the conversation was handed) and nth counts that turn's judgements
    so far for that kind."""

    def __init__(self, fails=None, raises: Exception | None = None) -> None:
        self.fails, self.raises = fails or (lambda kind, turn, nth: False), raises
        self.subject_calls: list = []
        self.all_calls: list = []
        self.kind = "readme"
        self.seen: dict = {}
        self.messages = self

    def create(self, **kw):
        self.all_calls.append(kw)
        if self.raises:
            raise self.raises
        if "tools" in kw:  # the subject: a text reply, no command
            # The harness keeps appending to its messages list, so keep this call's own copy.
            self.subject_calls.append(dict(kw, messages=list(kw["messages"])))
            first = kw["messages"][0]["content"][0]["text"]
            self.kind = next((k for k, marker in MARKERS.items() if marker in first), "readme")
            return Response([Block("text", text="(fake subject reply)")])
        names = re.findall(r"^- (\w+):", kw["system"], re.M)
        turn = turn_of(names)
        nth = self.seen[(self.kind, turn)] = self.seen.get((self.kind, turn), 0) + 1
        verdict = names[1] if self.fails(self.kind, turn, nth) else names[0]
        return Response([Block("text", text='{"verdict": "%s", "reason": "fake"}' % verdict)])


def run_eval(client: FakeClient) -> tuple[object, str]:
    """Run the harness main() against the fake client: (exit code, what it printed).
    A main() that raises instead of returning is reported as its exception, not a crash."""
    fake_sdk = types.ModuleType("anthropic")
    fake_sdk.Anthropic = lambda: client
    saved = (sys.modules.get("anthropic"), os.environ.get("ANTHROPIC_API_KEY"))
    sys.modules["anthropic"], os.environ["ANTHROPIC_API_KEY"] = fake_sdk, "not-a-real-key"
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ev.main()
    except Exception as e:  # noqa: BLE001
        code = f"raised {type(e).__name__}: {e}"
    finally:
        for name, old in zip(("anthropic", "ANTHROPIC_API_KEY"), saved):
            store = sys.modules if name == "anthropic" else os.environ
            if old is None:
                store.pop(name, None)
            else:
                store[name] = old
    return code, out.getvalue() + err.getvalue()


def user_texts(call: dict) -> list:
    """What the user said in each turn of the conversation this subject call carried."""
    said = []
    for m in call["messages"]:
        if m["role"] == "user":
            said.append(" ".join(b["text"] for b in m["content"] if b.get("type") == "text"))
    return said


print("1. the turns and the two conversations")
check("every turn passes on its first verdict", all(list(t["verdicts"])[0] == t["pass"] for t in ev.TURNS.values()))
check("every turn of every path exists", all(n in ev.TURNS for names in ev.PATHS.values() for n in names))
check("the yes path is T1 to T5 and the no path is T1, T2, T3n",
      ev.PATHS == {"yes": ["T1", "T2", "T3", "T4", "T5"], "no": ["T1", "T2", "T3n"]}, ev.PATHS)
good = FakeClient(fails=lambda kind, turn, nth: kind != "readme" and turn == "T1")
code, printed = run_eval(good)
check("a README that holds with both controls failing exits 0", code == 0, (code, printed[-300:]))
check("the README and both controls were run", {"readme", "old", "menu"} == {
    next((k for k, marker in MARKERS.items() if marker in c["messages"][0]["content"][0]["text"]), "readme")
    for c in good.subject_calls}, len(good.subject_calls))
check("the verdicts of the no conversation are reported",
      "[README/no] conversation 1/3: PASS ['SHOW_SCREEN', 'RELAY_AND_ASK', 'STOPS']" in printed, printed[:600])
check("the verdicts of the yes conversation reach T5",
      "[README/yes] conversation 1/3: PASS ['SHOW_SCREEN', 'RELAY_AND_ASK', 'INSTALL_NOW', 'HANDS_BACK', 'HANDS_BACK']"
      in printed, printed[:600])
no_calls = [c for c in good.subject_calls if user_texts(c)[-1:] == ["no"]]
yes_calls = [c for c in good.subject_calls if user_texts(c)[-1:] == ["yes"]]
check("the subject was asked at T3n and at T3", len(no_calls) == 3 and len(yes_calls) == 3, (len(no_calls), len(yes_calls)))
check("the no conversation has no yes anywhere in its history",
      all("yes" not in user_texts(c) for c in no_calls))
permission = [c for c in good.subject_calls if user_texts(c)[-1:] == [ev.TURNS["T5"]["say"]]]
check("T5 is the user giving permission, after T4 asked about Allow", len(permission) == 3 and all(
    user_texts(c)[-2] == ev.TURNS["T4"]["say"] for c in permission), len(permission))
check("no call to the SDK passes temperature", all("temperature" not in c for c in good.all_calls))

print("2. anything that is not a verdict exits 2")
for exc in (TypeError("Messages.create() got an unexpected keyword argument 'temperature'"),
            RuntimeError("connection reset"), KeyError("content")):
    code, printed = run_eval(FakeClient(raises=exc))
    check(f"{type(exc).__name__} exits 2 and is printed", code == 2 and type(exc).__name__ in printed
          and "::error::" in printed, (code, printed[:300]))

print("3. what the verdicts decide")


def controls_fail_at_t1(kind: str, turn: str, nth: int) -> bool:
    return kind != "readme" and turn == "T1"


cases = (
    ("README fails T3n in every conversation: exit 1",
     lambda kind, turn, nth: controls_fail_at_t1(kind, turn, nth) or (kind == "readme" and turn == "T3n"), 1),
    ("README fails T5 in every conversation: exit 1",
     lambda kind, turn, nth: controls_fail_at_t1(kind, turn, nth) or (kind == "readme" and turn == "T5"), 1),
    ("README fails T3n in one conversation of three: tolerated, exit 0",
     lambda kind, turn, nth: controls_fail_at_t1(kind, turn, nth) or (kind == "readme" and turn == "T3n" and nth == 1), 0),
    ("no control fails: the harness cannot see the failure, exit 2", lambda kind, turn, nth: False, 2),
    ("only the old-contract control fails, the menu control passes the bar: exit 2",
     lambda kind, turn, nth: kind == "old" and turn == "T1", 2),
    ("only the menu control fails, the old-contract control passes the bar: exit 2",
     lambda kind, turn, nth: kind == "menu" and turn == "T1", 2),
)
for name, fails, want in cases:
    code, printed = run_eval(FakeClient(fails=fails))
    check(name, code == want, (code, printed[-300:]))

print("4. the SDK call and the workflow")
calls = [n for n in ast.walk(ast.parse(EVAL.read_text(encoding="utf-8")))
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "create"]
check("the script makes its API calls through create()", len(calls) >= 2, len(calls))
check("no create() call passes temperature",
      not any(k.arg == "temperature" for c in calls for k in c.keywords))
installs = re.findall(r"pip install anthropic\S*", WORKFLOW.read_text(encoding="utf-8"))
check("the workflow pins anthropic to an exact version",
      installs != [] and all(re.fullmatch(r"pip install anthropic==\d+\.\d+\.\d+", i) for i in installs), installs)

if FAILURES:
    print(f"\n{len(FAILURES)} check(s) failed")
    sys.exit(1)
print("\nPASS: the install eval harness does what it says")
