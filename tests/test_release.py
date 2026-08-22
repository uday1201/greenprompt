"""
test_release.py — unit tests for the release automation in scripts/release.py.

Covers only the pure functions: version arithmetic, the pyproject rewrite, and
the CHANGELOG promotion. Nothing here touches git, the network, or PyPI, so the
suite stays runnable in CI.

The stakes justify the coverage: a PyPI version number can never be reused, so a
bug in bump_version() or promote_changelog() is not something a follow-up commit
can undo.
"""

import ast
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import release  # noqa: E402


class TestBumpVersion(unittest.TestCase):
    def test_bump_levels(self):
        self.assertEqual(release.bump_version("0.2.0", "patch"), "0.2.1")
        self.assertEqual(release.bump_version("0.2.0", "minor"), "0.3.0")
        self.assertEqual(release.bump_version("0.2.0", "major"), "1.0.0")

    def test_minor_and_major_reset_lower_components(self):
        self.assertEqual(release.bump_version("1.4.7", "minor"), "1.5.0")
        self.assertEqual(release.bump_version("1.4.7", "major"), "2.0.0")

    def test_explicit_version_is_accepted(self):
        self.assertEqual(release.bump_version("0.2.0", "0.4.2"), "0.4.2")

    def test_explicit_downgrade_is_rejected(self):
        # Guards against a typo shipping a version PyPI will refuse or,
        # worse, that reorders the release history.
        with self.assertRaises(release.ReleaseError):
            release.bump_version("0.2.0", "0.1.9")

    def test_explicit_same_version_is_rejected(self):
        with self.assertRaises(release.ReleaseError):
            release.bump_version("0.2.0", "0.2.0")

    def test_garbage_spec_is_rejected(self):
        for spec in ("", "1.0", "v1.0.0", "latest", "1.0.0a1"):
            with self.subTest(spec=spec), self.assertRaises(release.ReleaseError):
                release.bump_version("0.2.0", spec)

    def test_non_semver_current_version_is_rejected(self):
        with self.assertRaises(release.ReleaseError):
            release.bump_version("0.2", "patch")


PYPROJECT_SAMPLE = """[tool.poetry]
name = "greenprompt"
version = "0.2.0"
description = "A green prompt tool"

[tool.poetry.dependencies]
python = ">=3.9,<4.0"
requests = ">=2.32.3,<3.0.0"

[tool.something-else]
version = "9.9.9"
"""


class TestPyprojectRewrite(unittest.TestCase):
    def test_read_version(self):
        self.assertEqual(release.read_version(PYPROJECT_SAMPLE), "0.2.0")

    def test_read_version_missing(self):
        with self.assertRaises(release.ReleaseError):
            release.read_version("[tool.poetry]\nname = 'x'\n")

    def test_set_version_touches_only_the_first_version_line(self):
        out = release.set_version(PYPROJECT_SAMPLE, "0.3.0")
        self.assertIn('version = "0.3.0"', out)
        # The unrelated table further down must survive untouched.
        self.assertIn('version = "9.9.9"', out)
        self.assertEqual(out.count('version = "0.3.0"'), 1)

    def test_set_version_leaves_dependencies_alone(self):
        out = release.set_version(PYPROJECT_SAMPLE, "0.3.0")
        self.assertIn('requests = ">=2.32.3,<3.0.0"', out)
        self.assertIn('python = ">=3.9,<4.0"', out)

    def test_round_trip(self):
        out = release.set_version(PYPROJECT_SAMPLE, "1.2.3")
        self.assertEqual(release.read_version(out), "1.2.3")


CHANGELOG_SAMPLE = """# Changelog

Preamble text.

## [Unreleased]

### Added

- A new thing.

## [0.2.0] — 2026-08-22

Older release.

[0.2.0]: https://github.com/uday1201/greenprompt/releases/tag/v0.2.0
"""


class TestChangelogPromotion(unittest.TestCase):
    def test_notes_are_promoted_under_the_new_version(self):
        out, notes = release.promote_changelog(CHANGELOG_SAMPLE, "0.3.0", "2026-09-01")
        self.assertIn("## [0.3.0] — 2026-09-01", out)
        self.assertIn("- A new thing.", notes)
        # The promoted notes sit under the new heading, not under Unreleased.
        after_heading = out.split("## [0.3.0] — 2026-09-01", 1)[1]
        self.assertIn("- A new thing.", after_heading.split("## [0.2.0]")[0])

    def test_a_fresh_empty_unreleased_section_is_opened(self):
        out, _ = release.promote_changelog(CHANGELOG_SAMPLE, "0.3.0", "2026-09-01")
        self.assertIn("## [Unreleased]", out)
        unreleased = out.split("## [Unreleased]", 1)[1].split("## [")[0]
        self.assertIn(release.EMPTY_NOTES, unreleased)
        self.assertNotIn("A new thing", unreleased)

    def test_link_reference_is_added(self):
        out, _ = release.promote_changelog(CHANGELOG_SAMPLE, "0.3.0", "2026-09-01")
        self.assertIn(
            "[0.3.0]: https://github.com/uday1201/greenprompt/releases/tag/v0.3.0", out
        )

    def test_previous_release_is_preserved(self):
        out, _ = release.promote_changelog(CHANGELOG_SAMPLE, "0.3.0", "2026-09-01")
        self.assertIn("## [0.2.0] — 2026-08-22", out)
        self.assertIn("Older release.", out)

    def test_empty_notes_are_refused(self):
        empty = CHANGELOG_SAMPLE.replace(
            "### Added\n\n- A new thing.", release.EMPTY_NOTES
        )
        with self.assertRaises(release.ReleaseError):
            release.promote_changelog(empty, "0.3.0", "2026-09-01")

    def test_empty_notes_allowed_with_flag(self):
        empty = CHANGELOG_SAMPLE.replace(
            "### Added\n\n- A new thing.", release.EMPTY_NOTES
        )
        out, notes = release.promote_changelog(
            empty, "0.3.0", "2026-09-01", allow_empty=True
        )
        self.assertIn("## [0.3.0] — 2026-09-01", out)
        self.assertEqual(notes, release.EMPTY_NOTES)

    def test_missing_unreleased_section_is_refused(self):
        with self.assertRaises(release.ReleaseError):
            release.promote_changelog("# Changelog\n\n## [0.2.0] — x\n", "0.3.0", "d")

    def test_promotion_is_idempotent_in_shape(self):
        # Promoting twice in a row must still yield a well-formed document with
        # exactly one Unreleased heading.
        once, _ = release.promote_changelog(CHANGELOG_SAMPLE, "0.3.0", "2026-09-01")
        twice, _ = release.promote_changelog(
            once, "0.4.0", "2026-09-02", allow_empty=True
        )
        self.assertEqual(twice.count("## [Unreleased]"), 1)
        for v in ("0.4.0", "0.3.0", "0.2.0"):
            self.assertIn(f"## [{v}]", twice)


class TestRealRepositoryFiles(unittest.TestCase):
    """The checked-in files must actually work with the script."""

    def test_real_pyproject_version_is_readable(self):
        text = (release.ROOT / "pyproject.toml").read_text()
        self.assertRegex(release.read_version(text), r"^\d+\.\d+\.\d+$")

    def test_real_changelog_has_an_unreleased_section(self):
        text = (release.ROOT / "CHANGELOG.md").read_text()
        out, _ = release.promote_changelog(
            text, "99.0.0", "2099-01-01", allow_empty=True
        )
        self.assertIn("## [99.0.0] — 2099-01-01", out)


class TestTwoPhaseInterface(unittest.TestCase):
    """
    The release runs in two phases because the repository ruleset requires a
    pull request for any change to main — a direct `git push origin main` is
    rejected even with bypass rights, so the version bump travels through a
    pull request and only the tag is pushed directly.
    """

    def test_tag_release_exists(self):
        self.assertTrue(callable(release.tag_release))

    def test_phase_one_never_pushes_to_the_release_branch(self):
        """
        A regression guard on the actual constraint: an earlier version ran
        `git push origin main`, which the ruleset rejects at release time.
        """
        tree = ast.parse(pathlib.Path(release.__file__).read_text())
        main_fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "main"
        )
        for node in ast.walk(main_fn):
            if isinstance(node, ast.List):
                argv = [e.value for e in node.elts if isinstance(e, ast.Constant)]
                if argv[:3] == ["git", "push", "origin"]:
                    self.assertNotEqual(argv[3:4], [release.RELEASE_BRANCH])

    def test_tag_release_refuses_a_version_mismatch(self):
        """Guards against tagging before the release pull request is merged."""
        with (
            mock.patch.object(release, "run", return_value=""),
            mock.patch.object(release, "read_version", return_value="0.2.0"),
        ):
            with self.assertRaises(release.ReleaseError) as ctx:
                release.tag_release("0.3.0")
        self.assertIn("0.2.0", str(ctx.exception))

    def test_tag_release_refuses_an_existing_tag(self):
        def fake_run(cmd, **kw):
            return "v0.3.0" if cmd[:3] == ["git", "tag", "--list"] else ""

        with (
            mock.patch.object(release, "run", side_effect=fake_run),
            mock.patch.object(release, "read_version", return_value="0.3.0"),
        ):
            with self.assertRaises(release.ReleaseError):
                release.tag_release("0.3.0")

    def test_tag_release_refuses_a_version_already_on_pypi(self):
        with (
            mock.patch.object(release, "run", return_value=""),
            mock.patch.object(release, "read_version", return_value="0.3.0"),
            mock.patch.object(release, "published_versions", return_value={"0.3.0"}),
        ):
            with self.assertRaises(release.ReleaseError):
                release.tag_release("0.3.0")

    def test_tag_release_pushes_the_tag_when_everything_agrees(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return ""

        with (
            mock.patch.object(release, "run", side_effect=fake_run),
            mock.patch.object(release, "read_version", return_value="0.3.0"),
            mock.patch.object(release, "published_versions", return_value=set()),
        ):
            release.tag_release("0.3.0")

        self.assertIn(["git", "push", "origin", "v0.3.0"], calls)


if __name__ == "__main__":
    unittest.main()
