Prepare a new GreenPrompt PyPI release.

Current version is in `pyproject.toml` under `[tool.poetry] version`.
PyPI package: https://pypi.org/project/greenprompt/

Task: $ARGUMENTS (e.g., "bump to 0.2.0", "patch release", "check release readiness")

Steps:

1. Read the current version:
   ```bash
   grep '^version' greenprompt/greenprompt/pyproject.toml
   ```

2. Run the linter and formatter to ensure code is clean:
   ```bash
   cd greenprompt/greenprompt && poetry run ruff check .
   cd greenprompt/greenprompt && poetry run ruff fmt --check .
   ```

3. Check for known bugs that should be fixed before release. Read these files and verify:
   - `api.py` line 2: `from analytics import` → should be `from greenprompt.analytics import`
   - `api.py` line 130: proxy URL `/ollama/api/` → should be `/api/`
   - `core.py` line 73-141: `gpu_usage` may be undefined if `has_gpu()` returns False
   - `analytics.py` lines 96-98: `start_time`/`end_time` params are overwritten with None
   - `cli.py` lines 199-209: `score` command redundantly re-parses args
   Report which bugs are still present.

4. Verify the package builds cleanly:
   ```bash
   cd greenprompt/greenprompt && poetry build
   ```
   Check `dist/` for the generated `.whl` and `.tar.gz`.

5. If bumping the version, update `pyproject.toml`:
   ```bash
   cd greenprompt/greenprompt && poetry version <new-version>
   # or edit manually
   ```

6. Generate a release checklist:
   - [ ] Version bumped in pyproject.toml
   - [ ] Ruff lint passes
   - [ ] Known bugs addressed (or documented as known issues)
   - [ ] README reflects new features/changes
   - [ ] `poetry build` succeeds
   - [ ] Test install: `pip install dist/*.whl` and run `greenprompt --help`
   - [ ] Publish: `poetry publish` (requires PyPI credentials)

Do NOT publish to PyPI without explicit confirmation from the user.
