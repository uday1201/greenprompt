"""
samplerMac.py — Continuous macOS power sampling via powermetrics.

Provides PowerMonitor, a daemon thread that calls `sudo powermetrics` every
second and maintains a 10-minute ring buffer of CPU/GPU/combined power
readings. Requires macOS and root privileges (for powermetrics).

This module is macOS-only. For Linux/Windows, see sysUsage.py stubs and
docs/platform-support.md for the implementation roadmap.
"""

from collections import deque
import threading
import time
import subprocess
from greenprompt.sysUsage import parse_powermetrics_output


class PowerMonitor:
    """
    Background daemon thread that samples macOS CPU/GPU power every second.

    Maintains a fixed-size deque of (timestamp, sample_dict) tuples covering
    the last `window_size` seconds. Callers filter by timestamp range to
    compute average power and energy for any time interval within the window.

    Usage:
        monitor = PowerMonitor()
        monitor.start()
        # ... run workload ...
        # Use sysUsage.measure_power_mac(start, end, monitor) to get metrics.
        monitor.stop()

    Attributes:
        samples: deque of (float timestamp, dict{cpu_power_w, gpu_power_w,
            combined_power_w}) tuples.
        running: bool, True while the background thread is active.
    """
    def __init__(self, sample_interval=1, window_size=600):  # store 10 minutes
        self.samples = deque(maxlen=window_size)
        self.running = False
        self.sample_interval = sample_interval
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while self.running:
            power = self.sample_once()
            if power:
                self.samples.append((time.time(), power))
            time.sleep(self.sample_interval)

    def sample_once(self):
        """
        Take a single powermetrics sample and return parsed power values.

        Runs `sudo powermetrics --samplers cpu_power -n 1 -i 1000` as a
        subprocess (1-second interval, 1 sample). Parses the output with
        parse_powermetrics_output().

        Returns:
            dict with keys cpu_power_w, gpu_power_w, combined_power_w,
            or None if the subprocess fails.
        """
        try:
            out = subprocess.check_output(
                [
                    "sudo",
                    "powermetrics",
                    "--samplers",
                    "cpu_power",
                    "-n",
                    "1",
                    "-i",
                    "1000",
                ],
                stderr=subprocess.DEVNULL,
            ).decode()
            parsed = parse_powermetrics_output(out, 1)  # use 1 second sample duration
            return {
                "combined_power_w": parsed["combined_power_w"],
                "cpu_power_w": parsed["cpu_power_w"],
                "gpu_power_w": parsed["gpu_power_w"],
            }
        except Exception as e:
            print(f"Error sampling power metrics: {e}")
            return None

    def start(self):
        print("Starting power monitor...")
        self.running = True
        self.thread.start()

    def stop(self):
        print("Stopping power monitor...")
        self.running = False
        self.thread.join()

    def get_range_average(self, start_ts, end_ts):
        """
        Compute the average combined power (W) for samples in [start_ts, end_ts].

        Args:
            start_ts: Unix timestamp (float) for the start of the range.
            end_ts: Unix timestamp (float) for the end of the range.

        Returns:
            Average combined_power_w as a float, or None if no samples found.
        """
        relevant = [s for ts, s in self.samples if start_ts <= ts <= end_ts]
        if not relevant:
            return None
        combined = [r["combined_power_w"] for r in relevant]
        return sum(combined) / len(combined)
