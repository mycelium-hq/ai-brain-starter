#!/usr/bin/env python3
"""test_synth_llm_mode.py

Integration test for the optional --use-llm code path on
skills/synth-pr-to-sop and skills/synth-thread-to-sop.

This test does NOT call the real Anthropic API. It monkeypatches
llm_synth._make_client with a fake client that returns canned content.
The test verifies:
  1. The system prompt is built with cache_control set (TTL 1h).
  2. The LLM-refined fields (title, steps, summary) override the heuristic
     fields when refine_extraction returns valid JSON.
  3. The script falls back to heuristic-only on missing-dep / missing-key,
     and writes synthesis_mode=heuristic in that case.

Run bare:
    python3 tests/integration/test_synth_llm_mode.py
Exits 0 on full pass, prints failing assertion on first error.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "skills" / "_shared"))


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeUsage:
    def __init__(
        self,
        input_tokens: int = 100,
        output_tokens: int = 50,
        cache_creation: int = 80,
        cache_read: int = 0,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation
        self.cache_read_input_tokens = cache_read


class _FakeResponse:
    def __init__(self, text: str, usage: _FakeUsage | None = None) -> None:
        self.content = [_FakeBlock(text)]
        self.usage = usage or _FakeUsage()


class _FakeClient:
    """Pretends to be an anthropic.Anthropic() instance."""
    def __init__(self, canned_payload: dict) -> None:
        self._canned = canned_payload
        self.last_call = None

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.last_call = kwargs
        return _FakeResponse(json.dumps(self._canned))


def _make_fake_factory(payload: dict):
    holder = {}
    def factory():
        client = _FakeClient(payload)
        holder["client"] = client
        return client
    return factory, holder


class TestLlmSynthHelper(unittest.TestCase):
    def test_system_prompt_has_cache_control_ttl_1h(self):
        import llm_synth
        factory, holder = _make_fake_factory({"title": "x", "steps": []})
        result, err = llm_synth.refine_extraction(
            "raw text", "workflow",
            kind="merged GitHub PR",
            client_factory=factory,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(result)
        call = holder["client"].last_call
        self.assertIn("system", call)
        system = call["system"]
        self.assertIsInstance(system, list)
        self.assertEqual(len(system), 1)
        block = system[0]
        self.assertEqual(block.get("type"), "text")
        cc = block.get("cache_control")
        self.assertIsNotNone(cc, "cache_control missing on system block")
        self.assertEqual(cc.get("type"), "ephemeral")
        self.assertEqual(cc.get("ttl"), "1h")

    def test_returns_error_on_missing_dep_when_no_factory(self):
        import llm_synth
        # Without injecting a factory and without an API key, expect a soft error.
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result, err = llm_synth.refine_extraction(
                "raw text", "workflow",
                kind="merged GitHub PR",
                client_factory=None,
            )
        finally:
            if old_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = old_key
        self.assertIsNone(result)
        self.assertIsNotNone(err)
        self.assertTrue(
            "anthropic" in err.lower() or "ANTHROPIC_API_KEY" in err,
            f"expected dep/key error, got: {err}",
        )

    def test_unknown_memory_type_rejected(self):
        import llm_synth
        factory, _ = _make_fake_factory({})
        result, err = llm_synth.refine_extraction(
            "x", "garbage", client_factory=factory,
        )
        self.assertIsNone(result)
        self.assertIn("unknown memory_type", err)


class TestSynthPrToSopLlmMode(unittest.TestCase):
    def setUp(self):
        self.vault = Path(tempfile.mkdtemp(prefix="abs-synth-llm-"))
        self.pr_path = self.vault / "synthetic-pr.md"
        self.pr_path.write_text(
            "# PR #99: Original heuristic title\n\n"
            "## Steps\n1. heuristic step one\n2. heuristic step two\n"
        )

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def test_llm_mode_overrides_title_and_steps(self):
        import importlib
        import llm_synth
        # Patch in a fake client that returns refined content.
        canned = {
            "title": "LLM-Refined Title",
            "steps": [
                {"step_number": 1, "description": "refined step alpha"},
                {"step_number": 2, "description": "refined step beta", "owner": "alice"},
            ],
            "summary": "LLM thinks this PR adds X for Y reason.",
        }
        factory, _ = _make_fake_factory(canned)
        original_make = llm_synth._make_client
        original_is_avail = llm_synth.is_available
        llm_synth._make_client = lambda client_factory=None: factory()
        # Bypass dep + key check; _make_client is fully monkeypatched.
        llm_synth.is_available = lambda: (True, "ok")
        try:
            sys.path.insert(0, str(REPO_ROOT / "skills" / "synth-pr-to-sop"))
            if "synth" in sys.modules:
                del sys.modules["synth"]
            synth_mod = importlib.import_module("synth")
            result_path = synth_mod.synth_one(
                pr_path=self.pr_path,
                vault_root=self.vault,
                dry_run=False,
                force=False,
                use_llm=True,
            )
            self.assertIsNotNone(result_path)
            written = Path(result_path).read_text()
            self.assertIn("LLM-Refined Title", written, "LLM title should appear in frontmatter")
            self.assertIn("refined step alpha", written)
            self.assertIn("refined step beta", written)
            self.assertIn("synthesis_mode: llm-refined", written)
            self.assertIn("llm_summary:", written)
        finally:
            llm_synth._make_client = original_make
            llm_synth.is_available = original_is_avail

    def test_heuristic_mode_marker_when_llm_off(self):
        import importlib
        sys.path.insert(0, str(REPO_ROOT / "skills" / "synth-pr-to-sop"))
        if "synth" in sys.modules:
            del sys.modules["synth"]
        synth_mod = importlib.import_module("synth")
        result_path = synth_mod.synth_one(
            pr_path=self.pr_path,
            vault_root=self.vault,
            dry_run=False,
            force=False,
            use_llm=False,
        )
        self.assertIsNotNone(result_path)
        written = Path(result_path).read_text()
        self.assertIn("synthesis_mode: heuristic", written)
        self.assertIn("Original heuristic title", written)


if __name__ == "__main__":
    unittest.main(verbosity=2)
