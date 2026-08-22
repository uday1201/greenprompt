"""
test_cli.py — unit tests for server lifecycle management.

The defect these cover was destructive: `run` and `stop` took a PID from the
second line of `lsof -i :PORT` output and sent it SIGKILL, with no check that
the process was a GreenPrompt server. `greenprompt run --port 5432` would kill
Postgres.

Every subprocess call is mocked. Nothing here starts, signals, or inspects a
real process.
"""

import subprocess
import unittest
from unittest import mock

from greenprompt import cli


def _completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


class TestListeningPids(unittest.TestCase):
    def test_parses_one_pid_per_line(self):
        with mock.patch.object(
            cli.subprocess, "run", return_value=_completed("123\n456\n")
        ):
            self.assertEqual(cli.listening_pids(5000), ["123", "456"])

    def test_empty_output_yields_no_pids(self):
        with mock.patch.object(cli.subprocess, "run", return_value=_completed("")):
            self.assertEqual(cli.listening_pids(5000), [])

    def test_non_numeric_noise_is_discarded(self):
        with mock.patch.object(
            cli.subprocess, "run", return_value=_completed("COMMAND\n123\n")
        ):
            self.assertEqual(cli.listening_pids(5000), ["123"])

    def test_missing_lsof_is_not_fatal(self):
        # Windows has no lsof; this must degrade rather than raise.
        with mock.patch.object(cli.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(cli.listening_pids(5000), [])

    def test_queries_only_listening_sockets(self):
        with mock.patch.object(
            cli.subprocess, "run", return_value=_completed("")
        ) as run:
            cli.listening_pids(5000)
        argv = run.call_args[0][0]
        self.assertIn("-sTCP:LISTEN", argv)
        self.assertIn("-t", argv)
        self.assertIn("-iTCP:5000", argv)


class TestIsGreenpromptApi(unittest.TestCase):
    def test_recognises_our_server(self):
        cmdline = "/usr/bin/python3 -m greenprompt.api --port=5000"
        with mock.patch.object(cli.subprocess, "run", return_value=_completed(cmdline)):
            self.assertTrue(cli.is_greenprompt_api("123"))

    def test_rejects_an_unrelated_process(self):
        with mock.patch.object(
            cli.subprocess, "run", return_value=_completed("postgres -D /data")
        ):
            self.assertFalse(cli.is_greenprompt_api("123"))

    def test_rejects_a_dead_pid(self):
        with mock.patch.object(cli.subprocess, "run", return_value=_completed("")):
            self.assertFalse(cli.is_greenprompt_api("123"))

    def test_missing_ps_is_not_fatal(self):
        with mock.patch.object(cli.subprocess, "run", side_effect=FileNotFoundError):
            self.assertFalse(cli.is_greenprompt_api("123"))


class TestStopApi(unittest.TestCase):
    def test_kills_our_server(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=["123"]),
            mock.patch.object(cli, "is_greenprompt_api", return_value=True),
            mock.patch.object(cli.subprocess, "run") as run,
        ):
            killed = cli.stop_api(5000)
        self.assertEqual(killed, ["123"])
        run.assert_called_once_with(["kill", "123"], check=True)

    def test_refuses_to_kill_a_foreign_process(self):
        """The whole point: an unrecognised PID must survive."""
        with (
            mock.patch.object(cli, "listening_pids", return_value=["999"]),
            mock.patch.object(cli, "is_greenprompt_api", return_value=False),
            mock.patch.object(cli.subprocess, "run") as run,
        ):
            killed = cli.stop_api(5432)
        self.assertEqual(killed, [])
        run.assert_not_called()

    def test_uses_sigterm_not_sigkill(self):
        # SIGKILL gave the sampler thread no chance to shut down.
        with (
            mock.patch.object(cli, "listening_pids", return_value=["123"]),
            mock.patch.object(cli, "is_greenprompt_api", return_value=True),
            mock.patch.object(cli.subprocess, "run") as run,
        ):
            cli.stop_api(5000)
        self.assertNotIn("-9", run.call_args[0][0])

    def test_kills_only_the_recognised_pids_of_several(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=["111", "222"]),
            mock.patch.object(cli, "is_greenprompt_api", side_effect=[False, True]),
            mock.patch.object(cli.subprocess, "run") as run,
        ):
            killed = cli.stop_api(5000)
        self.assertEqual(killed, ["222"])
        run.assert_called_once_with(["kill", "222"], check=True)

    def test_nothing_listening_is_not_an_error(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=[]),
            mock.patch.object(cli.subprocess, "run") as run,
        ):
            self.assertEqual(cli.stop_api(5000), [])
        run.assert_not_called()

    def test_a_failed_kill_is_reported_not_raised(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=["123"]),
            mock.patch.object(cli, "is_greenprompt_api", return_value=True),
            mock.patch.object(
                cli.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "kill"),
            ),
        ):
            self.assertEqual(cli.stop_api(5000), [])


class TestRunApi(unittest.TestCase):
    def test_refuses_to_start_over_a_foreign_process(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=["999"]),
            mock.patch.object(cli, "is_greenprompt_api", return_value=False),
            mock.patch.object(cli.subprocess, "Popen") as popen,
        ):
            result = cli.run_api(5432)
        self.assertIsNone(result)
        popen.assert_not_called()

    def test_replaces_our_own_stale_server(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=["123"]),
            mock.patch.object(cli, "is_greenprompt_api", return_value=True),
            mock.patch.object(cli, "stop_api", return_value=["123"]) as stop,
            mock.patch.object(cli.subprocess, "Popen") as popen,
        ):
            cli.run_api(5000)
        stop.assert_called_once()
        popen.assert_called_once()

    def test_starts_on_a_free_port(self):
        with (
            mock.patch.object(cli, "listening_pids", return_value=[]),
            mock.patch.object(cli, "stop_api", return_value=[]),
            mock.patch.object(cli.subprocess, "Popen") as popen,
        ):
            cli.run_api(5000)
        argv = popen.call_args[0][0]
        self.assertIn("-m", argv)
        self.assertIn("greenprompt.api", argv)
        self.assertIn("--port=5000", argv)

    def test_spawned_command_is_recognised_by_the_ownership_check(self):
        """
        The two halves must agree: whatever run_api spawns has to be something
        is_greenprompt_api() will later recognise, or stop can never work.
        """
        with (
            mock.patch.object(cli, "listening_pids", return_value=[]),
            mock.patch.object(cli, "stop_api", return_value=[]),
            mock.patch.object(cli.subprocess, "Popen") as popen,
        ):
            cli.run_api(5000)
        spawned = " ".join(popen.call_args[0][0])
        self.assertIn(cli.API_PROCESS_MARKER, spawned)


if __name__ == "__main__":
    unittest.main()
