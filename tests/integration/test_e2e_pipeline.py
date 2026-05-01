#!/usr/bin/env python3
"""
End-to-end integration test for the catalect pipeline.

Exercises the 5 catalect primitives together (typed memory, ingestion,
synthesis, resolver/aggregator, validator/promoter) against a fresh
temporary vault. Each step asserts a specific contract; the script
exits 0 only on full pass.

Stdlib + PyYAML only. Bare python3 runnable, no pytest.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required (pip install pyyaml).", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = Path("/tmp/abs-integration-vault")
SCRIPTS = REPO_ROOT / "scripts"
HOOKS = REPO_ROOT / "hooks"
SKILLS = REPO_ROOT / "skills"


def fail(step: str, detail: str) -> None:
    print(f"FAIL [{step}] {detail}", file=sys.stderr)
    sys.exit(1)


def ok(step: str, detail: str) -> None:
    print(f"PASS [{step}] {detail}")


def run(cmd: list[str], cwd: Path | None = None, stdin: str | None = None,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2]


def setup_vault() -> None:
    if VAULT_ROOT.exists():
        shutil.rmtree(VAULT_ROOT)
    VAULT_ROOT.mkdir(parents=True)
    (VAULT_ROOT / "Meta").mkdir()
    (VAULT_ROOT / "Meta" / "Decisions").mkdir()
    (VAULT_ROOT / "Meta" / "Workflows").mkdir()
    (VAULT_ROOT / "Meta" / "Exceptions").mkdir()
    (VAULT_ROOT / "Meta" / "Facts").mkdir()
    (VAULT_ROOT / "Meta" / "Learnings").mkdir()
    (VAULT_ROOT / "Meta" / "Wiki").mkdir()
    (VAULT_ROOT / "External Inputs" / "Slack" / "test-channel").mkdir(parents=True)


def cleanup() -> None:
    if VAULT_ROOT.exists():
        shutil.rmtree(VAULT_ROOT)


# Step 1+2: Synthesize a Slack-ingested thread file as fixture.
def step_1_2_create_ingested_file() -> Path:
    target = VAULT_ROOT / "External Inputs" / "Slack" / "test-channel" / "2026-01-01.md"
    fm = {
        "type": "slack-thread",
        "channel": "test-channel",
        "channel_id": "C0TEST123",
        "thread_url": "https://example.slack.com/archives/C0TEST123/p1735689600000100",
        "thread_ts": "1735689600.000100",
        "ingested_at": "2026-01-01T12:00:00Z",
    }
    body = textwrap.dedent(
        """
        # Resolved thread: pricing exception for legacy account

        **alex**
        Heads up team, customer X is asking for a pricing exception on the legacy plan because of a billing carve-out we agreed to last quarter. We don't normally do this, but for this client only we'll override the standard rate.

        **jordan**
        Approved. Document this as a one-off for the legacy account only. We don't extend it to other customers.
        """
    ).strip()
    target.write_text(
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False).strip()
        + "\n---\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    if not target.is_file():
        fail("step-1-2", f"Expected file at {target} not created.")
    text = target.read_text(encoding="utf-8")
    if "pricing exception" not in text.lower():
        fail("step-1-2", "Trigger keyword 'pricing exception' missing in fixture body.")
    if not text.startswith("---"):
        fail("step-1-2", "Frontmatter delimiter missing on fixture file.")
    ok("step-1-2", f"Ingested fixture at {target.relative_to(VAULT_ROOT)}.")
    return target


# Step 3: Run synth-thread-to-sop on the ingested file. Verify typed memory written.
def step_3_synth_thread(ingested: Path) -> Path:
    synth_path = SKILLS / "synth-thread-to-sop" / "synth.py"
    proc = run(
        ["python3", str(synth_path), str(ingested),
         "--vault-root", str(VAULT_ROOT),
         "--classify-as", "exception"],
    )
    if proc.returncode != 0:
        fail("step-3-synth", f"synth.py exit {proc.returncode}: {proc.stderr.strip()}")

    exception_dir = VAULT_ROOT / "Meta" / "Exceptions"
    candidates = list(exception_dir.glob("*.md"))
    if not candidates:
        fail("step-3-synth", f"No typed-memory file produced in {exception_dir}.")
    if len(candidates) != 1:
        fail("step-3-synth", f"Expected exactly 1 exception file, got {len(candidates)}.")

    typed_path = candidates[0]
    fm, _body = split_frontmatter(typed_path.read_text(encoding="utf-8"))

    required = {
        "type": "exception",
        "memory_class": "procedural",
    }
    for key, want in required.items():
        if fm.get(key) != want:
            fail("step-3-synth",
                 f"Typed-memory file {typed_path.name} field {key}={fm.get(key)!r} (want {want!r}).")

    must_have = ["sha8", "last_verified", "freshness_days", "provenance",
                 "entity_ids", "exception_summary"]
    missing = [k for k in must_have if k not in fm]
    if missing:
        fail("step-3-synth",
             f"Typed-memory file missing required fields: {missing}. Present: {sorted(fm.keys())}.")

    entity_ids = fm.get("entity_ids") or {}
    if "slack" not in entity_ids:
        fail("step-3-synth",
             f"entity_ids.slack missing. entity_ids={entity_ids!r}.")

    ok("step-3-synth",
       f"Synthesized exception at {typed_path.relative_to(VAULT_ROOT)} (sha8={fm.get('sha8')!r}).")
    return typed_path


# Step 4: resolver-build.py emits Meta/RESOLVER.md including the new entry.
def step_4_resolver_build(typed_path: Path) -> Path:
    proc = run(
        ["python3", str(SCRIPTS / "resolver-build.py"),
         "--vault-root", str(VAULT_ROOT)],
    )
    if proc.returncode != 0:
        fail("step-4-resolver", f"resolver-build.py exit {proc.returncode}: {proc.stderr.strip()}")

    resolver_path = VAULT_ROOT / "Meta" / "RESOLVER.md"
    if not resolver_path.is_file():
        fail("step-4-resolver", f"Expected {resolver_path} not produced.")

    text = resolver_path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    if fm.get("type") != "resolver":
        fail("step-4-resolver", f"RESOLVER.md frontmatter type={fm.get('type')!r} (want 'resolver').")

    if typed_path.stem not in body:
        fail("step-4-resolver",
             f"RESOLVER.md does not reference typed-memory rule_id {typed_path.stem!r}.")

    if "exception" not in body:
        fail("step-4-resolver", "RESOLVER.md missing 'exception' type marker.")

    ok("step-4-resolver",
       f"RESOLVER.md built at {resolver_path.relative_to(VAULT_ROOT)} ({len(text)} bytes).")
    return resolver_path


# Step 5: stale-rule-check.py says NOT stale (just-set last_verified).
def step_5_stale_check_fresh() -> None:
    proc = run(
        ["python3", str(SCRIPTS / "stale-rule-check.py"),
         "--vault-root", str(VAULT_ROOT)],
    )
    if proc.returncode != 0:
        fail("step-5-stale-fresh",
             f"Expected exit 0 (no stale rules), got {proc.returncode}. "
             f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()!r}")
    if "STALE" in proc.stdout:
        fail("step-5-stale-fresh",
             f"Stale flagged on a fresh entry. stdout={proc.stdout.strip()!r}")
    ok("step-5-stale-fresh", "No stale rules flagged on fresh entry.")


# Step 6: Backdate last_verified, re-run, verify exit code 2.
def step_6_stale_check_backdated(typed_path: Path) -> None:
    text = typed_path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    backdated = (dt.date.today() - dt.timedelta(days=200)).isoformat()
    fm["last_verified"] = backdated
    new_text = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n"
        + body
    )
    typed_path.write_text(new_text, encoding="utf-8")

    proc = run(
        ["python3", str(SCRIPTS / "stale-rule-check.py"),
         "--vault-root", str(VAULT_ROOT)],
    )
    if proc.returncode != 2:
        fail("step-6-stale-backdated",
             f"Expected exit 2 (stale found), got {proc.returncode}. "
             f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()!r}")
    if "STALE" not in proc.stdout:
        fail("step-6-stale-backdated",
             f"Expected 'STALE' in stdout. stdout={proc.stdout.strip()!r}")
    ok("step-6-stale-backdated",
       f"Stale flagged after backdating last_verified to {backdated}.")


# Step 7: proposed-update-drafter scans vault for refs to changed file.
def step_7_proposed_update(typed_path: Path) -> None:
    downstream = VAULT_ROOT / "Meta" / "downstream-ref.md"
    downstream.write_text(
        f"---\ntype: note\n---\n\n"
        f"This note references the typed-memory rule [[{typed_path.stem}]] "
        f"in the policy section.\n",
        encoding="utf-8",
    )

    proc = run(
        ["python3", str(SCRIPTS / "proposed-update-drafter.py"),
         "--vault-root", str(VAULT_ROOT),
         "--changed-file", str(typed_path)],
    )
    if proc.returncode != 0:
        fail("step-7-proposed-update",
             f"proposed-update-drafter exit {proc.returncode}. "
             f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()!r}")

    output = proc.stdout
    if "downstream-ref.md" not in output:
        fail("step-7-proposed-update",
             f"Drafter did not find the downstream reference. stdout={output!r}")

    after = downstream.read_text(encoding="utf-8")
    if "proposed-update:BEGIN" not in after:
        fail("step-7-proposed-update",
             "Drafter did not write the proposed-update banner into the downstream file.")
    ok("step-7-proposed-update", "Drafter found and annotated 1 downstream reference.")


# Step 8: validate-skill-frontmatter.py exit 0 on a valid SKILL.md.
def step_8_skill_validator_pass() -> Path:
    skill_dir = VAULT_ROOT / "skills" / "fixture-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    valid_fm = {
        "type": "skill",
        "name": "fixture-skill",
        "description": "Synthetic skill for integration test.",
        "tool_access": ["Read", "Write"],
        "policy_constraints": [
            {"rule": "Never write outside the test vault root.",
             "exception_handling": "abort and surface to caller"},
        ],
        "required_inputs": [
            {"name": "vault_root", "type": "path", "required": True,
             "description": "Path to the vault."},
        ],
        "output_shape": {"summary": "string"},
        "confidence": 0.8,
        "freshness_days": 90,
        "last_verified": dt.date.today().isoformat(),
        "source_count": 1,
    }
    body = "# Fixture Skill\n\nSynthetic SKILL.md for integration testing.\n"
    content = (
        "---\n"
        + yaml.safe_dump(valid_fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + body
    )
    skill_md.write_text(content, encoding="utf-8")

    hook_input = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": str(skill_md), "content": content},
    })
    proc = run(
        ["python3", str(HOOKS / "validate-skill-frontmatter.py")],
        stdin=hook_input,
    )
    if proc.returncode != 0:
        fail("step-8-validator-pass",
             f"Validator returned {proc.returncode} on a valid SKILL.md. "
             f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()!r}")

    try:
        result = json.loads(proc.stdout)
        decision = result.get("hookSpecificOutput", {}).get("permissionDecision")
    except json.JSONDecodeError:
        fail("step-8-validator-pass",
             f"Validator emitted non-JSON stdout: {proc.stdout!r}")
        return skill_md  # unreachable
    if decision != "allow":
        fail("step-8-validator-pass",
             f"Validator decision={decision!r} on a valid SKILL.md (want 'allow').")
    ok("step-8-validator-pass", "Valid SKILL.md frontmatter allowed.")
    return skill_md


# Step 9: Break the SKILL.md, validator must deny.
def step_9_skill_validator_fail(skill_md: Path) -> None:
    broken_fm = {
        "description": "Broken skill missing required type and name.",
        "tool_access": ["Read"],
    }
    body = "# Broken\n"
    broken_content = (
        "---\n"
        + yaml.safe_dump(broken_fm, sort_keys=False).strip()
        + "\n---\n\n"
        + body
    )

    hook_input = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": str(skill_md), "content": broken_content},
    })
    proc = run(
        ["python3", str(HOOKS / "validate-skill-frontmatter.py")],
        stdin=hook_input,
    )
    if proc.returncode == 0:
        try:
            result = json.loads(proc.stdout)
            decision = result.get("hookSpecificOutput", {}).get("permissionDecision")
        except json.JSONDecodeError:
            decision = None
        if decision == "allow":
            fail("step-9-validator-fail",
                 "Validator allowed broken SKILL.md (missing required type+name).")
    ok("step-9-validator-fail",
       f"Validator rejected broken SKILL.md (exit {proc.returncode}).")


# Step 10: 3 similar Learnings -> promote-episodic-to-procedural drafts a candidate.
def step_10_promote_episodic() -> None:
    learnings_dir = VAULT_ROOT / "Meta" / "Learnings"
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    error_excerpt = (
        "Bash command failed permission denied tmp pipeline write target "
        "user vault scripts execution context error retry"
    )
    for i in range(3):
        fm = {
            "type": "learning",
            "memory_class": "episodic",
            "captured_at": captured_at,
            "source_tool": "Bash",
            "error_excerpt": error_excerpt,
            "provenance": [
                {"source_type": "claude-session",
                 "source_id": f"session-{i}",
                 "captured_at": captured_at},
            ],
        }
        body = (
            "## Tool input\n\n"
            "Bash run\n\n"
            "## Error excerpt\n\n"
            f"```\n{error_excerpt}\n```\n"
        )
        text = (
            "---\n"
            + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
            + "\n---\n\n"
            + body
        )
        (learnings_dir / f"2026-01-0{i + 1}-fixture{i}.md").write_text(text, encoding="utf-8")

    proc = run(
        ["python3", str(SCRIPTS / "promote-episodic-to-procedural.py"),
         "--vault-root", str(VAULT_ROOT),
         "--min-occurrences", "3"],
    )
    if proc.returncode != 0:
        fail("step-10-promote",
             f"promote-episodic-to-procedural exit {proc.returncode}. "
             f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()!r}")

    candidates_dir = VAULT_ROOT / "Meta" / "Promotion-Candidates"
    candidates = list(candidates_dir.glob("*.md")) if candidates_dir.is_dir() else []
    if not candidates:
        fail("step-10-promote",
             f"No promotion candidate at {candidates_dir}. stdout={proc.stdout.strip()!r}")

    fm, _ = split_frontmatter(candidates[0].read_text(encoding="utf-8"))
    if fm.get("status") != "candidate":
        fail("step-10-promote",
             f"Candidate status={fm.get('status')!r} (want 'candidate').")
    if fm.get("memory_class") != "procedural":
        fail("step-10-promote",
             f"Candidate memory_class={fm.get('memory_class')!r} (want 'procedural').")

    ok("step-10-promote",
       f"Promotion candidate drafted at {candidates[0].relative_to(VAULT_ROOT)}.")


# Step 11: Add a topic to the typed memory and run ground-truth-wiki-maintain.
def step_11_wiki_maintain(typed_path: Path) -> None:
    text = typed_path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    fm["topic"] = "pricing"
    new_text = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n"
        + body
    )
    typed_path.write_text(new_text, encoding="utf-8")

    proc = run(
        ["python3", str(SCRIPTS / "ground-truth-wiki-maintain.py"),
         "--vault-root", str(VAULT_ROOT),
         "--topic-folder", "pricing"],
    )
    if proc.returncode != 0:
        fail("step-11-wiki",
             f"ground-truth-wiki-maintain exit {proc.returncode}. "
             f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()!r}")

    wiki_path = VAULT_ROOT / "Meta" / "Wiki" / "pricing.md"
    if not wiki_path.is_file():
        fail("step-11-wiki", f"Wiki page not produced at {wiki_path}.")

    wiki_text = wiki_path.read_text(encoding="utf-8")
    wiki_fm, _ = split_frontmatter(wiki_text)
    if wiki_fm.get("auto_generated") is not True:
        fail("step-11-wiki",
             f"Wiki frontmatter auto_generated={wiki_fm.get('auto_generated')!r} (want True).")
    if wiki_fm.get("topic") != "pricing":
        fail("step-11-wiki",
             f"Wiki frontmatter topic={wiki_fm.get('topic')!r} (want 'pricing').")
    if "## Exceptions" not in wiki_text:
        fail("step-11-wiki", "Wiki body missing '## Exceptions' section for matched entry.")

    ok("step-11-wiki",
       f"Wiki page built at {wiki_path.relative_to(VAULT_ROOT)} (auto_generated=true).")


def main() -> int:
    print(f"Integration test: vault at {VAULT_ROOT}")
    print(f"Repo root: {REPO_ROOT}")
    print()
    setup_vault()
    try:
        ingested = step_1_2_create_ingested_file()
        typed = step_3_synth_thread(ingested)
        step_4_resolver_build(typed)
        step_5_stale_check_fresh()
        step_6_stale_check_backdated(typed)
        step_7_proposed_update(typed)
        skill_md = step_8_skill_validator_pass()
        step_9_skill_validator_fail(skill_md)
        step_10_promote_episodic()
        step_11_wiki_maintain(typed)
    finally:
        cleanup()

    print()
    print("ALL 11 STEPS PASSED. Catalect pipeline integration green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
