"""
constants.py — runtime configuration for GreenPrompt.

This module is machine-independent and safe to commit. Platform values are
derived live at import time, so they are always correct for the machine that
is actually running — they are never baked in by whoever last ran `setup`.

Tunable values (OLLAMA_URL, CPU_TDP_W) come from a user config file written by
`greenprompt setup`, resolved in this order:

    1. $GREENPROMPT_CONFIG            — explicit path to a JSON file
    2. $GREENPROMPT_HOME/config.json
    3. ~/.greenprompt/config.json     — default

Storing these outside the package means `greenprompt setup` works from any
directory and survives reinstalls and upgrades. Earlier versions generated a
`constants.py` in the current working directory, where nothing ever imported
it; any such stray file is obsolete and can be deleted.

Only three names are read by the rest of the codebase — OS, OLLAMA_URL, and
CPU_TDP_W. The remaining platform values are exposed for informational use;
`sysUsage.get_system_info()` is the authoritative source for anything
persisted to the database.
"""

import json
import os
import platform

# --- Defaults ---------------------------------------------------------------

#: Ollama server base URL (no trailing slash).
OLLAMA_URL = "http://127.0.0.1:11434"

#: CPU TDP in watts. Used only by LinuxPowerMonitor's "linear_tdp" fallback
#: mode; ignored when RAPL or ARM big.LITTLE sampling is available.
CPU_TDP_W = 40.0

#: Informational: "rapl" (direct Intel/AMD energy counter) or "estimated".
CPU_POWER_SOURCE = "estimated"


# --- Live platform values ---------------------------------------------------
# Derived on every import. Cheap (no psutil/cpuinfo import) and always
# reflects the current machine, which is what the power-measurement dispatch
# in sysUsage.py and api.py depends on.

OS = platform.system()
OS_VERSION = platform.version()
PLATFORM = platform.platform()
MACHINE = platform.machine()
PROCESSOR = platform.processor()


# --- User config overlay ----------------------------------------------------

#: Keys that may be overridden by the user config file. Platform values are
#: deliberately excluded — pinning OS to a stale value breaks power sampling.
_OVERRIDABLE = ("OLLAMA_URL", "CPU_TDP_W", "CPU_POWER_SOURCE")


def config_path():
    """
    Return the path to the user config file (which may not exist yet).

    Honors $GREENPROMPT_CONFIG, then $GREENPROMPT_HOME/config.json, then
    ~/.greenprompt/config.json.
    """
    explicit = os.environ.get("GREENPROMPT_CONFIG")
    if explicit:
        return os.path.expanduser(explicit)
    home = os.environ.get("GREENPROMPT_HOME")
    if home:
        return os.path.join(os.path.expanduser(home), "config.json")
    return os.path.join(os.path.expanduser("~"), ".greenprompt", "config.json")


def load_config():
    """
    Read the user config file and return it as a dict.

    Returns an empty dict if the file is absent, unreadable, or not valid
    JSON — a broken config must never stop GreenPrompt from importing.
    """
    try:
        with open(config_path()) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _apply_config():
    """Overlay whitelisted values from the user config onto this module."""
    cfg = load_config()
    for key in _OVERRIDABLE:
        if cfg.get(key) is not None:
            globals()[key] = cfg[key]


_apply_config()

# Env var wins over the config file, for one-off runs and CI.
OLLAMA_URL = os.environ.get("GREENPROMPT_OLLAMA_URL", OLLAMA_URL).rstrip("/")
