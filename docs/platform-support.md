# GreenPrompt Platform Support

## Current Status

| Feature | macOS (Apple Silicon) | macOS (Intel) | Linux | Windows |
|---|---|---|---|---|
| Live CPU power sampling | ✅ `powermetrics` | ✅ `powermetrics` | ✅ RAPL / ARM / TDP | ❌ stub |
| Live GPU power sampling | ✅ via `powermetrics` | ✅ via `powermetrics` | ✅ `nvidia-smi dmon` | ❌ stub |
| GPU detection | ✅ `system_profiler` | ✅ `system_profiler` | ✅ `nvidia-smi -L` | ✅ `nvidia-smi -L` |
| GPU utilization stats | — (not available) | — (not available) | ✅ `nvidia-smi` | ✅ `nvidia-smi` |
| Token counting | ✅ tiktoken | ✅ tiktoken | ✅ tiktoken | ✅ tiktoken |
| Token-based energy estimate | ✅ | ✅ | ✅ | ✅ |
| Prompt scoring | ✅ NLTK | ✅ NLTK | ✅ NLTK | ✅ NLTK |
| SQLite logging | ✅ | ✅ | ✅ | ✅ |
| REST API | ✅ Flask | ✅ Flask | ✅ Flask | ✅ Flask |
| Web dashboard | ✅ Plotly | ✅ Plotly | ✅ Plotly | ✅ Plotly |
| `run` / `stop` server lifecycle | ✅ | ✅ | ✅ | ❌ needs `lsof` |
| `sudo` requirement | `setup` once | `setup` once | No | No |

---

## macOS (fully supported)

All features are available on macOS (Apple Silicon and Intel).

Power sampling uses `powermetrics`, a macOS system tool that reports per-package CPU and GPU power in milliwatts. It requires root privileges, but GreenPrompt itself does not: `samplerMac.py` shells out to `sudo powermetrics` internally, and running `setup` once as root installs `/etc/sudoers.d/greenprompt` so that call never prompts for a password.

```bash
sudo greenprompt setup                          # once — installs the sudoers rule
greenprompt run --port 5000                     # no sudo
greenprompt prompt "..." --model llama3.2:latest  # no sudo
```

`samplerMac._check_powermetrics_sudo()` verifies the rule at startup with `sudo -n powermetrics --version` and warns if it is missing; readings are zero until `sudo greenprompt setup` is run.

The `PowerMonitor` class in `samplerMac.py` runs `powermetrics` in a subprocess every second. On Apple Silicon, this reports unified memory architecture (UMA) CPU and GPU power as separate values. On Intel Macs, it reports CPU package power; integrated GPU power may be reported as 0 depending on the Mac model.

---

## Linux (fully supported)

Live power measurement landed in 0.2.0. `LinuxPowerMonitor` in `samplerLinux.py`
mirrors the `PowerMonitor` interface exactly — a daemon thread appending
`(timestamp, sample_dict)` tuples to a 600-entry deque — so
`sysUsage.measure_power_linux()` shares its averaging logic with the macOS path.

No `sudo` is required.

### CPU sampling modes

The mode is auto-detected once, at monitor construction, in priority order:

| Mode | Detected when | Method | Accuracy |
|---|---|---|---|
| `rapl` | `/sys/class/powercap/intel-rapl*/…/energy_uj` is readable | Energy counter delta ÷ elapsed seconds, with `max_energy_range_uj` overflow handling | Measured |
| `arm_biglittle` | `psutil.cpu_freq(percpu=True)` reports more than one distinct per-CPU max frequency | Per-cluster frequency-squared model over each CPU's `scaling_cur_freq` (power ∝ V²f, V scaling with frequency) | Modelled |
| `linear_tdp` | Neither of the above | `cpu_percent / 100 × CPU_TDP_W` | Estimated |

`CPU_TDP_W` comes from the user config file and is used **only** in `linear_tdp`
mode. `greenprompt setup` detects a sensible value from the CPU brand string and
records which source is available as `CPU_POWER_SOURCE`.

RAPL sysfs is root-readable only on some distributions (a mitigation for the
PLATYPUS side-channel). If `energy_uj` cannot be opened, detection silently falls
through to the next mode — check the startup line in `greenprompt log_api` to see
which mode was actually selected.

### GPU sampling

A single long-running `nvidia-smi dmon -s p -d 1` process (`NvidiaDmonReader`)
streams power readings, rather than forking a subprocess every second. If `dmon`
fails to start, the monitor falls back to a per-call
`nvidia-smi --query-gpu=power.draw` subprocess. Hardware that does not report
power draw — unified-memory parts such as GB10 return `[N/A]` — yields `0.0 W`
rather than an error.

### Short prompts

If a prompt completes in less than one sample interval, its window can contain
zero samples. `measure_power_linux()` then borrows the nearest sample on either
side (within `2 × sample_interval`) and sets `"extrapolated": true` on the
result so the value is not mistaken for a direct measurement.

### GPU utilization

`has_gpu()` and `get_gpu_usage()` work on Linux via `nvidia-smi`:

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

These utilization figures are returned in the `/api/prompt` response as
`gpu_usage`, but there is no column for them in `prompt_usage`, so they are not
persisted. The energy figure comes from the sampler's power readings, not from
utilization.

---

## Windows (partial support)

Scoring, logging, token counting, the REST API, and the dashboard all work.
Power measurement is not implemented. `sysUsage.measure_power_windows()` attempts
a WMI thermal-zone read and returns a *string* rather than the metrics dict every
other platform returns, so `core.run_prompt()` treats the result as missing and
records `energy_wh`, `cpu_power_w`, and `gpu_power_w` as `0`. It also imports
`wmi`, which is not a declared dependency. Windows is now the only platform
without live power sampling.

`has_gpu()` and `get_gpu_usage()` work via `nvidia-smi` if CUDA drivers are installed.

Note: `lsof` calls in `cli.py` (used by `run` and `stop` commands to manage the API server process) are Unix-only. On Windows, `greenprompt run` and `greenprompt stop` will fail. The API server can still be started manually:

```cmd
python -m greenprompt.api --port=5000
```

---

## Linux implementation reference

Linux power measurement is implemented; this section records where each piece
lives for anyone extending it.

| Concern | Location |
|---|---|
| Sampler thread, mode detection, ring buffer | `greenprompt/samplerLinux.py` |
| RAPL counter read and overflow handling | `samplerLinux.LinuxPowerMonitor._sample_cpu_rapl()` |
| ARM cluster detection and TDP table | `samplerLinux._detect_cpu_clusters()`, `_CLUSTER_TDP` |
| `nvidia-smi dmon` reader and fallback | `samplerLinux.NvidiaDmonReader` |
| Window averaging, baseline, extrapolation | `sysUsage.measure_power_linux()` |
| Monitor construction at server start | `api.py` `__main__` block, dispatching on `constants.OS` |
| Regression tests (76 cases) | `tests/test_linux_stress.py` |

The test suite simulates each CPU architecture and its edge cases — counter
overflow, missing `nvidia-smi`, empty sample windows, concurrent access — so
changes to the sampler can be validated without the corresponding hardware.

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

If you're implementing Windows power measurement, `samplerLinux.py` is the closest
template — it already handles multiple detection tiers, a graceful fallback chain,
and thread-safe sampling. The interface to match is `measure_power_mac()` in
`sysUsage.py`:

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
