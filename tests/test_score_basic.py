"""
test_score_basic.py — unit tests for the offline prompt scorer.

scoreBasic.py is the most user-visible logic in the project — 18 scoring
dimensions behind `greenprompt score` — and had no test coverage at all.

Two things are pinned here:

  * **Lazy corpora.** Four `nltk.download()` calls used to run at import time,
    and `cli.py` imports this module unconditionally, so every command
    including `--help` attempted four network round-trips before printing
    anything. Downloads must now happen on demand and only when data is
    genuinely missing.
  * **Scoring behaviour.** The dimension set, the score arithmetic, the
    ordering property that a well-formed prompt outscores a bare one, and that
    a bare imperative is credited regardless of which verb opens it.
"""

import importlib
import unittest
from unittest import mock

from greenprompt import scoreBasic


class TestLazyNltkData(unittest.TestCase):
    def setUp(self):
        # Each test decides for itself whether the data is "already present".
        self._saved = scoreBasic._nltk_data_ready
        self.addCleanup(lambda: setattr(scoreBasic, "_nltk_data_ready", self._saved))

    def test_importing_the_module_downloads_nothing(self):
        """The regression: `greenprompt --help` used to hit the network."""
        with mock.patch("nltk.download") as download:
            importlib.reload(scoreBasic)
        download.assert_not_called()

    def test_present_resources_are_not_redownloaded(self):
        scoreBasic._nltk_data_ready = False
        with mock.patch("nltk.data.find"), mock.patch("nltk.download") as download:
            scoreBasic.ensure_nltk_data()
        download.assert_not_called()

    def test_only_the_missing_resource_is_downloaded(self):
        scoreBasic._nltk_data_ready = False

        def find(path):
            if path == "corpora/stopwords":
                raise LookupError(path)

        with (
            mock.patch("nltk.data.find", side_effect=find),
            mock.patch("nltk.download") as download,
        ):
            scoreBasic.ensure_nltk_data()

        self.assertEqual(download.call_count, 1)
        self.assertEqual(download.call_args[0][0], "stopwords")

    def test_result_is_memoized(self):
        scoreBasic._nltk_data_ready = False
        with mock.patch("nltk.data.find") as find:
            scoreBasic.ensure_nltk_data()
            calls_after_first = find.call_count
            scoreBasic.ensure_nltk_data()
        self.assertEqual(find.call_count, calls_after_first)

    def test_force_rechecks(self):
        scoreBasic._nltk_data_ready = True
        with mock.patch("nltk.data.find") as find:
            scoreBasic.ensure_nltk_data(force=True)
        self.assertGreater(find.call_count, 0)

    def test_every_resource_has_a_lookup_path(self):
        for name, path in scoreBasic._NLTK_RESOURCES:
            with self.subTest(name=name):
                self.assertTrue(name and path)
                self.assertIn("/", path)

    def test_scoring_ensures_data_first(self):
        scoreBasic._nltk_data_ready = False
        with mock.patch.object(scoreBasic, "ensure_nltk_data") as ensure:
            # Guard the rest of the pipeline so only the ordering is observed.
            with (
                mock.patch.object(scoreBasic, "get_verbs", return_value=["explain"]),
                mock.patch.object(scoreBasic, "count_unique_keywords", return_value=5),
            ):
                scoreBasic.score_prompt("Explain inertia.")
        ensure.assert_called()


#: A prompt that deliberately exercises many dimensions at once.
RICH_PROMPT = (
    "You are an experienced physics tutor. Explain the concept of inertia to a "
    "first-year student, given that they already understand velocity. "
    "Format: three bullet points. For example, reference a car braking. "
    "Step 1: define it. Step 2: give the example. "
    "Do not use jargon. Use a friendly, encouraging tone. "
    "Set temperature to 0.2 for a deterministic answer. "
    "Verify the explanation against the textbook definition. "
    "Use inclusive, unbiased language. Keep the response concise to save energy."
)

BARE_PROMPT = "inertia"


class TestScorePromptContract(unittest.TestCase):
    def test_returns_the_documented_keys(self):
        result = scoreBasic.score_prompt(RICH_PROMPT)
        self.assertEqual(
            set(result), {"total_score", "max_score", "score_percent", "details"}
        )

    def test_max_score_is_fifty(self):
        self.assertEqual(scoreBasic.score_prompt(BARE_PROMPT)["max_score"], 50)

    def test_percent_is_consistent_with_the_total(self):
        result = scoreBasic.score_prompt(RICH_PROMPT)
        expected = result["total_score"] / result["max_score"] * 100
        self.assertAlmostEqual(result["score_percent"], expected)

    def test_total_equals_the_sum_of_the_details(self):
        result = scoreBasic.score_prompt(RICH_PROMPT)
        self.assertEqual(result["total_score"], sum(result["details"].values()))

    def test_score_stays_within_bounds(self):
        for prompt in (RICH_PROMPT, BARE_PROMPT, "Summarize this."):
            with self.subTest(prompt=prompt[:20]):
                result = scoreBasic.score_prompt(prompt)
                self.assertGreaterEqual(result["total_score"], 0)
                self.assertLessEqual(result["total_score"], result["max_score"])
                self.assertGreaterEqual(result["score_percent"], 0.0)
                self.assertLessEqual(result["score_percent"], 100.0)

    def test_reports_eighteen_dimensions(self):
        details = scoreBasic.score_prompt(RICH_PROMPT)["details"]
        self.assertEqual(len(details), 18)

    def test_every_dimension_score_is_a_non_negative_int(self):
        for name, value in scoreBasic.score_prompt(RICH_PROMPT)["details"].items():
            with self.subTest(dimension=name):
                self.assertIsInstance(value, int)
                self.assertGreaterEqual(value, 0)

    def test_is_deterministic(self):
        self.assertEqual(
            scoreBasic.score_prompt(RICH_PROMPT), scoreBasic.score_prompt(RICH_PROMPT)
        )


class TestScoringBehaviour(unittest.TestCase):
    def test_a_well_formed_prompt_outscores_a_bare_one(self):
        rich = scoreBasic.score_prompt(RICH_PROMPT)["total_score"]
        bare = scoreBasic.score_prompt(BARE_PROMPT)["total_score"]
        self.assertGreater(rich, bare)

    def test_role_is_credited(self):
        with_role = scoreBasic.score_prompt("You are a physics tutor. Explain inertia.")
        without = scoreBasic.score_prompt("Explain inertia.")
        self.assertGreaterEqual(
            with_role["details"]["RTCF Structure"], without["details"]["RTCF Structure"]
        )

    def test_output_format_is_credited(self):
        formatted = scoreBasic.score_prompt("Explain inertia. Format: bullet points.")
        self.assertGreater(formatted["details"]["Output Specification"], 0)

    def test_energy_awareness_is_credited(self):
        result = scoreBasic.score_prompt(
            "Explain inertia. Keep it short to reduce the carbon footprint."
        )
        self.assertGreater(result["details"]["Energy Awareness"], 0)

    def test_energy_awareness_misses_the_phrase_energy_consumption(self):
        """
        Documents a gap rather than asserting desired behaviour.

        energy_awareness() matches the literal "energy usage", so the equally
        natural "energy consumption" scores zero. Out of scope for the
        correctness pass this file accompanies; captured so the limitation is
        visible and a future fix shows up as a failing test.
        """
        result = scoreBasic.score_prompt(
            "Explain inertia. Keep it short to reduce energy consumption."
        )
        self.assertEqual(result["details"]["Energy Awareness"], 0)

    def test_empty_prompt_does_not_crash(self):
        result = scoreBasic.score_prompt("")
        self.assertEqual(result["max_score"], 50)
        self.assertGreaterEqual(result["total_score"], 0)

    def test_whitespace_only_prompt_does_not_crash(self):
        self.assertGreaterEqual(scoreBasic.score_prompt("   \n\t ")["total_score"], 0)

    def test_very_long_prompt_does_not_crash(self):
        result = scoreBasic.score_prompt("Explain inertia. " * 500)
        self.assertLessEqual(result["total_score"], 50)


class TestHelpers(unittest.TestCase):
    def test_normalize_collapses_whitespace_and_lowercases(self):
        self.assertEqual(scoreBasic.normalize("  Hello   WORLD \n"), "hello world")

    def test_has_explicit_role(self):
        for text in ("you are a tutor", "act as a reviewer", "role: editor"):
            with self.subTest(text=text):
                self.assertTrue(scoreBasic.has_explicit_role(text))
        self.assertFalse(scoreBasic.has_explicit_role("what is inertia"))

    def test_has_explicit_task_detects_action_verbs(self):
        self.assertTrue(scoreBasic.has_explicit_task("summarize this article"))

    def test_has_format(self):
        self.assertTrue(scoreBasic.has_format("format: bullet points"))

    def test_count_unique_keywords_excludes_stopwords(self):
        # "the" and "of" are stopwords and must not be counted.
        count = scoreBasic.count_unique_keywords("the concept of inertia")
        self.assertEqual(count, 2)

    def test_count_unique_keywords_deduplicates(self):
        self.assertEqual(scoreBasic.count_unique_keywords("inertia inertia inertia"), 1)

    def test_get_verbs_returns_verbs(self):
        verbs = [v.lower() for v in scoreBasic.get_verbs("Please explain inertia.")]
        self.assertIn("explain", verbs)

    def test_bare_imperatives_are_detected(self):
        """
        Every one of these returned no verbs before the imperative fix, so the
        prompt lost 3 points on Instructional Tone and 1 on RTCF Structure.
        """
        for prompt, verb in [
            ("Explain inertia.", "explain"),
            ("List three benefits of solar energy.", "list"),
            ("Generate five ideas.", "generate"),
            ("Define entropy.", "define"),
            ("Summarize this article.", "summarize"),
            ("Write a haiku about the sea.", "write"),
        ]:
            with self.subTest(prompt=prompt):
                self.assertIn(verb, [v.lower() for v in scoreBasic.get_verbs(prompt)])
                details = scoreBasic.score_prompt(prompt)["details"]
                self.assertEqual(details["Instructional Tone"], 3)
                self.assertGreaterEqual(details["RTCF Structure"], 1)

    def test_imperative_detection_is_verb_independent(self):
        """
        The defect was that crediting depended on *which* verb opened the
        prompt. Two prompts of identical structure must now score identically.
        """
        a = scoreBasic.score_prompt("Summarize this article.")  # tagger got this right
        b = scoreBasic.score_prompt("Explain this article.")  # tagger got this wrong
        self.assertEqual(
            a["details"]["Instructional Tone"], b["details"]["Instructional Tone"]
        )
        self.assertEqual(a["details"]["RTCF Structure"], b["details"]["RTCF Structure"])

    def test_non_imperative_openings_are_not_credited_as_tasks(self):
        # A question is not a task; the imperative path must not fire.
        self.assertFalse(scoreBasic.has_explicit_task("What is inertia?"))
        self.assertFalse(scoreBasic.has_explicit_task("The cat sat on the mat."))

    def test_imperative_is_found_in_a_later_sentence(self):
        verbs = [
            v.lower() for v in scoreBasic.get_verbs("You are a tutor. Explain inertia.")
        ]
        self.assertIn("explain", verbs)

    def test_imperative_is_found_after_a_newline(self):
        verbs = [
            v.lower()
            for v in scoreBasic.get_verbs("Context: physics\nList three laws.")
        ]
        self.assertIn("list", verbs)

    def test_verbs_are_not_duplicated(self):
        # "Summarize" is found by both the tagger and the imperative pass.
        verbs = [v.lower() for v in scoreBasic.get_verbs("Summarize this article.")]
        self.assertEqual(len(verbs), len(set(verbs)))

    def test_sentence_initial_noun_is_not_treated_as_a_verb(self):
        self.assertEqual(
            scoreBasic._sentence_initial_imperatives("Inertia is a concept."), []
        )

    def test_known_false_positive_is_accepted(self):
        """
        Documents an accepted trade rather than desired behaviour: a
        sentence-initial noun that is spelled like an instruction verb is
        credited. The alternative — parsing well enough to tell them apart —
        is not available to a regex-and-POS scorer.
        """
        self.assertEqual(
            scoreBasic._sentence_initial_imperatives("List of items follows."), ["List"]
        )

    def test_empty_and_punctuation_only_text_is_safe(self):
        for text in ("", "   ", "...", "!?"):
            with self.subTest(text=text):
                self.assertEqual(scoreBasic._sentence_initial_imperatives(text), [])

    def test_task_detection_uses_the_shared_vocabulary(self):
        # has_explicit_task must not keep a private list that can drift.
        self.assertTrue(scoreBasic.has_explicit_task("Refactor this function."))
        self.assertIn("refactor", scoreBasic.INSTRUCTION_VERBS)

    def test_instruction_verbs_are_all_lowercase(self):
        # Lookups are done on .lower(), so an uppercase entry would be dead.
        for verb in scoreBasic.INSTRUCTION_VERBS:
            with self.subTest(verb=verb):
                self.assertEqual(verb, verb.lower())

    def test_original_core_task_verbs_are_all_retained(self):
        """The pre-existing vocabulary must not have been lost in the merge."""
        original = {
            "summarize",
            "list",
            "explain",
            "describe",
            "define",
            "compare",
            "generate",
            "analyze",
            "write",
            "compose",
            "translate",
            "solve",
            "classify",
            "extract",
            "categorize",
            "review",
            "evaluate",
        }
        self.assertTrue(original.issubset(scoreBasic.INSTRUCTION_VERBS))


if __name__ == "__main__":
    unittest.main()
