# Changelog

All notable changes to GreenPrompt are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `run_prompt()` called `score_prompt()` twice to populate two adjacent fields,
  running the entire NLTK pipeline a second time for every prompt.
- `MODEL_ENERGY_MAP` was matched exactly against the raw model name, which no
  tagged Ollama name (`llama3.2:latest`) could ever satisfy, so every prompt
  silently used the fallback rate. Names are now normalised — tag and namespace
  stripped — and matched by family with a longest-prefix fallback. Measured
  energy was never affected; the token-based estimate was.
- `datetime.utcnow()`, deprecated in Python 3.12, replaced with a helper that
  produces byte-identical output. The format is pinned by tests because
  timestamps are compared as strings, so an offset-aware value would have
  broken `/api/usage/timeframe` against existing databases.
- `greenprompt run` and `greenprompt stop` took a PID from `lsof` output and
  sent it `SIGKILL` without checking what it was — `--port 5432` would kill
  Postgres. Both now verify the process is a GreenPrompt API server before
  signalling it, query only listening sockets, and send `SIGTERM` so the
  sampler can shut down. `run` refuses to start on a port held by anything else.
- Serving `greenprompt.api:app` through an external WSGI server left the power
  monitor unstarted, recording `energy_wh = 0` with no error. Added a
  `create_app()` factory that starts the sampler; use
  `gunicorn 'greenprompt.api:create_app()'`.
- `scoreBasic` ran four `nltk.download()` calls at import time, so every CLI
  invocation — `greenprompt --help` included — attempted four network round
  trips. Corpora are now fetched on demand and only when actually missing.

### Added

- `scripts/release.py`, which automates cutting a release: version arithmetic,
  the `pyproject.toml` rewrite, promoting this file's `## [Unreleased]` section,
  the commit, the annotated tag, and the push. Every precondition — branch,
  clean tree, sync with origin, tag availability, PyPI version availability,
  monotonic version, non-empty release notes, lint, tests — runs before any file
  is written, because a PyPI version number can never be reused once published.
  `--rehearse` dry-runs the whole pipeline without changing anything.
- `tests/test_release.py`: 22 tests covering the release script's version
  arithmetic, `pyproject.toml` rewriting, and CHANGELOG promotion.
- A Releasing section in `CONTRIBUTING.md`.
- Test coverage for the previously untested modules: `core.py`, `dbconn.py`,
  `cli.py`, the API's monitor lifecycle, and `scoreBasic.py` — 109 new tests,
  taking the suite from 98 to 207.

### Fixed

- `CONTRIBUTING.md` told contributors to run `ruff fmt` (not a ruff subcommand)
  and `pytest` (not a dependency, and not how the suite is written). Both now
  match the tooling the project actually uses.

## [0.2.0] — 2026-08-22

The headline change is live power measurement on Linux: GreenPrompt now reports
real watt-hours on Linux as well as macOS, and Windows is the only remaining
platform without hardware sampling.

### Added

- **Linux power measurement.** `LinuxPowerMonitor` (`samplerLinux.py`) samples
  CPU power once a second, auto-selecting the best available source: Intel/AMD
  RAPL energy counters (measured), an ARM big.LITTLE frequency-squared model, or
  a `CPU_TDP_W`-scaled fallback. GPU power comes from a single long-running
  `nvidia-smi dmon` process rather than a subprocess per tick.
- Short prompts that finish inside one sample interval now interpolate from
  neighbouring samples and are flagged with `"extrapolated": true`.
- A 76-case regression suite (`tests/test_linux_stress.py`) that simulates each
  CPU architecture, counter overflow, absent `nvidia-smi`, empty sample windows,
  and concurrent access — so the sampler can be validated without the hardware.
- CI: lint, unit tests, and a CLI smoke test on every push and pull request,
  across Python 3.9 through 3.13.
- A hardened PyPI release pipeline using Trusted Publishing (OIDC), with
  tag/version agreement checks, a duplicate-version guard, wheel install
  verification, and a `workflow_dispatch` dry-run mode.
- `--port` flag on the `prompt` and `dashboard` commands.

### Changed

- **No GreenPrompt command requires root any more.** On macOS, running
  `sudo greenprompt setup` once installs `/etc/sudoers.d/greenprompt` so that
  `powermetrics` can be sampled without a password; `run`, `stop`, and `prompt`
  are ordinary user commands from then on.
- **Configuration moved out of the package.** Tunables live in
  `~/.greenprompt/config.json` (overridable via `$GREENPROMPT_CONFIG` or
  `$GREENPROMPT_HOME`) instead of a generated `constants.py`. Platform values
  are derived live on every import, so they can never go stale or leak one
  machine's identity into another's install.
- **Much smaller install.** Seven declared dependencies that the package never
  imported — `openai`, `twine`, `statsmodels`, `nbformat`, `ruff`,
  `pre-commit`, `ipykernel` — moved to the dev group. A clean install goes from
  88 packages / 471 MB to 33 packages / 247 MB.
- Default model is now `llama3.2:latest` (was `llama2`).
- Package classifiers now declare Linux support alongside macOS.

### Fixed

- The database schema is created on demand, so a fresh working directory no
  longer fails with `no such table: prompt_usage`.
- The dashboard renders empty charts on an empty database instead of raising
  `KeyError`.
- API errors from `run_prompt()` return a JSON error with an appropriate status
  code instead of a 500 traceback.
- Machine-specific constants are no longer committed to the repository.

### Known limitations

- Windows has no live power sampling; `energy_wh` is `0` there.
- `run` and `stop` depend on `lsof` and therefore do not work on Windows.
- `MODEL_ENERGY_MAP` is keyed on bare model names and never matches a tagged
  Ollama name, so `energy_estimate_tokens` always uses the fallback rate. This
  affects the token-based estimate only, not measured energy.

## [0.1.1] — 2025-06-10

Initial public release: Ollama prompt execution with macOS `powermetrics`
energy measurement, 18-dimension offline prompt scoring, SQLite logging, a
Flask REST API, and a Plotly dashboard.

[0.2.0]: https://github.com/uday1201/greenprompt/releases/tag/v0.2.0
[0.1.1]: https://github.com/uday1201/greenprompt/releases/tag/v0.1.1
