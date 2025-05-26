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
├── proxy.py                # Optional HTTP proxy for Ollama API
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

4. **Start Sampling Daemon** (optionally in a TMUX or background)  
   ```bash
   python samplerMac.py
   ```

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
```

### Web Dashboard

1. Open a new terminal window or tab.

2. Navigate to the frontend directory:

   ```bash
   cd ollama-ui
   ```
3. Install dependencies (if you haven't already):
   ```bash
   npm install
   ```
4. Run the frontend development server:
   ```bash
   npm run dev
   ```
5. The frontend UI will be accessible at:
   http://127.0.0.1:5000:5713/chat

### API Endpoints
- `POST /api/generate` → Run a prompt  
- `GET /api/usage/all` → All records  
- `GET /api/usage/model/<model>` → Records for a model  
- `GET /api/usage/timeframe?start=ISO&end=ISO` → Time‑filtered records  

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