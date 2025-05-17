import platform
import psutil
import socket
import cpuinfo
import shutil

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


if _name_ == "_main_":
    system_info = get_system_info()
    for key, value in system_info.items():
        print(f"{key}: {value}")