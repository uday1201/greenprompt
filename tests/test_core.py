"""
test_core.py — unit tests for prompt execution and energy estimation.

Covers the two defects fixed in greenprompt/core.py:

  * `estimate_energy_from_tokens()` matched model names exactly, which no
    tagged Ollama name ("llama3.2:latest") could ever satisfy, so every prompt
    silently used the fallback rate.
  * `run_prompt()` called `score_prompt()` twice to fill two adjacent fields,
    running the whole NLTK pipeline a second time for no reason.

Nothing here touches the network, the database, or the power samplers.
"""

import unittest
from unittest import mock

from greenprompt import core


class TestNormalizeModelName(unittest.TestCase):
    def test_strips_ollama_tag(self):
        self.assertEqual(core.normalize_model_name("llama3.2:latest"), "llama3.2")
        self.assertEqual(core.normalize_model_name("mistral:7b-instruct"), "mistral")

    def test_strips_namespace(self):
        self.assertEqual(core.normalize_model_name("library/llama3"), "llama3")
        self.assertEqual(core.normalize_model_name("library/llama3:latest"), "llama3")

    def test_lowercases_and_trims(self):
        self.assertEqual(core.normalize_model_name("  LLaMA3:Latest  "), "llama3")

    def test_untagged_name_is_unchanged(self):
        self.assertEqual(core.normalize_model_name("gpt-4o"), "gpt-4o")

    def test_empty_and_none_are_safe(self):
        self.assertEqual(core.normalize_model_name(""), "")
        self.assertEqual(core.normalize_model_name(None), "")


class TestEstimateEnergyFromTokens(unittest.TestCase):
    def test_tagged_ollama_name_no_longer_falls_through(self):
        # The regression this whole change exists for: before the fix this
        # returned the 0.01 default for every tagged model.
        tagged = core.estimate_energy_from_tokens("llama3.2:latest", 1000)
        self.assertAlmostEqual(tagged, core.MODEL_ENERGY_MAP["llama3"])
        self.assertNotAlmostEqual(tagged, core.DEFAULT_ENERGY_PER_1K_WH)

    def test_exact_family_match(self):
        for family, rate in core.MODEL_ENERGY_MAP.items():
            with self.subTest(family=family):
                self.assertAlmostEqual(
                    core.estimate_energy_from_tokens(family, 1000), rate
                )

    def test_point_release_inherits_family_rate(self):
        self.assertAlmostEqual(
            core.estimate_energy_from_tokens("llama3.1", 1000),
            core.MODEL_ENERGY_MAP["llama3"],
        )

    def test_longest_prefix_wins(self):
        # "gpt-4o" must not be matched by the shorter "gpt-4" prefix.
        self.assertAlmostEqual(
            core.estimate_energy_from_tokens("gpt-4o", 1000),
            core.MODEL_ENERGY_MAP["gpt-4o"],
        )
        self.assertNotAlmostEqual(
            core.estimate_energy_from_tokens("gpt-4o", 1000),
            core.MODEL_ENERGY_MAP["gpt-4"],
        )

    def test_unknown_model_uses_the_default(self):
        self.assertAlmostEqual(
            core.estimate_energy_from_tokens("nonesuch-9000", 1000),
            core.DEFAULT_ENERGY_PER_1K_WH,
        )

    def test_scales_linearly_with_tokens(self):
        one_k = core.estimate_energy_from_tokens("llama2", 1000)
        ten_k = core.estimate_energy_from_tokens("llama2", 10000)
        self.assertAlmostEqual(ten_k, one_k * 10)

    def test_zero_tokens_is_zero_energy(self):
        self.assertEqual(core.estimate_energy_from_tokens("llama2", 0), 0)

    def test_result_is_always_a_float_and_non_negative(self):
        for model in ("llama3.2:latest", "unknown", "gpt-4"):
            with self.subTest(model=model):
                v = core.estimate_energy_from_tokens(model, 500)
                self.assertIsInstance(v, float)
                self.assertGreaterEqual(v, 0.0)


def _ollama_response(status=200, payload=None):
    """Build a stand-in for the requests.Response returned by Ollama."""
    resp = mock.Mock()
    resp.status_code = status
    resp.text = "error body"
    resp.json.return_value = (
        payload
        if payload is not None
        else {
            "response": "an answer",
            "prompt_eval_count": 12,
            "eval_count": 30,
        }
    )
    return resp


class TestRunPrompt(unittest.TestCase):
    """run_prompt() with every external dependency stubbed out."""

    def setUp(self):
        patches = {
            "requests": mock.patch.object(core, "requests"),
            "measure": mock.patch.object(core, "measure_power_for_pid"),
            "has_gpu": mock.patch.object(core, "has_gpu", return_value=False),
            "sysinfo": mock.patch.object(
                core, "get_system_info", return_value={"OS": "Test"}
            ),
            "save": mock.patch.object(core, "save_prompt_usage"),
            "score": mock.patch.object(core, "score_prompt"),
        }
        self.m = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

        # requests.exceptions must stay real so the `except` clause is valid.
        self.m["requests"].exceptions = __import__("requests").exceptions
        self.m["requests"].post.return_value = _ollama_response()
        self.m["measure"].return_value = {
            "energy_wh": 0.5,
            "combined_power_w": 10.0,
            "cpu_power_w": 7.0,
            "gpu_power_w": 3.0,
            "baseline_energy_wh": 0.1,
            "baseline_power_w": 2.0,
        }
        self.m["score"].return_value = {
            "score_percent": 46.0,
            "details": {"Clarity": 5},
        }

    def test_score_prompt_is_called_exactly_once(self):
        """The defect: two calls built two adjacent fields of the same dict."""
        core.run_prompt("a prompt", model="llama3.2:latest", monitor=None)
        self.m["score"].assert_called_once_with("a prompt")

    def test_score_fields_come_from_the_single_call(self):
        result = core.run_prompt("a prompt", model="llama3.2:latest", monitor=None)
        self.assertEqual(result["prompt_score"], 46.0)
        self.assertEqual(result["prompt_score_details"], {"Clarity": 5})

    def test_measured_power_is_passed_through(self):
        result = core.run_prompt("a prompt", monitor=None)
        self.assertEqual(result["total_energy (Wh)"], 0.5)
        self.assertEqual(result["cpu_power_w (W)"], 7.0)
        self.assertEqual(result["gpu_power_w (W)"], 3.0)
        self.assertEqual(result["baseline_power (W)"], 2.0)

    def test_token_counts_come_from_the_ollama_payload(self):
        result = core.run_prompt("a prompt", monitor=None)
        self.assertEqual(result["prompt_tokens"], 12)
        self.assertEqual(result["completion_tokens"], 30)
        self.assertEqual(result["total_tokens"], 42)

    def test_token_estimate_uses_the_tagged_model(self):
        result = core.run_prompt("a prompt", model="llama3.2:latest", monitor=None)
        self.assertAlmostEqual(
            result["energy_estimate_tokens"],
            core.estimate_energy_from_tokens("llama3.2:latest", 42),
        )
        # And that is not the fallback rate, which is the point of the fix.
        self.assertNotAlmostEqual(
            result["energy_estimate_tokens"], 42 / 1000 * core.DEFAULT_ENERGY_PER_1K_WH
        )

    def test_missing_power_data_degrades_to_zero(self):
        self.m["measure"].return_value = {"error": "no samples"}
        result = core.run_prompt("a prompt", monitor=None)
        self.assertEqual(result["total_energy (Wh)"], 0)
        self.assertEqual(result["combined_power_w (W)"], 0)

    def test_result_is_persisted(self):
        core.run_prompt("a prompt", monitor=None)
        self.m["save"].assert_called_once()

    def test_a_save_failure_does_not_lose_the_result(self):
        self.m["save"].side_effect = RuntimeError("disk full")
        result = core.run_prompt("a prompt", monitor=None)
        self.assertEqual(result["response"], "an answer")

    def test_non_200_from_ollama_raises(self):
        self.m["requests"].post.return_value = _ollama_response(status=500)
        with self.assertRaises(RuntimeError):
            core.run_prompt("a prompt", monitor=None)

    def test_connection_error_raises_runtimeerror(self):
        import requests as real_requests

        self.m["requests"].post.side_effect = real_requests.exceptions.ConnectionError()
        with self.assertRaises(RuntimeError):
            core.run_prompt("a prompt", monitor=None)


if __name__ == "__main__":
    unittest.main()
