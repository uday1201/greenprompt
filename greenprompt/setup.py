import glob
import os
import platform
from greenprompt.sysUsage import get_system_info
from greenprompt.dbconn import init_db
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


def sanitize_key(key):
    """
    Sanitize keys to make them valid Python variable names.
    Replaces spaces and special characters with underscores.
    """
    return key.upper().replace(" ", "_").replace("(", "").replace(")", "")


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
            ("cortex-x925", 23.0),   # 10-core P-cluster (NVIDIA Grace / Snapdragon X Elite)
            ("cortex-a725",  8.0),   # 10-core E-cluster
            ("cortex-x4",   30.0),
            ("cortex-x3",   25.0),
            ("cortex-x2",   20.0),
            ("cortex-x1",   15.0),
            ("a78",         10.0),
            ("i9-",         65.0),
            ("i7-",         45.0),
            ("i5-",         35.0),
            ("i3-",         25.0),
            ("ryzen 9",     65.0),
            ("ryzen 7",     45.0),
            ("ryzen 5",     35.0),
            ("apple m",     20.0),
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

    # Get system information
    system_info = get_system_info()

    # Run git update-index to hide constants.py
    try:
        subprocess.run(
            [
                "git",
                "update-index",
                "--no-assume-unchanged",
                "greenprompt/constants.py",
            ],
            check=True,
        )
        print("Updated git index to track changes to constants.py.")
    except Exception as e:
        print(f"Could not update git index: {e}")

    # Save system information to constants.py
    constants_py_path = os.path.join(os.getcwd(), "constants.py")
    cpu_tdp_w = detect_cpu_tdp_w()

    # Detect CPU power measurement source for informational display
    cpu_power_source = "estimated"
    if platform.system() == "Linux":
        rapl_files = glob.glob("/sys/class/powercap/intel-rapl*/intel-rapl*:0/energy_uj")
        direct_rapl = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
        if rapl_files or os.path.exists(direct_rapl):
            cpu_power_source = "rapl"

    with open(constants_py_path, "w") as py_file:
        py_file.write("# Auto-generated constants file\n")
        for key, value in system_info.items():
            sanitized_key = sanitize_key(key)
            py_file.write(f"{sanitized_key} = {repr(value)}\n")
        # Add ollama URL
        py_file.write(f"OLLAMA_URL = {repr(OLLAMA_URL)}\n")
        # CPU TDP estimate used by LinuxPowerMonitor in linear_tdp fallback mode.
        # In arm_biglittle or rapl mode this value is not used for sampling.
        py_file.write(f"CPU_TDP_W = {cpu_tdp_w}\n")
        # Informational: 'rapl' (Intel/AMD direct measurement) or 'estimated' (ARM/other)
        py_file.write(f"CPU_POWER_SOURCE = {repr(cpu_power_source)}\n")
    print(f"✅ System information saved to {constants_py_path} (CPU_TDP_W={cpu_tdp_w}W, CPU_POWER_SOURCE={cpu_power_source!r})")

    # On macOS, configure passwordless sudo for powermetrics so `greenprompt run`
    # works without sudo after this one-time setup.
    configure_powermetrics_sudoers()

    # Download required NLTK data
    print("Downloading required NLTK data...")
    download_nltk_data()
    print("✅ NLTK data downloaded.")

    # Check if Ollama is installed
    check_ollama()

    # Initialize the database and create tables
    init_db()


if __name__ == "__main__":
    main()
