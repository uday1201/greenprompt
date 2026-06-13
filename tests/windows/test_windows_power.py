"""
Windows power monitoring tests — measure_power_windows() and WMI integration.

These tests are skipped automatically when not running on Windows.
To run them locally:
    pytest tests/windows/ -v   # on Windows

Adding tests:
  - Mock wmi.WMI() calls to avoid needing real hardware.
  - Test the fallback path in measure_power_for_pid() for Windows.
  - Verify energy_wh is 0.0 (Windows path is a placeholder today).
"""

import sys
import unittest

WINDOWS = sys.platform == "win32"


@unittest.skipUnless(WINDOWS, "Windows-only tests")
class TestWindowsPowerFallback(unittest.TestCase):
    pass  # add tests here
