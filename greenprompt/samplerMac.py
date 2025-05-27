from collections import deque
import threading
import time
import subprocess
from greenprompt.sysUsage import parse_powermetrics_output

class PowerMonitor:
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
        try:
            out = subprocess.check_output(
                ["sudo", "powermetrics", "--samplers", "cpu_power", "-n", "1", "-i", "1000"],
                stderr=subprocess.DEVNULL
            ).decode()
            parsed = parse_powermetrics_output(out, 1)  # use 1 second sample duration
            return {
                "combined_power_w": parsed["combined_power_w"],
                "cpu_power_w": parsed["cpu_power_w"],
                "gpu_power_w": parsed["gpu_power_w"]
            }
        except Exception as e:
            print(f"Error sampling power metrics: {e}")
            return None

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()

    def get_range_average(self, start_ts, end_ts):
        relevant = [s for ts, s in self.samples if start_ts <= ts <= end_ts]
        if not relevant:
            return None
        combined = [r["combined_power_w"] for r in relevant]
        return sum(combined) / len(combined)