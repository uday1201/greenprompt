# GreenPrompt 🌱

## Overview
GreenPrompt is a local-first tool that tracks and visualizes the real-world energy consumption of AI prompts, locally. It intercepts or wraps LLM calls (via Ollama’s local API), samples CPU/GPU power, logs prompt metadata and energy usage, and provides both CLI and Web UI interfaces for analysis.

> **macOS only** (uses `powermetrics` for power sampling)

## Features
- **Baseline & Prompt Sampling**: Continuously samples system power in a 10‑minute sliding window; computes a 1‑minute baseline before each prompt and measures power during execution.
- **Token & Model Tracking**: Captures prompt and completion token counts, model used.
- **Energy Estimation**: Calculates energy in Wh based on sampled power data and execution duration.
- **Persistent Logging**: Stores every prompt run in a SQLite database (`greenprompt_usage.db`).
- **CLI Interface**: Run prompts, view immediate stats.
- **Web API & Dashboard**: Flask-based endpoints for retrieving usage and a simple HTML dashboard.
- **Proxy Server**: (Optional) Intercept existing Ollama API traffic to log usage without code changes.

## Architecture & Flow
1. **Power Sampling**  
   - `samplerMac.py` defines `PowerMonitor`, a background thread that samples combined CPU/GPU power every second and retains a 10‑minute history.
2. **Prompt Execution**  
   - `core.py`’s `run_prompt` function:
     - Retrieves a 1‑minute baseline average from `PowerMonitor`.
     - Sends the user prompt to Ollama at `127.0.0.1:5000:11434` (or via proxy).
     - Records start and end timestamps.
     - Queries `PowerMonitor` for samples during execution.
     - Calculates average power and energy.
3. **Data Persistence**  
   - `dbconn.py` provides `init_db()` and `save_prompt_usage()`, storing each run’s metadata in SQLite.
4. **Interfaces**  
   - **CLI** (`cli.py`): `greenprompt <prompt>` to run and log.
   - **Web App** (`web.py`/`api.py`):  
     - `POST /api/generate` to run prompts.  
     - `GET /api/usage/all` / `model/<model>` / `timeframe` to retrieve logs.
   - **Setup Script** (`setup.py`): Initializes the DB and rebinds Ollama port.

## File Structure
```
greenprompt/
├── cli.py                  # CLI entry point
├── core.py                 # Prompt runner & energy estimator
├── dbconn.py               # SQLite connection, init, and save/query functions
├── samplerMac.py           # macOS PowerMonitor for sampling power
├── sysUsage.py             # OS-agnostic wrappers & estimators
├── setup.py                # Tool setup: DB init, Ollama rebind
├── analytics.py            # Plotly graphs for the dashboard
├── web.py                  # Flask web server, HTML dashboard
├── templates/
│   └── index.html          # Web UI template
├── static/                 # Optional assets (CSS)
└── constants.py            # User-editable settings
```

## Installation & Setup

### PyPI Installation
You can install GreenPrompt directly from PyPI:

```bash
pip install greenprompt
```

Or, can build it using Poetry
```bash
# If you don't have Poetry, install it first:
pip install poetry

# Install dependencies and build the package
poetry install

# (Optional) To build a distributable wheel and sdist:
poetry build
```
And install it

```bash
# If you want to install the built package locally (after poetry build):
pip install dist/*.whl
```

Or, if you just want to install in your current environment for development:

```bash
poetry install
```

This will install both the `greenprompt` and `gp` CLI commands.

### Development Installation
2. **Clone & Install**  
   ```bash
   git clone <repo-url>
   cd greenprompt
   poetry install
   ```

3. **Initialize**  
   ```bash
   python setup.py
   ```
   - Creates `greenprompt_usage.db`  
   - Rebinds Ollama to port 11435 (via setup instructions)


## Usage

### CLI Usage
Once installed, use the following commands:

```bash
# Setup Ollama port, initialize database, and generate constants
greenprompt setup
# or using alias
gp setup

# Start the web API server and dashboard
greenprompt run --port 5000
gp run --port 5000

# Send a prompt and display stats
greenprompt prompt "Hello, world!" --model llama2
gp prompt "Hello, world!" --model llama2

# Monitor the last 10 prompt usage entries
greenprompt monitor --count 10
gp monitor --count 10

# Launch Dashboard
greenprompt dashboard
gp dashboard
```

## API Endpoints

- **POST /api/prompt**  
  Send a JSON body with `prompt` and optional `model`.  
  Returns the generated response and all energy/token metrics.

- **GET /api/usage/all**  
  Retrieve all prompt usage records as a JSON array.

- **GET /api/usage/model/<model>**  
  Retrieve prompt usage records filtered by model.

- **GET /api/usage/timeframe?start=ISO&end=ISO**  
  Retrieve prompt usage records between `start` and `end` ISO timestamps.

- **GET /dashboard**  
  Serve the HTML dashboard with embedded Plotly analytics.

- **Proxy all Ollama API calls** via **ANY /ollama/api/<path>**  
  Forward requests to the local Ollama server (default port 11434), preserving method, headers, query params, and body.


## Limitations
- **macOS only** (relies on `powermetrics`)  
- Per-process power usage is estimated proportionally from system metrics  
- CLI proxy requires redirecting Ollama to use `127.0.0.1:5000:11434`

## Future Work
- Linux & Windows support (via Intel Power Gadget, `rapl`, `nvidia-smi`)  
- VS Code & browser extensions  
- Carbon offset integrations  
- Team dashboards & enterprise reporting

## License
[MIT License](LICENSE)