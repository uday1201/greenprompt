"""
test_writability.py — unit tests for detecting an unwritable database.

A real machine had `~/greenprompt_usage.db` owned by root, created by an old
`sudo greenprompt run`. Its last row was written the day ownership changed:
every prompt in the following year silently failed to persist, because
`run_prompt()` caught the error and printed a warning that, under the API
server, went to /tmp/api.log where nobody looks.

Two behaviours are pinned here: an unwritable database is reported with a
message that names the file and the remedy, and a prompt that could not be
saved says so in its result rather than looking identical to a successful one.
"""

import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from greenprompt import core, dbconn


class WritabilityTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)
        self.path = os.path.join(self.tmp, dbconn.DB_FILENAME)

    def _cleanup(self):
        # Restore write permission so the temp tree can be removed.
        if os.path.exists(self.path):
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_readonly_db(self):
        with mock.patch.object(dbconn, "DB_PATH", self.path):
            dbconn.init_db()
        os.chmod(self.path, stat.S_IRUSR)
        return self.path


class TestCheckWritable(WritabilityTestCase):
    def test_a_missing_file_is_fine(self):
        # Nothing to check yet; init_db() will create it.
        dbconn.check_writable(os.path.join(self.tmp, "not-there.db"))

    def test_a_writable_file_is_fine(self):
        with mock.patch.object(dbconn, "DB_PATH", self.path):
            dbconn.init_db()
        dbconn.check_writable(self.path)

    def test_a_readonly_file_raises(self):
        path = self._make_readonly_db()
        with self.assertRaises(dbconn.DatabaseNotWritable):
            dbconn.check_writable(path)

    def test_the_message_names_the_file(self):
        path = self._make_readonly_db()
        with self.assertRaises(dbconn.DatabaseNotWritable) as ctx:
            dbconn.check_writable(path)
        self.assertIn(path, str(ctx.exception))

    def test_the_message_gives_a_remedy(self):
        path = self._make_readonly_db()
        with self.assertRaises(dbconn.DatabaseNotWritable) as ctx:
            dbconn.check_writable(path)
        message = str(ctx.exception)
        self.assertIn("chown", message)
        self.assertIn("GREENPROMPT_DB", message)

    def test_the_message_does_not_leak_sqlites_wording(self):
        # "attempt to write a readonly database" names neither file nor fix.
        path = self._make_readonly_db()
        with self.assertRaises(dbconn.DatabaseNotWritable) as ctx:
            dbconn.check_writable(path)
        self.assertNotIn("attempt to write a readonly database", str(ctx.exception))

    def test_defaults_to_the_database_in_use(self):
        path = self._make_readonly_db()
        with mock.patch.object(dbconn, "DB_PATH", path):
            with self.assertRaises(dbconn.DatabaseNotWritable):
                dbconn.check_writable()


class TestInitDbReportsUnwritable(WritabilityTestCase):
    def test_init_db_raises_the_clear_error(self):
        path = self._make_readonly_db()
        with mock.patch.object(dbconn, "DB_PATH", path):
            with self.assertRaises(dbconn.DatabaseNotWritable):
                dbconn.init_db()

    def test_reads_also_surface_it(self):
        # get_prompt_usage() calls init_db(), so the dashboard and monitor get
        # the actionable message too rather than an opaque SQLite error.
        path = self._make_readonly_db()
        with mock.patch.object(dbconn, "DB_PATH", path):
            with self.assertRaises(dbconn.DatabaseNotWritable):
                dbconn.get_prompt_usage()


def _ollama_response():
    resp = mock.Mock()
    resp.status_code = 200
    resp.json.return_value = {
        "response": "an answer",
        "prompt_eval_count": 5,
        "eval_count": 7,
    }
    return resp


class TestRunPromptReportsPersistence(unittest.TestCase):
    """A discarded measurement must not look like a successful one."""

    def setUp(self):
        patches = {
            "requests": mock.patch.object(core, "requests"),
            "measure": mock.patch.object(
                core, "measure_power_for_pid", return_value={}
            ),
            "has_gpu": mock.patch.object(core, "has_gpu", return_value=False),
            "sysinfo": mock.patch.object(core, "get_system_info", return_value={}),
            "score": mock.patch.object(
                core, "score_prompt", return_value={"score_percent": 1, "details": {}}
            ),
            "save": mock.patch.object(core, "save_prompt_usage"),
        }
        self.m = {k: v.start() for k, v in patches.items()}
        for v in patches.values():
            self.addCleanup(v.stop)
        self.m["requests"].exceptions = __import__("requests").exceptions
        self.m["requests"].post.return_value = _ollama_response()

    def test_a_successful_save_is_reported(self):
        result = core.run_prompt("p", monitor=None)
        self.assertTrue(result["saved"])
        self.assertNotIn("save_error", result)

    def test_a_failed_save_is_reported_in_the_result(self):
        self.m["save"].side_effect = dbconn.DatabaseNotWritable("cannot write")
        result = core.run_prompt("p", monitor=None)
        self.assertFalse(result["saved"])
        self.assertIn("cannot write", result["save_error"])

    def test_the_answer_is_still_returned_when_the_save_fails(self):
        # The model already did the work; losing the row must not lose that.
        self.m["save"].side_effect = OSError("disk full")
        result = core.run_prompt("p", monitor=None)
        self.assertEqual(result["response"], "an answer")
        self.assertFalse(result["saved"])


if __name__ == "__main__":
    unittest.main()
