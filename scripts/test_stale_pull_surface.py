#!/usr/bin/env python3
"""Controls for the stale-successful-pull surface + the shared lock reclaim.

MYC-3175 items 2 and 4.

ITEM 2 — surface pull FAILURE, not staleness. The updater stamps
`.ai-brain-starter-last-successful-pull` only when it has confirmed the clone
current with origin. `.ai-brain-starter-last-update` keeps moving on every
ATTEMPT, so a permanently-blocked clone looks busy; only the gap reveals it.
"Behind origin" is useless here — a clone that cannot fetch cannot learn it is
behind, so the obvious signal is the one the failure suppresses.

ITEM 4 — ONE reclaim implementation, shared by every consumer that
fast-forwards a managed clone (the install clone + the ~/dev hub fleet). A
second copy would rot the moment one is fixed.

  1. a fresh success stamp is SILENT
  2. a stamp older than the threshold FIRES        <- the catch
  3. a MISSING stamp is silent (pre-seed install, not a freeze)
  4. a pinned install is silent even when stale (advertised opt-out)
  5. threshold is env-tunable
  6. the message names the diagnosis command
  7. the updater SEEDS the stamp on its first run
  8. the updater ADVANCES the stamp on a real successful pull
  9. the updater does NOT advance it when the pull fails  <- the whole point
 10. dev_repo_scan imports the SAME reclaim (one implementation, not a copy)

Stdlib + git only. Exit 0 = all pass.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SURFACER = ROOT / "hooks" / "surface-deployed-hooks-behind.py"
UPDATER = ROOT / "scripts" / "ai-brain-auto-update.py"

PASS = 0
FAIL = 0


def ok(label):
    global PASS
    PASS += 1
    print(f"PASS  {label}")


def bad(label, why):
    global FAIL
    FAIL += 1
    print(f"FAIL  {label} :: {why}")


def surfacer_out(state: Path, extra_env=None) -> str:
    env = {**os.environ,
           "ABS_UPDATE_STATE_DIR": str(state),
           "ABS_SETTINGS_JSON": str(state / "settings.json"),
           "ABS_SKILL_DIR": str(state / "noskill")}
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, str(SURFACER)], input="{}",
                       capture_output=True, text=True, env=env, timeout=60,
                       encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    return d.get("hookSpecificOutput", {}).get("additionalContext", "")


def mkstate(tmp: Path, name: str, age_days=None, pinned=False) -> Path:
    s = tmp / name
    s.mkdir(parents=True, exist_ok=True)
    (s / "settings.json").write_text("{}", encoding="utf-8")
    if age_days is not None:
        stamp = s / ".ai-brain-starter-last-successful-pull"
        stamp.touch()
        t = time.time() - age_days * 86400
        os.utime(stamp, (t, t))
    if pinned:
        (s / ".ai-brain-starter-pinned").touch()
    return s


TMP = Path(tempfile.mkdtemp())

# MYC-4907: the updater now refuses any ABS_SKILL_DIR that does not resolve
# strictly inside ~/.claude/skills. run_updater() below drives ABS_SKILL_DIR
# at a clone that used to sit directly under TMP (outside any HOME), which
# would now be refused -- give it a fake HOME whose skills root the clone
# lives under instead of touching the real one.
FAKE_HOME = TMP / "home"
SKILLS_ROOT = FAKE_HOME / ".claude" / "skills"
SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

# --- 1-6: the surface -------------------------------------------------------
out = surfacer_out(mkstate(TMP, "fresh", age_days=2))
ok("1. fresh success stamp (2d) is silent") if "not successfully updated" not in out \
    else bad("1. fresh", out[:150])

out = surfacer_out(mkstate(TMP, "stale", age_days=40))
if "not successfully updated" in out and "40 days" in out:
    ok("2. stale success stamp (40d) FIRES and names the age")
else:
    bad("2. stale", f"got: {out[:200]!r}")

out = surfacer_out(mkstate(TMP, "nostamp"))
ok("3. MISSING stamp is silent (pre-seed install, not a freeze)") \
    if "not successfully updated" not in out else bad("3. missing", out[:150])

out = surfacer_out(mkstate(TMP, "pinned", age_days=99, pinned=True))
ok("4. pinned install is silent even at 99d (opt-out honored)") \
    if "not successfully updated" not in out else bad("4. pinned", out[:150])

out = surfacer_out(mkstate(TMP, "tunable", age_days=5),
                   {"ABS_STALE_PULL_DAYS": "3"})
ok("5. ABS_STALE_PULL_DAYS lowers the threshold") if "not successfully updated" in out \
    else bad("5. tunable", f"got: {out[:150]!r}")

out = surfacer_out(mkstate(TMP, "msg", age_days=40))
ok("6. message names the diagnosis command") if "git pull --ff-only" in out \
    else bad("6. message", out[:200])

# --- 7-9: the updater's stamping -------------------------------------------
env0 = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def mkrepo(p: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(p)], check=True, env=env0)
    (p / "f.txt").write_text("x", encoding="utf-8")
    # F3 identity check (MYC-4907): _skill_dir() now also requires this file
    # to exist under the candidate, or a contained-but-foreign checkout is
    # refused. Committed here so clone() (run_updater's ABS_SKILL_DIR
    # target) inherits it from origin's first commit.
    (p / "scripts").mkdir(parents=True, exist_ok=True)
    (p / "scripts" / "ai-brain-auto-update.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "add", "f.txt", "scripts"], check=True, env=env0)
    subprocess.run(["git", "-C", str(p), "commit", "-qm", "init"], check=True, env=env0)
    subprocess.run(["git", "-C", str(p), "branch", "-M", "main"], check=True, env=env0)
    return p


def run_updater(clone: Path, state: Path, session_id: str | None = None):
    """MYC-4704 gate e6: the pull is now two-phase -- a bare call (no
    session_id, matching this helper's original no-input shape) only
    STAGES a pull; the merge itself waits for a later call whose
    session_id both differs from the staging call's AND clears
    ABS_UPDATE_MIN_DEPLOY_DELAY_SECONDS (set to 0 here -- this file tests
    the last_ok/staleness contract, not the elapsed-time gate, which
    test_ai_brain_auto_update.sh already covers on its own)."""
    env = {**env0, "HOME": str(FAKE_HOME), "USERPROFILE": str(FAKE_HOME), "ABS_SKILL_DIR": str(clone),
           "ABS_UPDATE_STATE_DIR": str(state),
           "ABS_UPDATE_INTERVAL_DAYS": "0", "ABS_UPDATE_MIN_DEPLOY_DELAY_SECONDS": "0"}
    kwargs = {}
    if session_id is not None:
        kwargs["input"] = json.dumps({"session_id": session_id})
    return subprocess.run([sys.executable, str(UPDATER)], capture_output=True,
                          text=True, env=env, timeout=180,
                          encoding="utf-8", errors="replace", **kwargs)


origin = mkrepo(TMP / "o1")
clone = SKILLS_ROOT / "c1"
subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, env=env0)
st = TMP / "s1"
st.mkdir()
run_updater(clone, st)
stamp = st / ".ai-brain-starter-last-successful-pull"
ok("7. updater SEEDS the success stamp on first run") if stamp.is_file() \
    else bad("7. seed", "stamp absent after a run")

# 8. advances on a real, COMPLETED pull. MYC-4704 gate e6 made the pull
# two-phase: a bare call only STAGES (last_ok must NOT advance yet -- it
# is not yet confirmed current), so this drives it through both phases --
# stage with one session_id, resolve with a different one -- before
# asserting either half of the original claim.
(origin / "new.txt").write_text("y", encoding="utf-8")
subprocess.run(["git", "-C", str(origin), "add", "new.txt"], check=True, env=env0)
subprocess.run(["git", "-C", str(origin), "commit", "-qm", "second"], check=True, env=env0)
old_t = time.time() - 10 * 86400
os.utime(stamp, (old_t, old_t))
run_updater(clone, st, session_id="stage-8")      # phase 1: stage only
if (clone / "new.txt").exists() or stamp.stat().st_mtime > old_t + 86400:
    bad("8. premise", "staging alone already pulled or advanced the stamp "
                      "-- the two-phase gate is not doing its job")
run_updater(clone, st, session_id="resolve-8")     # phase 2: a different,
                                                    # old-enough (MINDELAY=0)
                                                    # session resolves it
if stamp.stat().st_mtime > old_t + 86400 and (clone / "new.txt").exists():
    ok("8. updater ADVANCES the stamp once a staged pull actually completes")
else:
    bad("8. advance", f"pulled={(clone/'new.txt').exists()} "
                      f"advanced={stamp.stat().st_mtime > old_t + 86400}")

# 9. does NOT advance when the pull is blocked  <- the signal's whole value
origin2 = mkrepo(TMP / "o2")
clone2 = SKILLS_ROOT / "c2"
subprocess.run(["git", "clone", "-q", str(origin2), str(clone2)], check=True, env=env0)
(origin2 / "z.txt").write_text("z", encoding="utf-8")
subprocess.run(["git", "-C", str(origin2), "add", "z.txt"], check=True, env=env0)
subprocess.run(["git", "-C", str(origin2), "commit", "-qm", "third"], check=True, env=env0)
st2 = TMP / "s2"
st2.mkdir()
run_updater(clone2, st2)  # seed (this one legitimately pulls z.txt)
stamp2 = st2 / ".ai-brain-starter-last-successful-pull"

# Origin must be AHEAD again, or "no stamp advance" would be untestable: a clone
# already current is CORRECTLY confirmed current, blocked working tree or not.
(origin2 / "w.txt").write_text("w", encoding="utf-8")
subprocess.run(["git", "-C", str(origin2), "add", "w.txt"], check=True, env=env0)
subprocess.run(["git", "-C", str(origin2), "commit", "-qm", "fourth"], check=True, env=env0)

frozen_t = time.time() - 30 * 86400
os.utime(stamp2, (frozen_t, frozen_t))
# Block the ff the way a real user does: dirty a tracked file.
(clone2 / "f.txt").write_text("locally edited", encoding="utf-8")
run_updater(clone2, st2)
if (clone2 / "w.txt").exists():
    bad("9. premise", "the pull was NOT blocked — fixture proves nothing")
elif abs(stamp2.stat().st_mtime - frozen_t) < 60:
    ok("9. blocked pull does NOT advance the stamp — the freeze stays visible")
else:
    bad("9. no-advance", "stamp advanced despite a blocked pull (signal is worthless)")

# --- 10: one implementation, not a copy ------------------------------------
def _load(name: str, path: Path):
    """Register in sys.modules BEFORE exec: @dataclass resolves its class's
    module there, and a missing entry crashes on Python 3.12+."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load("_drs", ROOT / "hooks" / "_lib" / "dev_repo_scan.py")
gl = _load("_gl", ROOT / "hooks" / "_lib" / "git_locks.py")
if getattr(m, "reclaim_stale_git_locks", None) is not None and \
        m.reclaim_stale_git_locks.__doc__ == gl.reclaim_stale_git_locks.__doc__:
    ok("10. dev_repo_scan uses the SAME canonical reclaim (no second copy)")
else:
    bad("10. shared impl", "dev_repo_scan does not resolve to hooks/_lib/git_locks")

print()
print(f"=== summary: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
