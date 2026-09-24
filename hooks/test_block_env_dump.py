#!/usr/bin/env python3
"""pytest suite for hooks/block-env-dump.py (MYC-4988).

Drives the hook as a REAL SUBPROCESS with JSON on stdin -- the same shape
Claude Code uses to call a PreToolUse hook -- so these tests prove the
WIRED hook, not just its importable internals. The commands below are TEST
DATA fed to the hook's stdin; the hook only ever parses the string, it
never executes it, and neither does this file.

Cases are grouped: (1) the two witnessed incident commands, (2) one deny
per bullet in the hook's docstring, (3) the three remote secret-dump
forms, (4) the full self-DoS control -- every ALLOWED form the ticket
names, which must all keep passing, (5) bypass, (6) fail-open on a crash.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "block-env-dump.py"


def run_hook(command: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Run the hook as a subprocess with a Bash tool_input payload.

    Scrubs any inherited ENV_DUMP_BYPASS from the child env first --
    MYC-2094's lesson: an exported bypass sitting in the test runner's own
    shell must never silently invert every verdict in this file.
    """
    env = dict(os.environ)
    env.pop("ENV_DUMP_BYPASS", None)
    if env_extra:
        env.update(env_extra)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace", timeout=10,
    )


def assert_denied(command: str) -> None:
    r = run_hook(command)
    assert r.returncode == 2, (
        f"expected DENY (rc=2), got rc={r.returncode} for: {command!r}\nstderr={r.stderr}"
    )
    assert "BLOCKED" in r.stderr


def assert_allowed(command: str, env_extra=None) -> None:
    r = run_hook(command, env_extra=env_extra)
    assert r.returncode == 0, (
        f"expected ALLOW (rc=0), got rc={r.returncode} for: {command!r}\nstderr={r.stderr}"
    )


# ---------------------------------------------------------------------------
# 1. DENIED -- witnessed commands (verbatim, the incident this hook closes)
# ---------------------------------------------------------------------------

def test_denies_witnessed_grep_sed_pipeline():
    assert_denied(
        r'env | grep -iE "agent_id|AGENT_ID|CLAUDE_AGENT|SESSION_ID" | '
        r"sed -E 's/(=.{0,8}).*/\1.../'"
    )


def test_denies_witnessed_sort_sed_pipeline():
    assert_denied(r"env | sort | sed -E 's/^([^=]+)=(.{0,10}).*/\1=\2.../'")


# ---------------------------------------------------------------------------
# 2. DENIED -- one case per deny bullet
# ---------------------------------------------------------------------------

def test_denies_bare_env():
    assert_denied("env")


def test_denies_env_redirected_to_file():
    assert_denied("env > /tmp/leak.txt")


def test_denies_printenv_bare():
    assert_denied("printenv")


def test_denies_printenv_with_name():
    assert_denied("printenv HOME")


def test_denies_bare_export():
    assert_denied("export")


def test_denies_export_dash_p():
    assert_denied("export -p")


def test_denies_bare_set():
    assert_denied("set")


def test_denies_declare_no_operands():
    assert_denied("declare -x")


def test_denies_declare_dash_p():
    assert_denied("declare -p")


def test_denies_echo_secret_var():
    assert_denied("echo $GITHUB_TOKEN")


def test_denies_printf_secret_var():
    assert_denied('printf "%s" "$DB_PASSWORD"')


def test_denies_echo_dsn_suffix():
    assert_denied("echo $PROD_DATABASE_URL")


def test_denies_ps_dash_capital_e():
    assert_denied("ps -E")


def test_denies_ps_bsd_dashless_e():
    assert_denied("ps eww")


def test_denies_proc_self_environ():
    assert_denied("cat /proc/self/environ")


def test_denies_proc_pid_environ():
    assert_denied("cat /proc/1234/environ")


# ---------------------------------------------------------------------------
# 3. DENIED -- remote secret-dump vocabulary (three forms)
# ---------------------------------------------------------------------------

def test_denies_heroku_config():
    assert_denied("heroku config -a app")


def test_denies_fly_secrets_list():
    assert_denied("fly secrets list -a app")


def test_denies_vercel_env_pull():
    assert_denied("vercel env pull")


# ---------------------------------------------------------------------------
# Builder-style sed as the FIRST stage after env (no grep/sort in between)
# must still deny -- it keeps a value snippet, so it is not names-only.
# ---------------------------------------------------------------------------

def test_builder_style_sed_as_first_stage_still_denies():
    assert_denied(r"env | sed -E 's/^([^=]+)=(.{0,10}).*/\1=\2.../'")


# ---------------------------------------------------------------------------
# 4. ALLOWED -- the self-DoS control. Every one of these must keep passing.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "env FOO=1 python3 x.py",
    "env -i PATH=/usr/bin ls",
    "env -u FOO make",
    "env | cut -d= -f1",
    "env | cut -d'=' -f1",
    'env | cut -d "=" -f 1',
    "env | sed 's/=.*//'",
    "env | awk -F= '{print $1}'",
    "compgen -e",
    '[ -n "${FOO_TOKEN:-}" ] && echo set',
    "echo ${#FOO_TOKEN}",
    "export FOO=bar",
    "set -euo pipefail",
    "set -- a b",
    "declare -x FOO=bar",
    "ps -p 123 -o pid=",
    'grep -rn "printenv" hooks/',
    'git commit -m "mention env | sort"',
], ids=[
    "env-runs-a-command", "env-dash-i", "env-dash-u",
    "env-pipe-cut-glued", "env-pipe-cut-single-quoted", "env-pipe-cut-spaced",
    "env-pipe-sed", "env-pipe-awk",
    "compgen-dash-e", "presence-check", "length-form",
    "export-with-value", "set-flags", "set-dashdash",
    "declare-with-value", "ps-pid-lookup",
    "grep-for-the-word-printenv", "commit-message-mentions-env-pipe-sort",
])
def test_allows_self_dos_control(command):
    assert_allowed(command)


def test_allows_names_only_pipeline_continuation():
    # "Names-only pipelines may continue past the extractor."
    assert_allowed("env | cut -d= -f1 | grep -i key")


# ---------------------------------------------------------------------------
# 5. Bypass
# ---------------------------------------------------------------------------

def test_inline_bypass_allows():
    r = run_hook("ENV_DUMP_BYPASS=1 env")
    assert r.returncode == 0, r.stderr


def test_session_env_bypass_allows():
    r = run_hook("env", env_extra={"ENV_DUMP_BYPASS": "1"})
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# 6. Fail-open on its own crash / irrelevant input
# ---------------------------------------------------------------------------

def test_fails_open_on_malformed_stdin():
    env = dict(os.environ)
    env.pop("ENV_DUMP_BYPASS", None)
    r = subprocess.run(
        [sys.executable, str(HOOK)], input="not json{{{",
        capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace", timeout=10,
    )
    assert r.returncode == 0


def test_ignores_non_bash_tool():
    env = dict(os.environ)
    env.pop("ENV_DUMP_BYPASS", None)
    payload = {"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}}
    r = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace", timeout=10,
    )
    assert r.returncode == 0


def test_ignores_empty_command():
    assert_allowed("")
