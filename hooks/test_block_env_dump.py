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


# ---------------------------------------------------------------------------
# 7. Review item 1 -- redirects stripped before every "bare" test, including
# attached forms glued by shlex into one token (no whitespace-splitting for
# shell operators): `2>/dev/null`, `>/tmp/x`, `>>x`, `env>out.txt`.
# ---------------------------------------------------------------------------

def test_denies_env_stderr_redirect_attached():
    assert_denied("env 2>/dev/null")


def test_denies_env_stdout_redirect_attached():
    assert_denied("env >/tmp/x")


def test_denies_env_append_redirect_attached():
    assert_denied("env >>x")


def test_denies_env_word_glued_to_redirect():
    assert_denied("env>out.txt")


def test_denies_env_stderr_redirect_piped_to_grep():
    # A redirect on env's OWN stderr must not be misread as "a real command
    # word follows env" -- it is still a bare dump, piped to a non-extractor.
    assert_denied("env 2>/dev/null | grep -i key")


def test_denies_export_redirected_to_file():
    assert_denied("export > /tmp/x")


def test_denies_set_redirected_to_file():
    assert_denied("set > /tmp/x")


def test_denies_declare_redirected_to_file():
    assert_denied("declare > /tmp/x")


def test_denies_export_dash_p_stderr_redirect_piped():
    assert_denied("export -p 2>/dev/null | grep -i token")


def test_denies_set_stderr_redirect_piped():
    assert_denied("set 2>/dev/null | grep -i token")


def test_allows_env_real_command_survives_redirect_strip():
    # A REAL command after env must still allow, even with a redirect
    # attached -- the redirect must not eat the genuine trailing command.
    assert_allowed("env FOO=1 python3 x.py 2>/dev/null")


# ---------------------------------------------------------------------------
# 8. Review item 2 -- `_skip_leading` also skips shell keywords: then, do,
# else, elif, if, while, until, {, ! and (.
# ---------------------------------------------------------------------------

def test_skip_leading_skips_shell_keywords_directly():
    # Direct unit proof of the function's own contract. "(" cannot occur as
    # a leading TOKEN via _deny_reason's own segment splitter (it is always
    # consumed as a segment separator upstream, never left inside a
    # segment's text/tokens outside quotes) -- proven end-to-end elsewhere
    # for every OTHER keyword in this list, this is the direct proof for it.
    import importlib.util
    spec = importlib.util.spec_from_file_location("bed", HOOK)
    bed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bed)
    for kw in ("then", "do", "else", "elif", "if", "while", "until", "{", "!", "("):
        assert bed._skip_leading([kw, "env"]) == 1, f"keyword not skipped: {kw!r}"


def test_denies_if_then_env():
    assert_denied("if true; then env; fi")


def test_denies_if_then_else_env():
    assert_denied("if true; then true; else env; fi")


def test_denies_if_env_condition():
    assert_denied("if env; then true; fi")


def test_denies_elif_env():
    assert_denied("if false; then true; elif env; then true; fi")


def test_denies_while_env_condition():
    assert_denied("while env; do true; done")


def test_denies_until_env_condition():
    assert_denied("until env; do true; done")


def test_denies_do_env_body():
    assert_denied("for i in 1; do env; done")


def test_denies_brace_group_env():
    assert_denied("{ env; }")


def test_denies_bang_env():
    assert_denied("! env")


# ---------------------------------------------------------------------------
# 9. Review item 3 -- echo/printf secret check rewrite: indirect ${!v}
# expansion, ${V:+x}/${V+x} allowed, single-quoted text ignored, only
# uppercase names count, substring-anywhere vs whole-component name rules
# with a PATH/FILE/DIR exception, and pipe-destination awareness.
# ---------------------------------------------------------------------------

def test_denies_indirect_expansion_in_loop():
    assert_denied('for v in OPENAI_API_KEY; do echo "$v=${!v}"; done')


def test_denies_indirect_expansion_direct():
    assert_denied('echo "${!SOME_VAR}"')


def test_allows_indirect_name_list_star():
    assert_allowed("echo ${!FOO*}")


def test_allows_indirect_name_list_at():
    assert_allowed("echo ${!FOO@}")


def test_allows_colon_plus_substitution():
    assert_allowed('echo "${GITHUB_TOKEN:+set}"')


def test_allows_plus_substitution_no_colon():
    assert_allowed('echo "${GITHUB_TOKEN+x}"')


def test_denies_minus_default_still_reveals_value():
    # ":-"/"-" expand to the REAL value when set (only fall back to the
    # default when unset) -- unlike ":+"/"+", this is not in the allowed set.
    assert_denied('echo "${GITHUB_TOKEN:-default}"')


def test_allows_single_quoted_var_reference():
    assert_allowed("echo '$GITHUB_TOKEN'")


def test_denies_apostrophe_inside_double_quotes_still_scanned():
    # A "'" inside "..." has no special meaning in bash and must not be
    # misread as opening a real single-quoted span that swallows content.
    assert_denied('echo "it'"'"'s $GITHUB_TOKEN"')


def test_allows_lowercase_secret_shaped_name():
    assert_allowed('key=abc; echo "$key"')


def test_denies_uppercase_password_substring_anywhere():
    assert_denied("echo $PGPASSWORD")


def test_allows_ssh_key_path_exception():
    assert_allowed('echo "$SSH_KEY_PATH"')


def test_denies_key_component_without_path_exception():
    assert_denied("echo $MY_KEY")


def test_denies_pat_component():
    assert_denied("echo $GITHUB_PAT")


def test_denies_dsn_component():
    assert_denied("echo $DB_DSN")


def test_allows_keychain_path_not_a_key_component():
    assert_allowed("echo $KEYCHAIN_PATH")


def test_allows_patch_dir_not_a_pat_component():
    assert_allowed("echo $PATCH_DIR")


def test_denies_substring_extraction_still_denies():
    assert_denied('echo "${GITHUB_TOKEN:0:8}"')


def test_allows_echo_secret_piped_into_non_printer():
    assert_allowed('echo "$DOCKER_PASSWORD" | docker login -u me --password-stdin')


def test_allows_printf_secret_piped_into_gh_auth():
    assert_allowed("printf '%s' \"$GITHUB_TOKEN\" | gh auth login --with-token")


def test_denies_echo_secret_piped_into_head():
    assert_denied('echo "$ANTHROPIC_API_KEY" | head -c 10')


def test_denies_echo_secret_piped_into_cat():
    assert_denied('echo "$GITHUB_TOKEN" | cat')
