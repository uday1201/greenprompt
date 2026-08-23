"""
test_migrate.py — unit tests for database consolidation and sudo path handling.

Two related problems are covered.

**Consolidation.** Versions before 0.3.0 resolved the database path from the
working directory, so a user can easily end up with several databases; the
machine this was developed on had three. `greenprompt migrate` folds them into
the one in use, and must be safe to run repeatedly — the property most easily
got wrong, and the one that would silently double a user's history.

**sudo.** `greenprompt setup` is meant to be run once as root to install the
powermetrics rule, but it also creates the config and the database. Resolving
those against `~` gives root's home, or gives the user's home with root-owned
files that the user then cannot write.
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from greenprompt import constants, dbconn


def _make_db(path, rows):
    """Create a prompt_usage database at `path` holding `rows`."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    with mock.patch.object(dbconn, "DB_PATH", path):
        dbconn.init_db()
    for ts, prompt, model in rows:
        conn.execute(
            "INSERT INTO prompt_usage (timestamp, prompt, model) VALUES (?, ?, ?)",
            (ts, prompt, model),
        )
    conn.commit()
    conn.close()
    return path


class MigrateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.target = os.path.join(self.tmp, "target", dbconn.DB_FILENAME)
        p = mock.patch.object(dbconn, "DB_PATH", self.target)
        p.start()
        self.addCleanup(p.stop)

    def rows(self):
        return dbconn.get_prompt_usage()


class TestIsUsageDatabase(MigrateTestCase):
    def test_recognises_a_real_database(self):
        src = _make_db(os.path.join(self.tmp, "a", dbconn.DB_FILENAME), [])
        self.assertTrue(dbconn.is_usage_database(src))

    def test_rejects_a_missing_file(self):
        self.assertFalse(dbconn.is_usage_database(os.path.join(self.tmp, "nope.db")))

    def test_rejects_a_non_sqlite_file(self):
        path = os.path.join(self.tmp, "junk.db")
        with open(path, "w") as f:
            f.write("this is not a database")
        self.assertFalse(dbconn.is_usage_database(path))

    def test_rejects_a_sqlite_file_without_the_table(self):
        path = os.path.join(self.tmp, "other.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
        conn.commit()
        conn.close()
        self.assertFalse(dbconn.is_usage_database(path))


class TestMergeDatabase(MigrateTestCase):
    def test_copies_rows(self):
        src = _make_db(
            os.path.join(self.tmp, "a", dbconn.DB_FILENAME),
            [
                ("2026-01-01T00:00:00.1", "p1", "m"),
                ("2026-01-02T00:00:00.2", "p2", "m"),
            ],
        )
        self.assertEqual(dbconn.merge_database(src), 2)
        self.assertEqual(len(self.rows()), 2)

    def test_is_idempotent(self):
        """Running a merge twice must not double the history."""
        src = _make_db(
            os.path.join(self.tmp, "a", dbconn.DB_FILENAME),
            [("2026-01-01T00:00:00.1", "p1", "m")],
        )
        dbconn.merge_database(src)
        second = dbconn.merge_database(src)
        self.assertEqual(second, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_merging_three_sources_converges(self):
        srcs = [
            _make_db(
                os.path.join(self.tmp, name, dbconn.DB_FILENAME),
                [(f"2026-01-0{i}T00:00:00.{i}", f"p{i}", "m")],
            )
            for i, name in enumerate(("a", "b", "c"), start=1)
        ]
        for _ in range(2):  # twice over
            for src in srcs:
                dbconn.merge_database(src)
        self.assertEqual(len(self.rows()), 3)

    def test_only_new_rows_are_copied(self):
        src = _make_db(
            os.path.join(self.tmp, "a", dbconn.DB_FILENAME),
            [
                ("2026-01-01T00:00:00.1", "p1", "m"),
                ("2026-01-02T00:00:00.2", "p2", "m"),
            ],
        )
        dbconn.merge_database(src)
        _make_db(src, [("2026-01-03T00:00:00.3", "p3", "m")])
        self.assertEqual(dbconn.merge_database(src), 1)
        self.assertEqual(len(self.rows()), 3)

    def test_dry_run_writes_nothing(self):
        src = _make_db(
            os.path.join(self.tmp, "a", dbconn.DB_FILENAME),
            [("2026-01-01T00:00:00.1", "p1", "m")],
        )
        self.assertEqual(dbconn.merge_database(src, dry_run=True), 1)
        self.assertEqual(len(self.rows()), 0)

    def test_source_is_left_untouched(self):
        src = _make_db(
            os.path.join(self.tmp, "a", dbconn.DB_FILENAME),
            [("2026-01-01T00:00:00.1", "p1", "m")],
        )
        before = open(src, "rb").read()
        dbconn.merge_database(src)
        self.assertEqual(open(src, "rb").read(), before)

    def test_merging_the_target_into_itself_is_a_no_op(self):
        _make_db(self.target, [("2026-01-01T00:00:00.1", "p1", "m")])
        self.assertEqual(dbconn.merge_database(self.target), 0)
        self.assertEqual(len(self.rows()), 1)

    def test_rejects_a_non_database(self):
        path = os.path.join(self.tmp, "junk.db")
        with open(path, "w") as f:
            f.write("nope")
        with self.assertRaises(ValueError):
            dbconn.merge_database(path)

    def test_rows_with_null_fields_are_matched_correctly(self):
        # `IS` rather than `=`, so NULL identity columns dedupe properly.
        src = os.path.join(self.tmp, "a", dbconn.DB_FILENAME)
        _make_db(src, [])
        conn = sqlite3.connect(src)
        conn.execute(
            "INSERT INTO prompt_usage (timestamp, prompt, model) VALUES (?, NULL, NULL)",
            ("2026-01-01T00:00:00.1",),
        )
        conn.commit()
        conn.close()
        self.assertEqual(dbconn.merge_database(src), 1)
        self.assertEqual(dbconn.merge_database(src), 0)

    def test_merged_rows_get_fresh_ids(self):
        _make_db(self.target, [("2026-01-01T00:00:00.1", "existing", "m")])
        src = _make_db(
            os.path.join(self.tmp, "a", dbconn.DB_FILENAME),
            [("2026-02-01T00:00:00.9", "incoming", "m")],
        )
        dbconn.merge_database(src)
        ids = [r["id"] for r in self.rows()]
        self.assertEqual(len(ids), len(set(ids)))


class TestFindDatabases(MigrateTestCase):
    def test_finds_databases_below_a_root(self):
        _make_db(os.path.join(self.tmp, "proj-a", dbconn.DB_FILENAME), [])
        _make_db(os.path.join(self.tmp, "proj-b", dbconn.DB_FILENAME), [])
        found = dbconn.find_databases(search_roots=[self.tmp], exclude=[self.target])
        self.assertEqual(len(found), 2)

    def test_excludes_the_database_in_use(self):
        _make_db(self.target, [])
        found = dbconn.find_databases(search_roots=[self.tmp])
        self.assertNotIn(os.path.abspath(self.target), found)

    def test_ignores_files_that_are_not_databases(self):
        path = os.path.join(self.tmp, "fake", dbconn.DB_FILENAME)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            f.write("not a database")
        self.assertEqual(dbconn.find_databases(search_roots=[self.tmp]), [])

    def test_respects_the_depth_limit(self):
        deep = os.path.join(self.tmp, "a", "b", "c", "d", "e", dbconn.DB_FILENAME)
        _make_db(deep, [])
        self.assertEqual(
            dbconn.find_databases(search_roots=[self.tmp], max_depth=2), []
        )

    def test_skips_hidden_and_dependency_directories(self):
        for noisy in (".git", "node_modules", ".venv"):
            _make_db(os.path.join(self.tmp, noisy, dbconn.DB_FILENAME), [])
        self.assertEqual(dbconn.find_databases(search_roots=[self.tmp]), [])

    def test_a_missing_root_is_not_an_error(self):
        self.assertEqual(
            dbconn.find_databases(search_roots=[os.path.join(self.tmp, "absent")]), []
        )


class TestInvokingUserHome(unittest.TestCase):
    def test_plain_user_gets_expanduser(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUDO_USER", None)
            self.assertEqual(constants.invoking_user_home(), os.path.expanduser("~"))

    def test_sudo_resolves_the_invoking_user(self):
        fake = mock.Mock(pw_dir="/Users/someone")
        with (
            mock.patch.dict(os.environ, {"SUDO_USER": "someone"}),
            mock.patch.object(os, "geteuid", return_value=0),
            mock.patch.dict("sys.modules", {"pwd": mock.Mock(getpwnam=lambda n: fake)}),
        ):
            self.assertEqual(constants.invoking_user_home(), "/Users/someone")

    def test_sudo_user_set_but_not_root_is_ignored(self):
        # e.g. a leftover SUDO_USER in an unprivileged shell.
        with (
            mock.patch.dict(os.environ, {"SUDO_USER": "someone"}),
            mock.patch.object(os, "geteuid", return_value=501),
        ):
            self.assertEqual(constants.invoking_user_home(), os.path.expanduser("~"))

    def test_unknown_sudo_user_falls_back(self):
        pwd_stub = mock.Mock(getpwnam=mock.Mock(side_effect=KeyError("nope")))
        with (
            mock.patch.dict(os.environ, {"SUDO_USER": "ghost"}),
            mock.patch.object(os, "geteuid", return_value=0),
            mock.patch.dict("sys.modules", {"pwd": pwd_stub}),
        ):
            self.assertEqual(constants.invoking_user_home(), os.path.expanduser("~"))


class TestGiveToInvokingUser(unittest.TestCase):
    def test_no_op_when_not_root(self):
        with (
            mock.patch.object(os, "geteuid", return_value=501),
            mock.patch.object(os, "chown") as chown,
        ):
            constants.give_to_invoking_user("/tmp/whatever")
        chown.assert_not_called()

    def test_no_op_without_sudo_uid(self):
        with (
            mock.patch.object(os, "geteuid", return_value=0),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(os, "chown") as chown,
        ):
            constants.give_to_invoking_user("/tmp/whatever")
        chown.assert_not_called()

    def test_chowns_to_the_invoking_user(self):
        with (
            mock.patch.object(os, "geteuid", return_value=0),
            mock.patch.dict(os.environ, {"SUDO_UID": "501", "SUDO_GID": "20"}),
            mock.patch.object(os, "chown") as chown,
        ):
            constants.give_to_invoking_user("/a", "/b")
        chown.assert_has_calls([mock.call("/a", 501, 20), mock.call("/b", 501, 20)])

    def test_a_failing_chown_is_swallowed(self):
        with (
            mock.patch.object(os, "geteuid", return_value=0),
            mock.patch.dict(os.environ, {"SUDO_UID": "501", "SUDO_GID": "20"}),
            mock.patch.object(os, "chown", side_effect=OSError),
        ):
            constants.give_to_invoking_user("/nonexistent")  # must not raise


class TestSchemaIsIdempotent(MigrateTestCase):
    def test_init_db_can_run_repeatedly(self):
        for _ in range(3):
            dbconn.init_db()
        self.assertEqual(self.rows(), [])

    def test_indexes_are_created(self):
        dbconn.init_db()
        conn = dbconn.get_connection()
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        conn.close()
        self.assertIn("idx_prompt_usage_timestamp", names)
        self.assertIn("idx_prompt_usage_model", names)

    def test_indexes_survive_a_second_init(self):
        dbconn.init_db()
        dbconn.init_db()  # CREATE INDEX IF NOT EXISTS must not raise


def _make_legacy_db(path, columns, rows):
    """Create a prompt_usage table with only `columns` — an older schema."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    cols = ", ".join(f"{c} TEXT" for c in columns if c != "id")
    conn.execute(
        f"CREATE TABLE prompt_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols})"
    )
    placeholders = ", ".join("?" for _ in rows[0]) if rows else ""
    names = ", ".join(c for c in columns if c != "id")
    for row in rows:
        conn.execute(f"INSERT INTO prompt_usage ({names}) VALUES ({placeholders})", row)
    conn.commit()
    conn.close()
    return path


class TestMergeAcrossSchemaVersions(MigrateTestCase):
    """
    The table has gained columns over time — prompt_score and
    prompt_score_details arrived with prompt scoring, energy_estimate_* later —
    so databases worth merging are exactly the ones with fewer columns. On the
    machine this was developed on, three real databases had three different
    schemas: 20, 18 and 16 columns.
    """

    def test_source_missing_columns_still_merges(self):
        src = _make_legacy_db(
            os.path.join(self.tmp, "old", dbconn.DB_FILENAME),
            ["id", "timestamp", "prompt", "model", "response"],
            [("2026-01-01T00:00:00.1", "p1", "m", "r1")],
        )
        self.assertEqual(dbconn.merge_database(src), 1)
        row = self.rows()[0]
        self.assertEqual(row["prompt"], "p1")
        self.assertEqual(row["response"], "r1")
        # A column the source never had comes through as NULL, not an error.
        self.assertIsNone(row["prompt_score"])

    def test_merging_mixed_schemas_is_still_idempotent(self):
        modern = _make_db(
            os.path.join(self.tmp, "new", dbconn.DB_FILENAME),
            [("2026-01-01T00:00:00.1", "p1", "m")],
        )
        legacy = _make_legacy_db(
            os.path.join(self.tmp, "old", dbconn.DB_FILENAME),
            ["id", "timestamp", "prompt", "model"],
            [("2026-02-01T00:00:00.2", "p2", "m")],
        )
        for _ in range(3):
            dbconn.merge_database(modern)
            dbconn.merge_database(legacy)
        self.assertEqual(len(self.rows()), 2)

    def test_a_source_sharing_no_columns_is_rejected(self):
        path = os.path.join(self.tmp, "weird", dbconn.DB_FILENAME)
        os.makedirs(os.path.dirname(path))
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE prompt_usage (id INTEGER PRIMARY KEY, unrelated TEXT)"
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ValueError):
            dbconn.merge_database(path)

    def test_extra_columns_in_the_source_are_ignored(self):
        src = _make_legacy_db(
            os.path.join(self.tmp, "future", dbconn.DB_FILENAME),
            ["id", "timestamp", "prompt", "model", "invented_column"],
            [("2026-01-01T00:00:00.1", "p1", "m", "x")],
        )
        self.assertEqual(dbconn.merge_database(src), 1)
        self.assertEqual(self.rows()[0]["prompt"], "p1")


class TestDiscoveryAndMergeTogether(MigrateTestCase):
    def test_discovered_databases_merge_to_a_stable_total(self):
        for i, name in enumerate(("p1", "p2", "p3"), start=1):
            _make_db(
                os.path.join(self.tmp, name, dbconn.DB_FILENAME),
                [(f"2026-0{i}-01T00:00:00.{i}", f"prompt {i}", "m")],
            )
        found = dbconn.find_databases(search_roots=[self.tmp], exclude=[self.target])
        self.assertEqual(len(found), 3)
        for _ in range(2):
            for src in found:
                dbconn.merge_database(src)
        self.assertEqual(len(self.rows()), 3)


if __name__ == "__main__":
    unittest.main()
