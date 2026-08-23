"""
test_packaging.py — invariants between declared support and tested support.

`pyproject.toml` declared `>=3.9,<4.0`, which promises Python 3.14. tiktoken
publishes no 3.14 wheels, so pip falls back to a source build and the install
dies with "can't find Rust compiler" — the documented install simply fails on a
machine whose default python3 is 3.14. CI ran 3.9 to 3.13 and never saw it.

The rule these tests encode: every interpreter the package claims to support
must be one CI actually runs. A claim nobody tests is how that bug survived.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def declared_range():
    """(lower, upper) as (major, minor) tuples from the python constraint."""
    text = PYPROJECT.read_text()
    match = re.search(r'(?m)^python\s*=\s*">=(\d+)\.(\d+),\s*<(\d+)\.(\d+)"', text)
    if not match:
        raise AssertionError("could not parse the python constraint")
    lo_major, lo_minor, hi_major, hi_minor = (int(g) for g in match.groups())
    return (lo_major, lo_minor), (hi_major, hi_minor)


def matrix_versions():
    """Python versions listed in the CI test matrix."""
    text = WORKFLOW.read_text()
    match = re.search(r"(?m)^\s*python-version:\s*\[(.+?)\]", text)
    if not match:
        raise AssertionError("could not find the CI python matrix")
    return [
        tuple(int(p) for p in v.strip().strip("'\"").split("."))
        for v in match.group(1).split(",")
    ]


class TestDeclaredSupportIsTested(unittest.TestCase):
    def test_the_constraint_is_parseable(self):
        lo, hi = declared_range()
        self.assertLess(lo, hi)

    def test_the_matrix_is_parseable(self):
        self.assertTrue(matrix_versions())

    def test_every_declared_version_is_in_the_ci_matrix(self):
        """
        The invariant. Declaring `<4.0` while testing up to 3.13 is what let an
        uninstallable 3.14 be advertised as supported.
        """
        (lo_major, lo_minor), (hi_major, hi_minor) = declared_range()
        self.assertEqual(lo_major, hi_major, "a range spanning majors is not handled")

        declared = {(lo_major, minor) for minor in range(lo_minor, hi_minor)}
        tested = set(matrix_versions())
        missing = sorted(declared - tested)
        self.assertEqual(
            missing,
            [],
            "pyproject.toml claims support for "
            + ", ".join(f"{a}.{b}" for a, b in missing)
            + " but CI does not test them",
        )

    def test_the_matrix_does_not_test_undeclared_versions(self):
        # The other direction: testing 3.14 while excluding it would be a
        # contradiction worth surfacing too.
        (lo_major, lo_minor), (_, hi_minor) = declared_range()
        declared = {(lo_major, minor) for minor in range(lo_minor, hi_minor)}
        extra = sorted(set(matrix_versions()) - declared)
        self.assertEqual(
            extra,
            [],
            "CI tests "
            + ", ".join(f"{a}.{b}" for a, b in extra)
            + " but pyproject.toml excludes them",
        )

    def test_the_upper_bound_excludes_314(self):
        """
        Pinned deliberately, with the reason recorded so it is lifted knowingly.

        tiktoken has no 3.14 wheels. When it does, raise the bound and add 3.14
        to the matrix in the same change — this test will fail until both are
        done together.
        """
        _, (major, minor) = declared_range()
        self.assertEqual((major, minor), (3, 14))

    def test_the_reason_for_the_cap_is_recorded(self):
        self.assertIn("tiktoken", PYPROJECT.read_text())


if __name__ == "__main__":
    unittest.main()
