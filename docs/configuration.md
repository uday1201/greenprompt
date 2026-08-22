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

By default:

```
~/.greenprompt/greenprompt_usage.db
```

`dbconn.resolve_db_path()` picks the location once, at import, in this order:

| Order | Source | Notes |
|---|---|---|
| 1 | `$GREENPROMPT_DB` | Explicit path to a database file |
| 2 | `DB_PATH` in the config file | Same file as `OLLAMA_URL` and `CPU_TDP_W` |
| 3 | `./greenprompt_usage.db` | Only if it already exists — see below |
| 4 | `$GREENPROMPT_HOME/greenprompt_usage.db` | |
| 5 | `~/.greenprompt/greenprompt_usage.db` | Default |

The parent directory is created on demand, so no setup step is required.

> **Upgrading from ≤ 0.2.0:** the path used to be `os.getcwd()` unconditionally,
> so which database you got depended on where you ran the command. Step 3
> preserves that: if a `greenprompt_usage.db` already exists in the directory
> you run from, it is still used and nothing moves. Only directories without
> one fall through to the new default.

### Per-project databases

Still supported, and now explicit rather than a side effect of your shell's
working directory:

```bash
GREENPROMPT_DB=~/projects/project-a/usage.db greenprompt run
GREENPROMPT_DB=~/projects/project-a/usage.db greenprompt prompt "..."
```

Or set it for a whole shell session:

```bash
export GREENPROMPT_DB=~/projects/project-a/usage.db
```

The important part is that `run`, `prompt`, and `dashboard` see the *same*
value — a dashboard reading a different database from the one prompts were
written to is exactly the failure this resolution order removes.

### Consolidating databases from older versions

If you accumulated several databases by running from different directories,
find them and merge them into the new default:

```bash
find ~ -name greenprompt_usage.db 2>/dev/null

sqlite3 ~/.greenprompt/greenprompt_usage.db \
  "ATTACH '/path/to/other/greenprompt_usage.db' AS old;
   INSERT INTO prompt_usage (
     timestamp, prompt, prompt_score, prompt_score_details, response, model,
     prompt_tokens, completion_tokens, total_tokens, energy_estimate_prompt,
     energy_estimate_tokens, duration_sec, energy_wh, baseline_power_w,
     baseline_energy_wh, cpu_power_w, gpu_power_w, combined_power_w, system_info
   )
   SELECT timestamp, prompt, prompt_score, prompt_score_details, response, model,
     prompt_tokens, completion_tokens, total_tokens, energy_estimate_prompt,
     energy_estimate_tokens, duration_sec, energy_wh, baseline_power_w,
     baseline_energy_wh, cpu_power_w, gpu_power_w, combined_power_w, system_info
   FROM old.prompt_usage;"
```

`id` is deliberately omitted so rows get fresh autoincrement keys. Back up both
files first, and note that rows carry the prompt score recorded at the time —
scoring changed in 0.3.0, so older rows are not directly comparable.

### Multiple databases

You can maintain separate databases per project by running `greenprompt setup` from different directories:

```bash
# Project A
cd ~/projects/project-a
greenprompt setup
greenprompt run

# Project B
cd ~/projects/project-b
greenprompt setup
greenprompt run --port 5001  # different port to avoid conflict
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
greenprompt run --port 8080
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

The CLI and API default to `llama3.2:latest`. Override per-request:

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
    "llama3":   0.012,
    "mistral":  0.008,
    "phi":      0.005,
}
```

Unknown models fall back to `0.01` Wh/1000 tokens.

### How a model name is matched

The name is normalised before lookup: the Ollama tag and any namespace are
stripped and the rest is lowercased, so `library/llama3.2:latest` becomes
`llama3.2`. Matching then proceeds in order:

1. **Exact family match** — `llama2` hits the `llama2` entry.
2. **Longest matching prefix** — `llama3.2` inherits the `llama3` rate, so
   point releases do not each need their own entry. Longest-first ordering
   means `gpt-4o` is never shadowed by `gpt-4`.
3. **Fallback** — `DEFAULT_ENERGY_PER_1K_WH` (0.01 Wh/1000 tokens).

Before 0.3.0 the lookup was an exact match on the raw name, which no tagged
Ollama model could satisfy — every prompt silently used the fallback rate.

These rates are order-of-magnitude heuristics for offline comparison, not
measurements. The hardware-measured `energy_wh` is the authoritative figure and
was never affected by this.

---

## NLTK Data

`greenprompt setup` downloads the following NLTK corpora up front. If setup has
not been run, `scoreBasic.ensure_nltk_data()` fetches whatever is missing the
first time a prompt is scored — nothing is downloaded at import time, so no
command pays for this just by starting up.

| Resource | Used by |
|---|---|
| `punkt` | Tokenization in `scoreBasic.py` |
| `punkt_tab` | Extended tokenizer tables |
| `averaged_perceptron_tagger` | POS tagging for verb detection |
| `averaged_perceptron_tagger_eng` | English-specific tagger |
| `wordnet` | Available for future use |
| `stopwords` | Keyword richness scoring |

NLTK data is downloaded to the default NLTK data path (usually `~/nltk_data/`). You can change this by setting the `NLTK_DATA` environment variable before running setup.

For a fully offline install, run `greenprompt setup` once on a connected
machine, or pre-populate `NLTK_DATA`. Once every resource above resolves,
scoring makes no network calls at all.
