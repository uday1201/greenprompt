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

def get_system_info():
    """
    Collect static system hardware and OS metadata.

    Returns:
        dict with keys: OS, OS Version, Platform, Machine, Processor, CPU,
        CPU Cores (Physical), CPU Cores (Total), CPU Frequency (Current/Min/Max),
        RAM (Total), Disk (Total/Used/Free), Hostname, IP Address.
    """
    info = {
        "OS": platform.system(),
        "OS Version": platform.version(),
        "Platform": platform.platform(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
        "CPU": cpuinfo.get_cpu_info().get('brand_raw', 'N/A'),
        "CPU Cores (Physical)": psutil.cpu_count(logical=False),
        "CPU Cores (Total)": psutil.cpu_count(logical=True),
        "CPU Frequency (Current)": f"{psutil.cpu_freq().current:.2f} MHz" if psutil.cpu_freq() else "N/A",
        "CPU Frequency (Min)": f"{psutil.cpu_freq().min:.2f} MHz" if psutil.cpu_freq() else "N/A",
        "CPU Frequency (Max)": f"{psutil.cpu_freq().max:.2f} MHz" if psutil.cpu_freq() else "N/A",
        "RAM (Total)": f"{round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB",
        "Disk (Total)": f"{round(shutil.disk_usage('/').total / (1024 ** 3), 2)} GB",
        "Disk (Used)": f"{round(shutil.disk_usage('/').used / (1024 ** 3), 2)} GB",
        "Disk (Free)": f"{round(shutil.disk_usage('/').free / (1024 ** 3), 2)} GB",
        "Hostname": socket.gethostname(),
        "IP Address": socket.gethostbyname(socket.gethostname()),
    }

    return info

# Platform-specific power consumption measurement placeholders
def measure_power_mac(start_time, end_time, monitor=None):
    """
    Uses PowerMonitor samples for macOS. Returns average CPU/GPU/Combined power and energy.
    """
    duration = end_time - start_time
    # Baseline: average combined power for 1 minute before prompt start
    baseline_start = start_time - 60
    baseline_end = start_time
    baseline_samples = [s for ts, s in getattr(monitor, "samples", []) if baseline_start <= ts <= baseline_end]
    if baseline_samples:
        baseline_avg = sum(s.get("combined_power_w", 0.0) for s in baseline_samples) / len(baseline_samples)
        baseline_energy_wh = (baseline_avg * 60) / 3600.0
    else:
        baseline_avg = None
        baseline_energy_wh = None
    # Filter monitor.samples for timestamps in [start_time, end_time]
    samples = [s for ts, s in getattr(monitor, "samples", []) if start_time <= ts <= end_time]
    if not samples:
        return {"error": "No power samples found between start_time and end_time. Try increasing monitor window or sample interval."}
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
        print("Warning: LinuxPowerMonitor not running — energy_wh will be 0. Start with 'greenprompt run'.")
        return _zero

    # Single thread-safe snapshot — avoids two separate deque iterations that
    # could be inconsistent if the sampler appends between them.
    if hasattr(monitor, "_lock"):
        with monitor._lock:
            all_samples = list(monitor.samples)
    else:
        all_samples = list(getattr(monitor, "samples", []))

    baseline_start = start_time - 60
    baseline_samples = [s for ts, s in all_samples if baseline_start <= ts <= start_time]
    prompt_samples = [s for ts, s in all_samples if start_time <= ts <= end_time]

    # Short-prompt interpolation: find nearest neighbors when window is empty
    extrapolated = False
    if not prompt_samples:
        sample_interval = getattr(monitor, "sample_interval", 1)
        threshold = 2 * sample_interval

        before = [(ts, s) for ts, s in all_samples if ts < start_time]
        after  = [(ts, s) for ts, s in all_samples if ts > end_time]

        neighbors = []
        if before and (start_time - before[-1][0]) <= threshold:
            neighbors.append(before[-1][1])
        if after and (after[0][0] - end_time) <= threshold:
            neighbors.append(after[0][1])

        if neighbors:
            prompt_samples = neighbors
            extrapolated = True
        else:
            print("Warning: No power samples in prompt window — monitor may need more warm-up time.")
            return _zero

    avg_cpu      = sum(s.get("cpu_power_w", 0.0)      for s in prompt_samples) / len(prompt_samples)
    avg_gpu      = sum(s.get("gpu_power_w", 0.0)      for s in prompt_samples) / len(prompt_samples)
    avg_combined = sum(s.get("combined_power_w", 0.0) for s in prompt_samples) / len(prompt_samples)
    energy_wh    = (avg_combined * duration) / 3600.0

    if baseline_samples:
        baseline_avg       = sum(s.get("combined_power_w", 0.0) for s in baseline_samples) / len(baseline_samples)
        baseline_energy_wh = (baseline_avg * 60.0) / 3600.0
    else:
        baseline_avg       = 0.0
        baseline_energy_wh = 0.0

    result = {
        "cpu_power_w":        avg_cpu,
        "gpu_power_w":        avg_gpu,
        "combined_power_w":   avg_combined,
        "duration_sec":       duration,
        "energy_wh":          energy_wh,
        "baseline_power_w":   baseline_avg,
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
            "cpu_power_w": 0.0, "gpu_power_w": 0.0, "combined_power_w": 0.0,
            "duration_sec": duration, "energy_wh": 0.0,
            "baseline_power_w": 0.0, "baseline_energy_wh": 0.0,
        }
    else:
        duration = end_time - start_time
        return {
            "cpu_power_w": 0.0, "gpu_power_w": 0.0, "combined_power_w": 0.0,
            "duration_sec": duration, "energy_wh": 0.0,
            "baseline_power_w": 0.0, "baseline_energy_wh": 0.0,
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
            output = subprocess.check_output(["system_profiler", "SPDisplaysDataType"]).decode()
            return "Chipset Model" in output  # heuristic
        elif os_type in ["Linux", "Windows"]:
            # Check if nvidia-smi exists and returns at least one GPU
            try:
                result = subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.DEVNULL).decode()
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
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,power.draw,power.limit,utilization.gpu,"
                    "utilization.memory,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader",
                ],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            # Parse and reformat so [N/A] values are visible but don't crash callers
            parts = [p.strip() for p in output.split(",")]
            labels = ["name", "power_draw", "power_limit", "gpu_util",
                      "mem_util", "mem_used", "mem_total", "temperature"]
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
    combined_power = float(combined_power_match.group(1)) / 1000 if combined_power_match else cpu_power + gpu_power

    # Try to get an average CPU active residency
    cpu_active_matches = re.findall(r"CPU \d+ active residency:\s+([\d.]+)%", output)
    if cpu_active_matches:
        cpu_active_avg = sum(float(p) for p in cpu_active_matches) / len(cpu_active_matches)
    else:
        cpu_active_avg = None

    # Estimate energy
    energy_wh = (combined_power * duration_sec) / 3600

    return {
        "cpu_power_w": cpu_power,
        "gpu_power_w": gpu_power,
        "combined_power_w": combined_power,
        "cpu_active_avg": cpu_active_avg,
        "energy_wh": energy_wh
    }