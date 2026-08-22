"""
test_dbconn.py — unit tests for the SQLite persistence layer.

The headline case is the timestamp format. `datetime.utcnow()` is deprecated
in Python 3.12, but the obvious replacement — `datetime.now(timezone.utc)` —
emits a "+00:00" suffix. Because `get_prompt_usage()` filters by comparing
timestamps as *strings*, that suffix would sort inconsistently against every
row already written and silently break /api/usage/timeframe. These tests pin
the format so a future cleanup cannot reintroduce the problem.

Every test runs against a temporary database file, never the real one.
"""

import ast
import os
import pathlib
import tempfile
import warnings
import unittest
from datetime import datetime
from unittest import mock

from greenprompt import dbconn


class TestUtcNowIso(unittest.TestCase):
    def test_has_no_timezone_suffix(self):
        value = dbconn.utc_now_iso()
        self.assertFalse(value.endswith("+00:00"), value)
        self.assertFalse(value.endswith("Z"), value)

    def test_parses_back_as_a_naive_datetime(self):
        parsed = datetime.fromisoformat(dbconn.utc_now_iso())
        self.assertIsNone(parsed.tzinfo)

    def test_matches_the_legacy_utcnow_shape(self):
        # Exactly what datetime.utcnow().isoformat() produced, so old rows and
        # new rows remain mutually comparable as strings.
        self.assertRegex(
            dbconn.utc_now_iso(),
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$",
        )

    def test_is_actually_utc_and_current(self):
        produced = datetime.fromisoformat(dbconn.utc_now_iso())
        delta = abs((datetime.utcnow() - produced).total_seconds())
        self.assertLess(delta, 5)

    def test_values_sort_chronologically_as_strings(self):
        # The property /api/usage/timeframe depends on.
        early = "2020-01-01T00:00:00"
        now = dbconn.utc_now_iso()
        self.assertLess(early, now)


class DbTestCase(unittest.TestCase):
    """Point dbconn at a throwaway database for the duration of each test."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)  # let init_db create it
        patcher = mock.patch.object(dbconn, "DB_PATH", self.db_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(
            lambda: os.path.exists(self.db_path) and os.unlink(self.db_path)
        )

    @staticmethod
    def record(**overrides):
        data = {
            "prompt": "a prompt",
            "prompt_score": 46,
            "prompt_score_details": {"Clarity": 5},
            "response": "an answer",
            "model": "llama3.2:latest",
            "prompt_tokens": 12,
            "completion_tokens": 30,
            "total_tokens": 42,
            "energy_estimate_prompt": 0.001,
            "energy_estimate_tokens": 0.002,
            "duration_sec": 1.5,
            "total_energy (Wh)": 0.5,
            "baseline_power (W)": 2.0,
            "baseline_energy (Wh)": 0.1,
            "cpu_power_w (W)": 7.0,
            "gpu_power_w (W)": 3.0,
            "combined_power_w (W)": 10.0,
        }
        data.update(overrides)
        return data


class TestSchema(DbTestCase):
    def test_init_db_creates_the_table(self):
        dbconn.init_db()
        self.assertTrue(os.path.exists(self.db_path))
        self.assertEqual(dbconn.get_prompt_usage(), [])

    def test_init_db_is_idempotent(self):
        dbconn.init_db()
        dbconn.init_db()  # must not raise
        self.assertEqual(dbconn.get_prompt_usage(), [])

    def test_reads_work_without_an_explicit_init(self):
        # A fresh working directory must not raise "no such table".
        self.assertEqual(dbconn.get_prompt_usage(), [])

    def test_stored_columns_match_the_declared_column_order(self):
        with mock.patch.object(dbconn, "get_system_info", return_value={"OS": "Test"}):
            dbconn.save_prompt_usage(self.record())
        row = dbconn.get_prompt_usage()[0]
        self.assertEqual(tuple(row.keys()), dbconn.PROMPT_USAGE_COLUMNS)


class TestSaveAndRead(DbTestCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(dbconn, "get_system_info", return_value={"OS": "Test"})
        p.start()
        self.addCleanup(p.stop)

    def test_round_trip(self):
        dbconn.save_prompt_usage(self.record())
        rows = dbconn.get_prompt_usage()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prompt"], "a prompt")
        self.assertEqual(rows[0]["model"], "llama3.2:latest")
        self.assertEqual(rows[0]["total_tokens"], 42)

    def test_display_keys_are_mapped_to_columns(self):
        # run_prompt() returns "total_energy (Wh)"; the column is energy_wh.
        dbconn.save_prompt_usage(self.record())
        row = dbconn.get_prompt_usage()[0]
        self.assertEqual(row["energy_wh"], 0.5)
        self.assertEqual(row["cpu_power_w"], 7.0)
        self.assertEqual(row["baseline_power_w"], 2.0)

    def test_plain_column_names_also_accepted(self):
        rec = self.record()
        for display, plain in (
            ("total_energy (Wh)", "energy_wh"),
            ("cpu_power_w (W)", "cpu_power_w"),
        ):
            rec[plain] = rec.pop(display)
        dbconn.save_prompt_usage(rec)
        row = dbconn.get_prompt_usage()[0]
        self.assertEqual(row["energy_wh"], 0.5)
        self.assertEqual(row["cpu_power_w"], 7.0)

    def test_timestamp_written_in_the_pinned_format(self):
        dbconn.save_prompt_usage(self.record())
        ts = dbconn.get_prompt_usage()[0]["timestamp"]
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")

    def test_json_blobs_are_serialised(self):
        dbconn.save_prompt_usage(self.record())
        row = dbconn.get_prompt_usage()[0]
        self.assertIsInstance(row["prompt_score_details"], str)
        self.assertIn("Clarity", row["prompt_score_details"])


class TestFilters(DbTestCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(dbconn, "get_system_info", return_value={"OS": "Test"})
        p.start()
        self.addCleanup(p.stop)
        dbconn.init_db()
        # Insert rows with controlled timestamps, bypassing utc_now_iso.
        conn = dbconn.get_connection()
        for ts, model in [
            ("2026-01-01T00:00:00", "llama2"),
            ("2026-06-01T00:00:00", "llama3.2:latest"),
            ("2026-12-01T00:00:00", "llama3.2:latest"),
        ]:
            conn.execute(
                "INSERT INTO prompt_usage (timestamp, model) VALUES (?, ?)", (ts, model)
            )
        conn.commit()
        conn.close()

    def test_no_filter_returns_everything(self):
        self.assertEqual(len(dbconn.get_prompt_usage()), 3)

    def test_results_are_ordered_by_timestamp(self):
        rows = dbconn.get_prompt_usage()
        stamps = [r["timestamp"] for r in rows]
        self.assertEqual(stamps, sorted(stamps))

    def test_model_filter_is_exact(self):
        rows = dbconn.get_prompt_usage(model="llama3.2:latest")
        self.assertEqual(len(rows), 2)
        rows = dbconn.get_prompt_usage(model="llama3.2")
        self.assertEqual(len(rows), 0)

    def test_start_time_is_inclusive(self):
        rows = dbconn.get_prompt_usage(start_time="2026-06-01T00:00:00")
        self.assertEqual(len(rows), 2)

    def test_end_time_is_inclusive(self):
        rows = dbconn.get_prompt_usage(end_time="2026-06-01T00:00:00")
        self.assertEqual(len(rows), 2)

    def test_timeframe_window(self):
        rows = dbconn.get_prompt_usage(
            start_time="2026-02-01T00:00:00", end_time="2026-11-01T00:00:00"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp"], "2026-06-01T00:00:00")

    def test_a_naive_timestamp_row_is_found_by_a_naive_bound(self):
        # Regression guard: had utc_now_iso() grown a "+00:00" suffix, rows
        # written by the app would no longer compare correctly against bounds
        # of this shape, which is what the API and dashboard send.
        with mock.patch.object(dbconn, "get_system_info", return_value={}):
            dbconn.save_prompt_usage(self.record())
        rows = dbconn.get_prompt_usage(start_time="2000-01-01T00:00:00")
        self.assertEqual(len(rows), 4)

    def test_combined_model_and_timeframe(self):
        rows = dbconn.get_prompt_usage(
            model="llama3.2:latest",
            start_time="2026-02-01T00:00:00",
            end_time="2026-11-01T00:00:00",
        )
        self.assertEqual(len(rows), 1)


class TestNoDeprecationWarning(unittest.TestCase):
    def test_module_never_calls_utcnow(self):
        """
        Guard against the deprecated call returning.

        Parsed rather than grepped: `datetime.utcnow()` legitimately appears in
        the docstring that explains why it was replaced, and a text search
        cannot tell that apart from a real call.
        """
        tree = ast.parse(pathlib.Path(dbconn.__file__).read_text())
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "utcnow"
        ]
        self.assertEqual(
            calls, [], "datetime.utcnow() is deprecated; use utc_now_iso()"
        )

    def test_saving_emits_no_deprecation_warning(self):
        """The behavioural counterpart: exercise the write path under -W error."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)
        try:
            with (
                mock.patch.object(dbconn, "DB_PATH", path),
                mock.patch.object(dbconn, "get_system_info", return_value={}),
                warnings.catch_warnings(),
            ):
                warnings.simplefilter("error", DeprecationWarning)
                dbconn.save_prompt_usage({"prompt": "x"})
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
