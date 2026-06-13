# GreenPrompt Platform Support

## Current Status

| Feature | macOS (Apple Silicon) | macOS (Intel) | Linux | Windows |
|---|---|---|---|---|
| Live CPU power sampling | ✅ `powermetrics` | ✅ `powermetrics` | ❌ stub | ❌ stub |
| Live GPU power sampling | ✅ via `powermetrics` | ✅ via `powermetrics` | ❌ stub | ❌ stub |
| GPU detection | ✅ `system_profiler` | ✅ `system_profiler` | ✅ `nvidia-smi -L` | ✅ `nvidia-smi -L` |
| GPU utilization stats | — (not available) | — (not available) | ✅ `nvidia-smi` | ✅ `nvidia-smi` |
| Token counting | ✅ tiktoken | ✅ tiktoken | ✅ tiktoken | ✅ tiktoken |
| Token-based energy estimate | ✅ | ✅ | ✅ | ✅ |
| Prompt scoring | ✅ NLTK | ✅ NLTK | ✅ NLTK | ✅ NLTK |
| SQLite logging | ✅ | ✅ | ✅ | ✅ |
| REST API | ✅ Flask | ✅ Flask | ✅ Flask | ✅ Flask |
| Web dashboard | ✅ Plotly | ✅ Plotly | ✅ Plotly | ✅ Plotly |
| `sudo` requirement | Yes (powermetrics) | Yes (powermetrics) | No | No |

---

## macOS (fully supported)

All features are available on macOS (Apple Silicon and Intel).

Power sampling uses `powermetrics`, a macOS system tool that reports per-package CPU and GPU power in milliwatts. It requires root privileges, which is why `greenprompt run` and `greenprompt setup` require `sudo`.

```bash
sudo greenprompt setup
sudo greenprompt run --port 5000
greenprompt prompt "..." --model llama2  # no sudo needed for prompt
```

The `PowerMonitor` class in `samplerMac.py` runs `powermetrics` in a subprocess every second. On Apple Silicon, this reports unified memory architecture (UMA) CPU and GPU power as separate values. On Intel Macs, it reports CPU package power; integrated GPU power may be reported as 0 depending on the Mac model.

---

## Linux (partial support)

On Linux, `greenprompt` works for:
- Token counting and estimation
- Prompt scoring
- SQLite logging
- REST API and web dashboard

**Power measurement returns zero.** The `measure_power_for_pid()` function returns the string `"Linux power measurement not implemented."` on Linux (the old `psutil`-based stub is commented out), so `energy_wh`, `cpu_power_w`, and `gpu_power_w` are all `0` in the database.

`sudo` is **not required** on Linux since `powermetrics` is not called.

### GPU on Linux

`has_gpu()` and `get_gpu_usage()` work correctly on Linux via `nvidia-smi`:

```python
# has_gpu() calls:
subprocess.check_output(["nvidia-smi", "-L"])

# get_gpu_usage() calls:
subprocess.check_output([
    "nvidia-smi",
    "--query-gpu=utilization.gpu,memory.used,memory.total",
    "--format=csv,nounits,noheader"
])
```

GPU utilization is printed to the console during `run_prompt()` but is **not** currently included in the energy calculation on Linux.

---

## Windows (partial support)

Same status as Linux: scoring, logging, and API work; power measurement is not implemented.

`has_gpu()` and `get_gpu_usage()` work via `nvidia-smi` if CUDA drivers are installed.

Note: `lsof` calls in `cli.py` (used by `run` and `stop` commands to manage the API server process) are Unix-only. On Windows, `greenprompt run` and `greenprompt stop` will fail. The API server can still be started manually:

```cmd
python -m greenprompt.api --port=5000
```

---

## Roadmap: Linux Power Measurement

### Approach 1 — Intel RAPL (CPU)

Linux exposes Intel Running Average Power Limit (RAPL) counters via sysfs or the `perf_event` subsystem. Reading `/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj` gives cumulative microjoules.

```python
def read_rapl_energy_uj():
    with open("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj") as f:
        return int(f.read())

start_energy = read_rapl_energy_uj()
# ... run prompt ...
end_energy = read_rapl_energy_uj()
energy_j = (end_energy - start_energy) / 1_000_000
energy_wh = energy_j / 3600
```

**Requirements:** Intel CPU (Sandybridge+), Linux kernel ≥ 3.13. AMD CPUs expose RAPL via a compatible interface. May require root or `CAP_DAC_READ_SEARCH` capability.

### Approach 2 — NVIDIA GPU via `nvidia-smi`

For NVIDIA GPUs, `nvidia-smi` can report instantaneous power draw:

```bash
nvidia-smi --query-gpu=power.draw --format=csv,nounits,noheader
# Output: 45.2
```

Sample this in a background thread (similar to `PowerMonitor`) and integrate over time:

```python
import subprocess, time, threading
from collections import deque

class LinuxPowerMonitor:
    def __init__(self, interval=1):
        self.samples = deque(maxlen=600)
        self.interval = interval
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while True:
            try:
                gpu_w = float(subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=power.draw",
                     "--format=csv,nounits,noheader"]
                ).decode().strip())
                self.samples.append((time.time(), {"gpu_power_w": gpu_w}))
            except Exception:
                pass
            time.sleep(self.interval)

    def start(self):
        self._thread.start()
```

### Approach 3 — AMD ROCm

For AMD GPUs on Linux, use `rocm-smi`:

```bash
rocm-smi --showpower
```

### Implementation Plan

The cleanest path for Linux support:

1. Implement `LinuxPowerMonitor` in `samplerLinux.py` using RAPL + `nvidia-smi` (following the same interface as `PowerMonitor` in `samplerMac.py`).
2. Update `sysUsage.measure_power_for_pid()` to call `measure_power_linux()` using the Linux monitor instead of the stub.
3. Update `api.py` to instantiate the correct monitor based on `constants.OS`.
4. Add `nvidia-smi` and `pyrapl` (or direct sysfs reads) to optional dependencies in `pyproject.toml`.

---

## Roadmap: Windows Power Measurement

### Approach 1 — Intel Power Gadget

Intel provides a Windows SDK for CPU power reading. The `pyintelpower` package wraps it.

### Approach 2 — WMI + NVIDIA

```python
import wmi
c = wmi.WMI(namespace="root\\wmi")
# Battery-based power reading (rough approximation)
```

Combined with `nvidia-smi` for GPU power.

### Approach 3 — Windows Performance Counters

```python
import win32pdh
# Read CPU and power counters via PDH API
```

---

## Contributing Platform Support

If you're implementing Linux or Windows power measurement, the interface to match is `measure_power_mac()` in `sysUsage.py`:

```python
def measure_power_mac(start_time: float, end_time: float, monitor) -> dict:
    return {
        "cpu_power_w": float,      # average CPU watts during [start, end]
        "gpu_power_w": float,      # average GPU watts during [start, end]
        "combined_power_w": float, # average combined watts
        "duration_sec": float,
        "energy_wh": float,        # (combined_power_w × duration_sec) / 3600
        "baseline_power_w": float, # average combined watts during [start-60, start]
        "baseline_energy_wh": float,
    }
```

The `monitor` parameter is a platform-specific monitor object with a `samples` attribute of `(timestamp, dict)` tuples.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution workflow.
