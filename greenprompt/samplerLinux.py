"""
samplerLinux.py — Continuous Linux power sampling via psutil and nvidia-smi.

Provides LinuxPowerMonitor, a daemon thread that samples CPU utilization
(via psutil) and GPU power draw (via nvidia-smi) every second, maintaining
a 10-minute ring buffer identical in structure to samplerMac.PowerMonitor.

CPU power is estimated as: cpu_percent / 100 * cpu_tdp_w
GPU power is read directly from nvidia-smi (watts).

RAPL is not used because this system is ARM-based (Cortex-X925); RAPL
requires Intel or AMD CPUs. nvidia-smi is the only direct power reading
available on this hardware.

This module is Linux-only. For macOS, see samplerMac.py.
"""

from collections import deque
import threading
import time
import subprocess
import psutil


def _parse_nvidia_power(raw: str) -> float:
    """
    Parse a power.draw value from nvidia-smi CSV output.

    nvidia-smi may return '[N/A]' or 'N/A' for unsupported fields.
    Returns 0.0 in those cases.

    Args:
        raw: Stripped string from nvidia-smi (e.g. '3.92', '[N/A]', 'N/A').

    Returns:
        Power in watts as a float, or 0.0 if not available/parseable.
    """
    raw = raw.strip()
    if not raw or raw in ("[N/A]", "N/A", "Unknown Error"):
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


class LinuxPowerMonitor:
    """
    Background daemon thread that samples Linux CPU/GPU power every second.

    Maintains a fixed-size deque of (timestamp, sample_dict) tuples covering
    the last `window_size` seconds — identical interface to samplerMac.PowerMonitor
    so that measure_power_linux() can use the same logic as measure_power_mac().

    CPU power = psutil.cpu_percent() / 100 * cpu_tdp_w  (estimated)
    GPU power = nvidia-smi power.draw (direct measurement)

    Usage:
        monitor = LinuxPowerMonitor(cpu_tdp_w=40)
        monitor.start()
        time.sleep(5)   # warm up before first prompt
        # ... run workload ...
        # Use sysUsage.measure_power_linux(start, end, monitor) to get metrics.
        monitor.stop()

    Attributes:
        samples: deque of (float timestamp, dict{cpu_power_w, gpu_power_w,
            combined_power_w}) tuples.
        running: bool, True while the background thread is active.
        cpu_tdp_w: float, assumed CPU thermal design power in watts.
    """

    def __init__(self, sample_interval: int = 1, window_size: int = 600, cpu_tdp_w: float = 40.0):
        """
        Args:
            sample_interval: Seconds between samples (default 1).
            window_size: Max samples to retain; 600 = 10-minute window (default).
            cpu_tdp_w: CPU thermal design power in watts used for estimation
                (default 40W for ARM Cortex-X925). Edit CPU_TDP_W in constants.py
                to match your hardware.
        """
        self.samples = deque(maxlen=window_size)
        self.running = False
        self.sample_interval = sample_interval
        self.cpu_tdp_w = cpu_tdp_w
        self._gpu_available = None  # None = not yet checked
        self._gpu_unavailable_warned = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        # Prime psutil CPU measurement — first call always returns 0.0
        psutil.cpu_percent(interval=0.1)

    def _run(self):
        while self.running:
            power = self.sample_once()
            if power:
                self.samples.append((time.time(), power))
            time.sleep(self.sample_interval)

    def _check_gpu(self) -> bool:
        """Return True if nvidia-smi is available and reports a GPU."""
        if self._gpu_available is not None:
            return self._gpu_available
        try:
            result = subprocess.check_output(
                ["nvidia-smi", "-L"], stderr=subprocess.DEVNULL
            ).decode().strip()
            self._gpu_available = bool(result)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            self._gpu_available = False
            if not self._gpu_unavailable_warned:
                print("LinuxPowerMonitor: nvidia-smi not available — GPU power will be 0.0 W")
                self._gpu_unavailable_warned = True
        return self._gpu_available

    def sample_once(self) -> dict | None:
        """
        Take a single power sample using psutil (CPU) and nvidia-smi (GPU).

        Returns:
            dict with keys cpu_power_w, gpu_power_w, combined_power_w,
            or None if sampling fails entirely.
        """
        try:
            # CPU: non-blocking, uses delta since last call
            cpu_pct = psutil.cpu_percent(interval=None)
            cpu_power_w = (cpu_pct / 100.0) * self.cpu_tdp_w

            # GPU: direct power reading via nvidia-smi
            gpu_power_w = 0.0
            if self._check_gpu():
                try:
                    raw = subprocess.check_output(
                        [
                            "nvidia-smi",
                            "--query-gpu=power.draw",
                            "--format=csv,nounits,noheader",
                        ],
                        stderr=subprocess.DEVNULL,
                    ).decode()
                    gpu_power_w = _parse_nvidia_power(raw)
                except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                    gpu_power_w = 0.0

            combined_power_w = cpu_power_w + gpu_power_w
            return {
                "cpu_power_w": cpu_power_w,
                "gpu_power_w": gpu_power_w,
                "combined_power_w": combined_power_w,
            }
        except Exception as e:
            print(f"LinuxPowerMonitor: error sampling: {e}")
            return None

    def start(self):
        """Start the background sampling thread."""
        print("Starting Linux power monitor...")
        self.running = True
        self.thread.start()

    def stop(self):
        """Stop the background sampling thread and wait for it to exit."""
        print("Stopping Linux power monitor...")
        self.running = False
        self.thread.join()

    def get_range_average(self, start_ts: float, end_ts: float) -> float | None:
        """
        Compute the average combined power (W) for samples in [start_ts, end_ts].

        Args:
            start_ts: Unix timestamp for the start of the range.
            end_ts: Unix timestamp for the end of the range.

        Returns:
            Average combined_power_w as a float, or None if no samples found.
        """
        relevant = [s for ts, s in self.samples if start_ts <= ts <= end_ts]
        if not relevant:
            return None
        combined = [r["combined_power_w"] for r in relevant]
        return sum(combined) / len(combined)
