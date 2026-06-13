"""
Shared pytest configuration and fixtures for all GreenPrompt test suites.

Platform-skip markers are applied automatically: tests in tests/macos/ and
tests/windows/ use @unittest.skipUnless(platform, ...) so they are no-ops
on other OSes and don't need any special invocation.

To add a new environment's tests:
  1. Create  tests/<env>/  with an __init__.py and test_*.py files.
  2. Use @unittest.skipUnless(sys.platform == "<platform>", ...) to gate
     tests that require real hardware or OS-specific APIs.
  3. Extract helpers shared across envs into tests/common/helpers.py.
"""
