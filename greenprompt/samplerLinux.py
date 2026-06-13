"""
samplerLinux.py — Continuous Linux power sampling via psutil, sysfs, and nvidia-smi.

Provides LinuxPowerMonitor, a daemon thread that samples CPU and GPU power every
second, maintaining a 10-minute ring buffer identical in structure to
samplerMac.PowerMonitor.

CPU measurement strategy (auto-detected at startup, priority order):
  1. rapl       — Intel/AMD only: reads energy_uj counter delta from sysfs.
                  Ground-truth watts, no estimation.
  2. arm_biglittle — ARM big.LITTLE (e.g. Cortex-X925 + A725): per-cluster
                  frequency-squared model. Reads scaling_cur_freq from sysfs.
                  Better than linear because power ∝ V²f and V scales with freq.
  3. linear_tdp — Fallback: cpu_percent / 100 * cpu_tdp_w.

GPU measurement:
  One long-running `nvidia-smi dmon -s p -d 1` process (NvidiaDmonReader)
  instead of a subprocess fork every second. Falls back to per-call subprocess
  if dmon fails to start.

Thread safety: self.samples is protected by self._lock. Stop uses threading.Event
so stop() returns immediately instead of waiting up to 1s for sleep() to expire.

This module is Linux-only. For macOS, see samplerMac.py.
"""

from collections import deque
import glob
import os
import threading
import time
import subprocess
import psutil


# Per-cluster TDP and idle power estimates for known ARM big.LITTLE configurations.
# Keyed by cluster max frequency in MHz (int). Used only in arm_biglittle mode.
_CLUSTER_TDP = {
    2808: {"tdp_w": 8.0,  "idle_w": 0.5},   # Cortex-A725 efficiency cores
    3900: {"tdp_w": 23.0, "idle_w": 1.0},   # Cortex-X925 performance cores
}


def _parse_nvidia_power(raw: str) -> float:
    """
    Parse a power.draw value from nvidia-smi CSV output.

    nvidia-smi may return '[N/A]' or 'N/A' for unsupported fields (e.g. GB10
    unified memory). Returns 0.0 in those cases.

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


def _detect_rapl_path() -> "str | None":
    """Return the RAPL energy_uj sysfs path if Intel/AMD RAPL is available, else None."""
    direct = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
    if os.path.exists(direct):
        return direct
    candidates = glob.glob("/sys/class/powercap/intel-rapl*/intel-rapl*:0/energy_uj")
    return candidates[0] if candidates else None


def _detect_cpu_clusters() -> dict:
    """
    Detect ARM big.LITTLE CPU clusters by grouping CPUs by max frequency.

    Uses psutil.cpu_freq(percpu=True) to read per-CPU max frequencies and groups
    CPU indices by max_mhz. Returns a dict only if more than one distinct max
    frequency is found (i.e. a heterogeneous cluster arrangement).

    Returns:
        {max_mhz_int: [cpu_indices]} if big.LITTLE detected, {} otherwise.
    """
    try:
        freqs = psutil.cpu_freq(percpu=True)
        if not freqs or len(freqs) < 2:
            return {}
        clusters = {}
        for i, f in enumerate(freqs):
            clusters.setdefault(int(f.max), []).append(i)
        return clusters if len(clusters) > 1 else {}
    except Exception:
        return {}


class NvidiaDmonReader:
    """
    Wraps a single long-running `nvidia-smi dmon` process for efficient GPU power polling.

    Instead of forking nvidia-smi on every sample tick, one process streams output
    continuously. A daemon thread reads lines and updates _power_w under a lock.
    Callers read get_power() with no subprocess overhead.

    dmon output format (columns vary by -s flag; -s p gives power and temp):
        # gpu   pwr  gtemp  mtemp    sm   mem   enc   dec   jpg   ofa
        # Idx     W      C      C     %     %     %     %     %     %
            0     4     40      -     2     -     0     0     -     -

    Column index 1 (0-indexed after split) = power in watts.
    Header lines start with '#' and are skipped.
    """

    def __init__(self):
        self._power_w = 0.0
        self._lock = threading.Lock()
        self._failed = False
        self._proc = None
        try:
            self._proc = subprocess.Popen(
                ["nvidia-smi", "dmon", "-s", "p", "-d", "1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
        except (FileNotFoundError, OSError):
            self._failed = True

    def _read_loop(self):
        for line in self._proc.stdout:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    with self._lock:
                        self._power_w = float(parts[1])
                except ValueError:
                    pass

    def get_power(self) -> float:
        """Return the most recently read GPU power in watts."""
        with self._lock:
            return self._power_w

    def stop(self):
        """Terminate the dmon process. The reader thread exits naturally."""
        if self._proc:
            self._proc.terminate()
            self._proc.wait()
            self._proc = None


class LinuxPowerMonitor:
    """
    Background daemon thread that samples Linux CPU/GPU power every second.

    Maintains a fixed-size deque of (timestamp, sample_dict) tuples covering
    the last `window_size` seconds — identical interface to samplerMac.PowerMonitor
    so that measure_power_linux() can use the same logic as measure_power_mac().

    CPU mode is auto-detected at construction time:
      - "rapl":          Intel/AMD energy counter (ground truth)
      - "arm_biglittle": per-cluster frequency-squared model
      - "linear_tdp":    cpu_percent * cpu_tdp_w fallback

    GPU mode:
      - NvidiaDmonReader (single long-running process) if nvidia-smi is available
      - Per-call subprocess fallback if dmon fails to start

    Usage:
        monitor = LinuxPowerMonitor(cpu_tdp_w=23.0)
        monitor.start()
        time.sleep(5)   # warm up before first prompt
        # Use sysUsage.measure_power_linux(start, end, monitor) to get metrics.
        monitor.stop()

    Attributes:
        samples: deque of (float timestamp, dict{cpu_power_w, gpu_power_w,
            combined_power_w}) tuples. Protected by self._lock.
        running: bool, True while the background thread is active.
        cpu_tdp_w: float, CPU TDP used in linear_tdp fallback mode.
        _cpu_mode: str, one of "rapl", "arm_biglittle", "linear_tdp".
    """

    def __init__(self, sample_interval: int = 1, window_size: int = 600, cpu_tdp_w: float = 40.0):
        """
        Args:
            sample_interval: Seconds between samples (default 1).
            window_size: Max samples to retain; 600 = 10-minute window.
            cpu_tdp_w: CPU TDP in watts for linear_tdp fallback mode. Ignored when
                RAPL or arm_biglittle is detected. Edit CPU_TDP_W in constants.py.
        """
        self.samples = deque(maxlen=window_size)
        self.running = False
        self.sample_interval = sample_interval
        self.cpu_tdp_w = cpu_tdp_w
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

        # CPU mode detection: rapl > arm_biglittle > linear_tdp
        rapl_path = _detect_rapl_path()
        if rapl_path:
            self._cpu_mode = "rapl"
            self._rapl_path = rapl_path
            self._rapl_max_path = rapl_path.replace("energy_uj", "max_energy_range_uj")
            self._rapl_last_energy = None
            self._rapl_last_ts = None
        else:
            clusters = _detect_cpu_clusters()
            if clusters:
                self._cpu_mode = "arm_biglittle"
                self._clusters = clusters  # {max_mhz_int: [cpu_indices]}
            else:
                self._cpu_mode = "linear_tdp"

        self._gpu_available = None
        self._gpu_unavailable_warned = False
        self._dmon = None
        # Prime psutil per-CPU measurement — first call always returns 0.0
        psutil.cpu_percent(percpu=True, interval=0.1)

    def _run(self):
        while self.running:
            power = self.sample_once()
            if power:
                with self._lock:
                    self.samples.append((time.time(), power))
            # threading.Event.wait wakes immediately when stop() sets the event,
            # avoiding the up-to-1s sleep() latency of the old implementation.
            self._stop_event.wait(timeout=self.sample_interval)

    def _check_gpu(self) -> bool:
        """Return True if nvidia-smi is available and reports a GPU. Cached after first check."""
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

    def _sample_cpu_rapl(self) -> float:
        """
        Read CPU package power via RAPL energy counter delta (Intel/AMD only).

        Reads energy_uj, computes delta since last call, divides by elapsed seconds.
        Returns 0.0 on the first call (no prior baseline) and on read errors.
        Handles counter overflow via max_energy_range_uj.
        """
        try:
            with open(self._rapl_path) as f:
                energy_uj = int(f.read().strip())
            ts = time.time()
            if self._rapl_last_energy is None:
                self._rapl_last_energy, self._rapl_last_ts = energy_uj, ts
                return 0.0
            delta_uj = energy_uj - self._rapl_last_energy
            if delta_uj < 0:  # counter wrapped around
                try:
                    with open(self._rapl_max_path) as f:
                        max_range = int(f.read().strip())
                except (OSError, ValueError):
                    max_range = 2 ** 32 * 1000  # safe default
                delta_uj += max_range
            delta_s = ts - self._rapl_last_ts
            self._rapl_last_energy, self._rapl_last_ts = energy_uj, ts
            return (delta_uj / 1_000_000.0) / delta_s if delta_s > 0 else 0.0
        except (OSError, ValueError):
            return 0.0

    def _sample_cpu_biglittle(self) -> float:
        """
        Estimate CPU power for ARM big.LITTLE by summing per-cluster contributions.

        For each cluster: power = idle_W + util * (tdp - idle) * (cur_freq/max_freq)²
        The freq² term models the fact that dynamic power scales with V²f and
        voltage tracks frequency on most ARM platforms.

        Reads scaling_cur_freq from sysfs per CPU (cheap file reads, no subprocess).
        """
        cpu_pcts = psutil.cpu_percent(percpu=True, interval=None)
        total = 0.0
        n_clusters = len(self._clusters)
        for max_mhz, cpu_indices in self._clusters.items():
            info = _CLUSTER_TDP.get(
                max_mhz,
                {"tdp_w": self.cpu_tdp_w / n_clusters, "idle_w": 0.2},
            )
            # Read current frequency for each CPU in this cluster (kHz → MHz)
            freqs = []
            for i in cpu_indices:
                try:
                    with open(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq") as f:
                        freqs.append(int(f.read().strip()) / 1000.0)
                except OSError:
                    freqs.append(float(max_mhz))
            freq_ratio = min(1.0, (sum(freqs) / len(freqs)) / max_mhz)
            util = (
                sum(cpu_pcts[i] for i in cpu_indices if i < len(cpu_pcts))
                / len(cpu_indices)
            )
            total += (
                info["idle_w"]
                + (util / 100.0) * (info["tdp_w"] - info["idle_w"]) * (freq_ratio ** 2)
            )
        return total

    def sample_once(self) -> "dict | None":
        """
        Take a single power sample.

        CPU: dispatches to _sample_cpu_rapl, _sample_cpu_biglittle, or linear_tdp.
        GPU: reads from NvidiaDmonReader if active, else falls back to per-call nvidia-smi.

        Returns:
            dict with keys cpu_power_w, gpu_power_w, combined_power_w,
            or None if sampling fails entirely.
        """
        try:
            if self._cpu_mode == "rapl":
                cpu_power_w = self._sample_cpu_rapl()
            elif self._cpu_mode == "arm_biglittle":
                cpu_power_w = self._sample_cpu_biglittle()
            else:
                cpu_power_w = (psutil.cpu_percent(interval=None) / 100.0) * self.cpu_tdp_w

            gpu_power_w = 0.0
            if self._dmon is not None:
                gpu_power_w = self._dmon.get_power()
            elif self._check_gpu():
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

            return {
                "cpu_power_w": cpu_power_w,
                "gpu_power_w": gpu_power_w,
                "combined_power_w": cpu_power_w + gpu_power_w,
            }
        except Exception as e:
            print(f"LinuxPowerMonitor: error sampling: {e}")
            return None

    def start(self):
        """Start the background sampling thread and GPU dmon reader."""
        print("Starting Linux power monitor...")
        print(f"  CPU mode: {self._cpu_mode}")
        try:
            self._dmon = NvidiaDmonReader()
            if self._dmon._failed:
                print("  GPU: dmon unavailable, using per-call nvidia-smi fallback")
                self._dmon = None
            else:
                print("  GPU: nvidia-smi dmon streaming reader active")
        except Exception:
            self._dmon = None
        self.running = True
        self.thread.start()

    def stop(self):
        """Stop the background sampling thread and dmon reader."""
        print("Stopping Linux power monitor...")
        self.running = False
        self._stop_event.set()
        self.thread.join()
        if self._dmon:
            self._dmon.stop()
            self._dmon = None

    def get_range_average(self, start_ts: float, end_ts: float) -> "float | None":
        """
        Compute the average combined power (W) for samples in [start_ts, end_ts].

        Thread-safe: takes a snapshot of self.samples under self._lock before filtering.

        Args:
            start_ts: Unix timestamp for the start of the range.
            end_ts: Unix timestamp for the end of the range.

        Returns:
            Average combined_power_w as a float, or None if no samples found.
        """
        with self._lock:
            snapshot = list(self.samples)
        relevant = [s["combined_power_w"] for ts, s in snapshot if start_ts <= ts <= end_ts]
        return sum(relevant) / len(relevant) if relevant else None
