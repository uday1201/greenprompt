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
| `cli.py` | Argument parsing, user-facing output, API server lifecycle | Business logic, DB, power |
| `api.py` | HTTP routing, PowerMonitor lifecycle, request validation | DB queries (delegates to dbconn) |
| `core.py` | Prompt execution, energy calculation, score integration | HTTP routing, DB writes (delegates) |
| `dbconn.py` | SQLite schema, CRUD | All other concerns |
| `samplerMac.py` | macOS power sampling thread | Parsing (delegates to sysUsage) |
| `sysUsage.py` | OS detection, power measurement dispatch, parsing | Threading, storage |
| `scoreBasic.py` | NLTK-based prompt scoring | Any I/O or network calls |
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
        └─ save_prompt_usage(result)                   [dbconn.py]
```

### Power Sampling (macOS)

```
api.py startup (OS == Darwin)
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

### Hardware measurement (macOS)

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
energy_wh ≈ (token_count / 1000) × MODEL_ENERGY_MAP[model]
```

| Model | Wh per 1000 tokens |
|---|---|
| gpt-3.5 | 0.020 |
| gpt-4 | 0.060 |
| gpt-4o | 0.040 |
| llama2 | 0.010 |
| mistral | 0.008 |
| phi | 0.005 |
| (unknown) | 0.010 (default) |

These are static approximations for cross-platform use when hardware sampling is unavailable.

---

## Process Architecture

```
User terminal
    │
    │ greenprompt run
    ▼
cli.py (foreground)
    │ subprocess.Popen(greenprompt.api --port=5000)
    ▼
api.py (background, daemon)
    ├─ PowerMonitor thread (daemon, macOS only)
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
