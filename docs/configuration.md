# GreenPrompt Configuration Reference

## User config file

Tunable settings live in a JSON config file written by `greenprompt setup`. It is stored **outside** the package, so setup works from any directory and your settings survive reinstalls and upgrades.

The path is resolved in this order:

1. `$GREENPROMPT_CONFIG` — explicit path to a JSON file
2. `$GREENPROMPT_HOME/config.json`
3. `~/.greenprompt/config.json` — default

```bash
python -c "from greenprompt import constants; print(constants.config_path())"
```

### Configurable values

| Key | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `"http://127.0.0.1:11434"` | Ollama server base URL |
| `CPU_TDP_W` | `40.0` | CPU TDP in watts. Used **only** by `LinuxPowerMonitor`'s `linear_tdp` fallback; ignored when RAPL or ARM big.LITTLE sampling is active |
| `CPU_POWER_SOURCE` | `"estimated"` | Informational. `"rapl"` when direct Intel/AMD energy counters were detected |

```json
{
  "OLLAMA_URL": "http://192.168.1.100:11434",
  "CPU_TDP_W": 23.0,
  "CPU_POWER_SOURCE": "estimated"
}
```

Re-running `greenprompt setup` merges onto the existing file, so a hand-edited `OLLAMA_URL` is preserved while hardware values are refreshed.

`GREENPROMPT_OLLAMA_URL` overrides `OLLAMA_URL` for a single run without touching the file.

## `constants.py`

`greenprompt/constants.py` is a normal tracked source file — **not** generated, and safe to commit. It supplies the defaults above, overlays the user config, and derives platform values live on every import:

| Constant | Source |
|---|---|
| `OS` | `platform.system()` — `"Darwin"`, `"Linux"`, `"Windows"` |
| `OS_VERSION` | `platform.version()` |
| `PLATFORM` | `platform.platform()` |
| `MACHINE` | `platform.machine()` |
| `PROCESSOR` | `platform.processor()` |

Deriving these live is deliberate: `OS` drives power-measurement dispatch in `sysUsage.py` and monitor selection in `api.py`, so a stale value silently disables power sampling. They are never persisted to the config file.

For richer hardware detail (CPU brand, core counts, RAM, disk, hostname), call `sysUsage.get_system_info()` — that is what gets recorded per prompt in the `system_info` database column.

> **Migrating from ≤0.1.1:** older versions generated a `constants.py` into the current working directory, where nothing ever imported it. If you have a stray `./constants.py`, delete it and run `greenprompt setup` once.

---

## Database

### Location

```
<cwd>/greenprompt_usage.db
```

Where `<cwd>` is the working directory when `greenprompt setup` was run. The path is computed at import time in `dbconn.py`:

```python
DB_PATH = os.path.join(os.getcwd(), "greenprompt_usage.db")
```

> **Important:** Run all GreenPrompt commands (`run`, `prompt`, `monitor`, `dashboard`) from the **same directory** as setup to use the same database. If you run from a different directory, a new empty database will be created there.

### Multiple databases

You can maintain separate databases per project by running `greenprompt setup` from different directories:

```bash
# Project A
cd ~/projects/project-a
sudo greenprompt setup
sudo greenprompt run

# Project B
cd ~/projects/project-b
sudo greenprompt setup
sudo greenprompt run --port 5001  # different port to avoid conflict
```

### Schema

See [architecture.md](architecture.md#sqlite-schema) for the full `prompt_usage` table schema.

### Inspecting the database directly

```bash
sqlite3 greenprompt_usage.db

# Show all records
SELECT id, timestamp, model, total_tokens, energy_wh, prompt_score
FROM prompt_usage
ORDER BY timestamp DESC
LIMIT 10;

# Total energy by model
SELECT model, COUNT(*) as runs, SUM(energy_wh) as total_wh, AVG(energy_wh) as avg_wh
FROM prompt_usage
GROUP BY model;

# Exit
.quit
```

---

## API Server

### Port

Default: `5000`. Override with `--port`:

```bash
sudo greenprompt run --port 8080
```

### Log file

API server logs are written to `/tmp/api.log`. Tail with:

```bash
greenprompt log_api --follow
# or directly:
tail -f /tmp/api.log
```

The log file is truncated (cleared) each time the API server starts.

### CORS

CORS is enabled for all origins by default (`flask-cors`). This cannot currently be configured without editing `api.py`.

---

## PowerMonitor (macOS)

The `PowerMonitor` class in `samplerMac.py` has two configurable parameters set at instantiation in `api.py`:

| Parameter | Default | Description |
|---|---|---|
| `sample_interval` | `1` second | How often to call `powermetrics` |
| `window_size` | `600` samples | Ring buffer size (600 × 1s = 10 minutes) |

To change these, edit the `PowerMonitor()` instantiation in `api.py`:

```python
# api.py — increase to 20-minute window, sample every 2 seconds
monitor = PowerMonitor(sample_interval=2, window_size=600)
```

Note that `sample_interval` affects both the frequency of `powermetrics` calls and the resolution of energy calculations. A shorter interval gives finer-grained measurements but more subprocess overhead.

---

## Ollama

GreenPrompt requires Ollama running at `OLLAMA_URL` (default `http://127.0.0.1:11434`). GreenPrompt does not manage Ollama's lifecycle — start it separately:

```bash
ollama serve
# or as a background service (macOS)
brew services start ollama
```

### Default model

The CLI and API default to `llama2`. Override per-request:

```bash
greenprompt prompt "Hello" --model mistral
```

Or in the API:

```json
{"prompt": "Hello", "model": "phi"}
```

Any model name that Ollama recognizes is valid. Run `ollama list` to see installed models.

---

## Token-Based Energy Estimates

The `MODEL_ENERGY_MAP` in `core.py` maps model names to estimated watt-hours per 1000 tokens. Edit this dict to add or calibrate entries:

```python
# core.py
MODEL_ENERGY_MAP = {
    "gpt-3.5":  0.02,
    "gpt-4":    0.06,
    "gpt-4o":   0.04,
    "llama2":   0.01,
    "mistral":  0.008,
    "phi":      0.005,
    # Add your model:
    "llama3":   0.012,
}
```

Unknown models fall back to `0.01` Wh/1000 tokens.

---

## NLTK Data

`greenprompt setup` downloads the following NLTK corpora:

| Resource | Used by |
|---|---|
| `punkt` | Tokenization in `scoreBasic.py` |
| `punkt_tab` | Extended tokenizer tables |
| `averaged_perceptron_tagger` | POS tagging for verb detection |
| `averaged_perceptron_tagger_eng` | English-specific tagger |
| `wordnet` | Available for future use |
| `stopwords` | Keyword richness scoring |

NLTK data is downloaded to the default NLTK data path (usually `~/nltk_data/`). You can change this by setting the `NLTK_DATA` environment variable before running setup.
