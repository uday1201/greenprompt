#!/usr/bin/env python3
"""
release.py — cut a GreenPrompt release.

Automates the mechanical half of a release: work out the next version, write it
to pyproject.toml, promote the CHANGELOG's Unreleased section, commit, tag, and
push. Pushing the tag is what starts .github/workflows/publish.yaml, which
builds, verifies, and publishes to PyPI via Trusted Publishing.

    python scripts/release.py patch          # 0.2.0 -> 0.2.1
    python scripts/release.py minor          # 0.2.0 -> 0.3.0
    python scripts/release.py major          # 0.2.0 -> 1.0.0
    python scripts/release.py 0.4.2          # explicit
    python scripts/release.py minor --rehearse   # dry-run the pipeline, change nothing

Why a script and not a workflow: the repository's `Main` ruleset requires pull
requests with two approvals, and its bypass is granted to a repository role
rather than to github-actions[bot]. A workflow that pushed a version bump to
main would be rejected; a maintainer with bypass rights running this locally is
not.

Every check that can fail runs *before* anything is written, because a PyPI
version number can never be reused once published.
"""

import argparse
import datetime as _dt
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "uday1201/greenprompt"
PACKAGE = "greenprompt"
ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
RELEASE_BRANCH = "main"

#: Placeholder body that `promote_changelog` leaves behind in a fresh
#: Unreleased section. Releasing while this is all that is there means nobody
#: wrote release notes, so it is refused unless --allow-empty is passed.
EMPTY_NOTES = "Nothing yet."


class ReleaseError(Exception):
    """A precondition failed. Raised before any file is modified."""


# --- pure helpers (unit-tested in tests/test_release.py) --------------------


def bump_version(current: str, spec: str) -> str:
    """
    Resolve `spec` against `current` and return the new version string.

    `spec` is either one of "major", "minor", "patch", or an explicit X.Y.Z
    version. An explicit version must be strictly greater than the current one,
    which catches a typo'd downgrade before it reaches PyPI.
    """
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", current)
    if not m:
        raise ReleaseError(f"Current version {current!r} is not X.Y.Z")
    major, minor, patch = (int(g) for g in m.groups())

    if spec == "major":
        return f"{major + 1}.0.0"
    if spec == "minor":
        return f"{major}.{minor + 1}.0"
    if spec == "patch":
        return f"{major}.{minor}.{patch + 1}"

    if not re.fullmatch(r"\d+\.\d+\.\d+", spec):
        raise ReleaseError(
            f"{spec!r} is neither a bump level (major/minor/patch) nor an X.Y.Z version"
        )
    if tuple(int(x) for x in spec.split(".")) <= (major, minor, patch):
        raise ReleaseError(f"{spec} is not greater than the current version {current}")
    return spec


def read_version(pyproject_text: str) -> str:
    """Return the version from a pyproject.toml body."""
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject_text)
    if not m:
        raise ReleaseError("No version line found in pyproject.toml")
    return m.group(1)


def set_version(pyproject_text: str, new_version: str) -> str:
    """
    Return `pyproject_text` with the project version replaced.

    Only the first `version = "..."` line is touched — dependency constraints
    further down the file use different keys and must not be rewritten.
    """
    new_text, n = re.subn(
        r'(?m)^version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        pyproject_text,
        count=1,
    )
    if n != 1:
        raise ReleaseError("Could not rewrite the version line in pyproject.toml")
    return new_text


def promote_changelog(
    text: str, new_version: str, date: str, allow_empty: bool = False
):
    """
    Turn the Unreleased section into a released one and open a fresh Unreleased.

    Returns (new_text, notes) where `notes` is the body that was promoted, so
    the caller can show it before committing.
    """
    header = re.search(r"(?m)^## \[Unreleased\]\s*$", text)
    if not header:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' section")

    body_start = header.end()
    nxt = re.search(r"(?m)^## \[", text[body_start:])
    body_end = body_start + nxt.start() if nxt else len(text)
    notes = text[body_start:body_end].strip()

    if not allow_empty and (not notes or notes == EMPTY_NOTES):
        raise ReleaseError(
            "The Unreleased section is empty — write release notes first, "
            "or pass --allow-empty to release without them"
        )

    new_section = (
        f"## [Unreleased]\n\n{EMPTY_NOTES}\n\n"
        f"## [{new_version}] — {date}\n\n{notes}\n\n"
    )
    text = text[: header.start()] + new_section + text[body_end:].lstrip("\n")

    # Keep the link-reference block at the bottom in sync.
    link = f"[{new_version}]: https://github.com/{REPO}/releases/tag/v{new_version}"
    if link not in text:
        existing = re.search(r"(?m)^\[\d+\.\d+\.\d+\]: .*$", text)
        if existing:
            text = text[: existing.start()] + link + "\n" + text[existing.start() :]
        else:
            text = text.rstrip("\n") + "\n\n" + link + "\n"
    return text, notes


# --- environment interaction ------------------------------------------------


def run(cmd, capture=True, check=True):
    """Run a command in the repo root, returning stripped stdout."""
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capture, check=False)
    if check and r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()
        raise ReleaseError(f"`{' '.join(cmd)}` failed: {detail}")
    return (r.stdout or "").strip()


def published_versions():
    """Return the set of versions already on PyPI ({} if the project is new)."""
    url = f"https://pypi.org/pypi/{PACKAGE}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return set(json.load(resp)["releases"])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return set()
        raise ReleaseError(f"Could not reach PyPI: {e}")
    except Exception as e:  # noqa: BLE001 — network shape varies; all are fatal here
        raise ReleaseError(f"Could not reach PyPI: {e}")


def preflight(new_version: str, skip_tests: bool):
    """Fail before touching any file if the repo or the world is not ready."""
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch != RELEASE_BRANCH:
        raise ReleaseError(
            f"On branch {branch!r}; releases are cut from {RELEASE_BRANCH!r}"
        )

    if run(["git", "status", "--porcelain"]):
        raise ReleaseError("Working tree is dirty — commit or stash first")

    run(["git", "fetch", "origin", "--tags", "--quiet"])
    local = run(["git", "rev-parse", "HEAD"])
    remote = run(["git", "rev-parse", f"origin/{RELEASE_BRANCH}"])
    if local != remote:
        raise ReleaseError(
            f"Local {RELEASE_BRANCH} is not in sync with origin/{RELEASE_BRANCH} — pull first"
        )

    tag = f"v{new_version}"
    if run(["git", "tag", "--list", tag]):
        raise ReleaseError(f"Tag {tag} already exists locally")
    if run(["git", "ls-remote", "--tags", "origin", tag]):
        raise ReleaseError(f"Tag {tag} already exists on origin")

    if new_version in published_versions():
        raise ReleaseError(
            f"{PACKAGE} {new_version} is already on PyPI and can never be replaced"
        )

    if skip_tests:
        print("  ! skipping lint and tests (--skip-tests)")
        return
    # sys.executable, not "python" — plenty of systems only ship "python3",
    # and the gate must run under the same interpreter as this script.
    print("  running ruff…")
    run([sys.executable, "-m", "ruff", "check", "."])
    print("  running tests…")
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."])


def rehearse():
    """Trigger the publish workflow in dry-run mode and exit without changes."""
    print("Triggering a dry run of publish.yaml on main…")
    run(
        [
            "gh",
            "workflow",
            "run",
            "publish.yaml",
            "--ref",
            RELEASE_BRANCH,
            "-f",
            "dry_run=true",
        ]
    )
    print(f"  https://github.com/{REPO}/actions/workflows/publish.yaml")
    print("Nothing was changed locally.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cut a GreenPrompt release.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("spec", help="major | minor | patch | explicit X.Y.Z version")
    ap.add_argument(
        "--rehearse",
        action="store_true",
        help="dry-run the publish pipeline; change nothing",
    )
    ap.add_argument(
        "--allow-empty",
        action="store_true",
        help="release even though the Unreleased section is empty",
    )
    ap.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip the local lint/test gate (CI still runs them)",
    )
    ap.add_argument("-y", "--yes", action="store_true", help="do not prompt")
    args = ap.parse_args()

    try:
        if args.rehearse:
            rehearse()
            return 0

        pyproject_text = PYPROJECT.read_text()
        current = read_version(pyproject_text)
        new_version = bump_version(current, args.spec)
        tag = f"v{new_version}"
        print(f"Releasing {PACKAGE} {current} -> {new_version} ({tag})\n")

        print("Preflight:")
        preflight(new_version, args.skip_tests)
        print("  all checks passed\n")

        today = _dt.date.today().isoformat()
        changelog_text, notes = promote_changelog(
            CHANGELOG.read_text(), new_version, today, args.allow_empty
        )

        print("Release notes:")
        for line in (notes or EMPTY_NOTES).splitlines():
            print(f"  {line}")
        print()

        if not args.yes:
            reply = input(
                f"Tag and push {tag}? This publishes to PyPI permanently. [y/N] "
            )
            if reply.strip().lower() not in ("y", "yes"):
                print("Aborted; nothing was changed.")
                return 1

        PYPROJECT.write_text(set_version(pyproject_text, new_version))
        CHANGELOG.write_text(changelog_text)

        run(["git", "add", str(PYPROJECT), str(CHANGELOG)])
        run(["git", "commit", "-m", f"chore(release): {new_version}"])
        run(["git", "tag", "-a", tag, "-m", f"{tag}\n\n{notes}"])
        run(["git", "push", "origin", RELEASE_BRANCH])
        run(["git", "push", "origin", tag])

        print(f"\nPushed {tag}. The release pipeline is running:")
        print(f"  https://github.com/{REPO}/actions/workflows/publish.yaml")
        print(
            "  gh run watch $(gh run list --workflow publish.yaml --limit 1 --json databaseId --jq '.[0].databaseId')"
        )
        return 0

    except ReleaseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
