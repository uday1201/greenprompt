

# Contributing to GreenPrompt

Thank you for your interest in contributing to GreenPrompt! We welcome contributions from the community.

## How to Contribute

1. **Fork the repository** on GitHub.  
2. **Clone your fork**:
   ```bash
   git clone https://github.com/yourusername/greenprompt.git
   cd greenprompt
   ```
3. **Create a new branch** for your feature or bugfix:
   ```bash
   git checkout -b feature/my-new-feature
   ```
4. **Install dependencies** and set up the environment:
   ```bash
   poetry install
   ```
5. **Make your changes** and ensure code is linted and formatted:
   ```bash
   poetry run ruff check .
   poetry run ruff format .
   ```
6. **Add tests** for new functionality and run existing tests. The suite is
   written with the standard library's `unittest`, and is run from a scratch
   directory so that the CWD-relative database is created outside the repo:
   ```bash
   mkdir -p /tmp/gp-test && cd /tmp/gp-test
   python -m unittest discover -s "$OLDPWD/tests" -t "$OLDPWD" -v
   ```
7. **Commit your changes** following [Conventional Commits](https://www.conventionalcommits.org/) style:
   ```bash
   git commit -m "feat(cli): add new `stop` command"
   ```
8. **Push your branch** to your fork:
   ```bash
   git push origin feature/my-new-feature
   ```
9. **Open a Pull Request** on the main repository, describing your changes and referencing any related issues.

## Code Review

- We strive for timely reviews; maintainers will review your PR promptly.  
- Address review comments by updating your branch as needed.

## Reporting Issues

If you encounter bugs or have feature requests, please open an issue using the provided templates (`.github/ISSUE_TEMPLATE/`).

## Releasing

Releases are cut from `main` by a maintainer, using `scripts/release.py`. It
does the mechanical work — version arithmetic, the `pyproject.toml` rewrite,
promoting the CHANGELOG's `## [Unreleased]` section, the commit, the annotated
tag, and the push — behind a set of preconditions that all run *before*
anything is written.

```bash
python scripts/release.py patch      # 0.2.0 -> 0.2.1
python scripts/release.py minor      # 0.2.0 -> 0.3.0
python scripts/release.py major      # 0.2.0 -> 1.0.0
python scripts/release.py 0.4.2      # explicit version
```

Pushing the tag is what starts `.github/workflows/publish.yaml`, which verifies,
builds, publishes to PyPI via Trusted Publishing (OIDC — there is no API token),
and cuts a GitHub Release with the built artifacts attached.

To rehearse the whole pipeline without releasing anything:

```bash
python scripts/release.py patch --rehearse
```

That triggers the publish workflow in dry-run mode — lint, tests, build, and
metadata check run, but the publish step is skipped and nothing is written
locally.

### What the script refuses to do

Each of these is checked before any file is modified, because a PyPI version
number can never be reused once published:

- release from a branch other than `main`, or with a dirty working tree
- release when local `main` has diverged from `origin/main`
- reuse a tag that already exists locally or on the remote
- publish a version that is already on PyPI
- go backwards — an explicit version must exceed the current one
- release with an empty `## [Unreleased]` section (override with `--allow-empty`)

It also runs `ruff check` and the full test suite locally as a last gate;
`--skip-tests` bypasses that, and CI still enforces both.

### Writing release notes

Add entries under `## [Unreleased]` in `CHANGELOG.md` as you merge work, using
the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) headings (`Added`,
`Changed`, `Fixed`, `Removed`). The release script moves that section under the
new version heading and opens a fresh empty one, so the notes are written
incrementally rather than reconstructed from `git log` at release time.

### One-time setup

PyPI Trusted Publishing is already configured for this project:
owner `uday1201`, repository `greenprompt`, workflow `publish.yaml`,
environment `pypi`. The GitHub environment name must match that last value
exactly. No API token is involved.
