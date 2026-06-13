"""
macOS power monitoring tests — samplerMac.PowerMonitor and measure_power_mac().

These tests are skipped automatically when not running on macOS.
To run them locally:
    pytest tests/macos/ -v   # on a Mac

Adding tests:
  - Mock powermetrics output using tests/common/helpers.py utilities.
  - Use unittest.mock.patch("subprocess.Popen") to avoid needing root.
  - Test parse_powermetrics_output() with fixture strings for various
    Apple Silicon / Intel chip output formats.
"""

import sys
import unittest

MACOS = sys.platform == "darwin"


@unittest.skipUnless(MACOS, "macOS-only tests")
class TestMacOsPowerMonitor(unittest.TestCase):
    pass  # add tests here


@unittest.skipUnless(MACOS, "macOS-only tests")
class TestParsePowermetricsOutput(unittest.TestCase):
    pass  # add tests here
