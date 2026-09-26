#!/usr/bin/env python3
"""Test suite for hooks/block-env-dump.py (MYC-4988).

Plain script: `python3 hooks/test_block_env_dump.py` runs it directly, with
no pytest dependency (ci.sh's unit/type gate runs hooks/+tests/ suites this
way, under a Python that has no pytest installed). Every case is still a
parameterless `def test_*()`, so `pytest hooks/test_block_env_dump.py` also
collects and runs the identical set -- either runner exercises the same
cases against the same hook.

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
import tempfile
from pathlib import Path

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

def test_allows_self_dos_control():
    # Every ALLOWED form the ticket names, looped rather than parametrized
    # (this file runs as a plain script with no pytest) -- the trailing
    # comment on each line is the former pytest `ids=` label, kept so a
    # failure's command string plus this comment still identifies the case.
    # assert_allowed() embeds the failing command in its own message, so a
    # failure here still names exactly which command broke.
    commands = [
        "env FOO=1 python3 x.py",               # env-runs-a-command
        "env -i PATH=/usr/bin ls",               # env-dash-i
        "env -u FOO make",                       # env-dash-u
        "env | cut -d= -f1",                     # env-pipe-cut-glued
        "env | cut -d'=' -f1",                   # env-pipe-cut-single-quoted
        'env | cut -d "=" -f 1',                 # env-pipe-cut-spaced
        "env | sed 's/=.*//'",                   # env-pipe-sed
        "env | awk -F= '{print $1}'",            # env-pipe-awk
        "compgen -e",                            # compgen-dash-e
        '[ -n "${FOO_TOKEN:-}" ] && echo set',   # presence-check
        "echo ${#FOO_TOKEN}",                    # length-form
        "export FOO=bar",                        # export-with-value
        "set -euo pipefail",                     # set-flags
        "set -- a b",                            # set-dashdash
        "declare -x FOO=bar",                    # declare-with-value
        "ps -p 123 -o pid=",                     # ps-pid-lookup
        'grep -rn "printenv" hooks/',            # grep-for-the-word-printenv
        'git commit -m "mention env | sort"',    # commit-message-mentions-env-pipe-sort
    ]
    for command in commands:
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


# ---------------------------------------------------------------------------
# 10. Review item 4 -- remote vocabulary runs only when the SEGMENT's own
# command is heroku/aws/gcloud/vercel/doppler/fly/flyctl; /proc/.../environ
# runs on UNQUOTED text only. Stops false-blocking commit messages, greps,
# and PR bodies that merely mention these strings.
# ---------------------------------------------------------------------------

def test_allows_commit_message_mentioning_proc_environ():
    assert_allowed('git commit -m "block /proc/self/environ reads"')


def test_allows_grep_pattern_mentioning_proc_environ():
    assert_allowed('grep -rn "/proc/self/environ" hooks/')


def test_allows_commit_message_mentioning_heroku_config():
    assert_allowed('git commit -m "port the heroku config guard"')


def test_allows_grep_pattern_mentioning_aws_ssm():
    assert_allowed("rg -n 'aws ssm get-parameter' docs/")


def test_allows_pr_body_mentioning_vercel_env_pull():
    assert_allowed('gh pr create --title x --body "blocks vercel env pull"')


def test_denies_proc_environ_pid_substitution_no_spaces():
    assert_denied("cat /proc/$$/environ")


def test_still_denies_heroku_config_as_real_command():
    assert_denied("heroku config -a app")


def test_still_denies_fly_secrets_list_as_real_command():
    assert_denied("fly secrets list -a app")


def test_still_denies_vercel_env_pull_as_real_command():
    assert_denied("vercel env pull")


# ---------------------------------------------------------------------------
# 11. Review item 5 -- strip the path from EVERY verb, not just env.
# ---------------------------------------------------------------------------

def test_denies_printenv_full_path():
    assert_denied("/usr/bin/printenv")


def test_denies_echo_full_path_secret_var():
    assert_denied("/bin/echo $GITHUB_TOKEN")


def test_denies_export_full_path():
    assert_denied("/usr/bin/export -p")


def test_denies_set_full_path():
    assert_denied("/bin/set")


def test_denies_declare_full_path():
    assert_denied("/usr/bin/declare -p")


def test_denies_ps_full_path():
    assert_denied("/bin/ps -E")


# ---------------------------------------------------------------------------
# 12. Review item 6 -- ps: only single-dash short flags containing E count,
# so a long double-dash flag that happens to contain "E" (--sort=-%MEM) is
# not mistaken for the environment flag. BSD dashless "e" stays denied.
# ---------------------------------------------------------------------------

def test_allows_ps_long_flag_containing_uppercase_e():
    assert_allowed("ps aux --sort=-%MEM | head")


def test_still_denies_ps_dash_capital_e():
    assert_denied("ps -E")


def test_still_denies_ps_bsd_dashless_eww():
    assert_denied("ps eww")


def test_still_denies_ps_bsd_dashless_auxe():
    assert_denied("ps auxe")


def test_still_allows_ps_pid_lookup():
    assert_allowed('ps -p "$(pgrep -f server)" -o pid=')


# ---------------------------------------------------------------------------
# 13. Review item 7 -- declare -F (function NAMES only, no bodies) allowed.
# ---------------------------------------------------------------------------

def test_allows_declare_dash_capital_f():
    assert_allowed("declare -F")


def test_allows_declare_dash_capital_f_with_name():
    assert_allowed("declare -F my_func")


def test_still_denies_declare_dash_p():
    assert_denied("declare -p")


def test_still_denies_declare_no_operands():
    assert_denied("declare -x")


# ---------------------------------------------------------------------------
# 14. Review item 8 -- bypass is PER-SEGMENT: a bypass on one segment must
# not excuse a DIFFERENT segment in the same command.
# ---------------------------------------------------------------------------

def test_denies_bypass_on_harmless_segment_then_real_dump():
    assert_denied("ENV_DUMP_BYPASS=1 true; env")


def test_denies_real_dump_then_trailing_bypass():
    assert_denied("env; ENV_DUMP_BYPASS=1")


def test_denies_bypassed_printenv_then_unbypassed_echo():
    assert_denied('ENV_DUMP_BYPASS=1 printenv PATH && echo $GITHUB_TOKEN')


def test_denies_bypassed_pipe_segment_then_unbypassed_env():
    assert_denied("echo x | ENV_DUMP_BYPASS=1 cat; env")


def test_denies_bypassed_git_then_unbypassed_printenv():
    assert_denied("ENV_DUMP_BYPASS=1 git status && printenv")


def test_still_allows_inline_bypass_on_the_dump_itself():
    assert_allowed("ENV_DUMP_BYPASS=1 env")


def test_allows_exported_bypass_carries_to_later_segment():
    # An EXPORTED assignment really does reach later commands in the same
    # shell invocation, unlike a bare trailing/prefixing one.
    assert_allowed("export ENV_DUMP_BYPASS=1; env")


def test_still_allows_session_env_bypass():
    r = run_hook("env", env_extra={"ENV_DUMP_BYPASS": "1"})
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# 15. Review item 9 -- names-only extractors matched by EXACT argument list,
# not a regex that a wider selector can sneak past; grep -q/-c added as
# presence consumers (never print a value, only an exit code or a count).
# ---------------------------------------------------------------------------

def test_denies_cut_field_range():
    assert_denied("env | cut -d= -f1-2")


def test_denies_cut_field_list():
    assert_denied("env | cut -d= -f1,2")


def test_denies_cut_open_ended_range():
    assert_denied("env | cut -d= -f1-")


def test_denies_cut_spaced_field_range():
    assert_denied("env | cut -d= -f 1-3")


def test_denies_cut_with_complement_flag():
    assert_denied("env | cut -d= -f1 --complement")


def test_denies_sed_print_then_substitute():
    # -e p prints the pattern space AS-IS (the real value) before the
    # substitution ever runs -- not equivalent to the blessed bare script.
    assert_denied("env | sed -e p -e 's/=.*//'")


def test_allows_cut_glued_form():
    assert_allowed("env | cut -d= -f1")


def test_allows_cut_single_quoted_delimiter():
    assert_allowed("env | cut -d'=' -f1")


def test_allows_cut_fully_spaced_form():
    assert_allowed('env | cut -d "=" -f 1')


def test_allows_sed_bare_script():
    assert_allowed("env | sed 's/=.*//'")


def test_allows_awk_bare_script():
    assert_allowed("env | awk -F= '{print $1}'")


def test_still_denies_awk_multi_field_script():
    assert_denied("env | awk -F= '{print $1, $2}'")


def test_allows_names_only_pipeline_continues_past_extractor():
    assert_allowed("env | cut -d= -f1 | grep -i key")


def test_allows_grep_dash_q_presence_consumer():
    assert_allowed("env | grep -q '^GITHUB_TOKEN=' && echo set")


# ---------------------------------------------------------------------------
# 16. Review item 10 -- cheap extra coverage: gh auth token; security
# find-generic-password -w/-g; cat/head/tail of a .env file; docker/
# kubectl/podman exec ... env; python -c / node -e printing the WHOLE
# environment.
# ---------------------------------------------------------------------------

def test_denies_gh_auth_token():
    assert_denied("gh auth token")


def test_denies_security_find_generic_password_dash_w():
    assert_denied("security find-generic-password -s svc -w")


def test_denies_cat_dot_env():
    assert_denied("cat .env")


def test_denies_head_dot_env():
    assert_denied("head .env")


def test_denies_tail_dot_env():
    assert_denied("tail .env")


def test_denies_docker_exec_env():
    assert_denied("docker exec app env")


def test_denies_kubectl_exec_env():
    assert_denied("kubectl exec pod -- env")


def test_denies_podman_exec_env():
    assert_denied("podman exec app env")


def test_denies_python_dash_c_print_os_environ():
    assert_denied("python3 -c 'import os; print(os.environ)'")


def test_denies_python_dash_c_dict_os_environ():
    assert_denied("python3 -c 'import os; print(dict(os.environ))'")


def test_denies_node_dash_e_console_log_process_env():
    assert_denied("node -e 'console.log(process.env)'")


def test_denies_node_dash_e_json_stringify_process_env():
    assert_denied("node -e 'console.log(JSON.stringify(process.env))'")


def test_allows_cat_dot_env_example_template():
    assert_allowed("cat .env.example")


def test_allows_python_dash_c_single_var_subscript():
    assert_allowed('python3 -c \'import os; print(os.environ["HOME"])\'')


# ---------------------------------------------------------------------------
# 17. Review item 11 -- robustness: isinstance checks on the payload shape
# (null / list / string tool_input must not crash with rc=1), and a stderr
# line when hooks/_lib fails to import (today that degrades silently).
# ---------------------------------------------------------------------------

def _run_raw(raw: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("ENV_DUMP_BYPASS", None)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=raw,
        capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace", timeout=10,
    )


def test_json_null_payload_does_not_crash():
    r = _run_raw("null")
    assert r.returncode == 0, f"rc={r.returncode} (expected 0, not a crash) stderr={r.stderr}"
    assert "Traceback" not in r.stderr


def test_json_list_payload_does_not_crash():
    r = _run_raw("[]")
    assert r.returncode == 0, f"rc={r.returncode} (expected 0, not a crash) stderr={r.stderr}"
    assert "Traceback" not in r.stderr


def test_string_tool_input_does_not_crash():
    r = _run_raw(json.dumps({"tool_name": "Bash", "tool_input": "env"}))
    assert r.returncode == 0, f"rc={r.returncode} (expected 0, not a crash) stderr={r.stderr}"
    assert "Traceback" not in r.stderr


def test_lib_import_failure_warns_on_stderr():
    # Copy ONLY the hook (no _lib/ beside it) so the shell_parse import
    # fails at module load, then prove the degraded mode is now VISIBLE.
    # tempfile.TemporaryDirectory() in place of the pytest tmp_path fixture
    # -- this file has no pytest dependency.
    with tempfile.TemporaryDirectory() as tmp_dir:
        lone_hook = Path(tmp_dir) / "block-env-dump.py"
        lone_hook.write_text(HOOK.read_text())
        env = dict(os.environ)
        env.pop("ENV_DUMP_BYPASS", None)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "env"}})
        r = subprocess.run(
            [sys.executable, str(lone_hook)], input=payload,
            capture_output=True, text=True, env=env,
            encoding="utf-8", errors="replace", timeout=10,
        )
        assert r.returncode == 0  # still fails open -- degraded, not fixed
        assert r.stderr.strip() != "", "degraded _lib import must warn on stderr, not fail silently"


# ---------------------------------------------------------------------------
# 18. New vector -- pgrep listing forms that leak a titled process's
# environment. Measured on macOS with a clean-env canary: a process that
# sets its own title (npm, Node) exposes its leading ENVIRONMENT strings to
# `pgrep` whenever the short flags combine `l` (list name) with `f` (match
# full command line), in any clustering/order, or when `-a`/`--list-full`
# is present (Linux procps: unconditional full command line). PIDs-only
# (`-f` alone), name-only (`-l` alone), and any other single-letter flag
# stay allowed.
# ---------------------------------------------------------------------------

def test_denies_pgrep_glued_fl():
    assert_denied("pgrep -fl X")


def test_denies_pgrep_glued_lf():
    assert_denied("pgrep -lf X")


def test_denies_pgrep_separate_f_l():
    assert_denied("pgrep -f -l X")


def test_denies_pgrep_glued_afl():
    assert_denied("pgrep -afl X")


def test_denies_pgrep_glued_lfi():
    assert_denied("pgrep -lfi X")


def test_denies_pgrep_separate_n_l_f():
    assert_denied("pgrep -n -l -f X")


def test_denies_pgrep_lf_then_n():
    # The exact witnessed leak shape: -lf clustered, -n as a separate flag.
    assert_denied("pgrep -lf -n X")


def test_denies_pgrep_dash_a_alone_with_f():
    # -a in its own short-option cluster denies unconditionally (rule b),
    # even though the only thing paired with it here is a bare -f: on Linux
    # procps -a/--list-full means the full command line regardless of -l.
    assert_denied("pgrep -a -f X")


def test_denies_pgrep_list_full_long_flag():
    assert_denied("pgrep --list-full X")


def test_denies_pgrep_full_path():
    assert_denied("/usr/bin/pgrep -fl X")


def test_denies_sudo_pgrep_fl():
    assert_denied("sudo pgrep -fl X")


def test_denies_pgrep_fl_piped_to_head():
    # Piping into a non-extractor (head just limits lines, it does not
    # strip the value) must still deny -- same posture as bare `env` piped
    # into anything other than the three proven value-stripping extractors.
    assert_denied("pgrep -fl node | head")


def test_denies_pgrep_fl_in_and_chain():
    assert_denied("echo hi && pgrep -fl node")


def test_denies_pgrep_fl_in_semicolon_chain():
    assert_denied("true; pgrep -fl node")


# --- allowed pgrep forms ----------------------------------------------------

def test_allows_pgrep_dash_f_alone():
    assert_allowed("pgrep -f X")


def test_allows_pgrep_dash_f_piped_wc_l():
    assert_allowed("pgrep -f X | wc -l")


def test_allows_pgrep_dash_l_alone():
    assert_allowed("pgrep -l X")


def test_allows_pgrep_dash_x():
    assert_allowed("pgrep -x node")


def test_allows_pgrep_dash_n_dash_f():
    assert_allowed("pgrep -n -f X")


def test_allows_pgrep_dash_capital_p():
    assert_allowed("pgrep -P 123")


def test_allows_pkill_dash_f():
    # A different command entirely -- pkill signals, it does not print.
    assert_allowed("pkill -f X")


# --- mentions of the dangerous forms in non-pgrep contexts stay allowed -----

def test_allows_grep_mentioning_pgrep_fl():
    assert_allowed('grep "pgrep -fl" notes.md')


def test_allows_rg_mentioning_pgrep_fl():
    assert_allowed("rg 'pgrep -fl'")


def test_allows_echo_mentioning_pgrep_forms():
    assert_allowed('echo "use pgrep -f, not pgrep -fl"')


def test_allows_git_commit_message_mentioning_deny_pgrep_fl():
    assert_allowed('git commit -m "deny pgrep -fl"')


# --- known residual ----------------------------------------------------
# A dangerous pgrep form hidden inside a command substitution embedded in
# ANOTHER command's argument is not caught. The outer command's own
# resolved verb is "ps"; shlex hands the whole quoted "$(...)" back as ONE
# opaque argument token to that OUTER command, and this hook (like the rest
# of the file) does no command-substitution parsing of its own -- descending
# into $(...) would be new substitution-parsing scope this change does not
# add. Pinned here so a future change to that scope decision is deliberate,
# not a silent regression.

def test_allows_pgrep_fl_inside_command_substitution_residual():
    assert_allowed('ps -p "$(pgrep -fl x)" -o pid=')


# ---------------------------------------------------------------------------
# 19. Round 3 item 1 -- node inline print flags (-p/--print/-pe/--eval), not
# just -e, must trigger the whole-process.env content check.
# ---------------------------------------------------------------------------

def test_denies_node_dash_p_process_env():
    assert_denied("node -p process.env")


def test_denies_node_dash_dash_print_process_env():
    assert_denied("node --print process.env")


def test_denies_node_dash_pe_process_env():
    assert_denied("node -pe 'process.env'")


def test_denies_node_dash_dash_eval_console_log():
    assert_denied("node --eval 'console.log(process.env)'")


def test_denies_node_dash_p_json_stringify():
    assert_denied("node -p 'JSON.stringify(process.env)'")


def test_denies_node_dash_p_spread():
    assert_denied("node -p '({...process.env})'")


def test_allows_node_dash_p_dotted_subscript():
    assert_allowed("node -p process.env.HOME")


def test_allows_node_dash_p_bracket_subscript():
    assert_allowed("node -p 'process.env[\"HOME\"]'")


def test_allows_node_dash_p_object_keys_length():
    assert_allowed("node -p 'Object.keys(process.env).length'")


def test_allows_node_dash_e_boolean_presence():
    assert_allowed("node -e 'console.log(!!process.env.HOME)'")


def test_allows_node_dash_p_in_membership():
    assert_allowed('node -p \'"HOME" in process.env\'')


def test_allows_node_dash_dash_version():
    assert_allowed("node --version")


# ---------------------------------------------------------------------------
# 20. Round 3 item 2 -- python whole-env idioms beyond bare os.environ:
# .items()/.values()/.copy(), the {**os.environ} spread, and the
# `from os import environ` bare-name alias. Single-name access, membership,
# length, and names-only stay allowed.
# ---------------------------------------------------------------------------

def test_denies_python_items_list():
    assert_denied("python3 -c 'import os; print(list(os.environ.items()))'")


def test_denies_python_environ_copy():
    assert_denied("python3 -c 'import os; print(os.environ.copy())'")


def test_denies_python_values_list():
    assert_denied("python3 -c 'import os; print(list(os.environ.values()))'")


def test_denies_python_items_comprehension():
    assert_denied(
        'python3 -c \'import os; [print(f"{k}={v}") for k,v in os.environ.items()]\''
    )


def test_denies_python_dict_spread():
    assert_denied("python3 -c 'import os; print({**os.environ})'")


def test_denies_python_from_os_import_environ_bare_print():
    assert_denied("python3 -c 'from os import environ; print(environ)'")


def test_allows_python_in_membership_false_positive():
    # Reviewer false positive: currently denies, must become allowed.
    assert_allowed('python3 -c \'import os; print("KEY" in os.environ)\'')


def test_allows_python_environ_get():
    assert_allowed('python3 -c \'import os; print(os.environ.get("HOME"))\'')


def test_allows_python_environ_subscript():
    assert_allowed('python3 -c \'import os; print(os.environ["HOME"])\'')


def test_allows_python_getenv():
    assert_allowed('python3 -c \'import os; print(os.getenv("HOME"))\'')


def test_allows_python_len_environ():
    assert_allowed("python3 -c 'import os; print(len(os.environ))'")


def test_allows_python_sorted_keys():
    assert_allowed("python3 -c 'import os; print(sorted(os.environ.keys()))'")


def test_allows_python_list_bare_environ():
    assert_allowed("python3 -c 'import os; print(list(os.environ))'")


def test_allows_python_setdefault():
    assert_allowed("python3 -c 'import os; os.environ.setdefault(\"X\",\"1\")'")


# ---------------------------------------------------------------------------
# 21. Round 3 item 3 -- dotenv variants for the existing cat/head/tail
# reader set: .env.local/.env.production/etc are real runtime secrets;
# .env.example/.env.sample/etc are checked-in templates.
# ---------------------------------------------------------------------------

def test_denies_cat_dot_env_local():
    assert_denied("cat .env.local")


def test_denies_head_dot_env_production():
    assert_denied("head .env.production")


def test_denies_tail_dot_env_development_nested_path():
    assert_denied("tail -n 5 backend/.env.development")


def test_denies_cat_dot_env_test_local():
    assert_denied("cat .env.test.local")


def test_still_denies_cat_bare_dot_env():
    assert_denied("cat .env")


def test_still_denies_cat_foo_dot_env():
    assert_denied("cat foo.env")


def test_allows_cat_dot_env_example():
    assert_allowed("cat .env.example")


def test_allows_cat_dot_env_sample():
    assert_allowed("cat .env.sample")


def test_allows_cat_dot_env_template():
    assert_allowed("cat .env.template")


def test_allows_cat_dot_env_dist():
    assert_allowed("cat .env.dist")


def test_allows_cat_dot_env_defaults():
    assert_allowed("cat .env.defaults")


def test_allows_cat_env_dot_example_no_leading_dot():
    assert_allowed("cat env.example")


# ---------------------------------------------------------------------------
# 22. Round 3 item 4 -- jq's `env` builtin and `$ENV` global expose the whole
# process environment the same way os.environ/process.env do. Narrowed
# single-name access denies only when the name is secret-shaped (the same
# rule echo/printf already use), matching the "single value, but that value
# IS a secret" case rather than a bulk dump.
# ---------------------------------------------------------------------------

def test_denies_jq_bare_env():
    assert_denied("jq -n env")


def test_denies_jq_bare_dollar_env():
    assert_denied("jq -n '$ENV'")


def test_denies_jq_env_to_entries():
    assert_denied('jq -rn \'env|to_entries[]|"\\(.key)=\\(.value)"\'')


def test_denies_jq_env_tostream():
    assert_denied("jq -n 'env|tostream'")


def test_denies_jq_env_dot_secret_name():
    assert_denied("jq -n 'env.ANTHROPIC_API_KEY'")


def test_denies_jq_dollar_env_dot_secret_name():
    assert_denied("jq -n '$ENV.GITHUB_TOKEN'")


def test_allows_jq_env_pipe_keys():
    assert_allowed("jq -n 'env|keys'")


def test_allows_jq_env_dot_ordinary_name():
    assert_allowed("jq -n 'env.HOME'")


def test_allows_jq_dollar_env_dot_ordinary_name():
    assert_allowed("jq -n '$ENV.HOME'")


def test_allows_jq_dot_package_json():
    assert_allowed("jq . package.json")


def test_allows_jq_dash_r_dot_version():
    assert_allowed("jq -r .version package.json")


# ---------------------------------------------------------------------------
# 23. Round 3 item 5 -- wrapper resolution (timeout/nice/ionice/stdbuf/env/
# sudo), implemented locally in this hook: check the WRAPPED command as if
# it were the command. `sudo -E env` / `sudo -E pgrep -fl X` were a real gap
# -- sudo's OWN flag (-E) was never skipped, so word resolution landed on
# "-E" itself and matched nothing.
# ---------------------------------------------------------------------------

def test_denies_timeout_pgrep_fl():
    assert_denied("timeout 5 pgrep -fl foo")


def test_denies_timeout_env():
    assert_denied("timeout 5 env")


def test_denies_nice_pgrep_fl():
    assert_denied("nice pgrep -fl foo")


def test_denies_nice_dash_n_printenv():
    assert_denied("nice -n 10 printenv")


def test_denies_env_wrapping_pgrep_fl():
    assert_denied("env pgrep -fl foo")


def test_denies_env_dash_i_wrapping_printenv():
    assert_denied("env -i PATH=/usr/bin printenv")


def test_denies_sudo_dash_capital_e_env():
    assert_denied("sudo -E env")


def test_denies_sudo_dash_capital_e_pgrep_fl():
    assert_denied("sudo -E pgrep -fl foo")


def test_denies_stdbuf_glued_flag_env():
    assert_denied("stdbuf -oL env")


def test_allows_timeout_npm_test():
    assert_allowed("timeout 60 npm test")


def test_allows_nice_dash_n_make():
    assert_allowed("nice -n 10 make")


def test_allows_env_assign_wrapping_npm_build():
    assert_allowed("env FOO=1 npm run build")


def test_allows_env_dash_i_wrapping_ls():
    assert_allowed("env -i PATH=/usr/bin ls")


def test_allows_sudo_dash_capital_e_npm_install():
    assert_allowed("sudo -E npm i -g x")


# ---------------------------------------------------------------------------
# 24. Round 3 item 6 -- awk's ENVIRON array. A VARIABLE-keyed subscript
# (`ENVIRON[k]`, the shape a `for (k in ENVIRON)` loop body uses to read
# every value) denies; a literal-string-keyed subscript (`ENVIRON["HOME"]`,
# single named access) and ordinary field-splitting stay allowed.
# ---------------------------------------------------------------------------

def test_denies_awk_environ_for_in_with_concat():
    assert_denied('awk \'BEGIN{for(k in ENVIRON) print k"="ENVIRON[k]}\'')


def test_denies_awk_environ_for_in_value_only():
    assert_denied("awk 'BEGIN{for (k in ENVIRON) print ENVIRON[k]}'")


def test_allows_awk_environ_literal_key():
    assert_allowed('awk \'BEGIN{print ENVIRON["HOME"]}\'')


def test_allows_awk_field_split_dash_capital_f():
    assert_allowed("awk -F= '{print $1}'")


def test_allows_awk_field_print_with_file():
    assert_allowed("awk '{print $2}' file.txt")


# ---------------------------------------------------------------------------
# 25. Round 3 item 7 -- pgrep long options: --list-name maps to short `l`,
# --full maps to short `f`, so they combine with each other and with the
# short-flag union exactly like -l/-f do.
# ---------------------------------------------------------------------------

def test_denies_pgrep_long_list_name_and_long_full():
    assert_denied("pgrep --list-name --full foo")


def test_denies_pgrep_short_l_and_long_full():
    assert_denied("pgrep -l --full foo")


def test_denies_pgrep_short_f_and_long_list_name():
    assert_denied("pgrep -f --list-name foo")


def test_allows_pgrep_long_full_alone():
    assert_allowed("pgrep --full foo")


def test_allows_pgrep_long_list_name_alone():
    assert_allowed("pgrep --list-name foo")


# ---------------------------------------------------------------------------
# 26. Round 3 item 8 -- a here-string (`<<<`) feeding a secret-shaped
# variable into a printer (the same set the echo/printf check already
# reuses) prints its value into stdout exactly like `echo "$VAR" | cat`
# does. A non-printer consumer (docker login --password-stdin) and an
# ordinary or literal value stay allowed.
# ---------------------------------------------------------------------------

def test_denies_cat_herestring_secret_apikey():
    assert_denied('cat <<< "$ANTHROPIC_API_KEY"')


def test_denies_tee_herestring_secret_access_key():
    assert_denied('tee <<< "$AWS_SECRET_ACCESS_KEY"')


def test_denies_head_herestring_secret_token():
    assert_denied('head <<< "$GITHUB_TOKEN"')


def test_allows_docker_login_password_stdin_herestring():
    assert_allowed('docker login -u x --password-stdin <<< "$TOKEN"')


def test_allows_cat_herestring_ordinary_var():
    assert_allowed('cat <<< "$HOME"')


def test_allows_cat_herestring_literal_text():
    assert_allowed('cat <<< "hello"')


# ---------------------------------------------------------------------------
# 27. Round 3 item 9 -- other interpreters' whole-env objects: ruby ENV,
# perl %ENV, bun process.env/Bun.env, deno Deno.env.toObject(), and
# launchctl export/getenv (no inline script, subcommand-based).
# ---------------------------------------------------------------------------

def test_denies_ruby_bare_env():
    assert_denied("ruby -e 'p ENV'")


def test_denies_ruby_env_to_h():
    assert_denied("ruby -e 'puts ENV.to_h'")


def test_denies_perl_env_variable_keyed_hash():
    assert_denied("""perl -e 'print "$_=$ENV{$_}\\n" for keys %ENV'""")


def test_denies_perl_dumper_backslash_percent_env():
    assert_denied("perl -MData::Dumper -e 'print Dumper(\\%ENV)'")


def test_denies_bun_process_env():
    assert_denied("bun -e 'console.log(process.env)'")


def test_denies_bun_dot_env():
    assert_denied("bun -e 'console.log(Bun.env)'")


def test_denies_deno_eval_to_object():
    assert_denied("deno eval 'console.log(Deno.env.toObject())'")


def test_denies_launchctl_export():
    assert_denied("launchctl export")


def test_denies_launchctl_getenv_secret_name():
    assert_denied("launchctl getenv NVIDIA_API_KEY")


def test_allows_ruby_env_subscript():
    assert_allowed('ruby -e \'puts ENV["HOME"]\'')


def test_allows_perl_env_literal_key():
    assert_allowed("perl -e 'print $ENV{HOME}'")


def test_allows_bun_process_env_dotted():
    assert_allowed("bun -e 'console.log(process.env.HOME)'")


def test_allows_launchctl_list():
    assert_allowed("launchctl list")


def test_allows_launchctl_getenv_ordinary_name():
    assert_allowed("launchctl getenv PATH")


# ---------------------------------------------------------------------------
# 28. Round 3 item 10 -- one level of nested shell: bash -c/-lc, sh -c,
# zsh -c, and eval re-run the full check on the inner program, depth
# limited to 2 (this call is depth 1, the inner re-check is depth 2, no
# third level).
# ---------------------------------------------------------------------------

def test_denies_bash_dash_c_env():
    assert_denied("bash -c 'env'")


def test_denies_sh_dash_c_printenv():
    assert_denied('sh -c "printenv"')


def test_denies_zsh_dash_c_pgrep_fl():
    assert_denied("zsh -c 'pgrep -fl foo'")


def test_denies_eval_env_pipe_sort():
    assert_denied("eval 'env | sort'")


def test_denies_bash_dash_lc_node_p_process_env():
    assert_denied("bash -lc 'node -p process.env'")


def test_allows_bash_dash_c_npm_test():
    assert_allowed("bash -c 'npm test'")


def test_allows_sh_dash_c_echo_hi():
    assert_allowed('sh -c "echo hi"')


def test_allows_bash_dash_c_env_pipe_cut():
    assert_allowed("bash -c 'env | cut -d= -f1'")


def test_allows_eval_command_substitution_ssh_agent():
    assert_allowed('eval "$(ssh-agent -s)"')


# ---------------------------------------------------------------------------
# 29. Round 3 item 11 -- printenv gets the same names-only-extractor and
# presence-consumer allowance the env branch already has, plus a new
# count-only consumer (`wc -l`) both branches can use.
# ---------------------------------------------------------------------------

def test_allows_printenv_pipe_cut():
    assert_allowed("printenv | cut -d= -f1")


def test_allows_printenv_pipe_wc_l():
    assert_allowed("printenv | wc -l")


def test_still_denies_bare_printenv():
    assert_denied("printenv")


def test_still_denies_printenv_pipe_head():
    assert_denied("printenv | head")


def test_still_denies_printenv_with_name():
    assert_denied("printenv NAME")


# ---------------------------------------------------------------------------
# Plain-script runner. globals() preserves definition order (CPython 3.7+
# dict insertion order), so this walks every test_* function top-to-bottom
# exactly as written above, with no hand-maintained list to drift out of
# sync with the functions themselves.
# ---------------------------------------------------------------------------

# Today's test-function count (`grep -c '^def test_' hooks/test_block_env_dump.py`).
# A HARD FLOOR, not a target: if collection silently finds fewer tests than
# this -- a renamed test_* convention, a botched refactor, an import that
# swallowed defs -- main() must fail LOUD instead of reporting a green
# "0 passed, 0 failed" (or any N well under this) as success. Update this
# number in the SAME change that adds or removes a test_* function.
HARD_FLOOR = 162


def main() -> int:
    test_functions = [
        (name, obj) for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]

    passed = 0
    failures = []  # [(name, message), ...]
    for name, fn in test_functions:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failures.append((name, str(exc)))
        except Exception as exc:  # a crash is still a FAILURE, never a hang
            failures.append((name, f"{type(exc).__name__}: {exc}"))

    for name, message in failures:
        print(f"FAIL {name}: {message}")

    failed = len(failures)
    print(f"{passed} passed, {failed} failed")

    if failed > 0 or passed < HARD_FLOOR:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
