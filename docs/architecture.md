# GreenPrompt — Architecture

## Overview

GreenPrompt is structured as two cooperating processes:

1. **CLI process** — the short-lived user-facing process that parses commands and calls the API.
2. **API server process** — a long-running Flask server that owns the `PowerMonitor` thread and handles all prompt execution and data storage.

This separation lets `PowerMonitor` accumulate a warm 10-minute power history before any prompt is sent, ensuring accurate baseline measurements.

---

## Module Responsibilities

| Module | Owns | Does NOT own |
|---|---|---|
| `cli.py` | Argument parsing, user-facing output, API server lifecycle (including verifying process ownership before signalling) | Business logic, DB, power |
| `api.py` | HTTP routing, power monitor lifecycle via `create_app()`, request validation | DB queries (delegates to dbconn) |
| `core.py` | Prompt execution, energy calculation, score integration | HTTP routing, DB writes (delegates) |
| `dbconn.py` | SQLite schema, CRUD | All other concerns |
| `samplerMac.py` | macOS power sampling thread | Parsing (delegates to sysUsage) |
| `samplerLinux.py` | Linux power sampling thread — RAPL / ARM / TDP mode detection, `nvidia-smi dmon` | Parsing (delegates to sysUsage) |
| `sysUsage.py` | OS detection, power measurement dispatch, parsing | Threading, storage |
| `scoreBasic.py` | NLTK-based prompt scoring, on-demand corpora fetch | LLM calls; any I/O beyond fetching missing corpora |
| `analytics.py` | Plotly figure construction | Data loading (delegates to dbconn) |
| `setup.py` | First-run initialization | Runtime operations |
| `constants.py` | Shared configuration values | Logic |

---

## Data Flow

### Prompt Execution

```
greenprompt prompt "text" --model llama2
        │
        │  HTTP POST /api/prompt {"prompt": "text", "model": "llama2"}
        ▼
api.py: handle_prompt()
        │
        │  run_prompt(prompt, model, monitor=<PowerMonitor>)
        ▼
core.py: run_prompt()
        ├─ has_gpu() + get_gpu_usage()               [sysUsage.py]
        ├─ time.time() → start_time
        ├─ POST http://127.0.0.1:11434/api/generate   [Ollama HTTP]
        ├─ time.time() → end_time
        ├─ measure_power_for_pid(pid, start, end, monitor)
        │       └─ measure_power_mac(start, end, monitor)  [sysUsage.py]
        │               ├─ baseline: samples in [start-60, start]
        │               └─ prompt:   samples in [start, end]
        ├─ score_prompt(prompt)                        [scoreBasic.py]
        │       └─ called once; both prompt_score and prompt_score_details
        │          are read from the single result
        └─ save_prompt_usage(result)                   [dbconn.py]
                └─ timestamp via utc_now_iso() — naive UTC ISO 8601, because
                   get_prompt_usage() compares timestamps as strings
```

### Power Sampling

The sampler is started by `create_app()`, which dispatches on `constants.OS`.
Both platforms present the same interface — a daemon thread appending
`(timestamp, sample_dict)` to a 600-entry deque — so `sysUsage` can share its
averaging logic between them.

#### macOS

```
create_app() → init_power_monitor()   (OS == Darwin)
        │
        ▼
PowerMonitor.__init__()          [samplerMac.py]
        │  samples = deque(maxlen=600)   # 10-minute ring buffer
        │  thread = Thread(target=_run, daemon=True)
        ▼
PowerMonitor.start()
        │
        ▼
_run() [background daemon thread — never blocks API]
        └─ loop every 1 second:
                sample_once()
                  └─ subprocess: sudo powermetrics --samplers cpu_power -n 1 -i 1000
                  └─ parse_powermetrics_output(raw_text, 1)   [sysUsage.py]
                  └─ append (timestamp, {cpu_w, gpu_w, combined_w}) to deque
```

#### Linux

```
create_app() → init_power_monitor()   (OS == Linux)
        │
        ▼
LinuxPowerMonitor.__init__()     [samplerLinux.py]
        │  CPU mode detected once, in priority order:
        │    rapl          → /sys/class/powercap/intel-rapl*/…/energy_uj delta
        │    arm_biglittle → per-cluster frequency-squared model
        │    linear_tdp    → cpu_percent × CPU_TDP_W
        │  GPU: one long-running `nvidia-smi dmon -s p -d 1` process
        ▼
LinuxPowerMonitor.start()
        └─ loop every 1 second, appending to the same deque shape
```

On any other platform `init_power_monitor()` logs a warning and returns None;
energy readings are then 0.

### Dashboard Rendering

```
GET /dashboard
        │
        ▼
api.py: dashboard()
        │
        ▼
analytics.load_usage_data()          → dbconn.get_prompt_usage() → SQLite
        │
        ├─ total_prompts_energy_usage(df)
        ├─ energy_usage_timeline(df)
        ├─ cpu_gpu_usage_per_prompt(df)
        ├─ estimated_vs_actual_power(df)
        ├─ baseline_vs_total_usage(df)
        └─ model_comparison(df)
        │
        ▼  [Plotly figures serialized to JSON via PlotlyJSONEncoder]
render_template("dashboard.html", **chart_jsons)
```

---

## SQLite Schema

Table: `prompt_usage`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `timestamp` | TEXT | UTC ISO 8601 |
| `prompt` | TEXT | User's input text |
| `prompt_score` | INTEGER | Total score (0–50) |
| `prompt_score_details` | TEXT | JSON blob of per-dimension scores |
| `response` | TEXT | Ollama completion text |
| `model` | TEXT | Model name (e.g., `llama2`) |
| `prompt_tokens` | INTEGER | Tokens in the prompt |
| `completion_tokens` | INTEGER | Tokens in the response |
| `total_tokens` | INTEGER | prompt + completion |
| `energy_estimate_prompt` | REAL | Token-based estimate for prompt only (Wh) |
| `energy_estimate_tokens` | REAL | Token-based estimate for full run (Wh) |
| `duration_sec` | REAL | Wall-clock seconds for Ollama call |
| `energy_wh` | REAL | Hardware-measured energy (Wh) |
| `baseline_power_w` | REAL | 1-min idle average before prompt (W) |
| `baseline_energy_wh` | REAL | Baseline energy for 60-second window (Wh) |
| `cpu_power_w` | REAL | Average CPU power during prompt (W) |
| `gpu_power_w` | REAL | Average GPU power during prompt (W) |
| `combined_power_w` | REAL | Average combined power during prompt (W) |
| `system_info` | TEXT | JSON blob from `get_system_info()` |

**Database location:** `<cwd>/greenprompt_usage.db` where `cwd` is the working directory when `greenprompt setup` was run.

---

## Energy Calculation

### Hardware measurement (macOS and Linux)

```
energy_wh = (avg_combined_power_w × duration_sec) / 3600
```

Where `avg_combined_power_w` is the mean of all `PowerMonitor` samples timestamped between `start_time` and `end_time`.

### Baseline

```
baseline_energy_wh = (baseline_avg_power_w × 60) / 3600
```

Where `baseline_avg_power_w` is the mean of samples in `[start_time - 60, start_time]`.

### Token-based estimate (all platforms)

```
energy_wh ≈ (token_count / 1000) × rate_for(model)
```

| Model family | Wh per 1000 tokens |
|---|---|
| gpt-3.5 | 0.020 |
| gpt-4 | 0.060 |
| gpt-4o | 0.040 |
| llama2 | 0.010 |
| llama3 | 0.012 |
| mistral | 0.008 |
| phi | 0.005 |
| (unmatched) | 0.010 (`DEFAULT_ENERGY_PER_1K_WH`) |

`rate_for()` normalises the name before looking it up — the Ollama tag and any
namespace are stripped and the rest lowercased, so `library/llama3.2:latest`
becomes `llama3.2`. An exact family match wins; otherwise the longest matching
prefix applies, so point releases inherit their family's rate and `gpt-4o` is
never shadowed by `gpt-4`.

This matters because the lookup used to be an exact match on the raw name,
which no tagged Ollama model could satisfy — every prompt silently used the
default rate, and the dashboard's "estimated vs actual" chart was therefore
comparing measurements against a constant.

These are static approximations for cross-platform use when hardware sampling is unavailable.

---

## Process Architecture

```
User terminal
    │
    │ greenprompt run
    ▼
cli.py (foreground)
    │ refuses to start if the port is held by a non-GreenPrompt process
    │ subprocess.Popen(greenprompt.api --port=5000)
    ▼
api.py (background, daemon)
    ├─ power sampler thread (daemon; PowerMonitor on macOS,
    │                        LinuxPowerMonitor on Linux)
    └─ Flask dev server on :5000

User terminal
    │
    │ greenprompt prompt "..."
    ▼
cli.py (foreground, short-lived)
    │ requests.post("http://127.0.0.1:5000/api/prompt")
    ▼
api.py (handles request, returns JSON)
    │ prints results to user terminal
```

### Why Two Processes?

`PowerMonitor` must be running continuously — ideally for at least 60 seconds before any prompt — to produce a meaningful 1-minute baseline. A short-lived CLI process cannot maintain this state. The API server is a long-lived process that bridges the gap.

---

## Ollama Proxy

The proxy endpoint (`/ollama/api/<path>`) forwards requests to Ollama at `http://localhost:11434/api/<path>`. This allows existing tools that talk to Ollama to be pointed at GreenPrompt instead, gaining automatic energy logging with zero code changes.

```
Existing tool → POST http://localhost:5000/ollama/api/generate
                        │
                        ▼ (proxied)
                 POST http://localhost:11434/api/generate
                        │
                        ▼ (response streamed back)
                Existing tool receives response
```

Note: the proxy currently logs passively via the forward — it does not inject GreenPrompt's energy measurement into proxy calls. Direct measurement is only applied to calls made through `POST /api/prompt`.

---

## Key Design Decisions

**SQLite over a remote database** — keeps the tool fully local and zero-config. No signup, no network dependency beyond Ollama itself.

**DB path via `os.getcwd()`** — intentional: users can maintain separate databases per project by running from different directories.

**Daemon thread for PowerMonitor** — ensures the thread exits automatically when the Flask process terminates, preventing zombie processes.

**Token-based estimate alongside hardware measurement** — hardware measurement requires macOS and a warm `PowerMonitor`. The token estimate is always available as a platform-agnostic fallback, and the side-by-side comparison in the dashboard helps calibrate the static coefficients over time.

**NLTK + regex scoring (no model call)** — prompt scoring is deliberately offline. Making an LLM call to score a prompt would itself consume energy, defeating the purpose. The NLTK approach is fast (<50ms), free, and reproducible.

**`create_app()` as the WSGI entry point** — the sampler must be started by
whatever serves the app. Importing `app` directly deliberately starts nothing,
so the test suite can exercise the routes without spawning `powermetrics`; the
cost is that an external WSGI server must use the factory
(`gunicorn 'greenprompt.api:create_app()'`) or it will record `energy_wh = 0`
with no error.

**Verify before signalling** — `run` and `stop` only send a signal to a process
whose command line identifies it as a GreenPrompt API server, and use SIGTERM
rather than SIGKILL so the sampler thread can shut down. Killing whatever held
the port was convenient but meant `--port 5432` would kill Postgres.

**Naive UTC timestamps** — `get_prompt_usage()` filters by comparing timestamps
as strings. An offset-aware value would sort inconsistently against rows
already written, so `utc_now_iso()` deliberately emits no `+00:00` suffix even
though the underlying call is timezone-aware.
