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

- **Real-time power sampling** — Continuously samples system CPU/GPU power every second, retaining a 10-minute sliding window. macOS uses `powermetrics`; Linux uses Intel/AMD RAPL energy counters, an ARM big.LITTLE frequency model, or `nvidia-smi` for GPU power.
- **Per-prompt energy measurement** — Computes watt-hours consumed during each LLM call against a 1-minute idle baseline.
- **Token tracking** — Records prompt tokens, completion tokens, and total tokens per run from Ollama's response metadata.
- **Dual estimation** — Provides both hardware-measured power and token-based estimates for cross-validation and offline comparison.
- **Persistent logging** — Stores all run data in a local SQLite database (`greenprompt_usage.db`).
- **Prompt quality scoring** — Automatically scores every prompt on 18 dimensions using offline NLTK heuristics (RTCF structure, clarity, conciseness, energy awareness, and more). No LLM call, and no network access once the corpora are present.
- **Interactive dashboard** — Plotly-powered web dashboard with 6 chart types: energy timeline, CPU/GPU breakdown, model comparison, estimated vs. actual, and baseline overlay.
- **REST API** — Flask server exposing endpoints for running prompts and querying usage history.
- **Ollama proxy** — Optional transparent reverse proxy to intercept existing Ollama traffic without code changes.

---

## Requirements

- Python 3.9 or higher
- [Ollama](https://ollama.com) installed and running locally
- **Live power sampling on macOS and Linux** — `powermetrics` on macOS (Apple Silicon or Intel); RAPL, ARM big.LITTLE, or `nvidia-smi` on Linux
- Windows: scoring, logging, and token tracking work fully; power sampling returns zero (see [Platform Support](#platform-support))

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
# 1. Initialize (first time only; on macOS run it once with sudo so that
#    powermetrics can be used without a password prompt afterwards)
sudo greenprompt setup

# 2. Start the API server (required for prompt and dashboard commands)
greenprompt run --port 5000

# 3. Send a prompt and see energy stats
greenprompt prompt "Explain quantum entanglement in one sentence." --model llama3.2:latest

# 4. Open the analytics dashboard
greenprompt dashboard
```

---

## CLI Reference

GreenPrompt installs three equivalent command aliases: `greenprompt`, `gprompt`, and `greenp`.

### Command Overview

No GreenPrompt command needs to be run as root. The one exception is the
first `setup` on macOS: running it once with `sudo` installs a sudoers rule so
that `powermetrics` can be sampled without a password prompt from then on.
Without it, GreenPrompt still runs — energy readings are simply zero.

| Command | Description | Requires sudo |
|---|---|---|
| `setup` | Write config, download NLTK data, verify Ollama, create DB | Once, on macOS |
| `run` | Start the Flask API server in the background | No |
| `prompt` | Send a prompt; print response and energy stats | No |
| `monitor` | Display the last N prompt usage entries from DB | No |
| `score` | Score a prompt without sending it to a model | No |
| `dashboard` | Open the analytics dashboard in a browser | No |
| `stop` | Stop the running API server | No |
| `migrate` | Merge databases left by older versions into the one in use | No |
| `log_api` | Tail the API server log file | No |

---

### `greenprompt setup`

Initializes the environment: detects CPU power capabilities and writes them to the user config file (`~/.greenprompt/config.json` by default), downloads NLTK resources, verifies Ollama, and creates the SQLite database.

On macOS it also installs `/etc/sudoers.d/greenprompt`, which allows `powermetrics` to be sampled without a password. That step is the only reason to use `sudo` here, and it is skipped with an explanatory message if you run without it.

```bash
sudo greenprompt setup [--ollama-port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--ollama-port` | `11434` | Port where Ollama is running |

> **Note:** The database lives at `~/.greenprompt/greenprompt_usage.db` regardless of where you run `setup` from. If you already have a `greenprompt_usage.db` in the directory you run from, that one is used instead, so upgrading never strands existing data. Override with `$GREENPROMPT_DB`.

---

### `greenprompt run`

Starts the GreenPrompt Flask API server as a background process, along with the power sampler for the current platform: `PowerMonitor` on macOS, `LinuxPowerMonitor` on Linux. Neither requires root.

```bash
greenprompt run [--port PORT]
```

> **Note:** Wait 10–15 seconds after starting before sending the first prompt, so the sampler has collected enough readings to average over.

If a GreenPrompt server is already running on the port, it is stopped and
replaced. If the port is held by anything *else*, `run` reports it and refuses
to start rather than killing it — pick another port with `--port`.

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
| `--model` | `llama3.2:latest` | Ollama model name to use |

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

Stops the GreenPrompt API server listening on the given port.

Only processes identified as GreenPrompt API servers are signalled — anything
else listening on that port is reported and left alone. The signal is `SIGTERM`,
so the power sampler shuts down cleanly.

```bash
greenprompt stop [--port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--port` | `5000` | Port where the API server is running |

---

### `greenprompt migrate`

Folds databases left behind by older versions into the one currently in use.
Versions before 0.3.0 resolved the database path from the working directory, so
it is easy to have several.

```bash
greenprompt migrate --dry-run          # report what would move
greenprompt migrate                    # merge, with a confirmation prompt
greenprompt migrate --from path/to/greenprompt_usage.db   # explicit source
```

| Flag | Default | Description |
|---|---|---|
| `--from` | *(discover)* | Database to merge; repeatable. Skips discovery when given. |
| `--dry-run` | `False` | Report what would be merged without writing |
| `-y`, `--yes` | `False` | Do not prompt for confirmation |

With no `--from`, it searches your home directory and the current directory to
a bounded depth, skipping hidden and dependency directories.

**Safe to run repeatedly.** Rows are matched on `(timestamp, prompt, model)` —
timestamps carry microseconds — so a second run merges nothing. Source
databases are opened read-only and are never modified or deleted; delete them
yourself once you are satisfied.

Schemas are intersected rather than assumed to match. The table has gained
columns over releases, so an older database genuinely has fewer; only the
columns both sides share are copied and the rest are left empty.

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

All endpoints are served by `greenprompt run` on `http://localhost:<port>`.

> **Serving behind an external WSGI server:** use the application factory, not
> the bare `app` object. `greenprompt.api:app` deliberately starts no power
> sampler, so serving it directly records `energy_wh = 0` for every prompt with
> no error at all:
>
> ```bash
> gunicorn 'greenprompt.api:create_app()'
> ```

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
| Instructional Tone | 3 | Any verb, via POS tagging or as a sentence-initial instruction verb |
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
| Energy Awareness | 2 | Matches `energy usage`, `carbon`, `footprint`, `sustainable`, `green` (literal — `energy consumption` does not match) |
| Keyword Richness | 2 | ≥5 unique non-stopword tokens = 2; ≥2 = 1; else 0 |

See [docs/prompt-scoring.md](docs/prompt-scoring.md) for full details and optimization examples.

---

## Architecture

```
greenprompt/
├── cli.py           Entry point — argparse subcommands, starts API subprocess
├── api.py           Flask server — REST endpoints, Ollama proxy, create_app() factory
├── core.py          run_prompt() — orchestrates Ollama call, power measurement, scoring
├── dbconn.py        SQLite — init_db, save_prompt_usage, get_prompt_usage
├── samplerMac.py    PowerMonitor — daemon thread sampling powermetrics every second
├── samplerLinux.py  LinuxPowerMonitor — RAPL / ARM / TDP CPU sampling + nvidia-smi GPU
├── sysUsage.py      OS-agnostic wrappers — system info, power measurement, GPU detection
├── scoreBasic.py    Prompt scorer — 18-dimension offline NLTK/regex analysis
├── analytics.py     Plotly chart functions for the dashboard
├── constants.py     Tracked source — defaults, live platform values, user-config overlay
├── setup.py         Setup routine — writes ~/.greenprompt/config.json, DB init, NLTK download
└── templates/
    └── dashboard.html   Dashboard HTML with embedded Plotly JS

scripts/
└── release.py       Release automation — version bump, CHANGELOG, tag, push

tests/               207 tests, standard-library unittest
├── test_core.py            Energy estimation, model matching, run_prompt
├── test_dbconn.py          Timestamp format, persistence, filters
├── test_cli.py             Server lifecycle and process-ownership safety
├── test_api_lifecycle.py   Power monitor startup and the WSGI factory
├── test_score_basic.py     Scoring contract, behaviour, lazy corpora
├── test_linux_stress.py    Linux sampler — arch simulation and edge cases
└── test_release.py         Release script version and CHANGELOG logic
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

### Power Sampling

On macOS and Linux, a daemon thread samples once a second into a `collections.deque` holding the last 600 readings (10 minutes). When `run_prompt()` completes, the matching `measure_power_*()` function filters samples by `[start_time, end_time]` to compute average watts and energy, and separately averages the 60 seconds before the prompt as the idle baseline.

**macOS** — `PowerMonitor` (`samplerMac.py`) calls:
```bash
sudo powermetrics --samplers cpu_power -n 1 -i 1000
```

**Linux** — `LinuxPowerMonitor` (`samplerLinux.py`) picks the best available CPU source at startup:

| Mode | Condition | Method |
|---|---|---|
| `rapl` | `/sys/class/powercap/intel-rapl*/energy_uj` present | Intel/AMD energy counter delta — measured, not estimated |
| `arm_biglittle` | `psutil.cpu_freq(percpu=True)` reports more than one distinct max frequency | Per-cluster frequency-squared model over `scaling_cur_freq` (power ∝ V²f) |
| `linear_tdp` | Neither of the above | `cpu_percent / 100 × CPU_TDP_W` |

GPU power comes from a single long-running `nvidia-smi dmon -s p -d 1` process, with a per-call subprocess fallback. If the prompt is shorter than one sample interval, `measure_power_linux()` interpolates from neighbouring samples and flags the result with `"extrapolated": true`.

For detailed architecture documentation see [docs/architecture.md](docs/architecture.md).

---

## Configuration

Settings live in a JSON file written by `greenprompt setup`, by default `~/.greenprompt/config.json` (override with `$GREENPROMPT_CONFIG` or `$GREENPROMPT_HOME`).

| Key | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server URL |
| `CPU_TDP_W` | `40.0` | CPU TDP in watts; used only by the Linux `linear_tdp` fallback |
| `CPU_POWER_SOURCE` | `estimated` | Informational; `rapl` when direct energy counters were found |
| `DB_PATH` | *(unset)* | Explicit database location; `$GREENPROMPT_DB` overrides it |

```bash
# where is my config?
python -c "from greenprompt import constants; print(constants.config_path())"
```

Platform values (`OS`, `MACHINE`, `PLATFORM`, ...) are derived live on every import by `greenprompt/constants.py` and are never stored, so they always match the machine actually running.

**Database location:** Created in the working directory where `setup` was run:
```
<cwd>/greenprompt_usage.db
```
The database is at `~/.greenprompt/greenprompt_usage.db` by default, so every
command sees the same data no matter where it is run from. Resolution order:

| Order | Source |
|---|---|
| 1 | `$GREENPROMPT_DB` |
| 2 | `DB_PATH` in the config file |
| 3 | `./greenprompt_usage.db`, if it already exists |
| 4 | `$GREENPROMPT_HOME/greenprompt_usage.db` |
| 5 | `~/.greenprompt/greenprompt_usage.db` |

Step 3 keeps pre-0.3.0 per-directory databases working untouched. For
deliberate per-project separation, set `$GREENPROMPT_DB`.

See [docs/configuration.md](docs/configuration.md) for the full configuration reference.

---

## Platform Support

| Feature | macOS Apple Silicon | macOS Intel | Linux | Windows |
|---|---|---|---|---|
| Live CPU power sampling | ✅ powermetrics | ✅ powermetrics | ✅ RAPL / ARM / TDP | 🔜 Intel Power Gadget |
| Live GPU power sampling | ✅ powermetrics | ✅ powermetrics | ✅ nvidia-smi | 🔜 nvidia-smi |
| GPU detection | ✅ system_profiler | ✅ system_profiler | ✅ nvidia-smi | ✅ nvidia-smi |
| GPU utilization stats | — | — | ✅ nvidia-smi | ✅ nvidia-smi |
| Token counting | ✅ | ✅ | ✅ | ✅ |
| Prompt scoring | ✅ | ✅ | ✅ | ✅ |
| Database logging | ✅ | ✅ | ✅ | ✅ |
| REST API & dashboard | ✅ | ✅ | ✅ | ✅ |
| Token-based energy estimate | ✅ | ✅ | ✅ | ✅ |
| `run` / `stop` server lifecycle | ✅ | ✅ | ✅ | ❌ needs `lsof` |

Windows users will see `energy_wh = 0` for hardware power measurement; all other features are fully functional. See [docs/platform-support.md](docs/platform-support.md) for the implementation roadmap.

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
greenprompt run --port 5000
```

**Power readings are all zero on macOS**

The passwordless `powermetrics` rule is not installed, so the sampler cannot read power. Run setup once with sudo:
```bash
sudo greenprompt setup
```

**Power readings are all zero on Linux**

Check which mode the sampler chose — `greenprompt log_api` reports it at startup. In `linear_tdp` mode readings are estimates derived from `CPU_TDP_W`, not measurements. RAPL requires read access to `/sys/class/powercap/intel-rapl*/energy_uj`, which some distributions restrict to root. GPU power requires `nvidia-smi` on `PATH`.

**Power readings are all zero on Windows**

Live power sampling is not yet implemented on Windows. The `energy_estimate_tokens` field provides a token-count-based approximation.

**Power readings are all zero behind gunicorn / uwsgi**

The app was served as `greenprompt.api:app`, which starts no power sampler. Use
the factory instead:
```bash
gunicorn 'greenprompt.api:create_app()'
```

**`Port 5000 is in use by another process (PID …). Not starting.`**

Something that is not a GreenPrompt server is listening on that port —
frequently AirPlay Receiver on macOS, which claims 5000. GreenPrompt will not
kill an unrecognised process, so either free the port or choose another one:
```bash
greenprompt run --port 5050
greenprompt prompt "..." --port 5050
greenprompt dashboard --port 5050
```

**`Refusing to kill PID … : it is not a GreenPrompt API server.`**

`greenprompt stop` found something else on that port. This is a safeguard, not
a failure — check what it is with `lsof -nP -iTCP:<port> -sTCP:LISTEN` before
deciding what to do.

**My prompt scores lower than I expect**

Check the per-dimension breakdown — `greenprompt score "..."` returns every
dimension, so the zeros show exactly what is missing. The usual gaps are no
stated role (`You are a physics tutor…`), no output format (`Format: bullet
points`), and no context. See
[docs/prompt-scoring.md](docs/prompt-scoring.md#optimizing-for-score).

> Scores changed in 0.3.0: prompts opening with a bare imperative (`Explain
> inertia.`) previously lost 4 of 50 points to a tagger misfire and now score
> correctly. Rows already in your database keep their original scores, so
> comparisons that straddle the upgrade are not like-for-like.

**`Cannot write to …greenprompt_usage.db. It is owned by root.`**

A database created by an old `sudo greenprompt run` stays owned by root, and
every later command then fails to save — silently, before 0.5.0. Take ownership:
```bash
sudo chown $(whoami) ~/greenprompt_usage.db
```
Versions from 0.5.0 hand ownership back to the invoking user, so this only
affects files created earlier.

**Dashboard shows no data**

Check whether the database actually has rows:
```bash
greenprompt monitor --count 5
```
If empty, send some prompts first.

Before 0.3.0 the database path came from the working directory, so running
`prompt` and `dashboard` from different places silently used different files.
That is fixed, but data written by an older version may still be scattered.
Find it:
```bash
find ~ -name greenprompt_usage.db 2>/dev/null
```
Then merge them into the one in use:
```bash
greenprompt migrate --dry-run   # see what would move
greenprompt migrate
```
Or point at a single one with `GREENPROMPT_DB=/path/to/greenprompt_usage.db greenprompt dashboard`.

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
poetry run ruff format .
# run the test suite from a scratch directory (the DB path is CWD-relative)
mkdir -p /tmp/gp-test && cd /tmp/gp-test
python -m unittest discover -s "$OLDPWD/tests" -t "$OLDPWD"
cd "$OLDPWD"
git commit -m "feat(scope): description"
git push origin feature/your-feature
# open a pull request — CI runs on the PR, not on a bare branch push
```

Releases are cut with `python scripts/release.py <major|minor|patch>`, which
handles the version bump, CHANGELOG promotion, tag, and push. See the
[Releasing section of CONTRIBUTING.md](CONTRIBUTING.md#releasing).

### Roadmap

- Windows support via Intel Power Gadget / WMI, and a `lsof`-free server lifecycle
- Test coverage for the scoring, database, and analytics modules
- VS Code extension
- Browser extension for cloud LLM APIs
- Carbon offset integration
- Team dashboards and enterprise reporting

---

## License

[MIT License](LICENSE) — © Uday & Anirudh
