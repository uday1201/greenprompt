# Changelog

All notable changes to GreenPrompt are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.4.4] — 2026-08-23

### Fixed

- **macOS always warned that energy readings would be zero, even when they
  were not.** `_check_powermetrics_sudo()` probed with
  `sudo -n powermetrics --version`, but `--version` is not a powermetrics
  option: it prints usage and exits non-zero, so the check returned False
  unconditionally. Confirmed on a machine where a real sample runs passwordless
  and a prompt reports CPU 2.09 W. The probe now takes one real sample
  (`--samplers cpu_power -n 1 -i 1`, ~0.28s) and has a timeout so a missing
  rule cannot hang startup. `sudo -l` was evaluated as a cheaper alternative
  and rejected: on an admin account it exits 0 for any command.
- **`sudo greenprompt setup` failed for pipx and virtualenv installs**, which
  is most of them, with `sudo: greenprompt: command not found`. `sudo` replaces
  `PATH` with `secure_path`, which contains neither `~/.local/bin` nor any
  venv. Every instance in the docs, the CLI help, and the runtime hint now uses
  `sudo $(command -v greenprompt) setup` and says why.
- **The declared Python range promised versions that cannot install.**
  `>=3.9,<4.0` allowed pip to attempt 3.14, where `tiktoken` publishes no
  wheels; the install then fails with `can't find Rust compiler`. On a machine
  whose default `python3` is 3.14 the documented install simply did not work.
  Capped at `<3.14`, with the reason recorded so it is lifted deliberately.

### Added

- A packaging test asserting that every Python version `pyproject.toml` claims
  to support is one the CI matrix actually runs, in both directions. The 3.14
  breakage existed precisely because the declared range outran the tested one,
  and nothing checked the two against each other.

## [0.4.3] — 2026-08-22

### Fixed

- **A database left owned by root failed every write silently.** On the machine
  this was found, `~/greenprompt_usage.db` was created by a `sudo greenprompt
  run` before that was fixed, and its last row was written the day ownership
  changed — every prompt in the following year was discarded without the user
  seeing anything. `run_prompt()` caught the failure and printed a warning
  which, under the API server, goes to `/tmp/api.log`.

  Three changes. `run_prompt()` now records whether the row was written and the
  CLI says plainly when it was not, so a discarded measurement no longer looks
  identical to a saved one. An unwritable database raises `DatabaseNotWritable`
  naming the file, its owner, and the `chown` that fixes it, instead of
  SQLite's `attempt to write a readonly database`, which names neither. And
  `greenprompt migrate` checks the target once up front rather than reporting
  the target's problem against each source in turn.

  This is the residue of the sudo ownership bug rather than a regression: that
  fix stopped new root-owned files being created but could do nothing about
  files already in that state.

## [0.4.0] — 2026-08-22

### Added

- **`greenprompt migrate`**, which folds databases left behind by older
  versions into the one in use. Versions before 0.3.0 resolved the database
  path from the working directory, so having several is easy — the machine this
  was developed on had three, holding 10, 2 and 27 rows. Until now the only
  remedy was a hand-written `sqlite3 ATTACH` recipe in the docs.

  It is safe to run repeatedly: rows are identified by
  `(timestamp, prompt, model)` and timestamps carry microseconds, so a second
  run merges nothing. Sources are opened read-only and are never modified or
  deleted. Schemas are intersected rather than assumed equal — `prompt_score`
  and `prompt_score_details` arrived with prompt scoring and `energy_estimate_*`
  later still, so an older database genuinely has fewer columns, which is
  exactly the kind worth merging. `--dry-run` reports without writing, and
  `--from` takes explicit sources instead of searching.
- Indexes on `timestamp` and `model`, the columns `get_prompt_usage()` filters
  and orders by. Created with `IF NOT EXISTS`, so `init_db()` stays idempotent.

### Fixed

- **`sudo greenprompt setup` wrote the config and database to the wrong place,
  or left them owned by root.** Setup is documented as the one command to run
  with `sudo`, because installing the passwordless `powermetrics` rule needs
  root — but it also creates files, and it resolved their location with
  `os.path.expanduser("~")`. Depending on how sudo is configured that is either
  root's home, where the user never looks and a second empty database is
  created on the next command, or the user's home with root-owned files that
  every subsequent non-root run then fails to write.

  Paths now resolve against the invoking user (via `SUDO_USER`, which
  `configure_powermetrics_sudoers()` already relied on), and anything created
  as root is handed back to that user.

## [0.3.0] — 2026-08-22

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

### Changed

- **The database now lives at `~/.greenprompt/greenprompt_usage.db`.** The path
  was previously computed from `os.getcwd()` on every import, so running
  `greenprompt prompt` and `greenprompt dashboard` from different directories
  used different databases and the dashboard came up empty with no error — the
  cause of the "Dashboard shows no data" entry in the troubleshooting docs.

  Nothing is stranded by the change: a `greenprompt_usage.db` already present
  in the working directory is still used, so existing per-directory databases
  keep working exactly as before. Deliberate per-project separation is now
  explicit via `$GREENPROMPT_DB` or a `DB_PATH` config entry rather than
  implied by the shell's working directory. `docs/configuration.md` documents
  how to consolidate databases left behind by older versions.

- **Prompt scores are higher for prompts that open with a bare imperative.**
  `get_verbs()` relied solely on NLTK POS tagging, which labels a capitalised
  sentence-opening verb as a proper noun often enough that whether a prompt was
  credited depended on which verb it started with: `Summarize this article.`
  scored 3 for Instructional Tone while `Explain inertia.`, `List three
  benefits.`, `Generate five ideas.` and `Define entropy.` scored 0, losing 4
  of 50 points overall. Sentence-initial instruction verbs are now recognised
  directly, and `has_explicit_task()` shares that one vocabulary
  (`INSTRUCTION_VERBS`) instead of keeping a private list.

  Rows already in the database keep their recorded scores, so comparisons that
  straddle this release are not like-for-like. The accepted trade is that a
  sentence-initial noun spelled like an instruction verb (`List of items`) is
  now credited as a task.

### Fixed

- **Every prompt stalled for ~35 seconds and then failed with a 500** on any
  machine whose own hostname does not resolve — a `.local` name with no mDNS
  responder answering, a VPN, a container, a renamed machine.
  `get_system_info()` called `socket.gethostbyname(socket.gethostname())`,
  which does not fail fast: it blocks for the full DNS timeout before raising
  `gaierror`. Because it runs *after* the Ollama call, the model had already
  produced an answer, which was then discarded — the user paid the energy cost
  and got nothing. It was also called twice per prompt, so the stall doubled,
  and it was intermittent, since whether `.local` resolves depends on network
  state.

  The address is now obtained by asking the kernel which local interface would
  route to an unroutable address (RFC 5737 TEST-NET-1) over a UDP socket. No
  packet is sent and no name is resolved: 0.2 ms instead of 35 s, and it
  returns the real LAN address rather than whatever the hostname mapped to.

  `get_system_info()` is additionally now **total** — every probe is guarded
  and unavailable values degrade to `"N/A"` — and its result is cached for the
  life of the process, since everything it reports is static. Cold cost went
  from 35,045 ms to 41 ms; repeat calls are free. `save_prompt_usage()` also
  reuses the dict `run_prompt()` already built instead of recomputing it.

  Found by end-to-end testing before the 0.3.0 release; present in 0.2.0.

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

- `CONTRIBUTING.md` told contributors to run `ruff fmt` (not a ruff subcommand)
  and `pytest` (not a dependency, and not how the suite is written). Both now
  match the tooling the project actually uses.

### Documentation

- Corrected the claim in `docs/prompt-scoring.md` that dimension 6 captures
  imperative verbs. NLTK's tagger labels a sentence-opening `Explain` or `List`
  as a proper noun, so those prompts score 0 there and lose 4 of 50 points
  overall. Documented with a worked table, cross-referenced from the README
  troubleshooting section, and pinned by a test.
- Documented that Energy Awareness matches literal substrings, so
  `energy consumption` earns nothing while `energy usage` does.
- `docs/architecture.md`: added `samplerLinux.py` to the module table, split
  power sampling into macOS and Linux flows, documented the model-name matching
  rules, and recorded the reasoning behind `create_app()`, verify-before-signal,
  and naive UTC timestamps.
- `docs/platform-support.md`: `greenprompt run` now works on Windows — the
  `lsof` lookup degrades instead of raising — while `stop` still cannot
  enumerate listeners. The previous blanket "both will fail" was wrong.
- README: `run`/`stop` descriptions match their new behaviour, four new
  troubleshooting entries, the WSGI factory, and the test layout.

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

[0.4.4]: https://github.com/uday1201/greenprompt/releases/tag/v0.4.4
[0.4.3]: https://github.com/uday1201/greenprompt/releases/tag/v0.4.3
[0.4.0]: https://github.com/uday1201/greenprompt/releases/tag/v0.4.0
[0.3.0]: https://github.com/uday1201/greenprompt/releases/tag/v0.3.0
[0.2.0]: https://github.com/uday1201/greenprompt/releases/tag/v0.2.0
[0.1.1]: https://github.com/uday1201/greenprompt/releases/tag/v0.1.1
