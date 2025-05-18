import platform
import psutil
import socket
import cpuinfo
import shutil
import subprocess
import time
import os

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
        "RAM (Total)": f"{round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB",
        "Disk (Total)": f"{round(shutil.disk_usage('/').total / (1024 ** 3), 2)} GB",
        "Disk (Used)": f"{round(shutil.disk_usage('/').used / (1024 ** 3), 2)} GB",
        "Disk (Free)": f"{round(shutil.disk_usage('/').free / (1024 ** 3), 2)} GB",
        "Hostname": socket.gethostname(),
        "IP Address": socket.gethostbyname(socket.gethostname()),
    }

    return info

# Platform-specific power consumption measurement placeholders
def measure_power_mac(pid, duration=5):
    """
    Placeholder: Uses powermetrics for macOS. Requires sudo.
    """
    try:
        cmd = ["sudo", "powermetrics", "-n", "1", "-i", str(duration), "--samplers", "cpu_power"]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
        return output
    except Exception as e:
        return f"Error collecting power metrics on macOS: {e}"

def measure_power_linux(pid, duration=5):
    """
    Placeholder: Uses psutil sensors_battery for Linux (not process-specific).
    """
    try:
        # No direct per-process power usage; placeholder using battery info
        power_start = psutil.sensors_battery().power_plugged if psutil.sensors_battery() else None
        time.sleep(duration)
        power_end = psutil.sensors_battery().power_plugged if psutil.sensors_battery() else None
        return f"Power plugged start: {power_start}, end: {power_end}"
    except Exception as e:
        return f"Error collecting power metrics on Linux: {e}"

def measure_power_windows(pid, duration=5):
    """
    Placeholder: Uses WMI for Windows. Not process-specific.
    """
    try:
        import wmi
        c = wmi.WMI(namespace="root\\wmi")
        sensors = c.MSAcpi_ThermalZoneTemperature()
        time.sleep(duration)
        return f"Temperature sensors read: {len(sensors)}"
    except Exception as e:
        return f"Error collecting power metrics on Windows: {e}"

def measure_power_for_pid(pid, duration=5):
    os_type = platform.system()
    if os_type == "Darwin":
        return measure_power_mac(pid, duration)
    elif os_type == "Linux":
        return measure_power_linux(pid, duration)
    elif os_type == "Windows":
        return measure_power_windows(pid, duration)
    else:
        return "Unsupported OS for power measurement."
    
def has_gpu():
    os_type = platform.system()
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
    os_type = platform.system()
    try:
        if os_type == "Darwin":
            output = subprocess.check_output(["system_profiler", "SPDisplaysDataType"]).decode()
            return output
        elif os_type in ["Linux", "Windows"]:
            output = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,nounits,noheader"]).decode()
            return output
        else:
            return "GPU usage monitoring not supported on this OS."
    except Exception as e:
        return f"Error retrieving GPU usage: {e}"

# Example usage
if __name__ == "__main__":
    system_info = get_system_info()
    print("System Information:")
    for key, value in system_info.items():
        print(f"{key}: {value}")
    current_pid = os.getpid()
    print("\nMeasuring power usage:")
    print(measure_power_for_pid(current_pid, duration=5))
    if has_gpu():
        print("\nGPU detected.")
        print("\nChecking GPU usage:")
        print(get_gpu_usage())