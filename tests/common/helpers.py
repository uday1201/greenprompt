"""
Shared test utilities for GreenPrompt test suites.

Import these in any test file:
    from tests.common.helpers import make_monitor, sample_dict, cpu_pct_side_effect
"""

import threading
from collections import deque
from unittest.mock import patch


def sample_dict(cpu=5.0, gpu=3.0):
    """Return a minimal power sample dict."""
    return {"cpu_power_w": cpu, "gpu_power_w": gpu, "combined_power_w": cpu + gpu}


def cpu_pct_side_effect(*args, **kwargs):
    """
    Mock for psutil.cpu_percent that returns the right type per call site.

    - With percpu=True (used by _sample_cpu_biglittle and priming): returns a list.
    - Without percpu (linear_tdp path): returns a scalar float.
    """
    if kwargs.get("percpu"):
        return [15.0] * 20
    return 15.0


def make_monitor(samples=None, sample_interval=1, cpu_tdp_w=23.0):
    """
    Build a LinuxPowerMonitor-like object without starting a background thread.

    Patches hardware detection so the monitor is constructed in linear_tdp mode
    regardless of the host machine. Populate `samples` with (timestamp, dict)
    tuples to pre-seed the ring buffer.

    Args:
        samples: iterable of (float, dict) tuples to pre-load into the deque.
        sample_interval: seconds between samples (default 1).
        cpu_tdp_w: TDP used in linear_tdp mode (default 23.0 W).

    Returns:
        A fully-initialised LinuxPowerMonitor instance (thread not started).
    """
    from greenprompt.samplerLinux import LinuxPowerMonitor

    with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
         patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
         patch("psutil.cpu_percent", side_effect=cpu_pct_side_effect):
        m = LinuxPowerMonitor.__new__(LinuxPowerMonitor)
        m.samples = deque(maxlen=600)
        m.running = False
        m.sample_interval = sample_interval
        m.cpu_tdp_w = cpu_tdp_w
        m._lock = threading.Lock()
        m._stop_event = threading.Event()
        m._cpu_mode = "linear_tdp"
        m._gpu_available = None
        m._gpu_unavailable_warned = False
        m._dmon = None
        if samples:
            m.samples.extend(samples)
    return m
