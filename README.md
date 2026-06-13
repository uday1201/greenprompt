# GreenPrompt 🌱

[![PyPI version](https://badge.fury.io/py/greenprompt.svg)](https://badge.fury.io/py/greenprompt)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

**Track and reduce the real-world energy cost of your AI prompts.**

GreenPrompt is a local-first tool that intercepts Ollama LLM calls, measures CPU/GPU power consumption in real time, logs every prompt run to a local SQLite database, and provides a CLI and interactive web dashboard for energy analysis and reporting.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [REST API](#rest-api)
- [Web Dashboard](#web-dashboard)
- [Prompt Scoring](#prompt-scoring)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Platform Support](#platform-support)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Real-time power sampling** — Continuously samples system CPU/GPU power every second via macOS `powermetrics`, retaining a 10-minute sliding window.
- **Per-prompt energy measurement** — Computes watt-hours consumed during each LLM call against a 1-minute idle baseline.
- **Token tracking** — Records prompt tokens, completion tokens, and total tokens per run from Ollama's response metadata.
- **Dual estimation** — Provides both hardware-measured power and token-based estimates for cross-validation and offline comparison.
- **Persistent logging** — Stores all run data in a local SQLite database (`greenprompt_usage.db`).
- **Prompt quality scoring** — Automatically scores every prompt on 18 dimensions using offline NLTK heuristics (RTCF structure, clarity, conciseness, energy awareness, and more).
- **Interactive dashboard** — Plotly-powered web dashboard with 6 chart types: energy timeline, CPU/GPU breakdown, model comparison, estimated vs. actual, and baseline overlay.
- **REST API** — Flask server exposing endpoints for running prompts and querying usage history.
- **Ollama proxy** — Optional transparent reverse proxy to intercept existing Ollama traffic without code changes.

---

## Requirements

- Python 3.9 or higher
- [Ollama](https://ollama.com) installed and running locally
- **macOS required for live power sampling** — uses `powermetrics` (Apple Silicon or Intel)
- Linux/Windows: scoring, logging, and token tracking work fully; power sampling returns zero (see [Platform Support](#platform-support))

---

## Installation

### From PyPI

```bash
pip install greenprompt
```

### With Poetry

```bash
poetry add greenprompt
```

### Development Installation

```bash
git clone https://github.com/uday1201/greenprompt.git
cd greenprompt
poetry install
```

---

## Quick Start

```bash
# 1. Initialize (first time only; requires sudo on macOS for powermetrics)
sudo greenprompt setup

# 2. Start the API server (required for prompt and dashboard commands)
sudo greenprompt run --port 5000

# 3. Send a prompt and see energy stats
greenprompt prompt "Explain quantum entanglement in one sentence." --model llama2

# 4. Open the analytics dashboard
greenprompt dashboard
```

---

## CLI Reference

GreenPrompt installs three equivalent command aliases: `greenprompt`, `gprompt`, and `greenp`.

### Command Overview

| Command | Description | Requires sudo (macOS) |
|---|---|---|
| `setup` | Initialize DB, download NLTK data, configure Ollama | Yes |
| `run` | Start the Flask API server in the background | Yes |
| `prompt` | Send a prompt; print response and energy stats | No |
| `monitor` | Display the last N prompt usage entries from DB | No |
| `score` | Score a prompt without sending it to a model | No |
| `dashboard` | Open the analytics dashboard in a browser | No |
| `stop` | Stop the running API server | Yes |
| `log_api` | Tail the API server log file | No |

---

### `greenprompt setup`

Initializes the environment: writes `constants.py` with system info, downloads NLTK resources, verifies Ollama, and creates the SQLite database.

```bash
sudo greenprompt setup [--ollama-port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--ollama-port` | `11434` | Port where Ollama is running |

> **Note:** Run `setup` from the directory where you want the database (`greenprompt_usage.db`) to live. All subsequent commands should be run from the same directory.

---

### `greenprompt run`

Starts the GreenPrompt Flask API server as a background process. On macOS, also initializes the `PowerMonitor` background thread.

```bash
sudo greenprompt run [--port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--port` | `5000` | Port for the Flask server |

---

### `greenprompt prompt`

Sends a prompt to Ollama via the running API server, prints the LLM response, and displays detailed energy and token statistics.

```bash
greenprompt prompt "Your prompt here" [--model MODEL]
```

| Flag | Default | Description |
|---|---|---|
| `--model` | `llama2` | Ollama model name to use |

**Example:**

```bash
greenprompt prompt "List three benefits of solar energy. Format: bullet points." --model llama2
```

**Output:**

```
Response:
• Solar energy is renewable and inexhaustible.
• It reduces electricity bills significantly over time.
• It produces no greenhouse gas emissions during operation.

--- Prompt usage data ---
Prompt tokens:       14
Completion tokens:   43
Total tokens:        57
Duration (sec):      3.21
Baseline power (W):  4.20
Baseline energy (Wh):0.000070
CPU power (W):       8.60
GPU power (W):       0.00
Combined power (W):  8.60
Energy used (Wh):    0.000767
```

---

### `greenprompt monitor`

Displays the last N prompt usage entries from the local SQLite database.

```bash
greenprompt monitor [--count N]
```

| Flag | Default | Description |
|---|---|---|
| `--count` | `10` | Number of recent entries to show |

---

### `greenprompt score`

Scores a prompt on 18 quality dimensions without sending it to any model. Entirely offline and instant.

```bash
greenprompt score "Your prompt here"
```

**Example:**

```bash
greenprompt score "You are a physics expert. Explain Newton's second law to a high school student. Format: bullet points."
```

**Output:**

```python
{
  'total_score': 34,
  'max_score': 50,
  'score_percent': 68.0,
  'details': {
    'RTCF Structure': 3,
    'Clarity & Specificity': 5,
    'Conciseness': 5,
    'Contextual Priming': 0,
    'Output Specification': 5,
    'Instructional Tone': 3,
    ...
  }
}
```

---

### `greenprompt dashboard`

Opens the Plotly analytics dashboard at `http://localhost:5000/dashboard` in the default browser. Requires the API server to be running.

```bash
greenprompt dashboard
```

---

### `greenprompt stop`

Stops the Flask API server by killing the process on the given port.

```bash
sudo greenprompt stop [--port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--port` | `5000` | Port where the API server is running |

---

### `greenprompt log_api`

Tails the API server log file at `/tmp/api.log`.

```bash
greenprompt log_api [--follow]
```

| Flag | Default | Description |
|---|---|---|
| `--follow` | `False` | Follow (tail -f) the log output |

---

## REST API

The GreenPrompt Flask server exposes the following endpoints after `greenprompt run`.

### `POST /api/prompt`

Run a prompt through Ollama, measure energy, and log the result.

**Request body:**
```json
{
  "prompt": "Explain photosynthesis.",
  "model": "llama2"
}
```

**Response:**
```json
{
  "prompt": "Explain photosynthesis.",
  "prompt_score": 36.0,
  "prompt_score_details": {
    "RTCF Structure": 1,
    "Clarity & Specificity": 5
  },
  "response": "Photosynthesis is the process by which plants...",
  "model": "llama2",
  "prompt_tokens": 5,
  "completion_tokens": 82,
  "total_tokens": 87,
  "total_energy (Wh)": 0.000512,
  "duration_sec": 4.13,
  "combined_power_w (W)": 0.446,
  "cpu_power_w (W)": 0.312,
  "gpu_power_w (W)": 0.134,
  "energy_estimate_tokens": 0.00087,
  "energy_estimate_prompt": 0.000005,
  "baseline_energy (Wh)": 0.000067,
  "baseline_power (W)": 4.03,
  "gpu_usage": "No GPU detected",
  "system_info": { "OS": "Darwin", "CPU": "Apple M2", ... }
}
```

### `GET /api/usage/all`

Retrieve all prompt usage records as a JSON array.

```bash
curl http://localhost:5000/api/usage/all
```

### `GET /api/usage/model/<model>`

Filter usage records by model name.

```bash
curl http://localhost:5000/api/usage/model/llama2
```

### `GET /api/usage/timeframe?start=ISO&end=ISO`

Filter usage records by ISO 8601 timestamp range.

```bash
curl "http://localhost:5000/api/usage/timeframe?start=2024-01-01T00:00:00&end=2024-12-31T23:59:59"
```

### `GET /dashboard`

Serves the interactive analytics dashboard.

### `ANY /ollama/api/<path>`

Transparent reverse proxy to the local Ollama server at `http://localhost:11434`. Preserves method, headers, query params, and body.

```bash
# Example: list models via proxy
curl http://localhost:5000/ollama/api/tags
```

---

## Web Dashboard

The dashboard at `http://localhost:5000/dashboard` provides six interactive Plotly charts:

| Chart | Description |
|---|---|
| Overview indicators | Total prompts, total energy (Wh), total CPU/GPU watts, total tokens, energy per token |
| Energy usage timeline | Line chart of energy (Wh) per prompt over time |
| CPU vs GPU power | Grouped bar chart of CPU and GPU watts per prompt |
| Estimated vs actual energy | Comparison of token-estimate, prompt-estimate, and hardware-measured energy |
| Baseline vs total energy | Overlay of idle baseline and total energy per prompt |
| Model comparison | Average energy per model (bar chart) |

---

## Prompt Scoring

Every prompt sent through GreenPrompt is automatically scored on 18 quality dimensions. Use `greenprompt score` to evaluate prompts standalone.

The scorer is entirely offline — no API call is made. It uses NLTK POS tagging and regex pattern matching.

### Scoring Dimensions (50 points total)

| Dimension | Max | Detection method |
|---|---|---|
| RTCF Structure | 4 | Role pattern + task verb + context marker + format spec (1 pt each) |
| Clarity & Specificity | 5 | Task verb present and prompt ≤ 400 chars = 5; task verb only = 3 |
| Conciseness | 5 | Starts at 5; minus 1 per filler phrase ("please", "could you", "just", etc.) |
| Contextual Priming | 3 | Matches `context:`, `background:`, `for <word>`, `audience:` |
| Output Specification | 5 | Matches `format:`, `output as`, or table/bullet/list/json/csv/markdown |
| Instructional Tone | 3 | Any imperative verb detected via POS tagging |
| Examples & Few-Shot | 2 | Matches `example:`, `Q:`, `A:`, `sample output`, `e.g.` |
| Task Decomposition | 2 | Matches `first...then` sequence or `step N` numbering |
| Positive/Negative Examples | 2 | Matches `do not`, `exclude`, `not include`, `except` |
| Iterative Refinement | 2 | Matches `revise`, `improve`, `refine`, `rewrite`, `repeat` |
| Creativity Control | 2 | Matches `creative`, `imaginative`, `unusual`, `inventive` |
| Tone & Style | 2 | Matches `tone:`, `style:`, `formal`, `casual`, `humorous`, `professional` |
| Error Prevention | 2 | Matches `do not guess`, `only answer if sure`, `if unsure, say so` |
| Evaluation & Validation | 2 | Matches `double-check`, `verify`, `validate`, `cross-check` |
| Sensitivity & Inclusivity | 2 | Matches `inclusive`, `avoid bias`, `unbiased`, `sensitive to` |
| Efficiency & Sustainability | 2 | Matches `concise`, `briefly`, `max N words`, `minimize tokens` |
| Energy Awareness | 2 | Matches `energy usage`, `carbon`, `footprint`, `sustainable`, `green` |
| Keyword Richness | 2 | ≥5 unique non-stopword tokens = 2; ≥2 = 1; else 0 |

See [docs/prompt-scoring.md](docs/prompt-scoring.md) for full details and optimization examples.

---

## Architecture

```
greenprompt/
├── cli.py           Entry point — argparse subcommands, starts API subprocess
├── api.py           Flask server — REST endpoints, Ollama proxy, PowerMonitor init
├── core.py          run_prompt() — orchestrates Ollama call, power measurement, scoring
├── dbconn.py        SQLite — init_db, save_prompt_usage, get_prompt_usage
├── samplerMac.py    PowerMonitor — daemon thread sampling powermetrics every second
├── sysUsage.py      OS-agnostic wrappers — system info, power measurement, GPU detection
├── scoreBasic.py    Prompt scorer — 18-dimension offline NLTK/regex analysis
├── analytics.py     Plotly chart functions for the dashboard
├── constants.py     Auto-generated by setup — OS info, OLLAMA_URL
├── setup.py         Setup routine — DB init, constants write, NLTK download
└── templates/
    └── dashboard.html   Dashboard HTML with embedded Plotly JS
```

### Request Flow

```
User
  │
  ▼
greenprompt prompt "..."
  │  (CLI sends HTTP POST)
  ▼
POST /api/prompt  (api.py Flask server)
  │
  ▼
core.py: run_prompt(prompt, model)
  ├─ PowerMonitor.samples  ──► baseline avg (1 min before prompt)
  ├─ POST http://127.0.0.1:11434/api/generate  (Ollama)
  ├─ PowerMonitor.samples  ──► during-prompt avg
  ├─ energy_wh = (avg_combined_w × duration_sec) / 3600
  ├─ scoreBasic.score_prompt(prompt)
  └─ dbconn.save_prompt_usage(result)
        │
        ▼
    greenprompt_usage.db (SQLite)
```

### Power Sampling (macOS)

`PowerMonitor` runs as a daemon thread, calling:
```bash
sudo powermetrics --samplers cpu_power -n 1 -i 1000
```
every second. It stores the last 600 readings (10 minutes) in a `collections.deque`. When `run_prompt()` completes, `measure_power_mac()` filters samples by `[start_time, end_time]` to compute average watts and energy, and separately averages the 60 seconds before the prompt as the idle baseline.

For detailed architecture documentation see [docs/architecture.md](docs/architecture.md).

---

## Configuration

`constants.py` is auto-generated by `greenprompt setup`. Edit it manually to customize behavior.

| Constant | Description |
|---|---|
| `OS` | Platform string: `Darwin`, `Linux`, or `Windows` |
| `OLLAMA_URL` | Ollama server URL (default: `http://127.0.0.1:11434`) |
| `OS_VERSION` | OS version string |
| `PLATFORM` | Full platform string from `platform.platform()` |
| `MACHINE` | CPU architecture (e.g., `arm64`, `x86_64`) |
| `PROCESSOR` | Processor name string |

**Database location:** Created in the working directory where `setup` was run:
```
<cwd>/greenprompt_usage.db
```
Always run GreenPrompt commands from the same directory to use the same database file.

See [docs/configuration.md](docs/configuration.md) for the full configuration reference.

---

## Platform Support

| Feature | macOS Apple Silicon | macOS Intel | Linux | Windows |
|---|---|---|---|---|
| Live CPU/GPU power sampling | ✅ powermetrics | ✅ powermetrics | 🔜 RAPL | 🔜 Intel Power Gadget |
| GPU detection | ✅ system_profiler | ✅ system_profiler | ✅ nvidia-smi | ✅ nvidia-smi |
| GPU utilization stats | — | — | ✅ nvidia-smi | ✅ nvidia-smi |
| Token counting | ✅ | ✅ | ✅ | ✅ |
| Prompt scoring | ✅ | ✅ | ✅ | ✅ |
| Database logging | ✅ | ✅ | ✅ | ✅ |
| REST API & dashboard | ✅ | ✅ | ✅ | ✅ |
| Token-based energy estimate | ✅ | ✅ | ✅ | ✅ |

Linux and Windows users will see `energy_wh = 0` for hardware power measurement; all other features are fully functional. See [docs/platform-support.md](docs/platform-support.md) for the implementation roadmap.

---

## Troubleshooting

**`❌ Could not connect to Ollama at http://127.0.0.1:11434`**

Ollama is not running. Start it:
```bash
ollama serve
```

**`Error connecting to API`**

The GreenPrompt API server is not running:
```bash
sudo greenprompt run --port 5000
```

**`Error: 'setup' requires sudo privileges`**

The `setup`, `run`, and `stop` commands require root on macOS because `powermetrics` needs elevated permissions. Run with `sudo`.

**Power readings are all zero on Linux/Windows**

Live power sampling is not yet implemented for non-macOS platforms. The `energy_estimate_tokens` field provides a token-count-based approximation.

**Dashboard shows no data**

The database is either empty or was created in a different working directory. Check:
```bash
greenprompt monitor --count 5
```
If empty, send some prompts first. If the DB file is in a different directory, `cd` there before running GreenPrompt.

**`Warning: Power usage data is incomplete or missing`**

The `PowerMonitor` has not yet collected enough samples. Wait 10–15 seconds after `greenprompt run` before sending the first prompt.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution workflow. Quick summary:

```bash
git checkout -b feature/your-feature
poetry install
# make changes
poetry run ruff check .
poetry run ruff fmt .
git commit -m "feat(scope): description"
git push origin feature/your-feature
# open pull request
```

### Roadmap

- Linux power measurement via RAPL / `nvidia-smi`
- Windows support via Intel Power Gadget / WMI
- VS Code extension
- Browser extension for cloud LLM APIs
- Carbon offset integration
- Team dashboards and enterprise reporting

---

## License

[MIT License](LICENSE) — © Uday & Anirudh
