"""
test_api_lifecycle.py — unit tests for power monitor startup in the API server.

The defect: `monitor` was assigned only inside `if __name__ == "__main__":`.
Serving the module through an external WSGI server — the documented route on
Windows, and the obvious production path — left it at None, so every prompt
recorded energy_wh = 0 with no error at all. Silently wrong data is the worst
failure mode available, so these tests pin both halves of the fix: importing
`app` must still start nothing, and `create_app()` must start the sampler.

The samplers are injected as fake modules rather than imported, so the macOS
path is exercised on Linux CI and vice versa.
"""

import sys
import types
import unittest
from unittest import mock

from greenprompt import api


def _fake_sampler_module(name, attr):
    """A stand-in module exposing `attr` as a Mock monitor class."""
    module = types.ModuleType(name)
    setattr(module, attr, mock.Mock(name=attr))
    return module


class MonitorLifecycleTestCase(unittest.TestCase):
    """Reset the module-level monitor around every test."""

    def setUp(self):
        self._saved = api.monitor
        api.monitor = None
        self.addCleanup(lambda: setattr(api, "monitor", self._saved))


class TestImportSideEffects(MonitorLifecycleTestCase):
    def test_importing_app_starts_no_sampler(self):
        # Importing greenprompt.api must never spawn powermetrics — the test
        # suite imports `app` directly to exercise the routes.
        self.assertIsNone(api.monitor)

    def test_app_is_importable_without_create_app(self):
        self.assertIsNotNone(api.app)


class TestInitPowerMonitor(MonitorLifecycleTestCase):
    def test_darwin_starts_the_mac_sampler(self):
        fake = _fake_sampler_module("greenprompt.samplerMac", "PowerMonitor")
        with (
            mock.patch.object(api.constants, "OS", "Darwin"),
            mock.patch.dict(sys.modules, {"greenprompt.samplerMac": fake}),
        ):
            monitor = api.init_power_monitor()
        fake.PowerMonitor.assert_called_once()
        monitor.start.assert_called_once()

    def test_linux_starts_the_linux_sampler_with_the_configured_tdp(self):
        fake = _fake_sampler_module("greenprompt.samplerLinux", "LinuxPowerMonitor")
        with (
            mock.patch.object(api.constants, "OS", "Linux"),
            mock.patch.object(api.constants, "CPU_TDP_W", 23.0),
            mock.patch.dict(sys.modules, {"greenprompt.samplerLinux": fake}),
        ):
            monitor = api.init_power_monitor()
        fake.LinuxPowerMonitor.assert_called_once_with(cpu_tdp_w=23.0)
        monitor.start.assert_called_once()

    def test_unsupported_platform_returns_none_without_raising(self):
        with mock.patch.object(api.constants, "OS", "Windows"):
            self.assertIsNone(api.init_power_monitor())

    def test_unsupported_platform_warns(self):
        with (
            mock.patch.object(api.constants, "OS", "Windows"),
            mock.patch.object(api.logging, "warning") as warn,
        ):
            api.init_power_monitor()
        warn.assert_called_once()

    def test_is_idempotent(self):
        """A second call must not start a second sampler thread."""
        fake = _fake_sampler_module("greenprompt.samplerMac", "PowerMonitor")
        with (
            mock.patch.object(api.constants, "OS", "Darwin"),
            mock.patch.dict(sys.modules, {"greenprompt.samplerMac": fake}),
        ):
            first = api.init_power_monitor()
            second = api.init_power_monitor()
        self.assertIs(first, second)
        fake.PowerMonitor.assert_called_once()
        first.start.assert_called_once()

    def test_sets_the_module_global_used_by_handle_prompt(self):
        # /api/prompt reads the module global, so the factory must set it and
        # not merely return a value.
        fake = _fake_sampler_module("greenprompt.samplerMac", "PowerMonitor")
        with (
            mock.patch.object(api.constants, "OS", "Darwin"),
            mock.patch.dict(sys.modules, {"greenprompt.samplerMac": fake}),
        ):
            returned = api.init_power_monitor()
        self.assertIs(api.monitor, returned)


class TestCreateApp(MonitorLifecycleTestCase):
    def test_returns_the_flask_app(self):
        with mock.patch.object(api, "init_power_monitor") as init:
            self.assertIs(api.create_app(), api.app)
        init.assert_called_once()

    def test_starts_the_sampler(self):
        """The regression: this is what a WSGI deployment was missing."""
        fake = _fake_sampler_module("greenprompt.samplerMac", "PowerMonitor")
        with (
            mock.patch.object(api.constants, "OS", "Darwin"),
            mock.patch.dict(sys.modules, {"greenprompt.samplerMac": fake}),
        ):
            api.create_app()
        self.assertIsNotNone(api.monitor)

    def test_is_callable_as_a_wsgi_factory(self):
        # gunicorn 'greenprompt.api:create_app()' resolves the attribute and
        # calls it, so it must exist at module level and take no arguments.
        factory = getattr(api, "create_app")
        self.assertTrue(callable(factory))
        with mock.patch.object(api, "init_power_monitor"):
            self.assertIsNotNone(factory())


class TestPromptUsesTheMonitor(MonitorLifecycleTestCase):
    def test_handle_prompt_passes_the_module_monitor_to_run_prompt(self):
        sentinel = object()
        api.monitor = sentinel
        with mock.patch.object(api, "run_prompt", return_value={"ok": True}) as rp:
            client = api.app.test_client()
            client.post(
                "/api/prompt", json={"prompt": "hi", "model": "llama3.2:latest"}
            )
        self.assertIs(rp.call_args.kwargs["monitor"], sentinel)


if __name__ == "__main__":
    unittest.main()
