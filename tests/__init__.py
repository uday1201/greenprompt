"""GreenPrompt test suite.

Makes `tests` an importable package so `unittest discover -s tests -t .` can be
run from any working directory (used by .github/workflows/test.yml to verify
that the SQLite schema is auto-created outside the repo root).
"""
