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

When `setup` is run with `sudo`, paths resolve against the *invoking* user's
home rather than root's, and anything created is handed back to that user.
Otherwise the config and database would either land in `/var/root/` or be left
owned by root and unwritable by every later command.

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
merge them with the built-in command rather than by hand:

```bash
greenprompt migrate --dry-run   # report what would move
greenprompt migrate             # merge, with a confirmation prompt
```

It searches your home directory and the current directory to a bounded depth,
and accepts explicit sources:

```bash
greenprompt migrate --from ~/old-project/greenprompt_usage.db
```

Three properties make it safe to reach for:

- **Idempotent.** Rows are identified by `(timestamp, prompt, model)`, and
  timestamps carry microseconds, so re-running merges nothing. There is no
  window in which running it twice doubles your history.
- **Non-destructive.** Sources are opened read-only and are never modified or
  deleted. Delete them yourself once you have checked the result.
- **Schema-tolerant.** `prompt_score` and `prompt_score_details` arrived with
  prompt scoring, and `energy_estimate_*` later still, so a database written by
  an older version has fewer columns — which is precisely the kind worth
  merging. Only shared columns are copied; the rest stay empty.

Note that rows carry the prompt score recorded at the time. Scoring changed in
0.3.0, so older rows are not directly comparable with newer ones.

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
