"""
setup.py — one-time GreenPrompt initialization.

Run via `greenprompt setup`. Detects hardware, writes the user config file
(~/.greenprompt/config.json by default — see constants.config_path()),
configures passwordless sudo for powermetrics on macOS, downloads NLTK data,
verifies Ollama, and creates the SQLite database.

The config is written outside the package so that setup works from any
directory and survives reinstalls. Platform values (OS, machine, etc.) are
NOT persisted — constants.py derives those live on every import, so they can
never go stale or leak one machine's identity into another's install.
"""

import glob
import json
import os
import platform
from greenprompt import constants
from greenprompt.sysUsage import get_system_info
from greenprompt.dbconn import init_db, DB_PATH
import subprocess
import nltk

# Ollama URL for local server
OLLAMA_URL = "http://127.0.0.1:11434"
monitor = None


def download_nltk_data():
    resources = [
        "punkt",
        "averaged_perceptron_tagger",
        "wordnet",
        "stopwords",
        "punkt_tab",
        "averaged_perceptron_tagger_eng",
    ]
    for resource in resources:
        try:
            nltk.download(resource)
        except Exception as e:
            print(f"Could not download NLTK resource '{resource}': {e}")


def detect_cpu_power_source() -> str:
    """
    Report whether direct CPU energy measurement is available on this machine.

    Returns "rapl" when Intel/AMD RAPL sysfs counters are present (Linux only),
    otherwise "estimated". Informational only — LinuxPowerMonitor performs its
    own detection at startup.
    """
    if platform.system() != "Linux":
        return "estimated"
    direct = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
    if os.path.exists(direct):
        return "rapl"
    if glob.glob("/sys/class/powercap/intel-rapl*/intel-rapl*:0/energy_uj"):
        return "rapl"
    return "estimated"


def write_config(cpu_tdp_w: float, cpu_power_source: str) -> str:
    """
    Write the GreenPrompt user config file as JSON.

    Merges onto any existing config so hand-edited values (e.g. a custom
    OLLAMA_URL) are preserved across re-runs of setup.

    Args:
        cpu_tdp_w: Detected CPU TDP in watts.
        cpu_power_source: "rapl" or "estimated".

    Returns:
        The path the config was written to.
    """
    path = constants.config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    cfg = constants.load_config()
    cfg.setdefault("OLLAMA_URL", OLLAMA_URL)
    cfg["CPU_TDP_W"] = cpu_tdp_w
    cfg["CPU_POWER_SOURCE"] = cpu_power_source

    with open(path, "w") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def detect_cpu_tdp_w() -> float:
    """
    Estimate CPU TDP in watts for the current machine.

    Checks known CPU brand strings against a lookup table. Falls back to
    40W, a reasonable default for ARM Cortex-X925 (20-core) systems.

    Returns:
        Estimated CPU TDP in watts as a float.
    """
    try:
        import cpuinfo

        brand = cpuinfo.get_cpu_info().get("brand_raw", "").lower()
        # Known TDP estimates by CPU family
        tdp_map = [
            (
                "cortex-x925",
                23.0,
            ),  # 10-core P-cluster (NVIDIA Grace / Snapdragon X Elite)
            ("cortex-a725", 8.0),  # 10-core E-cluster
            ("cortex-x4", 30.0),
            ("cortex-x3", 25.0),
            ("cortex-x2", 20.0),
            ("cortex-x1", 15.0),
            ("a78", 10.0),
            ("i9-", 65.0),
            ("i7-", 45.0),
            ("i5-", 35.0),
            ("i3-", 25.0),
            ("ryzen 9", 65.0),
            ("ryzen 7", 45.0),
            ("ryzen 5", 35.0),
            ("apple m", 20.0),
        ]
        for keyword, tdp in tdp_map:
            if keyword in brand:
                return tdp
    except Exception:
        pass
    return 40.0  # default for Cortex-X925


def configure_powermetrics_sudoers():
    """
    Write /etc/sudoers.d/greenprompt to allow passwordless powermetrics.

    Only runs on macOS. Requires the current process to be root (i.e. the user
    ran `sudo greenprompt setup`). If this succeeds, subsequent `greenprompt run`
    calls work without sudo because samplerMac.py calls `sudo powermetrics`
    internally and the sudoers rule removes the password prompt.

    Prints instructions and returns False if the write fails (e.g. not root).
    """
    if platform.system() != "Darwin":
        return True

    powermetrics_path = "/usr/bin/powermetrics"
    sudoers_file = "/etc/sudoers.d/greenprompt"
    try:
        import pwd

        # Identify the real (non-root) user: SUDO_USER env var set by sudo
        real_user = os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
        rule = f"{real_user} ALL=(ALL) NOPASSWD: {powermetrics_path}\n"
        with open(sudoers_file, "w") as f:
            f.write(rule)
        # sudoers.d files must be mode 0440
        os.chmod(sudoers_file, 0o440)
        print(f"✅ Configured passwordless sudo for powermetrics ({sudoers_file})")
        print("   You can now run 'greenprompt run' without sudo.")
        return True
    except PermissionError:
        print(
            "ℹ️  Skipping powermetrics sudo configuration (not running as root).\n"
            "   For accurate power tracking on macOS, run setup once with sudo:\n"
            "       sudo greenprompt setup\n"
            "   After that, 'greenprompt run' works without sudo."
        )
        return False
    except Exception as e:
        print(f"Warning: could not configure sudoers for powermetrics: {e}")
        return False


def check_ollama():
    """
    Check if Ollama is installed. If not, install it and return the port.
    """
    print("Checking if Ollama is installed...")
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Ollama is installed: {result.stdout.strip()}")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        print("Ollama is not installed. Installing...")
        subprocess.run(["brew", "install", "ollama"], check=True)

    # Check the port Ollama is running on
    try:
        result = subprocess.run(
            ["lsof", "-i", ":11434"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("Ollama is running on port 11434.")
        else:
            print("Ollama is not running on port 11434. Starting it...")
            subprocess.run(["ollama", "serve"], check=True)
    except Exception as e:
        print(f"Error checking or starting Ollama: {e}")


def main():
    print("Setting up GreenPrompt...")

    # Report detected hardware. Not persisted — constants.py derives platform
    # values live, and get_system_info() is recorded per-prompt in the database.
    system_info = get_system_info()
    print(
        f"Detected: {system_info['OS']} / {system_info['Machine']} / "
        f"{system_info['CPU']} ({system_info['CPU Cores (Total)']} cores)"
    )

    # Write tunables to the user config file that constants.py reads.
    cpu_tdp_w = detect_cpu_tdp_w()
    cpu_power_source = detect_cpu_power_source()
    config_file = write_config(cpu_tdp_w, cpu_power_source)
    print(
        f"✅ Config written to {config_file} "
        f"(CPU_TDP_W={cpu_tdp_w}W, CPU_POWER_SOURCE={cpu_power_source!r})"
    )

    # On macOS, configure passwordless sudo for powermetrics so `greenprompt run`
    # works without sudo after this one-time setup.
    configure_powermetrics_sudoers()

    # Download required NLTK data
    print("Downloading required NLTK data...")
    download_nltk_data()
    print("✅ NLTK data downloaded.")

    # Check if Ollama is installed
    check_ollama()

    # Initialize the database and create tables. DB_PATH is relative to the
    # current working directory, so tell the user exactly where it landed.
    init_db()
    print(f"✅ Database ready at {DB_PATH}")


if __name__ == "__main__":
    main()
