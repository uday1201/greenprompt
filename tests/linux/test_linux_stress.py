"""
Stress tests and edge-case coverage for Linux power monitoring.

Covers:
  - CPU arch simulation (RAPL / ARM big.LITTLE / single-cluster / linear_tdp fallback)
  - sysfs failure modes (missing files, bad values, RAPL counter overflow)
  - NvidiaDmonReader (unavailable, garbled output, process death mid-run)
  - LinuxPowerMonitor thread safety (concurrent read/write under lock)
  - LinuxPowerMonitor lifecycle (rapid start/stop, deque rotation, no-GPU path)
  - measure_power_linux edge cases (None monitor, 0 samples, zero duration,
    start==end, no baseline, short-prompt interpolation threshold)
  - _parse_nvidia_power (all N/A variants, non-numeric, negative, large values)
  - API: empty prompt, missing JSON body, timeframe missing params

Shared helpers live in tests/common/helpers.py. Add new Linux-specific
test modules alongside this file as coverage grows.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch, mock_open

from tests.common.helpers import make_monitor as _make_monitor
from tests.common.helpers import sample_dict as _sample
from tests.common.helpers import cpu_pct_side_effect


# ===========================================================================
# 1. _parse_nvidia_power
# ===========================================================================

class TestParseNvidiaPower(unittest.TestCase):

    def _p(self, raw):
        from greenprompt.samplerLinux import _parse_nvidia_power
        return _parse_nvidia_power(raw)

    def test_normal_float(self):
        self.assertAlmostEqual(self._p("12.34"), 12.34)

    def test_na_variants(self):
        for val in ("[N/A]", "N/A", "Unknown Error", "", "  "):
            self.assertEqual(self._p(val), 0.0, msg=f"expected 0.0 for {val!r}")

    def test_non_numeric(self):
        self.assertEqual(self._p("watts"), 0.0)

    def test_zero(self):
        self.assertEqual(self._p("0"), 0.0)

    def test_large_value(self):
        self.assertAlmostEqual(self._p("999.9"), 999.9)

    def test_negative(self):
        # negative power is physically wrong but should parse without crash
        self.assertAlmostEqual(self._p("-1.5"), -1.5)

    def test_whitespace_padded(self):
        self.assertAlmostEqual(self._p("  7.5  "), 7.5)


# ===========================================================================
# 2. CPU architecture detection
# ===========================================================================

class TestDetectRaplPath(unittest.TestCase):

    def setUp(self):
        from greenprompt.samplerLinux import _detect_rapl_path
        self._fn = _detect_rapl_path

    def test_no_rapl_returns_none(self):
        with patch("os.path.exists", return_value=False), \
             patch("glob.glob", return_value=[]):
            self.assertIsNone(self._fn())

    def test_direct_path_found(self):
        with patch("os.path.exists", return_value=True):
            result = self._fn()
            self.assertIn("energy_uj", result)

    def test_glob_fallback(self):
        fake = "/sys/class/powercap/intel-rapl:0/intel-rapl:0:0/energy_uj"
        with patch("os.path.exists", return_value=False), \
             patch("glob.glob", return_value=[fake]):
            self.assertEqual(self._fn(), fake)

    def test_multiple_glob_returns_first(self):
        paths = [
            "/sys/class/powercap/intel-rapl:0/intel-rapl:0:0/energy_uj",
            "/sys/class/powercap/intel-rapl:1/intel-rapl:1:0/energy_uj",
        ]
        with patch("os.path.exists", return_value=False), \
             patch("glob.glob", return_value=paths):
            self.assertEqual(self._fn(), paths[0])


class TestDetectCpuClusters(unittest.TestCase):

    def setUp(self):
        from greenprompt.samplerLinux import _detect_cpu_clusters
        self._fn = _detect_cpu_clusters

    def _freq(self, max_mhz):
        f = MagicMock()
        f.max = float(max_mhz)
        return f

    def test_heterogeneous_two_clusters(self):
        freqs = [self._freq(2808)] * 10 + [self._freq(3900)] * 10
        with patch("psutil.cpu_freq", return_value=freqs):
            clusters = self._fn()
        self.assertEqual(set(clusters.keys()), {2808, 3900})
        self.assertEqual(len(clusters[2808]), 10)
        self.assertEqual(len(clusters[3900]), 10)

    def test_single_cluster_returns_empty(self):
        freqs = [self._freq(3200)] * 8
        with patch("psutil.cpu_freq", return_value=freqs):
            self.assertEqual(self._fn(), {})

    def test_none_returns_empty(self):
        with patch("psutil.cpu_freq", return_value=None):
            self.assertEqual(self._fn(), {})

    def test_empty_list_returns_empty(self):
        with patch("psutil.cpu_freq", return_value=[]):
            self.assertEqual(self._fn(), {})

    def test_single_cpu_returns_empty(self):
        with patch("psutil.cpu_freq", return_value=[self._freq(2400)]):
            self.assertEqual(self._fn(), {})

    def test_three_clusters(self):
        freqs = [self._freq(1800)] * 4 + [self._freq(2400)] * 4 + [self._freq(3600)] * 4
        with patch("psutil.cpu_freq", return_value=freqs):
            clusters = self._fn()
        self.assertEqual(len(clusters), 3)

    def test_psutil_exception_returns_empty(self):
        with patch("psutil.cpu_freq", side_effect=RuntimeError("no freq")):
            self.assertEqual(self._fn(), {})


# ===========================================================================
# 3. LinuxPowerMonitor construction — arch mode selection
# ===========================================================================

class TestMonitorModeSelection(unittest.TestCase):

    def _build(self, rapl=None, clusters=None):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=rapl), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters",
                   return_value=clusters or {}), \
             patch("psutil.cpu_percent", return_value=[0.0] * 4):
            return LinuxPowerMonitor()

    def test_rapl_mode_when_rapl_available(self):
        m = self._build(rapl="/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj")
        self.assertEqual(m._cpu_mode, "rapl")
        self.assertTrue(hasattr(m, "_rapl_path"))
        self.assertIsNone(m._rapl_last_energy)

    def test_biglittle_mode_when_clusters_detected(self):
        m = self._build(clusters={2808: [0, 1], 3900: [2, 3]})
        self.assertEqual(m._cpu_mode, "arm_biglittle")
        self.assertIn(2808, m._clusters)

    def test_linear_tdp_fallback(self):
        m = self._build(rapl=None, clusters={})
        self.assertEqual(m._cpu_mode, "linear_tdp")

    def test_rapl_takes_priority_over_biglittle(self):
        m = self._build(
            rapl="/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj",
            clusters={2808: [0], 3900: [1]},
        )
        self.assertEqual(m._cpu_mode, "rapl")


# ===========================================================================
# 4. _sample_cpu_rapl — sysfs read edge cases
# ===========================================================================

class TestSampleCpuRapl(unittest.TestCase):

    def _monitor_rapl(self, rapl_path="/fake/energy_uj"):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=rapl_path), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
             patch("psutil.cpu_percent", return_value=[0.0] * 4):
            m = LinuxPowerMonitor()
        m._rapl_path = rapl_path
        m._rapl_max_path = rapl_path.replace("energy_uj", "max_energy_range_uj")
        m._rapl_last_energy = None
        m._rapl_last_ts = None
        return m

    def test_first_call_returns_zero(self):
        m = self._monitor_rapl()
        with patch("builtins.open", mock_open(read_data="1000000")):
            result = m._sample_cpu_rapl()
        self.assertEqual(result, 0.0)
        self.assertEqual(m._rapl_last_energy, 1000000)

    def test_second_call_returns_watts(self):
        m = self._monitor_rapl()
        t0 = time.time()
        m._rapl_last_energy = 0
        m._rapl_last_ts = t0 - 1.0  # 1 second ago
        with patch("builtins.open", mock_open(read_data="1000000")):  # 1 J in 1s = 1W
            with patch("time.time", return_value=t0):
                result = m._sample_cpu_rapl()
        self.assertAlmostEqual(result, 1.0, places=1)

    def test_counter_overflow_handled(self):
        m = self._monitor_rapl()
        t0 = time.time()
        m._rapl_last_energy = 4_000_000_000_000  # near overflow
        m._rapl_last_ts = t0 - 1.0
        # New reading wraps to small value
        MAX = 4_294_967_295_000  # ~2^32 * 1000
        new_energy = 100_000  # wrapped around
        expected_delta_uj = new_energy - m._rapl_last_energy + MAX
        expected_w = (expected_delta_uj / 1_000_000.0) / 1.0

        def fake_open(path, *a, **kw):
            if "max_energy" in path:
                return mock_open(read_data=str(MAX))()
            return mock_open(read_data=str(new_energy))()

        with patch("builtins.open", fake_open), patch("time.time", return_value=t0):
            result = m._sample_cpu_rapl()
        self.assertGreater(result, 0.0)

    def test_oserror_returns_zero(self):
        m = self._monitor_rapl()
        m._rapl_last_energy = 0
        m._rapl_last_ts = time.time() - 1.0
        with patch("builtins.open", side_effect=OSError("no file")):
            self.assertEqual(m._sample_cpu_rapl(), 0.0)

    def test_bad_int_returns_zero(self):
        m = self._monitor_rapl()
        m._rapl_last_energy = 0
        m._rapl_last_ts = time.time() - 1.0
        with patch("builtins.open", mock_open(read_data="NOT_AN_INT")):
            self.assertEqual(m._sample_cpu_rapl(), 0.0)

    def test_zero_elapsed_returns_zero(self):
        m = self._monitor_rapl()
        ts = time.time()
        m._rapl_last_energy = 500_000
        m._rapl_last_ts = ts
        with patch("builtins.open", mock_open(read_data="1000000")), \
             patch("time.time", return_value=ts):  # same timestamp → delta_s == 0
            self.assertEqual(m._sample_cpu_rapl(), 0.0)


# ===========================================================================
# 5. _sample_cpu_biglittle — cluster model edge cases
# ===========================================================================

class TestSampleCpuBiglittle(unittest.TestCase):

    def _monitor_biglittle(self, clusters):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value=clusters), \
             patch("psutil.cpu_percent", return_value=[0.0] * 20):
            m = LinuxPowerMonitor()
        return m

    def test_idle_system_near_idle_power(self):
        clusters = {2808: list(range(10)), 3900: list(range(10, 20))}
        m = self._monitor_biglittle(clusters)
        cpu_pcts = [0.0] * 20
        sysfs_freq = "2808000"  # kHz = 2808 MHz

        with patch("psutil.cpu_percent", return_value=cpu_pcts), \
             patch("builtins.open", mock_open(read_data=sysfs_freq)):
            result = m._sample_cpu_biglittle()
        # At 0% util, freq_ratio=1, result = idle_w for each cluster
        expected = 0.5 + 1.0  # A725 idle + X925 idle
        self.assertAlmostEqual(result, expected, delta=0.5)

    def test_full_load_bounded_by_tdp(self):
        clusters = {2808: [0, 1], 3900: [2, 3]}
        m = self._monitor_biglittle(clusters)
        cpu_pcts = [100.0] * 4

        with patch("psutil.cpu_percent", return_value=cpu_pcts), \
             patch("builtins.open", mock_open(read_data="3900000")):
            result = m._sample_cpu_biglittle()
        # Should not exceed sum of TDP values
        max_expected = 8.0 + 23.0
        self.assertLessEqual(result, max_expected * 1.1)

    def test_missing_sysfs_falls_back_to_max_freq(self):
        clusters = {2808: [0, 1], 3900: [2, 3]}
        m = self._monitor_biglittle(clusters)
        cpu_pcts = [50.0] * 4

        with patch("psutil.cpu_percent", return_value=cpu_pcts), \
             patch("builtins.open", side_effect=OSError("no sysfs")):
            result = m._sample_cpu_biglittle()
        # Should still return a positive number using max freq as fallback
        self.assertGreater(result, 0.0)

    def test_unknown_cluster_freq_uses_tdp_fraction(self):
        # A cluster with max_mhz not in _CLUSTER_TDP should use cpu_tdp_w / n_clusters
        clusters = {9999: [0, 1]}
        m = self._monitor_biglittle(clusters)
        m.cpu_tdp_w = 20.0
        cpu_pcts = [50.0] * 2

        with patch("psutil.cpu_percent", return_value=cpu_pcts), \
             patch("builtins.open", mock_open(read_data="9999000")):
            result = m._sample_cpu_biglittle()
        self.assertGreater(result, 0.0)

    def test_cpu_pcts_shorter_than_cluster_indices(self):
        # Simulate psutil returning fewer entries than cluster claims
        clusters = {3900: [0, 1, 2, 3, 4]}
        m = self._monitor_biglittle(clusters)
        cpu_pcts = [50.0, 50.0]  # only 2 entries for 5 cpu indices

        with patch("psutil.cpu_percent", return_value=cpu_pcts), \
             patch("builtins.open", mock_open(read_data="3900000")):
            result = m._sample_cpu_biglittle()  # must not crash
        self.assertGreaterEqual(result, 0.0)

    def test_freq_ratio_capped_at_one(self):
        # If scaling_cur_freq > max_freq (shouldn't happen but defend against it)
        clusters = {2808: [0]}
        m = self._monitor_biglittle(clusters)
        cpu_pcts = [100.0]
        # Return a freq higher than max
        with patch("psutil.cpu_percent", return_value=cpu_pcts), \
             patch("builtins.open", mock_open(read_data="9999999")):
            result = m._sample_cpu_biglittle()
        # power should be capped at TDP, not exceed it due to freq_ratio > 1
        self.assertLessEqual(result, 8.0 * 1.1)


# ===========================================================================
# 6. NvidiaDmonReader edge cases
# ===========================================================================

class TestNvidiaDmonReader(unittest.TestCase):

    def test_unavailable_sets_failed(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            r = NvidiaDmonReader()
        self.assertTrue(r._failed)
        self.assertEqual(r.get_power(), 0.0)

    def test_oserror_sets_failed(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        with patch("subprocess.Popen", side_effect=OSError("perm denied")):
            r = NvidiaDmonReader()
        self.assertTrue(r._failed)

    def test_header_lines_skipped(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        lines = ["# gpu   pwr\n", "#  Idx   W\n", "   0   15\n"]
        proc = MagicMock()
        proc.stdout = iter(lines)
        with patch("subprocess.Popen", return_value=proc):
            r = NvidiaDmonReader()
            time.sleep(0.1)
        self.assertAlmostEqual(r.get_power(), 15.0)

    def test_garbled_line_ignored(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        lines = ["garbage output\n", "   0  NOTANUMBER\n", "   0   7\n"]
        proc = MagicMock()
        proc.stdout = iter(lines)
        with patch("subprocess.Popen", return_value=proc):
            r = NvidiaDmonReader()
            time.sleep(0.1)
        self.assertAlmostEqual(r.get_power(), 7.0)

    def test_empty_lines_ignored(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        lines = ["\n", "   \n", "   0   9\n"]
        proc = MagicMock()
        proc.stdout = iter(lines)
        with patch("subprocess.Popen", return_value=proc):
            r = NvidiaDmonReader()
            time.sleep(0.1)
        self.assertAlmostEqual(r.get_power(), 9.0)

    def test_stop_terminates_process(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        proc = MagicMock()
        proc.stdout = iter([])
        with patch("subprocess.Popen", return_value=proc):
            r = NvidiaDmonReader()
        r.stop()
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()

    def test_concurrent_reads_thread_safe(self):
        from greenprompt.samplerLinux import NvidiaDmonReader
        proc = MagicMock()
        proc.stdout = iter([f"   0   {i}\n" for i in range(100)])
        with patch("subprocess.Popen", return_value=proc):
            r = NvidiaDmonReader()
        errors = []
        def reader():
            for _ in range(200):
                try:
                    r.get_power()
                except Exception as e:
                    errors.append(e)
        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ===========================================================================
# 7. LinuxPowerMonitor lifecycle
# ===========================================================================

class TestMonitorLifecycle(unittest.TestCase):

    def _build_nogpu(self):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
             patch("psutil.cpu_percent", side_effect=cpu_pct_side_effect):
            m = LinuxPowerMonitor()
        return m

    def test_start_stop(self):
        m = self._build_nogpu()
        with patch.object(m, "_check_gpu", return_value=False), \
             patch("greenprompt.samplerLinux.NvidiaDmonReader") as MockDmon:
            MockDmon.return_value._failed = True
            m.start()
            time.sleep(0.5)
            m.stop()
        self.assertFalse(m.running)

    def test_rapid_start_stop_10x(self):
        """Monitor must survive 10 rapid start/stop cycles without deadlock."""
        for _ in range(10):
            from greenprompt.samplerLinux import LinuxPowerMonitor
            with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
                 patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
                 patch("psutil.cpu_percent", return_value=[5.0] * 4):
                m = LinuxPowerMonitor()
            with patch.object(m, "_check_gpu", return_value=False), \
                 patch("greenprompt.samplerLinux.NvidiaDmonReader") as MockDmon:
                MockDmon.return_value._failed = True
                m.start()
                time.sleep(0.05)
                m.stop()
            self.assertFalse(m.running)

    def test_samples_accumulate_over_time(self):
        m = self._build_nogpu()
        with patch.object(m, "_check_gpu", return_value=False), \
             patch("greenprompt.samplerLinux.NvidiaDmonReader") as MockDmon:
            MockDmon.return_value._failed = True
            m.start()
            time.sleep(3.5)
            m.stop()
        self.assertGreaterEqual(len(m.samples), 3)

    def test_deque_rotates_at_window_size(self):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
             patch("psutil.cpu_percent", return_value=[5.0] * 4):
            m = LinuxPowerMonitor(window_size=5)
        # Manually fill beyond window
        for i in range(10):
            m.samples.append((time.time() + i, _sample()))
        self.assertEqual(len(m.samples), 5)

    def test_sample_once_returns_dict(self):
        m = self._build_nogpu()
        m._dmon = None
        # linear_tdp mode: cpu_percent(interval=None) without percpu → scalar
        def _cpu_pct(*args, **kwargs):
            return [20.0] * 4 if kwargs.get("percpu") else 20.0
        with patch.object(m, "_check_gpu", return_value=False), \
             patch("psutil.cpu_percent", side_effect=_cpu_pct):
            result = m.sample_once()
        self.assertIsNotNone(result)
        self.assertIn("cpu_power_w", result)
        self.assertIn("gpu_power_w", result)
        self.assertIn("combined_power_w", result)
        self.assertGreaterEqual(result["cpu_power_w"], 0.0)

    def test_sample_once_exception_returns_none(self):
        m = self._build_nogpu()
        with patch("psutil.cpu_percent", side_effect=RuntimeError("psutil broken")):
            result = m.sample_once()
        self.assertIsNone(result)

    def test_get_range_average_empty_returns_none(self):
        m = self._build_nogpu()
        result = m.get_range_average(time.time() - 60, time.time())
        self.assertIsNone(result)

    def test_get_range_average_correct(self):
        m = self._build_nogpu()
        now = time.time()
        m.samples.append((now - 2, _sample(cpu=4.0, gpu=2.0)))
        m.samples.append((now - 1, _sample(cpu=6.0, gpu=4.0)))
        avg = m.get_range_average(now - 5, now)
        self.assertAlmostEqual(avg, 8.0)  # (6+6+10+10)/2 = 8

    def test_thread_safety_concurrent_append_and_read(self):
        """Concurrent appends and get_range_average must never raise."""
        m = self._build_nogpu()
        errors = []
        stop = threading.Event()

        def writer():
            while not stop.is_set():
                with m._lock:
                    m.samples.append((time.time(), _sample()))
                time.sleep(0.001)

        def reader():
            while not stop.is_set():
                try:
                    m.get_range_average(time.time() - 5, time.time())
                except Exception as e:
                    errors.append(e)
                time.sleep(0.001)

        threads = [threading.Thread(target=writer)] + \
                  [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        time.sleep(1.0)
        stop.set()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_stop_latency_under_500ms(self):
        m = self._build_nogpu()
        with patch.object(m, "_check_gpu", return_value=False), \
             patch("greenprompt.samplerLinux.NvidiaDmonReader") as MockDmon:
            MockDmon.return_value._failed = True
            m.start()
            time.sleep(0.5)
            t0 = time.time()
            m.stop()
            elapsed_ms = (time.time() - t0) * 1000
        self.assertLess(elapsed_ms, 500, f"stop() took {elapsed_ms:.0f}ms — too slow")


# ===========================================================================
# 8. measure_power_linux edge cases
# ===========================================================================

class TestMeasurePowerLinux(unittest.TestCase):

    def _call(self, start, end, monitor):
        from greenprompt.sysUsage import measure_power_linux
        return measure_power_linux(start, end, monitor)

    def test_none_monitor_returns_zeros(self):
        result = self._call(0, 1, None)
        self.assertEqual(result["energy_wh"], 0.0)
        self.assertEqual(result["cpu_power_w"], 0.0)

    def test_empty_samples_no_neighbors_returns_zeros(self):
        m = _make_monitor(samples=[])
        result = self._call(time.time() - 1, time.time(), m)
        self.assertEqual(result["energy_wh"], 0.0)

    def test_normal_samples_in_window(self):
        now = time.time()
        samples = [
            (now - 0.8, _sample(cpu=4.0, gpu=2.0)),
            (now - 0.4, _sample(cpu=6.0, gpu=2.0)),
        ]
        m = _make_monitor(samples=samples)
        result = self._call(now - 1.0, now, m)
        self.assertGreater(result["energy_wh"], 0.0)
        self.assertAlmostEqual(result["cpu_power_w"], 5.0)
        self.assertAlmostEqual(result["gpu_power_w"], 2.0)

    def test_short_prompt_interpolates_from_neighbors(self):
        now = time.time()
        # Samples right before and after a 0.1s prompt window
        samples = [
            (now - 0.8, _sample(cpu=4.0, gpu=2.0)),  # before
            (now + 0.5, _sample(cpu=6.0, gpu=2.0)),  # after
        ]
        m = _make_monitor(samples=samples, sample_interval=1)
        start = now - 0.05
        end = now + 0.05
        result = self._call(start, end, m)
        self.assertGreater(result["energy_wh"], 0.0)
        self.assertTrue(result.get("extrapolated", False))

    def test_short_prompt_no_neighbors_returns_zeros(self):
        now = time.time()
        # Neighbors too far away (> 2 * sample_interval)
        samples = [
            (now - 10.0, _sample()),   # too old
            (now + 10.0, _sample()),   # too far in future
        ]
        m = _make_monitor(samples=samples, sample_interval=1)
        result = self._call(now - 0.05, now + 0.05, m)
        self.assertEqual(result["energy_wh"], 0.0)
        self.assertFalse(result.get("extrapolated", False))

    def test_zero_duration_prompt(self):
        now = time.time()
        m = _make_monitor(samples=[(now - 0.5, _sample(cpu=5.0, gpu=3.0))])
        result = self._call(now, now, m)
        # energy = power * 0s = 0
        self.assertEqual(result["energy_wh"], 0.0)
        self.assertEqual(result["duration_sec"], 0.0)

    def test_start_equals_end(self):
        now = time.time()
        m = _make_monitor(samples=[(now - 0.5, _sample())])
        result = self._call(now, now, m)
        self.assertIn("cpu_power_w", result)

    def test_baseline_computed_from_60s_window(self):
        now = time.time()
        samples = (
            [(now - 70 + i, _sample(cpu=2.0, gpu=1.0)) for i in range(10)]  # before baseline
            + [(now - 50 + i, _sample(cpu=8.0, gpu=4.0)) for i in range(10)]  # in baseline
            + [(now - 0.5, _sample(cpu=10.0, gpu=5.0))]  # in prompt
        )
        m = _make_monitor(samples=samples)
        result = self._call(now - 0.2, now, m)
        self.assertAlmostEqual(result["baseline_power_w"], 12.0, delta=0.5)

    def test_no_baseline_samples_returns_zero_baseline(self):
        now = time.time()
        # Sample is inside the prompt window [now-0.2, now] only.
        # Baseline window is [now-60.2, now-0.2] — no samples there.
        m = _make_monitor(samples=[(now - 0.1, _sample(cpu=5.0, gpu=3.0))])
        result = self._call(now - 0.2, now, m)
        self.assertEqual(result["baseline_power_w"], 0.0)

    def test_monitor_without_lock_attribute_still_works(self):
        # Older monitor instances may lack _lock
        m = _make_monitor(samples=[(time.time() - 0.5, _sample())])
        del m._lock  # simulate old instance
        from greenprompt.sysUsage import measure_power_linux
        now = time.time()
        result = measure_power_linux(now - 0.3, now, m)
        self.assertIn("cpu_power_w", result)

    def test_only_after_neighbor_used(self):
        now = time.time()
        samples = [(now + 0.5, _sample(cpu=5.0, gpu=2.0))]  # only after
        m = _make_monitor(samples=samples, sample_interval=1)
        result = self._call(now - 0.05, now + 0.05, m)
        self.assertTrue(result.get("extrapolated", False))
        self.assertAlmostEqual(result["cpu_power_w"], 5.0)

    def test_only_before_neighbor_used(self):
        now = time.time()
        samples = [(now - 0.5, _sample(cpu=7.0, gpu=3.0))]  # only before
        m = _make_monitor(samples=samples, sample_interval=1)
        result = self._call(now - 0.05, now + 0.05, m)
        self.assertTrue(result.get("extrapolated", False))
        self.assertAlmostEqual(result["cpu_power_w"], 7.0)


# ===========================================================================
# 9. Architecture simulation — Intel RAPL end-to-end sampling
# ===========================================================================

class TestRaplEndToEnd(unittest.TestCase):

    def test_rapl_sampling_produces_nonzero_after_first_call(self):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        fake_rapl = "/tmp/fake_energy_uj"
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=fake_rapl), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
             patch("psutil.cpu_percent", return_value=[10.0] * 4):
            m = LinuxPowerMonitor()

        energy_values = iter([1_000_000, 3_000_000])  # 2J in 1s = 2W

        def fake_open(path, *a, **kw):
            if "max_energy" in path:
                return mock_open(read_data="4294967295000")()
            return mock_open(read_data=str(next(energy_values)))()

        t0 = time.time()
        with patch("builtins.open", fake_open), patch("time.time", return_value=t0):
            first = m._sample_cpu_rapl()  # sets baseline

        with patch("builtins.open", fake_open), \
             patch("time.time", return_value=t0 + 1.0):
            second = m._sample_cpu_rapl()

        self.assertEqual(first, 0.0)
        self.assertAlmostEqual(second, 2.0, places=0)


# ===========================================================================
# 10. API endpoint edge cases
# ===========================================================================

class TestApiEdgeCases(unittest.TestCase):

    def setUp(self):
        from greenprompt.api import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_empty_prompt_returns_400(self):
        resp = self.client.post(
            "/api/prompt",
            json={"prompt": "", "model": "llama3.2:latest"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_missing_json_body_returns_400(self):
        # Non-JSON content-type: get_json(silent=True) returns None → {} → prompt="" → 400
        resp = self.client.post("/api/prompt", data="not json",
                                content_type="text/plain")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_usage_all_returns_list(self):
        resp = self.client.get("/api/usage/all")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), list)

    def test_usage_by_model_returns_list(self):
        resp = self.client.get("/api/usage/model/llama3.2:latest")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), list)

    def test_usage_timeframe_missing_params_returns_400(self):
        resp = self.client.get("/api/usage/timeframe")
        self.assertEqual(resp.status_code, 400)

    def test_usage_timeframe_missing_end_returns_400(self):
        resp = self.client.get("/api/usage/timeframe?start=2026-01-01T00:00:00")
        self.assertEqual(resp.status_code, 400)

    def test_dashboard_returns_html(self):
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"GreenPrompt", resp.data)

    def test_bad_model_returns_400(self):
        with patch("greenprompt.api.run_prompt",
                   side_effect=RuntimeError("model 'badmodel' not found")):
            resp = self.client.post(
                "/api/prompt",
                json={"prompt": "hello", "model": "badmodel"},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_internal_exception_returns_500(self):
        with patch("greenprompt.api.run_prompt",
                   side_effect=Exception("unexpected crash")):
            resp = self.client.post(
                "/api/prompt",
                json={"prompt": "hello", "model": "llama3.2:latest"},
            )
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_concurrent_usage_all_requests(self):
        results = []
        errors = []
        def hit():
            try:
                r = self.client.get("/api/usage/all")
                results.append(r.status_code)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=hit) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertTrue(all(s == 200 for s in results))


# ===========================================================================
# 11. Stress: high-frequency sample_once calls (no crashes, no lock contention)
# ===========================================================================

class TestHighFrequencySampling(unittest.TestCase):

    def test_1000_sample_once_calls_no_crash(self):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
             patch("psutil.cpu_percent", side_effect=cpu_pct_side_effect):
            m = LinuxPowerMonitor()
        m._dmon = None
        errors = []
        with patch.object(m, "_check_gpu", return_value=False), \
             patch("psutil.cpu_percent", side_effect=cpu_pct_side_effect):
            for _ in range(1000):
                try:
                    result = m.sample_once()
                    if result is None:
                        errors.append("None result")
                except Exception as e:
                    errors.append(str(e))
        self.assertEqual(errors, [])

    def test_concurrent_sample_once_and_get_range(self):
        from greenprompt.samplerLinux import LinuxPowerMonitor
        with patch("greenprompt.samplerLinux._detect_rapl_path", return_value=None), \
             patch("greenprompt.samplerLinux._detect_cpu_clusters", return_value={}), \
             patch("psutil.cpu_percent", side_effect=cpu_pct_side_effect):
            m = LinuxPowerMonitor()
        m._dmon = None
        errors = []
        stop = threading.Event()

        def sampler():
            while not stop.is_set():
                with patch.object(m, "_check_gpu", return_value=False), \
                     patch("psutil.cpu_percent", side_effect=cpu_pct_side_effect):
                    s = m.sample_once()
                if s:
                    with m._lock:
                        m.samples.append((time.time(), s))
                time.sleep(0.001)

        def ranger():
            while not stop.is_set():
                try:
                    m.get_range_average(time.time() - 5, time.time())
                except Exception as e:
                    errors.append(e)
                time.sleep(0.001)

        threads = [threading.Thread(target=sampler)] + \
                  [threading.Thread(target=ranger) for _ in range(3)]
        for t in threads:
            t.start()
        time.sleep(1.5)
        stop.set()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
