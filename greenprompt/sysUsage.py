"""
sysUsage.py — OS-agnostic system information and power measurement dispatch.

Provides:
- get_system_info(): CPU, RAM, disk, OS metadata as a dict.
- measure_power_for_pid(): Dispatches to the correct OS-specific power function.
- measure_power_mac(): Reads from a PowerMonitor sample buffer (macOS only).
- measure_power_linux(): Reads from a LinuxPowerMonitor sample buffer (Linux only).
- measure_power_windows(): Placeholder — not yet implemented.
- has_gpu(): Detects GPU presence on all platforms.
- get_gpu_usage(): Returns GPU utilization stats (Linux/Windows via nvidia-smi).
- parse_powermetrics_output(): Parses raw macOS powermetrics text output.
"""

import platform
import psutil
import socket
import cpuinfo
import shutil
import subprocess
import time
import re
from greenprompt import constants

#: Substituted for any field that cannot be determined.
UNKNOWN = "N/A"


def _safe(fn, default=UNKNOWN):
    """
    Call `fn` and return `default` if it fails for any reason.

    Every field in get_system_info() is descriptive metadata — nothing reads it
    back to make a decision — so a field that cannot be determined must degrade
    to "N/A" rather than propagate. See get_system_info() for why this matters.
    """
    try:
        result = fn()
    except Exception:  # noqa: BLE001 — a probe failing must never propagate
        return default
    return default if result is None else result


def _cpu_freq_field(attr):
    """Format one psutil.cpu_freq() attribute in MHz, or N/A if unavailable."""

    def read():
        freq = psutil.cpu_freq()
        if freq is None:
            return None
        value = getattr(freq, attr, None)
        return f"{value:.2f} MHz" if value is not None else None

    return _safe(read)


def _bytes_as_gb(fn):
    """Format a byte count as a GB string, or N/A if it cannot be read."""

    def read():
        return f"{round(fn() / (1024**3), 2)} GB"

    return _safe(read)


#: TEST-NET-1 (RFC 5737). Never routed, and a UDP connect() sends no packets —
#: it only asks the kernel which local interface would be used.
_ROUTE_PROBE = ("192.0.2.1", 1)


def _ip_address():
    """
    Best-effort local IP address, without a DNS lookup.

    The obvious implementation, socket.gethostbyname(socket.gethostname()), is
    a trap. When the machine's own hostname does not resolve — a `.local` name
    with no mDNS responder answering, a VPN, a container, a renamed machine —
    the resolver does not fail fast. It **blocks for the full DNS timeout**,
    measured at 35 seconds on macOS, and only then raises gaierror. Since this
    runs on the prompt path, that stalled every prompt for over half a minute
    before discarding it.

    Opening a UDP socket toward an unroutable address asks the kernel which
    local interface it would use and returns that interface's address. No
    packet is sent, no name is resolved, and it completes in well under a
    millisecond. It also returns the actual LAN address rather than whatever
    the hostname happens to map to.
    """

    def probe():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.2)
            sock.connect(_ROUTE_PROBE)
            return sock.getsockname()[0]
        finally:
            sock.close()

    return _safe(probe)


#: Cache for get_system_info(). The values are static hardware and OS facts, so
#: gathering them once per process is both correct and materially cheaper than
#: doing it on every prompt.
_system_info_cache = None


def get_system_info(refresh=False):
    """
    Collect static system hardware and OS metadata.

    **This function never raises.** Any field that cannot be determined is
    reported as "N/A". That guarantee is load-bearing: get_system_info() is
    called by run_prompt() *after* the model has already produced an answer,
    and again by save_prompt_usage(). A probe that raised — as the IP address
    lookup did on any host whose own name does not resolve — discarded a
    completed prompt with a 500 and wrote no row, so the user paid the energy
    cost of the call and got nothing back.

    The result is cached for the life of the process. Everything reported here
    is static, and the alternative is re-probing the CPU, disks and network on
    every prompt.

    Args:
        refresh: Re-probe instead of returning the cached result.

    Returns:
        A fresh dict (mutating it cannot corrupt the cache) with keys: OS, OS
        Version, Platform, Machine, Processor, CPU, CPU Cores (Physical), CPU
        Cores (Total), CPU Frequency (Current/Min/Max), RAM (Total), Disk
        (Total/Used/Free), Hostname, IP Address.
    """
    global _system_info_cache
    if _system_info_cache is not None and not refresh:
        return dict(_system_info_cache)

    _system_info_cache = {
        "OS": _safe(platform.system),
        "OS Version": _safe(platform.version),
        "Platform": _safe(platform.platform),
        "Machine": _safe(platform.machine),
        "Processor": _safe(platform.processor),
        "CPU": _safe(lambda: cpuinfo.get_cpu_info().get("brand_raw", UNKNOWN)),
        "CPU Cores (Physical)": _safe(lambda: psutil.cpu_count(logical=False)),
        "CPU Cores (Total)": _safe(lambda: psutil.cpu_count(logical=True)),
        "CPU Frequency (Current)": _cpu_freq_field("current"),
        "CPU Frequency (Min)": _cpu_freq_field("min"),
        "CPU Frequency (Max)": _cpu_freq_field("max"),
        "RAM (Total)": _bytes_as_gb(lambda: psutil.virtual_memory().total),
        "Disk (Total)": _bytes_as_gb(lambda: shutil.disk_usage("/").total),
        "Disk (Used)": _bytes_as_gb(lambda: shutil.disk_usage("/").used),
        "Disk (Free)": _bytes_as_gb(lambda: shutil.disk_usage("/").free),
        "Hostname": _safe(socket.gethostname),
        "IP Address": _ip_address(),
    }
    return dict(_system_info_cache)


# Platform-specific power consumption measurement placeholders
def measure_power_mac(start_time, end_time, monitor=None):
    """
    Uses PowerMonitor samples for macOS. Returns average CPU/GPU/Combined power and energy.
    """
    duration = end_time - start_time
    # Baseline: average combined power for 1 minute before prompt start
    baseline_start = start_time - 60
    baseline_end = start_time
    baseline_samples = [
        s
        for ts, s in getattr(monitor, "samples", [])
        if baseline_start <= ts <= baseline_end
    ]
    if baseline_samples:
        baseline_avg = sum(
            s.get("combined_power_w", 0.0) for s in baseline_samples
        ) / len(baseline_samples)
        baseline_energy_wh = (baseline_avg * 60) / 3600.0
    else:
        baseline_avg = None
        baseline_energy_wh = None
    # Filter monitor.samples for timestamps in [start_time, end_time]
    samples = [
        s for ts, s in getattr(monitor, "samples", []) if start_time <= ts <= end_time
    ]
    if not samples:
        return {
            "error": "No power samples found between start_time and end_time. Try increasing monitor window or sample interval."
        }
    avg_cpu = sum(s.get("cpu_power_w", 0) for s in samples) / len(samples)
    avg_gpu = sum(s.get("gpu_power_w", 0) for s in samples) / len(samples)
    avg_combined = sum(s.get("combined_power_w", 0) for s in samples) / len(samples)
    energy_wh = (avg_combined * duration) / 3600
    return {
        "cpu_power_w": avg_cpu,
        "gpu_power_w": avg_gpu,
        "combined_power_w": avg_combined,
        "duration_sec": duration,
        "energy_wh": energy_wh,
        "baseline_power_w": baseline_avg,
        "baseline_energy_wh": baseline_energy_wh,
    }


def measure_power_linux(start_time: float, end_time: float, monitor=None) -> dict:
    """
    Compute power and energy metrics for a Linux prompt run from LinuxPowerMonitor samples.

    Takes a single thread-safe snapshot of monitor.samples, then filters for the
    prompt window [start_time, end_time] and a 60-second idle baseline before it.

    Short-prompt interpolation: if the prompt duration is shorter than the sampler
    interval (typically 1s), the window may contain zero samples. In that case,
    up to two neighboring samples (one before, one after the window, within
    2 × sample_interval seconds) are used as a proxy. The result includes
    "extrapolated": True when this path is taken.

    Args:
        start_time: Unix timestamp when the prompt started.
        end_time: Unix timestamp when the prompt ended.
        monitor: LinuxPowerMonitor instance, or None to return zeros with a warning.

    Returns:
        dict with keys: cpu_power_w, gpu_power_w, combined_power_w, duration_sec,
        energy_wh, baseline_power_w, baseline_energy_wh.
        Optional key: extrapolated (True if neighboring samples were used).
    """
    duration = end_time - start_time

    _zero = {
        "cpu_power_w": 0.0,
        "gpu_power_w": 0.0,
        "combined_power_w": 0.0,
        "duration_sec": duration,
        "energy_wh": 0.0,
        "baseline_power_w": 0.0,
        "baseline_energy_wh": 0.0,
    }

    if monitor is None:
        print(
            "Warning: LinuxPowerMonitor not running — energy_wh will be 0. Start with 'greenprompt run'."
        )
        return _zero

    # Single thread-safe snapshot — avoids two separate deque iterations that
    # could be inconsistent if the sampler appends between them.
    if hasattr(monitor, "_lock"):
        with monitor._lock:
            all_samples = list(monitor.samples)
    else:
        all_samples = list(getattr(monitor, "samples", []))

    baseline_start = start_time - 60
    baseline_samples = [
        s for ts, s in all_samples if baseline_start <= ts <= start_time
    ]
    prompt_samples = [s for ts, s in all_samples if start_time <= ts <= end_time]

    # Short-prompt interpolation: find nearest neighbors when window is empty
    extrapolated = False
    if not prompt_samples:
        sample_interval = getattr(monitor, "sample_interval", 1)
        threshold = 2 * sample_interval

        before = [(ts, s) for ts, s in all_samples if ts < start_time]
        after = [(ts, s) for ts, s in all_samples if ts > end_time]

        neighbors = []
        if before and (start_time - before[-1][0]) <= threshold:
            neighbors.append(before[-1][1])
        if after and (after[0][0] - end_time) <= threshold:
            neighbors.append(after[0][1])

        if neighbors:
            prompt_samples = neighbors
            extrapolated = True
        else:
            print(
                "Warning: No power samples in prompt window — monitor may need more warm-up time."
            )
            return _zero

    avg_cpu = sum(s.get("cpu_power_w", 0.0) for s in prompt_samples) / len(
        prompt_samples
    )
    avg_gpu = sum(s.get("gpu_power_w", 0.0) for s in prompt_samples) / len(
        prompt_samples
    )
    avg_combined = sum(s.get("combined_power_w", 0.0) for s in prompt_samples) / len(
        prompt_samples
    )
    energy_wh = (avg_combined * duration) / 3600.0

    if baseline_samples:
        baseline_avg = sum(
            s.get("combined_power_w", 0.0) for s in baseline_samples
        ) / len(baseline_samples)
        baseline_energy_wh = (baseline_avg * 60.0) / 3600.0
    else:
        baseline_avg = 0.0
        baseline_energy_wh = 0.0

    result = {
        "cpu_power_w": avg_cpu,
        "gpu_power_w": avg_gpu,
        "combined_power_w": avg_combined,
        "duration_sec": duration,
        "energy_wh": energy_wh,
        "baseline_power_w": baseline_avg,
        "baseline_energy_wh": baseline_energy_wh,
    }
    if extrapolated:
        result["extrapolated"] = True
    return result


def measure_power_windows(pid, start_time, end_time):  # noqa: ARG001
    """
    Placeholder: Uses WMI for Windows. Not process-specific.
    """
    try:
        import wmi

        c = wmi.WMI(namespace="root\\wmi")
        sensors = c.MSAcpi_ThermalZoneTemperature()
        time.sleep(end_time - start_time)
        return f"Temperature sensors read: {len(sensors)}"
    except Exception as e:
        return f"Error collecting power metrics on Windows: {e}"


def measure_power_for_pid(pid, start_time, end_time, monitor=None):
    """
    Dispatch power measurement to the appropriate OS-specific function.

    On macOS, reads from the PowerMonitor sample buffer (samplerMac.py).
    On Linux, reads from the LinuxPowerMonitor sample buffer (samplerLinux.py).
    On Windows, returns a zero dict (not yet implemented).

    Args:
        pid: Process ID (reserved for future per-process filtering).
        start_time: Unix timestamp when the workload started.
        end_time: Unix timestamp when the workload ended.
        monitor: Platform monitor instance (PowerMonitor or LinuxPowerMonitor).

    Returns:
        dict with cpu_power_w, gpu_power_w, combined_power_w, duration_sec,
        energy_wh, baseline_power_w, baseline_energy_wh. Never returns a string.
    """
    os_type = constants.OS
    if os_type == "Darwin":
        return measure_power_mac(start_time, end_time, monitor)
    elif os_type == "Linux":
        return measure_power_linux(start_time, end_time, monitor)
    elif os_type == "Windows":
        duration = end_time - start_time
        return {
            "cpu_power_w": 0.0,
            "gpu_power_w": 0.0,
            "combined_power_w": 0.0,
            "duration_sec": duration,
            "energy_wh": 0.0,
            "baseline_power_w": 0.0,
            "baseline_energy_wh": 0.0,
        }
    else:
        duration = end_time - start_time
        return {
            "cpu_power_w": 0.0,
            "gpu_power_w": 0.0,
            "combined_power_w": 0.0,
            "duration_sec": duration,
            "energy_wh": 0.0,
            "baseline_power_w": 0.0,
            "baseline_energy_wh": 0.0,
        }


def has_gpu():
    """
    Detect whether a GPU is present on the current machine.

    macOS: checks system_profiler SPDisplaysDataType for a Chipset Model entry.
    Linux/Windows: runs nvidia-smi -L and checks for non-empty output.

    Returns:
        True if a GPU is detected, False otherwise or on error.
    """
    os_type = constants.OS
    try:
        if os_type == "Darwin":
            # Check for any GPU listed in display hardware
            output = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"]
            ).decode()
            return "Chipset Model" in output  # heuristic
        elif os_type in ["Linux", "Windows"]:
            # Check if nvidia-smi exists and returns at least one GPU
            try:
                result = subprocess.check_output(
                    ["nvidia-smi", "-L"], stderr=subprocess.DEVNULL
                ).decode()
                return bool(result.strip())
            except subprocess.CalledProcessError:
                return False
        else:
            return False
    except Exception:
        return False


def get_gpu_usage():
    """
    Return current GPU utilization and power statistics.

    Linux/Windows: queries nvidia-smi for power draw, utilization, memory,
    and temperature. Handles [N/A] fields gracefully.
    macOS: returns a not-supported message (powermetrics covers GPU on macOS).

    Returns:
        str — formatted GPU stats string, or an explanatory string on error.
    """
    os_type = constants.OS
    try:
        if os_type == "Darwin":
            return "GPU usage monitoring not supported on macOS"
        elif os_type in ["Linux", "Windows"]:
            output = (
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,power.draw,power.limit,utilization.gpu,"
                        "utilization.memory,memory.used,memory.total,temperature.gpu",
                        "--format=csv,noheader",
                    ],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            # Parse and reformat so [N/A] values are visible but don't crash callers
            parts = [p.strip() for p in output.split(",")]
            labels = [
                "name",
                "power_draw",
                "power_limit",
                "gpu_util",
                "mem_util",
                "mem_used",
                "mem_total",
                "temperature",
            ]
            stats = dict(zip(labels, parts))
            return (
                f"GPU: {stats.get('name', 'N/A')} | "
                f"Power: {stats.get('power_draw', 'N/A')} / {stats.get('power_limit', 'N/A')} | "
                f"GPU util: {stats.get('gpu_util', 'N/A')} | "
                f"Mem: {stats.get('mem_used', 'N/A')} / {stats.get('mem_total', 'N/A')} | "
                f"Temp: {stats.get('temperature', 'N/A')}"
            )
        else:
            return "GPU usage monitoring not supported on this OS."
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        return f"Error retrieving GPU usage: {e}"


def parse_powermetrics_output(output: str, duration_sec: float) -> dict:
    """
    Parses powermetrics output from macOS and estimates CPU usage, power usage, and energy.

    Parameters:
        output (str): Raw text output from powermetrics.
        duration_sec (float): Duration the sampling covered (in seconds).

    Returns:
        dict: {
            'cpu_power_w': float,
            'gpu_power_w': float,
            'combined_power_w': float,
            'cpu_active_avg': float,  # if available
            'energy_wh': float
        }
    """
    # Extract CPU/GPU/Combined power in mW
    cpu_power_match = re.search(r"CPU Power:\s+([\d.]+)\s+mW", output)
    gpu_power_match = re.search(r"GPU Power:\s+([\d.]+)\s+mW", output)
    combined_power_match = re.search(r"Combined Power.*?:\s+([\d.]+)\s+mW", output)

    # Fallback defaults
    cpu_power = float(cpu_power_match.group(1)) / 1000 if cpu_power_match else 0.0
    gpu_power = float(gpu_power_match.group(1)) / 1000 if gpu_power_match else 0.0
    combined_power = (
        float(combined_power_match.group(1)) / 1000
        if combined_power_match
        else cpu_power + gpu_power
    )

    # Try to get an average CPU active residency
    cpu_active_matches = re.findall(r"CPU \d+ active residency:\s+([\d.]+)%", output)
    if cpu_active_matches:
        cpu_active_avg = sum(float(p) for p in cpu_active_matches) / len(
            cpu_active_matches
        )
    else:
        cpu_active_avg = None

    # Estimate energy
    energy_wh = (combined_power * duration_sec) / 3600

    return {
        "cpu_power_w": cpu_power,
        "gpu_power_w": gpu_power,
        "combined_power_w": combined_power,
        "cpu_active_avg": cpu_active_avg,
        "energy_wh": energy_wh,
    }
