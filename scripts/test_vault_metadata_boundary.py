#!/usr/bin/env python3
"""Regression: the vault metadata pipeline never reads or writes a note that
resolves outside the vault, and never walks through a symlink to reach one.

The failure this pins. A recursive `glob` (`**`) follows symlinks to
directories, so a shared team or cloud folder linked into a vault was walked
like any other folder, and the extractors wrote into the notes found there. The
person extractor derives its fields (last journal date, mention count, floor
co-occurrence) from the owner's private journals, so those fields landed in
files that every other member of the shared folder can read. A folder linked in
at the vault root was skipped by name; one linked in deeper, and a note that is
itself a symlink, were not.

What is asserted, at each place the pipeline touches a file:
  - the walker (`list_vault_files`) and the insight index (`load_vault_index`)
    yield only notes that live inside the vault, and the walk never lists a
    linked folder;
  - the writer (`process_file`) refuses a path that resolves outside the vault
    BEFORE it opens it, whichever way the path reached it;
  - the run summary counts and prints a refusal instead of filing it as an error;
  - the extractors that read the vault themselves (concept backlinks, person
    journals, CRM names) do not count a note reached through a link.
Negative controls keep the guard honest: a note inside the vault is still
written, and so is one in a vault that is itself reached through a symlink. The
positive control proves the fixture really does reproduce the hazard.

Hermetic: a temp vault, a temp "shared" folder beside it, a stand-in for the
person extractor where the extractor itself is not under test, and the real
concept and person extractors pointed at the temp vault where it is. Nothing
here reads a real journal folder or a real vault.

Auto-discovered by scripts/ci.sh via the scripts/test_*.py glob.
Run: python3 scripts/test_vault_metadata_boundary.py
"""
import contextlib
import glob
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

try:
    import yaml  # noqa: F401 -- the extractors and the insight engine import it
except ImportError:
    if os.environ.get("GITHUB_ACTIONS"):
        # CI installs PyYAML for this suite, so a runner without it is broken.
        # Raising keeps a privacy regression test from passing by not running.
        raise
    print("SKIP: PyYAML is not installed (pip install pyyaml); "
          "the vault boundary assertions did not run.")
    sys.exit(0)

sys.path.insert(0, os.path.join(HERE, "extractors"))

import _base  # noqa: E402
import _dispatcher  # noqa: E402
import concept  # noqa: E402
import person  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "vault_insight_engine", os.path.join(HERE, "vault-insight-engine.py"))
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

NOTE = "---\ntype: person\n---\n\nbody\n"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class FakePersonExtractor:
    """Stands in for extractors/person.py, so the test never scans a real
    journal folder. Emits one field, the way the real one emits its counts."""
    AUTO_FIELDS = ("person_journal_mention_count",)

    @staticmethod
    def extract(filepath, body, fm, context):
        return _base.ExtractionResult(
            {"person_journal_mention_count": 3}, ["person_journal_mention_count"])


class VaultBoundary(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # realpath: on macOS the temp dir sits behind the /var -> /private/var link.
        self.root = os.path.realpath(tmp.name)
        self.vault = os.path.join(self.root, "vault")
        self.shared = os.path.join(self.root, "shared-folder")  # a team or cloud folder
        self.sibling = os.path.join(self.root, "vault-copy")    # its name starts with the vault's

        # Every place the pipeline reads the vault root goes through these three
        # names; put them back after the test, before anything below can skip.
        self.addCleanup(setattr, _base, "VAULT", _base.VAULT)
        self.addCleanup(setattr, _dispatcher, "VAULT", _dispatcher.VAULT)
        self.addCleanup(setattr, engine, "VAULT", engine.VAULT)

        self.inside_note = os.path.join(self.vault, "👤 CRM", "Inside Person.md")
        for path in (
            self.inside_note,
            os.path.join(self.vault, ".hidden", "Hidden Person.md"),  # hidden folder
            os.path.join(self.vault, ".Dot Person.md"),               # hidden file
            os.path.join(self.shared, "👥 CRM", "Team Person.md"),
            os.path.join(self.shared, "Linked Person.md"),
            os.path.join(self.shared, "nested", "Nested Person.md"),
            os.path.join(self.sibling, "Sibling Person.md"),
        ):
            _write(path, NOTE)

        # Four ways a note outside the vault shows up under a vault path.
        self._link(self.shared, os.path.join(self.vault, "🤝 Shared"), True)
        self._link(os.path.join(self.shared, "nested"),
                   os.path.join(self.vault, "👤 CRM", "Team Share"), True)
        self._link(os.path.join(self.shared, "Linked Person.md"),
                   os.path.join(self.vault, "Linked Person.md"), False)
        self._link(os.path.join(self.sibling, "Sibling Person.md"),
                   os.path.join(self.vault, "Sibling Person.md"), False)
        # In production a folder linked in at the vault ROOT is also skipped by
        # name (SKIP_PARTS, computed once at import). This vault is built after
        # import, so that skip cannot help here: containment has to hold alone.
        self.outside_paths = (
            os.path.join(self.vault, "🤝 Shared", "👥 CRM", "Team Person.md"),      # folder link, vault root
            os.path.join(self.vault, "👤 CRM", "Team Share", "Nested Person.md"),  # folder link, nested
            os.path.join(self.vault, "Linked Person.md"),                          # the note is the link
            os.path.join(self.vault, "Sibling Person.md"),                         # target shares the vault's name as a prefix
        )
        self._point_at(self.vault)

    def _link(self, target, link, is_dir):
        try:
            os.symlink(target, link, target_is_directory=is_dir)
        except (OSError, NotImplementedError):
            self.skipTest("this platform cannot create symlinks here")

    def _point_at(self, vault):
        _base.VAULT = _dispatcher.VAULT = engine.VAULT = vault

    def _process(self, path, **kwargs):
        return _dispatcher.process_file(
            path, {"person": FakePersonExtractor}, {"crm_names": set()}, **kwargs)

    @contextlib.contextmanager
    def _spy_on_opens(self):
        """Record every open() the dispatcher makes, passing each one through."""
        with mock.patch.object(_dispatcher, "open", side_effect=open,
                               create=True) as spy:
            yield spy

    def _run_main(self, files=None):
        """Run the dispatcher's main() on the fixture vault with the stand-in
        extractor, and return what it printed. `files` replaces the walk."""
        report = io.StringIO()
        with mock.patch.object(_dispatcher, "discover_extractors",
                               return_value={"person": FakePersonExtractor}), \
                mock.patch.object(_dispatcher, "get_crm_names", return_value=set()), \
                mock.patch.object(sys, "argv", ["vault-metadata-extract"]), \
                contextlib.redirect_stdout(report):
            if files is None:
                _dispatcher.main()
            else:
                with mock.patch.object(_dispatcher, "list_vault_files",
                                       return_value=iter(files)):
                    _dispatcher.main()
        return report.getvalue()

    @contextlib.contextmanager
    def _record_listings(self):
        """Yield the list of every directory os.scandir is asked to list."""
        listed = []
        real_scandir = os.scandir

        def record(path):
            listed.append(os.fsdecode(path))
            return real_scandir(path)

        with mock.patch.object(os, "scandir", side_effect=record):
            yield listed

    def test_fixture_exposes_the_hazard(self):
        """Positive control: a recursive glob really does reach the outside
        notes through the links. If a future Python stopped following them this
        goes red and says the fixture no longer reproduces the bug, instead of
        letting every test below pass on nothing."""
        found = set(glob.glob(os.path.join(self.vault, "**", "*.md"), recursive=True))
        for path in self.outside_paths:
            self.assertIn(path, found)

    def test_walker_yields_only_notes_inside_the_vault(self):
        found = sorted(os.path.basename(p) for p in _dispatcher.list_vault_files())
        self.assertEqual(found, ["Inside Person.md"])

    def test_insight_index_yields_only_notes_inside_the_vault(self):
        found = sorted(os.path.basename(x["path"]) for x in engine.load_vault_index())
        self.assertEqual(found, ["Inside Person.md"])

    def test_walking_a_subfolder_stays_inside_the_vault(self):
        crm = os.path.join(self.vault, "👤 CRM")
        found = sorted(os.path.basename(p) for p in _base.iter_vault_markdown(crm))
        self.assertEqual(found, ["Inside Person.md"])

    def test_walking_a_folder_outside_or_above_the_vault_yields_nothing(self):
        for root in (self.shared, self.root):  # a sibling folder, and an ancestor of the vault
            with self.subTest(root=root):
                with self._record_listings() as listed:
                    found = list(_base.iter_vault_markdown(root))
                self.assertEqual(found, [])
                self.assertEqual(listed, [])  # not even the top folder is listed

    def test_walk_agrees_with_the_per_note_check(self):
        """The walker resolves each folder once instead of each note. It must
        still give exactly the answer is_inside_vault() gives note by note,
        including for a note linked to another note inside the vault."""
        alias = os.path.join(self.vault, "Alias Person.md")
        self._link(self.inside_note, alias, False)
        # A link to a folder is not entered even when it points inside the vault:
        # the notes are yielded under their real path only. The walker does not
        # apply the callers' skip-by-name (Archive), so the real path is yielded.
        _write(os.path.join(self.vault, "Archive", "Old Person.md"), NOTE)
        self._link(os.path.join(self.vault, "Archive"), os.path.join(self.vault, "Old Link"), True)
        self._link(os.path.join(self.vault, "👤 CRM"), os.path.join(self.vault, "CRM Alias"), True)
        expected = []
        for dirpath, dirnames, filenames in os.walk(self.vault):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                path = os.path.join(dirpath, name)
                if (name.endswith(".md") and not name.startswith(".")
                        and _base.is_inside_vault(path)):
                    expected.append(path)
        self.assertIn(alias, expected)  # a link that stays inside the vault is kept
        found = sorted(_base.iter_vault_markdown())
        self.assertEqual(found, sorted(expected))
        self.assertIn(os.path.join(self.vault, "Archive", "Old Person.md"), found)
        self.assertNotIn(os.path.join(self.vault, "Old Link", "Old Person.md"), found)
        self.assertNotIn(os.path.join(self.vault, "CRM Alias", "Inside Person.md"), found)

    def test_a_folder_os_walk_does_not_flag_as_a_link_is_still_not_entered(self):
        """A link that os.walk does not report as one (a Windows junction, for
        instance) is a folder os.walk would go into. Simulate that by making
        os.walk follow links, and expect the walker to prune a folder by where it
        resolves, before os.walk lists it."""
        real_walk = os.walk

        def follows_links(top, **kwargs):
            kwargs["followlinks"] = True
            return real_walk(top, **kwargs)

        with mock.patch.object(os, "walk", side_effect=follows_links), \
                self._record_listings() as listed:
            found = sorted(os.path.basename(p) for p in _base.iter_vault_markdown())
        self.assertEqual(found, ["Inside Person.md"])
        linked = (os.path.join(self.vault, "🤝 Shared"),
                  os.path.join(self.vault, "👤 CRM", "Team Share"))
        entered = [d for d in listed if any(d == p or d.startswith(p + os.sep) for p in linked)]
        self.assertEqual(entered, [])

    def test_walker_never_lists_a_linked_folder(self):
        """Filtering the results is not enough: a shared folder can be huge, or
        sit on a stalled mount, so the walk must not go into it at all."""
        with self._record_listings() as listed:
            list(_dispatcher.list_vault_files())
        self.assertIn(self.vault, listed)  # the recorder does see the walk
        linked = (os.path.join(self.vault, "🤝 Shared"),
                  os.path.join(self.vault, "👤 CRM", "Team Share"))
        entered = [d for d in listed if any(d == p or d.startswith(p + os.sep) for p in linked)]
        self.assertEqual(entered, [])

    def test_writer_refuses_a_path_that_resolves_outside_the_vault(self):
        for path in self.outside_paths:
            for kwargs in ({}, {"dry_run": True}, {"force": True}):
                with self.subTest(path=path, **kwargs):
                    before = _read(path)
                    with self._spy_on_opens() as opened:
                        status = self._process(path, **kwargs)
                    self.assertEqual(status, "OUTSIDE_VAULT")
                    self.assertEqual(opened.call_count, 0, "the refused path was opened")
                    self.assertEqual(_read(path), before)

    def test_writer_still_writes_a_note_inside_the_vault(self):
        """Negative control: the guard does not block a legitimate write. The
        spy sees this writer's opens, so the zero above is not vacuous."""
        with self._spy_on_opens() as opened:
            status = self._process(self.inside_note)
        self.assertEqual(status, "WROTE")
        self.assertTrue(opened.called)
        self.assertIn("person_journal_mention_count: 3", _read(self.inside_note))

    def test_a_vault_reached_through_a_symlink_keeps_working(self):
        """Negative control: the vault root itself may be a link (a synced
        folder, a relocated drive). Its own notes are inside it, not outside."""
        alias = os.path.join(self.root, "vault-alias")
        self._link(self.vault, alias, True)
        self._point_at(alias)
        found = {os.path.basename(p) for p in _dispatcher.list_vault_files()}
        self.assertIn("Inside Person.md", found)
        indexed = {os.path.basename(x["path"]) for x in engine.load_vault_index()}
        self.assertIn("Inside Person.md", indexed)
        self.assertEqual(
            self._process(os.path.join(alias, "👤 CRM", "Inside Person.md")), "WROTE")

    def test_summary_counts_and_prints_a_refusal(self):
        """A path the walker cannot yield can still reach the writer through
        another caller. The run must count it and say so, not file it as an
        error or drop it."""
        report = self._run_main(files=[self.outside_paths[1], self.inside_note])
        lines = report.splitlines()
        refused = [line for line in lines if "REFUSED" in line]
        self.assertEqual(len(refused), 1, report)
        self.assertTrue(refused[0].rstrip().endswith(": 1"), refused[0])
        self.assertFalse([line for line in lines if line.strip().startswith("Errors:")],
                         report)
        # The run went on past the refusal, and only the in-vault note changed.
        self.assertIn("person_journal_mention_count: 3", _read(self.inside_note))
        self.assertNotIn("person_journal_mention_count", _read(self.outside_paths[1]))

    def test_concept_mentions_do_not_count_notes_reached_through_a_link(self):
        """The backlink count reads the whole vault, so notes in a linked folder
        were counted as mentions and written into the concept note."""
        concept_note = os.path.join(self.vault, "📝 Notes", "Deep Work.md")
        _write(concept_note, "---\ntype: concept\n---\n\n# Deep Work\n")
        _write(os.path.join(self.vault, "📝 Notes", "Mentions It.md"),
               "---\ntype: note\n---\n\nSee [[Deep Work]].\n")
        elsewhere = os.path.join(self.root, "shared-notes")  # linked once, so each note is met once
        for name in ("Elsewhere One.md", "Elsewhere Two.md"):
            _write(os.path.join(elsewhere, name),
                   "---\ntype: note\n---\n\nAlso [[Deep Work]].\n")
        self._link(elsewhere, os.path.join(self.vault, "📝 Notes", "deeper"), True)
        with mock.patch.object(concept, "VAULT", self.vault), \
                mock.patch.object(concept, "_BACKLINK_INDEX", None):
            status = _dispatcher.process_file(
                concept_note, {"concept": concept}, {"crm_names": set()})
        self.assertEqual(status, "WROTE")
        self.assertIn("concept_mention_count: 1\n", _read(concept_note))

    def test_person_journal_fields_do_not_count_journals_reached_through_a_link(self):
        """The journal index reads the journal folder, so journals in a linked
        folder fed the mention count and the last-journal date."""
        journals = os.path.join(self.vault, "📓 Journals")
        entry = ("---\ncreationDate: 2026-08-0{day}T21:10\ntype: journal\n---\n\n"
                 "Spoke with [[Inside Person]] today.\n")
        _write(os.path.join(journals, "2026-08-01.md"), entry.format(day=1))
        for day, name in ((2, "Their One.md"), (3, "Their Two.md")):
            _write(os.path.join(self.shared, name), entry.format(day=day))
        self._link(self.shared, os.path.join(journals, "shared"), True)
        with mock.patch.object(person, "JOURNALS_ROOT", journals), \
                mock.patch.object(person, "_JOURNAL_INDEX", None):
            status = _dispatcher.process_file(
                self.inside_note, {"person": person}, {"crm_names": set()})
        self.assertEqual(status, "WROTE")
        written = _read(self.inside_note)
        self.assertIn("person_journal_mention_count: 1\n", written)
        self.assertIn('person_last_journal_iso: "2026-08-01"', written)

    def test_crm_names_do_not_include_notes_reached_through_a_link(self):
        crm = os.path.join(self.vault, "👤 CRM")  # Inside Person.md and the Team Share link
        with mock.patch.object(_base, "CRM_ROOT", crm), \
                mock.patch.object(_base, "_CRM_CACHE", None):
            names = _base.get_crm_names()
        self.assertEqual(names, {"Inside Person"})

    def test_a_crm_folder_outside_the_vault_is_reported_not_silently_empty(self):
        err = io.StringIO()
        with mock.patch.object(_base, "CRM_ROOT", self.shared), \
                mock.patch.object(_base, "_CRM_CACHE", None), \
                contextlib.redirect_stderr(err):
            names = _base.get_crm_names()
        self.assertEqual(names, set())
        self.assertIn("outside the vault", err.getvalue())

    def test_a_journal_folder_outside_the_vault_is_reported_not_silently_empty(self):
        err = io.StringIO()
        with mock.patch.object(person, "JOURNALS_ROOT", self.shared), \
                mock.patch.object(person, "_JOURNAL_INDEX", None), \
                contextlib.redirect_stderr(err):
            index = person._build_journal_index()
        self.assertEqual(index, {})
        self.assertIn("outside the vault", err.getvalue())

    def test_type_peek_refuses_a_path_that_resolves_outside_the_vault(self):
        """--type and --sample peek at each note's header, and that read comes
        before the writer's guard, so it needs the same boundary."""
        for path in self.outside_paths:
            with self.subTest(path=path):
                with self._spy_on_opens() as opened:
                    peeked = _dispatcher._peek_type(path)
                self.assertIsNone(peeked)
                self.assertEqual(opened.call_count, 0, "the refused path was opened")

    def test_type_peek_still_reads_a_note_inside_the_vault(self):
        """Negative control: the guard does not stop a legitimate peek."""
        with self._spy_on_opens() as opened:
            peeked = _dispatcher._peek_type(self.inside_note)
        self.assertEqual(peeked, "person")
        self.assertTrue(opened.called)

    def test_walker_records_what_it_skips_because_it_resolves_outside_the_vault(self):
        skipped = []
        list(_base.iter_vault_markdown(skipped=skipped))
        folders = sorted(os.path.relpath(p, self.vault) for kind, p in skipped if kind == "folder")
        notes = sorted(os.path.relpath(p, self.vault) for kind, p in skipped if kind == "note")
        self.assertEqual(folders, sorted(["🤝 Shared", os.path.join("👤 CRM", "Team Share")]))
        self.assertEqual(notes, ["Linked Person.md", "Sibling Person.md"])

    def test_summary_says_how_many_links_out_of_the_vault_were_skipped(self):
        """A link that is not walked is never an invisible exclusion: the run
        says how many folders and notes it left out, and which."""
        report = self._run_main()
        lines = [line for line in report.splitlines() if "resolve outside the vault" in line]
        self.assertEqual(len(lines), 1, report)
        self.assertIn("2 folder(s), 2 note(s)", lines[0])
        for name in ("🤝 Shared", "Team Share", "Linked Person.md", "Sibling Person.md"):
            self.assertIn(name, report)

    def test_summary_is_silent_about_links_when_there_are_none(self):
        """Negative control: a vault with no link out prints no such line."""
        clean = os.path.join(self.root, "clean-vault")
        _write(os.path.join(clean, "👤 CRM", "Only Person.md"), NOTE)
        self._point_at(clean)
        report = self._run_main()
        self.assertIn("Wrote / would-write: 1", report)  # the run did happen
        self.assertNotIn("resolve outside the vault", report)

    def test_insight_engine_says_how_many_links_out_of_the_vault_were_not_indexed(self):
        report = io.StringIO()
        with mock.patch.object(engine, "OUTPUT_PATH", os.path.join(self.root, "insights.md")), \
                mock.patch.object(sys, "argv", ["vault-insight-engine", "--quiet"]), \
                contextlib.redirect_stdout(report):
            engine.main()
        lines = [line for line in report.getvalue().splitlines()
                 if "resolve outside the vault" in line]
        self.assertEqual(len(lines), 1, report.getvalue())
        self.assertIn("2 folder(s), 2 note(s)", lines[0])


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): the fixture paths are emoji-named, and
    # a failing assertion prints them. Force UTF-8 so that can't crash the run.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    unittest.main(verbosity=2)
