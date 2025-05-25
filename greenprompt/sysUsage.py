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

def measure_power_linux(pid, start_time, end_time):
    """
    Placeholder: Uses psutil sensors_battery for Linux (not process-specific).
    """
    try:
        # No direct per-process power usage; placeholder using battery info
        power_start = psutil.sensors_battery().power_plugged if psutil.sensors_battery() else None
        time.sleep(end_time - start_time)
        power_end = psutil.sensors_battery().power_plugged if psutil.sensors_battery() else None
        return f"Power plugged start: {power_start}, end: {power_end}"
    except Exception as e:
        return f"Error collecting power metrics on Linux: {e}"

def measure_power_windows(pid, start_time, end_time):
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
    os_type = constants.OS
    if os_type == "Darwin":
        return measure_power_mac(start_time, end_time, monitor)
    elif os_type == "Linux":
        #return measure_power_linux(pid, start_time, end_time)
        return "Linux power measurement not implemented."
    elif os_type == "Windows":
        #return measure_power_windows(pid, start_time, end_time)
        return "Windows power measurement not implemented."
    else:
        return "Unsupported OS for power measurement."
    
def has_gpu():
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
    os_type = constants.OS
    try:
        if os_type == "Darwin":
            return "GPU usage monitoring not supported on macOS"
        elif os_type in ["Linux", "Windows"]:
            output = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,nounits,noheader"]).decode()
            return output
        else:
            return "GPU usage monitoring not supported on this OS."
    except Exception as e:
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