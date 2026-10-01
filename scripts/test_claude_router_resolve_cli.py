#!/usr/bin/env python3
"""Negative-control suite for how the router finds the `claude` CLI (MYC-5205).

`_resolve_cli()` used to fall back to a hardcoded list whose first entry was one
machine's `~/local/node-<version>-darwin-arm64/bin/claude`. On any other install
that directory does not exist, and on the machine it came from it stopped being the
right copy the day node was upgraded: the old directory stayed behind, frozen at
whatever version it had, and every scheduled job whose PATH lacked `claude` kept
resolving it. The fix globs the node-versioned installs, reads the version each one
carries in its own package.json (never spawning it), and takes the newest.

These plant real directory layouts under a throwaway HOME and prove, each against
the old behavior as well as the new:

  * the NEWEST install wins whatever order the directories sort in
  * a tie goes to the first one listed; an unreadable version never beats a readable one
  * CLAUDE_CLI_PATH overrides everything; a missing file falls through
  * `claude` on PATH still wins over every fallback
  * nothing found -> None
  * resolving never RUNS a candidate (a sentinel script proves it)
  * no machine-specific node-version directory is spelled out in the source, with
    a positive control showing the same check does find a planted copy

Run: python3 scripts/test_claude_router_resolve_cli.py
Run under pytest: pytest scripts/test_claude_router_resolve_cli.py
Exit 0 = pass. Vanilla unittest, no third-party deps.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import _claude_router as R  # noqa: E402

# Split so this file itself never carries the literal it asserts is absent.
FORBIDDEN_DIR = "node-v20.19.0" "-darwin-arm64"


def _symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink("target", os.path.join(d, "link"))
        except (OSError, NotImplementedError):
            return False
    return True


class ResolveCliFallback(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.system = self.root / "system"
        self.system.mkdir()

        env = {"HOME": str(self.home), "USERPROFILE": str(self.home)}
        patches = [
            mock.patch.dict(os.environ, env),
            # not on PATH: the state of every launchd/cron caller
            mock.patch.object(R.shutil, "which", lambda *_a, **_k: None),
            # stand-ins for /opt/homebrew/bin and /usr/local/bin, never the host's
            # create=True so this suite can also be pointed at a router that predates
            # the constant and fail on BEHAVIOR rather than on a missing attribute
            mock.patch.object(R, "_SYSTEM_CLI_FALLBACKS", (), create=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for var in ("CLAUDE_CLI_PATH", "CLAUDE_ROUTER_DISABLE_CLI"):
            os.environ.pop(var, None)

    # --- fixtures -----------------------------------------------------------
    def _install(self, prefix: Path, version: str | None, marker: Path | None = None) -> Path:
        """An npm-shaped install whose bin entry is a plain executable file with the
        package.json in the conventional place beside it (no symlinks needed)."""
        bin_dir = prefix / "bin"
        bin_dir.mkdir(parents=True)
        cli = bin_dir / "claude"
        body = "#!/bin/sh\n"
        if marker is not None:
            body += 'touch "%s"\n' % marker
        body += 'echo "%s (Claude Code)"\n' % (version or "0.0.0")
        cli.write_text(body, encoding="utf-8")
        cli.chmod(0o755)
        if version is not None:
            pkg = prefix / "lib" / "node_modules" / "@anthropic-ai" / "claude-code"
            pkg.mkdir(parents=True)
            (pkg / "package.json").write_text(
                json.dumps({"name": "@anthropic-ai/claude-code", "version": version}),
                encoding="utf-8")
        return cli

    def _node(self, name: str, version: str | None) -> Path:
        return self._install(self.home / "local" / name, version)

    # --- selection ----------------------------------------------------------
    def test_newest_install_wins_whatever_order_the_directories_sort_in(self):
        old = self._node("node-v18-old", "2.1.100")
        new = self._node("node-v20-mid", "2.1.300")
        other = self._node("node-v22-new", "2.1.200")
        # the fixture must put the newest version in the MIDDLE of the sort order,
        # so neither "first listed" nor "last listed" can pick it by accident
        self.assertEqual(sorted([old, new, other]).index(new), 1)
        self.assertEqual(R._resolve_cli(), str(new))

    def test_stale_copy_is_not_privileged_by_being_found_first(self):
        # The pre-fix list returned the first path that existed. Here the stale copy
        # sorts first AND is the only one such a list would have named.
        self._node("node-a-stale", "2.1.246")
        fresh = self._node("node-b-fresh", "2.1.286")
        self.assertEqual(R._resolve_cli(), str(fresh))

    def test_tie_goes_to_the_first_one_listed(self):
        first = self._node("node-a", "2.1.286")
        self._node("node-b", "2.1.286")
        self.assertEqual(R._resolve_cli(), str(first))

    def test_node_installs_are_listed_before_the_fixed_locations(self):
        node = self._node("node-a", "2.1.286")
        self._install(self.home / ".local", "2.1.286")   # same version, listed later
        self.assertEqual(R._resolve_cli(), str(node))

    def test_a_newer_fixed_location_beats_an_older_node_install(self):
        self._node("node-a", "2.1.100")
        local = self._install(self.home / ".local", "2.1.400")
        self.assertEqual(R._resolve_cli(), str(local))

    def test_system_locations_take_part(self):
        self._node("node-a", "2.1.100")
        sysbin = self._install(self.system / "opt", "2.1.500")
        with mock.patch.object(R, "_SYSTEM_CLI_FALLBACKS", (sysbin,), create=True):
            self.assertEqual(R._resolve_cli(), str(sysbin))

    def test_a_readable_version_beats_an_unreadable_one_even_when_later(self):
        self._node("node-a-noversion", None)
        known = self._node("node-b-known", "2.1.100")
        self.assertEqual(R._resolve_cli(), str(known))

    def test_with_no_readable_version_the_first_that_exists_is_used(self):
        first = self._node("node-a", None)
        self._node("node-b", None)
        self.assertEqual(R._resolve_cli(), str(first))

    def test_prerelease_suffix_does_not_break_the_comparison(self):
        self._node("node-a", "2.1.100")
        beta = self._node("node-b", "2.1.200-beta.1")
        self.assertEqual(R._resolve_cli(), str(beta))

    def test_a_package_json_for_some_other_package_is_not_a_version(self):
        self._node("node-a-liar", None)
        pkg = self.home / "local" / "node-a-liar" / "lib" / "node_modules" / "@anthropic-ai" / "claude-code"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(
            json.dumps({"name": "left-pad", "version": "9.9.9"}), encoding="utf-8")
        honest = self._node("node-b-honest", "2.1.100")
        self.assertEqual(R._resolve_cli(), str(honest))

    @unittest.skipUnless(_symlinks_supported(), "symlinks unavailable")
    def test_real_npm_layout_bin_symlink_into_the_package(self):
        # exactly what `npm i -g` lays down: bin/claude -> ../lib/.../bin/claude.exe
        for name, version in (("node-a", "2.1.246"), ("node-b", "2.1.286")):
            prefix = self.home / "local" / name
            pkg = prefix / "lib" / "node_modules" / "@anthropic-ai" / "claude-code"
            (pkg / "bin").mkdir(parents=True)
            (prefix / "bin").mkdir(parents=True)
            exe = pkg / "bin" / "claude.exe"
            exe.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
            exe.chmod(0o755)
            (pkg / "package.json").write_text(
                json.dumps({"name": "@anthropic-ai/claude-code", "version": version}),
                encoding="utf-8")
            os.symlink("../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe",
                       prefix / "bin" / "claude")
        self.assertEqual(R._resolve_cli(), str(self.home / "local" / "node-b" / "bin" / "claude"))

    @unittest.skipUnless(_symlinks_supported(), "symlinks unavailable")
    def test_native_installer_layout_reads_the_version_from_the_path(self):
        self._node("node-a", "2.1.100")
        versions = self.home / ".local" / "share" / "claude" / "versions"
        versions.mkdir(parents=True)
        binary = versions / "2.1.400"
        binary.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
        binary.chmod(0o755)
        (self.home / ".local" / "bin").mkdir(parents=True)
        os.symlink(binary, self.home / ".local" / "bin" / "claude")
        self.assertEqual(R._resolve_cli(), str(self.home / ".local" / "bin" / "claude"))

    # --- overrides, PATH, and nothing ----------------------------------------
    def test_claude_cli_path_overrides_everything(self):
        self._node("node-a", "2.1.900")
        chosen = self.root / "elsewhere" / "claude"
        chosen.parent.mkdir()
        chosen.write_text("x", encoding="utf-8")
        with mock.patch.dict(os.environ, {"CLAUDE_CLI_PATH": str(chosen)}):
            self.assertEqual(R._resolve_cli(), str(chosen))

    def test_a_missing_claude_cli_path_falls_through_to_the_installs(self):
        node = self._node("node-a", "2.1.100")
        with mock.patch.dict(os.environ, {"CLAUDE_CLI_PATH": str(self.root / "nope")}):
            self.assertEqual(R._resolve_cli(), str(node))

    def test_claude_on_path_still_wins_over_every_fallback(self):
        self._node("node-a", "2.1.900")
        with mock.patch.object(R.shutil, "which", lambda *_a, **_k: "/somewhere/on/PATH/claude"):
            self.assertEqual(R._resolve_cli(), "/somewhere/on/PATH/claude")

    def test_nothing_found_is_none(self):
        self.assertIsNone(R._resolve_cli())

    def test_disable_cli_is_none_even_with_installs_present(self):
        self._node("node-a", "2.1.100")
        with mock.patch.dict(os.environ, {"CLAUDE_ROUTER_DISABLE_CLI": "1"}):
            self.assertIsNone(R._resolve_cli())

    # --- resolving never runs a candidate -------------------------------------
    def test_resolving_never_spawns_a_candidate(self):
        marker_a, marker_b = self.root / "ran-a", self.root / "ran-b"
        self._install(self.home / "local" / "node-a", "2.1.100", marker_a)
        self._install(self.home / "local" / "node-b", "2.1.200", marker_b)
        with mock.patch.object(R.subprocess, "run", side_effect=AssertionError("spawned")), \
                mock.patch.object(R.subprocess, "Popen", side_effect=AssertionError("spawned")):
            chosen = R._resolve_cli()
        self.assertTrue(chosen.endswith(os.path.join("node-b", "bin", "claude")))
        self.assertFalse(marker_a.exists() or marker_b.exists(),
                         "a candidate was executed to read its version")


class SourceSpellsOutNoMachineSpecificDirectory(unittest.TestCase):
    """The pre-fix source named one machine's node-version directory."""

    @staticmethod
    def _mentions_forbidden(text: str) -> bool:
        return FORBIDDEN_DIR in text

    def test_router_source_has_no_node_version_directory(self):
        src = Path(R.__file__).read_text(encoding="utf-8")
        self.assertFalse(self._mentions_forbidden(src))

    def test_the_check_is_not_vacuous(self):
        # Positive control: the very same predicate does find a planted copy.
        planted = 'home / "local/%s/bin/claude",\n' % FORBIDDEN_DIR
        self.assertTrue(self._mentions_forbidden(planted))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "planted_router.py"
            f.write_text("fallbacks = [\n    " + planted + "]\n", encoding="utf-8")
            self.assertTrue(self._mentions_forbidden(f.read_text(encoding="utf-8")))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
