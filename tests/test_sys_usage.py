"""
test_sys_usage.py — unit tests for system metadata collection.

`get_system_info()` must never raise. The guarantee is load-bearing: it is
called by `run_prompt()` *after* the model has already produced an answer, and
again by `save_prompt_usage()`. When the IP-address lookup raised — which it
did on any host whose own name does not resolve, a routine situation — a
completed prompt was discarded with a 500 and no row was written. The user paid
the energy cost of the call and got nothing back.

Every probe is therefore tested for failing independently.
"""

import socket
import unittest
from unittest import mock

from greenprompt import sysUsage


EXPECTED_KEYS = {
    "OS",
    "OS Version",
    "Platform",
    "Machine",
    "Processor",
    "CPU",
    "CPU Cores (Physical)",
    "CPU Cores (Total)",
    "CPU Frequency (Current)",
    "CPU Frequency (Min)",
    "CPU Frequency (Max)",
    "RAM (Total)",
    "Disk (Total)",
    "Disk (Used)",
    "Disk (Free)",
    "Hostname",
    "IP Address",
}


class TestSafe(unittest.TestCase):
    def test_returns_the_value_on_success(self):
        self.assertEqual(sysUsage._safe(lambda: "value"), "value")

    def test_substitutes_the_default_on_any_exception(self):
        for exc in (OSError, ValueError, RuntimeError, socket.gaierror):
            with self.subTest(exc=exc.__name__):

                def boom():
                    raise exc("nope")

                self.assertEqual(sysUsage._safe(boom), sysUsage.UNKNOWN)

    def test_treats_none_as_unavailable(self):
        self.assertEqual(sysUsage._safe(lambda: None), sysUsage.UNKNOWN)

    def test_honours_a_custom_default(self):
        def boom():
            raise OSError

        self.assertEqual(sysUsage._safe(boom, default="fallback"), "fallback")

    def test_zero_and_false_are_preserved(self):
        # Falsy is not the same as unavailable — a 0-core reading is a value.
        self.assertEqual(sysUsage._safe(lambda: 0), 0)
        self.assertEqual(sysUsage._safe(lambda: False), False)


class TestIpAddress(unittest.TestCase):
    def test_never_performs_a_dns_lookup(self):
        """
        The regression guard that matters most.

        socket.gethostbyname(socket.gethostname()) does not fail fast when the
        hostname is unresolvable — it blocks for the full DNS timeout, measured
        at 35 seconds on macOS, before raising. On the prompt path that stalled
        every prompt for over half a minute and then discarded it. Reaching for
        the resolver again must fail this test.
        """
        with mock.patch.object(sysUsage.socket, "gethostbyname") as resolver:
            sysUsage._ip_address()
        resolver.assert_not_called()

    def test_uses_an_unroutable_udp_probe(self):
        # UDP connect() sends no packet; it only asks the kernel to pick a
        # local interface. The target must stay unroutable (RFC 5737).
        with mock.patch.object(sysUsage.socket, "socket") as sock:
            sysUsage._ip_address()
        sock.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        sock.return_value.connect.assert_called_once_with(sysUsage._ROUTE_PROBE)

    def test_returns_the_local_interface_address(self):
        with mock.patch.object(sysUsage.socket, "socket") as sock:
            sock.return_value.getsockname.return_value = ("10.0.0.5", 12345)
            self.assertEqual(sysUsage._ip_address(), "10.0.0.5")

    def test_a_failing_probe_yields_na(self):
        # No route to anywhere, e.g. a fully offline machine.
        with mock.patch.object(sysUsage.socket, "socket", side_effect=OSError):
            self.assertEqual(sysUsage._ip_address(), sysUsage.UNKNOWN)

    def test_the_socket_is_always_closed(self):
        with mock.patch.object(sysUsage.socket, "socket") as sock:
            sock.return_value.connect.side_effect = OSError
            sysUsage._ip_address()
        sock.return_value.close.assert_called_once()

    def test_completes_promptly(self):
        import time

        start = time.time()
        sysUsage._ip_address()
        self.assertLess(time.time() - start, 2.0)


class TestCaching(unittest.TestCase):
    def setUp(self):
        saved = sysUsage._system_info_cache
        sysUsage._system_info_cache = None
        self.addCleanup(lambda: setattr(sysUsage, "_system_info_cache", saved))

    def test_probes_only_once(self):
        with mock.patch.object(sysUsage, "_ip_address", return_value="1.2.3.4") as ip:
            sysUsage.get_system_info()
            sysUsage.get_system_info()
            sysUsage.get_system_info()
        ip.assert_called_once()

    def test_refresh_reprobes(self):
        with mock.patch.object(sysUsage, "_ip_address", return_value="1.2.3.4") as ip:
            sysUsage.get_system_info()
            sysUsage.get_system_info(refresh=True)
        self.assertEqual(ip.call_count, 2)

    def test_cached_calls_are_fast(self):
        import time

        sysUsage.get_system_info()
        start = time.time()
        for _ in range(100):
            sysUsage.get_system_info()
        self.assertLess(time.time() - start, 0.5)

    def test_returns_a_copy_so_callers_cannot_corrupt_the_cache(self):
        first = sysUsage.get_system_info()
        first["OS"] = "tampered"
        self.assertNotEqual(sysUsage.get_system_info()["OS"], "tampered")


class TestGetSystemInfo(unittest.TestCase):
    def setUp(self):
        # The result is cached process-wide; each test re-probes.
        saved = sysUsage._system_info_cache
        sysUsage._system_info_cache = None
        self.addCleanup(lambda: setattr(sysUsage, "_system_info_cache", saved))

    def test_returns_every_documented_key(self):
        self.assertEqual(set(sysUsage.get_system_info()), EXPECTED_KEYS)

    def test_never_raises_when_ip_lookup_fails(self):
        with mock.patch.object(sysUsage.socket, "socket", side_effect=socket.gaierror):
            info = sysUsage.get_system_info()
        self.assertEqual(info["IP Address"], sysUsage.UNKNOWN)
        self.assertEqual(set(info), EXPECTED_KEYS)

    def test_survives_every_probe_failing_at_once(self):
        """Worst case: nothing can be determined. Must still return a full dict."""
        with (
            mock.patch.object(sysUsage.socket, "gethostname", side_effect=OSError),
            mock.patch.object(sysUsage.socket, "socket", side_effect=OSError),
            mock.patch.object(sysUsage.cpuinfo, "get_cpu_info", side_effect=OSError),
            mock.patch.object(sysUsage.psutil, "cpu_count", side_effect=OSError),
            mock.patch.object(sysUsage.psutil, "cpu_freq", side_effect=OSError),
            mock.patch.object(sysUsage.psutil, "virtual_memory", side_effect=OSError),
            mock.patch.object(sysUsage.shutil, "disk_usage", side_effect=OSError),
            mock.patch.object(sysUsage, "platform") as plat,
        ):
            plat.system.side_effect = OSError
            plat.version.side_effect = OSError
            plat.platform.side_effect = OSError
            plat.machine.side_effect = OSError
            plat.processor.side_effect = OSError
            info = sysUsage.get_system_info()
        self.assertEqual(set(info), EXPECTED_KEYS)
        self.assertTrue(all(v == sysUsage.UNKNOWN for v in info.values()), info)

    def test_one_failing_probe_does_not_affect_the_others(self):
        with mock.patch.object(sysUsage.shutil, "disk_usage", side_effect=OSError):
            info = sysUsage.get_system_info()
        self.assertEqual(info["Disk (Total)"], sysUsage.UNKNOWN)
        self.assertNotEqual(info["OS"], sysUsage.UNKNOWN)

    def test_absent_cpu_freq_yields_na(self):
        # psutil.cpu_freq() legitimately returns None on some platforms.
        with mock.patch.object(sysUsage.psutil, "cpu_freq", return_value=None):
            info = sysUsage.get_system_info()
        for key in (
            "CPU Frequency (Current)",
            "CPU Frequency (Min)",
            "CPU Frequency (Max)",
        ):
            with self.subTest(key=key):
                self.assertEqual(info[key], sysUsage.UNKNOWN)

    def test_cpu_freq_is_formatted_in_mhz(self):
        freq = mock.Mock(current=2400.0, min=1000.0, max=3200.0)
        with mock.patch.object(sysUsage.psutil, "cpu_freq", return_value=freq):
            info = sysUsage.get_system_info()
        self.assertEqual(info["CPU Frequency (Current)"], "2400.00 MHz")
        self.assertEqual(info["CPU Frequency (Max)"], "3200.00 MHz")

    def test_disk_and_ram_are_formatted_in_gb(self):
        info = sysUsage.get_system_info()
        for key in ("RAM (Total)", "Disk (Total)", "Disk (Used)", "Disk (Free)"):
            with self.subTest(key=key):
                self.assertTrue(
                    info[key].endswith(" GB") or info[key] == sysUsage.UNKNOWN,
                    info[key],
                )

    def test_is_json_serialisable(self):
        # dbconn stores it with json.dumps, so a non-serialisable value here
        # would fail the write instead of the read.
        import json

        json.dumps(sysUsage.get_system_info())


class TestSystemInfoIsNotRecomputed(unittest.TestCase):
    """save_prompt_usage() should use the dict run_prompt() already built."""

    def setUp(self):
        import os
        import tempfile
        from greenprompt import dbconn

        self.dbconn = dbconn
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)
        p = mock.patch.object(dbconn, "DB_PATH", self.path)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(self.path) and os.unlink(self.path))

    def test_supplied_system_info_is_reused(self):
        with mock.patch.object(self.dbconn, "get_system_info") as gsi:
            self.dbconn.save_prompt_usage(
                {"prompt": "x", "system_info": {"OS": "Supplied"}}
            )
        gsi.assert_not_called()
        row = self.dbconn.get_prompt_usage()[0]
        self.assertIn("Supplied", row["system_info"])

    def test_missing_system_info_is_computed(self):
        with mock.patch.object(
            self.dbconn, "get_system_info", return_value={"OS": "Computed"}
        ) as gsi:
            self.dbconn.save_prompt_usage({"prompt": "x"})
        gsi.assert_called_once()
        self.assertIn("Computed", self.dbconn.get_prompt_usage()[0]["system_info"])

    def test_a_non_dict_system_info_is_replaced(self):
        with mock.patch.object(
            self.dbconn, "get_system_info", return_value={"OS": "Computed"}
        ) as gsi:
            self.dbconn.save_prompt_usage({"prompt": "x", "system_info": "not a dict"})
        gsi.assert_called_once()


if __name__ == "__main__":
    unittest.main()
