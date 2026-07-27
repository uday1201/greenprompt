Prepare and cut a GreenPrompt release.

Publishing is automated. `.github/workflows/publish.yaml` triggers on any `v*.*.*` tag and runs: verify (lint, 76 tests, version guards) → build (`poetry build`, `twine check --strict`, wheel install smoke test) → publish to PyPI via Trusted Publishing (OIDC, no API token) → create a GitHub Release with the artifacts attached.

Your job is to get the repository ready and push the tag. Do NOT run `poetry publish` by hand — that bypasses every guard below.

Task: $ARGUMENTS (e.g. "bump to 0.2.0", "patch release", "check release readiness")

## 1. Check readiness

```bash
# Current version
grep '^version' pyproject.toml

# What is already on PyPI (a published version can NEVER be reused)
curl -s https://pypi.org/pypi/greenprompt/json | python3 -c "import json,sys; print(sorted(json.load(sys.stdin)['releases']))"

# Working tree must be clean and on main
git status --short && git branch --show-current
```

Run the same gates CI will run, so failures surface locally instead of mid-release:

```bash
ruff check .
python -m unittest discover -s tests -t .
poetry build && python -m twine check --strict dist/*
```

## 2. Choose the version

Semver against the changes since the last tag (`git log $(git describe --tags --abbrev=0)..HEAD --oneline`):

- **patch** — bug fixes only
- **minor** — new features, new platform support, backwards-compatible changes
- **major** — breaking changes to the CLI, REST API, or database schema

The version in `pyproject.toml` and the tag MUST agree; the workflow hard-fails on a mismatch, and it also refuses to republish a version that already exists on PyPI.

## 3. Cut it

```bash
poetry version minor          # or major / patch / an explicit 0.2.0
git commit -am "chore(release): $(grep '^version' pyproject.toml | cut -d'"' -f2)"
git push
git tag "v$(grep '^version' pyproject.toml | cut -d'"' -f2)"
git push --tags
```

Then watch it:

```bash
gh run watch
```

## 4. Rehearse without publishing

To exercise the full pipeline (lint, tests, build, metadata check) with the upload skipped:

```bash
gh workflow run publish.yaml -f dry_run=true
gh run watch
```

## Release checklist

- [ ] Working tree clean, on `main`, up to date with origin
- [ ] `ruff check .` passes
- [ ] Full test suite passes
- [ ] Version bumped in `pyproject.toml` and not already on PyPI
- [ ] README and `docs/` reflect any behaviour changes in this release
- [ ] `poetry build` + `twine check --strict` pass locally
- [ ] Tag matches the `pyproject.toml` version exactly, prefixed with `v`

## Notes

- **Trusted Publishing must be configured once** at https://pypi.org/manage/project/greenprompt/settings/publishing/ with owner `uday1201`, repository `greenprompt`, workflow `publish.yaml`, environment `pypi`. Without it the publish step fails to authenticate.
- The `pypi` GitHub environment is where you add required reviewers if you want a human approval gate before any upload.
- Never delete and re-push a tag that has already published — PyPI will reject the duplicate version. Bump the patch version instead.
- Do not publish to PyPI without explicit confirmation from the user.
