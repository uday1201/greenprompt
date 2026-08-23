"""
test_sampler_mac_sudo.py — unit tests for the powermetrics sudo probe.

The probe used `sudo -n powermetrics --version`. That is not a flag —
powermetrics prints usage and exits non-zero — so the check returned False
unconditionally and every macOS user was warned that their energy readings
would be zero, including users whose readings were fine. Confirmed on a machine
where a real sample runs passwordless and a prompt reports CPU 2.09 W.

The tests are written against the *shape* of the command rather than its
output, so the specific mistake cannot come back unnoticed.
"""

import subprocess
import unittest
from unittest import mock

from greenprompt import samplerMac


class TestCheckPowermetricsSudo(unittest.TestCase):
    def _run_probe(self, **run_kwargs):
        with mock.patch.object(samplerMac.subprocess, "run", **run_kwargs) as run:
            result = samplerMac._check_powermetrics_sudo()
        return result, run

    def test_true_when_the_probe_succeeds(self):
        result, _ = self._run_probe(return_value=mock.Mock(returncode=0))
        self.assertTrue(result)

    def test_false_when_sudo_refuses(self):
        result, _ = self._run_probe(
            side_effect=subprocess.CalledProcessError(1, "sudo")
        )
        self.assertFalse(result)

    def test_false_when_powermetrics_is_absent(self):
        result, _ = self._run_probe(side_effect=FileNotFoundError)
        self.assertFalse(result)

    def test_false_on_timeout_rather_than_hanging(self):
        result, _ = self._run_probe(
            side_effect=subprocess.TimeoutExpired("powermetrics", 15)
        )
        self.assertFalse(result)

    def test_a_timeout_is_set(self):
        # Without one, a sudo password prompt could block server startup.
        _, run = self._run_probe(return_value=mock.Mock(returncode=0))
        self.assertIn("timeout", run.call_args.kwargs)
        self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_the_probe_never_uses_the_nonexistent_version_flag(self):
        """The regression guard: --version is not a powermetrics option."""
        _, run = self._run_probe(return_value=mock.Mock(returncode=0))
        self.assertNotIn("--version", run.call_args[0][0])

    def test_the_probe_takes_a_real_sample(self):
        _, run = self._run_probe(return_value=mock.Mock(returncode=0))
        argv = run.call_args[0][0]
        self.assertEqual(argv[:2], ["sudo", "-n"])
        self.assertIn("powermetrics", argv)
        self.assertIn("--samplers", argv)
        self.assertIn("cpu_power", argv)

    def test_the_probe_takes_exactly_one_sample(self):
        # Startup cost matters; this runs before the server accepts requests.
        # Note both sudo and powermetrics take a -n, so search past the binary.
        _, run = self._run_probe(return_value=mock.Mock(returncode=0))
        argv = run.call_args[0][0]
        after_binary = argv[argv.index("powermetrics") + 1 :]
        self.assertEqual(after_binary[after_binary.index("-n") + 1], "1")

    def test_the_probe_is_non_interactive(self):
        # Without -n, a missing rule would hang on a password prompt.
        _, run = self._run_probe(return_value=mock.Mock(returncode=0))
        self.assertIn("-n", run.call_args[0][0])

    def test_failure_is_checked_by_exit_status(self):
        _, run = self._run_probe(return_value=mock.Mock(returncode=0))
        self.assertTrue(run.call_args.kwargs.get("check"))


class TestSudoersHint(unittest.TestCase):
    def test_the_hint_uses_an_absolute_path(self):
        """
        A bare `sudo greenprompt setup` fails with `command not found` for pipx
        and venv installs, because sudo replaces PATH with secure_path.
        """
        self.assertIn("command -v", samplerMac._SUDOERS_HINT)

    def test_the_hint_explains_why(self):
        self.assertIn("PATH", samplerMac._SUDOERS_HINT)


if __name__ == "__main__":
    unittest.main()
