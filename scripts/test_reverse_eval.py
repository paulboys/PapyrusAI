#!/usr/bin/env python3
"""Tests for reverse_eval.py."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import reverse_eval as re_eval


# ---------------------------------------------------------------------------
# Sample fixture data
# ---------------------------------------------------------------------------

SAMPLE_TOKENS = [
    {"word": "Βίβλος", "lemma": "βίβλος", "gloss": "book", "morph": "N-NSF"},
    {"word": "γενέσεως", "lemma": "γένεσις", "gloss": "of-origin", "morph": "N-GSF"},
    {"word": "Ἰησοῦ", "lemma": "Ἰησοῦς", "gloss": "of-Jesus", "morph": "N-GSM-P"},
]

SAMPLE_VERSE = {"tokens": SAMPLE_TOKENS}

SAMPLE_INDEX = {
    "40.1.1": SAMPLE_VERSE,
    "40.1.2": {
        "tokens": [
            {"word": "Ἀβραὰμ", "lemma": "Ἀβραάμ", "gloss": "Abraham", "morph": "N-GSM-P"},
        ]
    },
    "43.3.16": {  # Famous verse — should be excluded by default
        "tokens": [
            {"word": "Οὕτως", "lemma": "οὕτως", "gloss": "so", "morph": "ADV"},
        ]
    },
}


# ---------------------------------------------------------------------------
# strip_accents
# ---------------------------------------------------------------------------

class TestStripAccents(unittest.TestCase):
    def test_plain_ascii_unchanged(self):
        self.assertEqual(re_eval.strip_accents("hello"), "hello")

    def test_removes_greek_accents(self):
        result = re_eval.strip_accents("Βίβλος")
        self.assertNotIn("\u0301", result)  # no combining acute
        self.assertIn("Β", result)

    def test_empty_string(self):
        self.assertEqual(re_eval.strip_accents(""), "")

    def test_idempotent(self):
        once = re_eval.strip_accents("γένεσις")
        twice = re_eval.strip_accents(once)
        self.assertEqual(once, twice)


# ---------------------------------------------------------------------------
# levenshtein
# ---------------------------------------------------------------------------

class TestLevenshtein(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(re_eval.levenshtein("abc", "abc"), 0)

    def test_empty_strings(self):
        self.assertEqual(re_eval.levenshtein("", ""), 0)

    def test_one_empty(self):
        self.assertEqual(re_eval.levenshtein("abc", ""), 3)
        self.assertEqual(re_eval.levenshtein("", "abc"), 3)

    def test_single_substitution(self):
        self.assertEqual(re_eval.levenshtein("abc", "axc"), 1)

    def test_single_insertion(self):
        self.assertEqual(re_eval.levenshtein("ab", "abc"), 1)

    def test_single_deletion(self):
        self.assertEqual(re_eval.levenshtein("abc", "ac"), 1)

    def test_symmetric(self):
        a, b = "kitten", "sitting"
        self.assertEqual(re_eval.levenshtein(a, b), re_eval.levenshtein(b, a))

    def test_known_distance(self):
        # "kitten" → "sitting" = 3 substitutions
        self.assertEqual(re_eval.levenshtein("kitten", "sitting"), 3)

    def test_greek_forms(self):
        # Same word with/without accent should be 1 char apart at most
        d = re_eval.levenshtein("Βίβλος", "Βιβλος")
        self.assertLessEqual(d, 2)


# ---------------------------------------------------------------------------
# build_*_prompt helpers
# ---------------------------------------------------------------------------

class TestBuildPrompts(unittest.TestCase):
    def test_tier1_contains_lemma(self):
        prompt = re_eval.build_tier1_prompt(SAMPLE_VERSE)
        self.assertIn("Lemma:", prompt)
        self.assertIn("βίβλος", prompt)
        self.assertIn("Morph:", prompt)
        self.assertIn("N-NSF", prompt)
        self.assertIn("book", prompt)

    def test_tier1_numbers_tokens(self):
        prompt = re_eval.build_tier1_prompt(SAMPLE_VERSE)
        for i in range(1, len(SAMPLE_TOKENS) + 1):
            self.assertIn(f"  {i}.", prompt)

    def test_tier2_no_lemma(self):
        prompt = re_eval.build_tier2_prompt(SAMPLE_VERSE)
        self.assertNotIn("Lemma:", prompt)
        self.assertIn("Morph:", prompt)
        self.assertIn("book", prompt)

    def test_tier3_glosses_only(self):
        prompt = re_eval.build_tier3_prompt(SAMPLE_VERSE)
        self.assertIn("book | of-origin | of-Jesus", prompt)
        self.assertNotIn("Morph:", prompt)
        self.assertNotIn("Lemma:", prompt)

    def test_build_prompt_dispatch(self):
        for tier, fn in [(1, re_eval.build_tier1_prompt),
                         (2, re_eval.build_tier2_prompt),
                         (3, re_eval.build_tier3_prompt)]:
            self.assertEqual(re_eval.build_prompt(SAMPLE_VERSE, tier),
                             fn(SAMPLE_VERSE))

    def test_build_prompt_invalid_tier(self):
        with self.assertRaises(ValueError):
            re_eval.build_prompt(SAMPLE_VERSE, 99)


# ---------------------------------------------------------------------------
# parse_numbered_response
# ---------------------------------------------------------------------------

class TestParseNumberedResponse(unittest.TestCase):
    def test_dot_format(self):
        text = "1. Βίβλος\n2. γενέσεως\n3. Ἰησοῦ"
        tokens = re_eval.parse_numbered_response(text, 3)
        self.assertEqual(tokens, ["Βίβλος", "γενέσεως", "Ἰησοῦ"])

    def test_paren_format(self):
        text = "1) Βίβλος\n2) γενέσεως"
        tokens = re_eval.parse_numbered_response(text, 2)
        self.assertEqual(tokens, ["Βίβλος", "γενέσεως"])

    def test_colon_format(self):
        text = "1: Βίβλος\n2: γενέσεως"
        tokens = re_eval.parse_numbered_response(text, 2)
        self.assertEqual(tokens, ["Βίβλος", "γενέσεως"])

    def test_strips_trailing_explanation(self):
        text = "1. Βίβλος - this means book\n2. γενέσεως (genitive)"
        tokens = re_eval.parse_numbered_response(text, 2)
        self.assertEqual(tokens[0], "Βίβλος")
        self.assertEqual(tokens[1], "γενέσεως")

    def test_strips_surrounding_quotes(self):
        text = '1. "Βίβλος"\n2. \'γενέσεως\''
        tokens = re_eval.parse_numbered_response(text, 2)
        self.assertEqual(tokens[0], "Βίβλος")
        self.assertEqual(tokens[1], "γενέσεως")

    def test_empty_input(self):
        tokens = re_eval.parse_numbered_response("", 3)
        self.assertEqual(tokens, [])

    def test_skips_blank_lines(self):
        text = "\n1. Βίβλος\n\n2. γενέσεως\n"
        tokens = re_eval.parse_numbered_response(text, 2)
        self.assertEqual(len(tokens), 2)


# ---------------------------------------------------------------------------
# parse_sentence_response
# ---------------------------------------------------------------------------

class TestParseSentenceResponse(unittest.TestCase):
    def test_basic_sentence(self):
        tokens = re_eval.parse_sentence_response("Βίβλος γενέσεως Ἰησοῦ")
        self.assertEqual(tokens, ["Βίβλος", "γενέσεως", "Ἰησοῦ"])

    def test_takes_first_line(self):
        tokens = re_eval.parse_sentence_response("Βίβλος γενέσεως\nSome explanation")
        self.assertEqual(tokens[0], "Βίβλος")
        self.assertNotIn("Some", tokens)

    def test_strips_punctuation(self):
        tokens = re_eval.parse_sentence_response("Βίβλος, γενέσεως.")
        self.assertIn("Βίβλος", tokens)
        self.assertIn("γενέσεως", tokens)

    def test_empty_input(self):
        tokens = re_eval.parse_sentence_response("")
        self.assertEqual(tokens, [])

    def test_non_greek_line_skipped(self):
        # Lines without letter characters are skipped
        tokens = re_eval.parse_sentence_response("---\nΒίβλος γενέσεως")
        self.assertIn("Βίβλος", tokens)


# ---------------------------------------------------------------------------
# score_token
# ---------------------------------------------------------------------------

class TestScoreToken(unittest.TestCase):
    def test_exact_match(self):
        s = re_eval.score_token("Βίβλος", "Βίβλος")
        self.assertTrue(s["exact_match"])
        self.assertEqual(s["edit_distance"], 0)

    def test_accent_stripped_match(self):
        stripped = re_eval.strip_accents("Βίβλος")
        s = re_eval.score_token(stripped, "Βίβλος")
        self.assertFalse(s["exact_match"])
        self.assertTrue(s["accent_stripped_match"])

    def test_mismatch(self):
        s = re_eval.score_token("wrong", "Βίβλος")
        self.assertFalse(s["exact_match"])
        self.assertFalse(s["accent_stripped_match"])
        self.assertGreater(s["edit_distance"], 0)

    def test_empty_prediction(self):
        s = re_eval.score_token("", "Βίβλος")
        self.assertFalse(s["exact_match"])
        self.assertEqual(s["predicted"], "")
        self.assertGreater(s["edit_distance"], 0)

    def test_none_prediction(self):
        s = re_eval.score_token(None, "Βίβλος")
        self.assertFalse(s["exact_match"])
        self.assertEqual(s["predicted"], "")

    def test_result_keys(self):
        s = re_eval.score_token("Βίβλος", "Βίβλος")
        for key in ("predicted", "ground_truth", "exact_match", "accent_stripped_match", "edit_distance"):
            self.assertIn(key, s)


# ---------------------------------------------------------------------------
# score_verse
# ---------------------------------------------------------------------------

class TestScoreVerse(unittest.TestCase):
    def _exact_predictions(self):
        return [t["word"] for t in SAMPLE_TOKENS]

    def test_perfect_score(self):
        result = re_eval.score_verse(self._exact_predictions(), SAMPLE_VERSE, tier=1)
        self.assertEqual(result["exact_matches"], 3)
        self.assertEqual(result["accent_stripped_matches"], 3)
        self.assertEqual(result["total_tokens"], 3)
        self.assertEqual(result["mean_edit_distance"], 0.0)

    def test_empty_predictions(self):
        result = re_eval.score_verse([], SAMPLE_VERSE, tier=1)
        self.assertEqual(result["exact_matches"], 0)
        self.assertEqual(result["total_tokens"], 3)
        self.assertEqual(result["predicted_count"], 0)

    def test_partial_predictions(self):
        result = re_eval.score_verse(["Βίβλος"], SAMPLE_VERSE, tier=1)
        self.assertEqual(result["exact_matches"], 1)
        self.assertEqual(result["total_tokens"], 3)

    def test_lemma_match_added_tier2(self):
        result = re_eval.score_verse(self._exact_predictions(), SAMPLE_VERSE, tier=2)
        for ts in result["token_scores"]:
            self.assertIn("lemma_match", ts)
            self.assertIsNotNone(ts["lemma_match"])

    def test_lemma_match_none_tier1(self):
        result = re_eval.score_verse(self._exact_predictions(), SAMPLE_VERSE, tier=1)
        for ts in result["token_scores"]:
            self.assertIsNone(ts["lemma_match"])

    def test_result_keys(self):
        result = re_eval.score_verse(self._exact_predictions(), SAMPLE_VERSE, tier=1)
        for key in ("token_scores", "total_tokens", "predicted_count",
                    "exact_matches", "accent_stripped_matches", "mean_edit_distance"):
            self.assertIn(key, result)


# ---------------------------------------------------------------------------
# sample_verses
# ---------------------------------------------------------------------------

class TestSampleVerses(unittest.TestCase):
    def test_excludes_famous(self):
        selected = re_eval.sample_verses(SAMPLE_INDEX, n=10, seed=42, exclude_famous=True)
        for k in selected:
            self.assertNotIn(k, re_eval.FAMOUS_VERSES)

    def test_includes_famous_when_requested(self):
        # With a small enough index, famous verse 43.3.16 can appear
        selected = re_eval.sample_verses(SAMPLE_INDEX, n=10, seed=42, exclude_famous=False)
        all_keys = set(SAMPLE_INDEX.keys())
        self.assertTrue(set(selected).issubset(all_keys))

    def test_n_capped_at_index_size(self):
        selected = re_eval.sample_verses(SAMPLE_INDEX, n=1000, seed=42)
        # Can't return more than available (non-famous) keys
        non_famous = [k for k in SAMPLE_INDEX if k not in re_eval.FAMOUS_VERSES]
        self.assertLessEqual(len(selected), len(non_famous))

    def test_reproducible_with_seed(self):
        a = re_eval.sample_verses(SAMPLE_INDEX, n=2, seed=7)
        b = re_eval.sample_verses(SAMPLE_INDEX, n=2, seed=7)
        self.assertEqual(a, b)

    def test_different_seeds_differ(self):
        # Only meaningful if index is large enough; with 2 non-famous keys
        # there may not be variation — just ensure no crash.
        re_eval.sample_verses(SAMPLE_INDEX, n=1, seed=1)
        re_eval.sample_verses(SAMPLE_INDEX, n=1, seed=99)


# ---------------------------------------------------------------------------
# cache_key
# ---------------------------------------------------------------------------

class TestCacheKey(unittest.TestCase):
    def test_returns_string(self):
        key = re_eval.cache_key("qwen2.5", "40.1.1", 2)
        self.assertIsInstance(key, str)

    def test_length_16(self):
        key = re_eval.cache_key("qwen2.5", "40.1.1", 2)
        self.assertEqual(len(key), 16)

    def test_deterministic(self):
        a = re_eval.cache_key("qwen2.5", "40.1.1", 2)
        b = re_eval.cache_key("qwen2.5", "40.1.1", 2)
        self.assertEqual(a, b)

    def test_different_inputs_different_keys(self):
        k1 = re_eval.cache_key("qwen2.5", "40.1.1", 1)
        k2 = re_eval.cache_key("qwen2.5", "40.1.1", 2)
        k3 = re_eval.cache_key("llama3.2", "40.1.1", 1)
        self.assertNotEqual(k1, k2)
        self.assertNotEqual(k1, k3)


# ---------------------------------------------------------------------------
# get_cached / save_cache
# ---------------------------------------------------------------------------

class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cache_dir = re_eval.CACHE_DIR
        re_eval.CACHE_DIR = self.tmpdir

    def tearDown(self):
        re_eval.CACHE_DIR = self.orig_cache_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_miss_returns_none(self):
        result = re_eval.get_cached("qwen2.5", "40.1.1", 2)
        self.assertIsNone(result)

    def test_save_then_get(self):
        re_eval.save_cache("qwen2.5", "40.1.1", 2, "Βίβλος γενέσεως", 1.5)
        cached = re_eval.get_cached("qwen2.5", "40.1.1", 2)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["response"], "Βίβλος γενέσεως")
        self.assertAlmostEqual(cached["elapsed"], 1.5)

    def test_cache_isolation_by_tier(self):
        re_eval.save_cache("qwen2.5", "40.1.1", 1, "tier1 response", 1.0)
        re_eval.save_cache("qwen2.5", "40.1.1", 2, "tier2 response", 2.0)
        c1 = re_eval.get_cached("qwen2.5", "40.1.1", 1)
        c2 = re_eval.get_cached("qwen2.5", "40.1.1", 2)
        self.assertEqual(c1["response"], "tier1 response")
        self.assertEqual(c2["response"], "tier2 response")


# ---------------------------------------------------------------------------
# load_index
# ---------------------------------------------------------------------------

class TestLoadIndex(unittest.TestCase):
    def test_load_valid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                        delete=False, encoding="utf-8") as f:
            json.dump(SAMPLE_INDEX, f, ensure_ascii=False)
            tmp_path = f.name
        try:
            loaded = re_eval.load_index(tmp_path)
            self.assertIn("40.1.1", loaded)
            self.assertEqual(loaded["40.1.1"]["tokens"][0]["word"], "Βίβλος")
        finally:
            os.unlink(tmp_path)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            re_eval.load_index("/nonexistent/path/verse_index.json")


# ---------------------------------------------------------------------------
# run_verse (mocked ollama_client)
# ---------------------------------------------------------------------------

class TestRunVerse(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cache_dir = re_eval.CACHE_DIR
        re_eval.CACHE_DIR = self.tmpdir

    def tearDown(self):
        re_eval.CACHE_DIR = self.orig_cache_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("reverse_eval.ollama_client")
    def test_calls_ollama_on_cache_miss(self, mock_client):
        mock_client.chat.return_value = "1. Βίβλος\n2. γενέσεως"
        response, elapsed, cache_hit = re_eval.run_verse(
            "qwen2.5", "40.1.1", SAMPLE_VERSE, tier=2
        )
        self.assertTrue(mock_client.chat.called)
        self.assertFalse(cache_hit)
        self.assertEqual(response, "1. Βίβλος\n2. γενέσεως")

    @patch("reverse_eval.ollama_client")
    def test_uses_cache_on_hit(self, mock_client):
        # Pre-populate cache
        re_eval.save_cache("qwen2.5", "40.1.1", 2, "cached response", 0.5)
        response, elapsed, cache_hit = re_eval.run_verse(
            "qwen2.5", "40.1.1", SAMPLE_VERSE, tier=2
        )
        mock_client.chat.assert_not_called()
        self.assertTrue(cache_hit)
        self.assertEqual(response, "cached response")

    @patch("reverse_eval.ollama_client")
    def test_no_cache_flag_bypasses_cache(self, mock_client):
        mock_client.chat.return_value = "fresh"
        re_eval.save_cache("qwen2.5", "40.1.1", 2, "stale", 0.1)
        response, _, cache_hit = re_eval.run_verse(
            "qwen2.5", "40.1.1", SAMPLE_VERSE, tier=2, no_cache=True
        )
        mock_client.chat.assert_called_once()
        self.assertFalse(cache_hit)
        self.assertEqual(response, "fresh")


# ---------------------------------------------------------------------------
# format_verse_report
# ---------------------------------------------------------------------------

class TestFormatVerseReport(unittest.TestCase):
    def _make_model_results(self, tier):
        predicted = [t["word"] for t in SAMPLE_TOKENS]
        score_data = re_eval.score_verse(predicted, SAMPLE_VERSE, tier=tier)
        return {"qwen2.5": ("1. Βίβλος\n2. γενέσεως\n3. Ἰησοῦ", score_data, 1.2, False)}

    def test_contains_verse_key(self):
        report = re_eval.format_verse_report(
            "40.1.1", SAMPLE_VERSE, self._make_model_results(1), tier=1
        )
        self.assertIn("40.1.1", report)

    def test_contains_ground_truth(self):
        report = re_eval.format_verse_report(
            "40.1.1", SAMPLE_VERSE, self._make_model_results(1), tier=1
        )
        self.assertIn("Βίβλος", report)
        self.assertIn("Ground truth", report)

    def test_tier_label_in_report(self):
        for tier in (1, 2, 3):
            report = re_eval.format_verse_report(
                "40.1.1", SAMPLE_VERSE, self._make_model_results(tier), tier=tier
            )
            self.assertIn(f"Tier {tier}", report)

    def test_contains_model_name(self):
        report = re_eval.format_verse_report(
            "40.1.1", SAMPLE_VERSE, self._make_model_results(2), tier=2
        )
        self.assertIn("qwen2.5", report)

    def test_score_table_present(self):
        report = re_eval.format_verse_report(
            "40.1.1", SAMPLE_VERSE, self._make_model_results(1), tier=1
        )
        self.assertIn("Ground Truth", report)
        self.assertIn("Predicted", report)


# ---------------------------------------------------------------------------
# format_summary_table
# ---------------------------------------------------------------------------

class TestFormatSummaryTable(unittest.TestCase):
    def _build_all_scores(self, tier):
        predicted = [t["word"] for t in SAMPLE_TOKENS]
        score_data = re_eval.score_verse(predicted, SAMPLE_VERSE, tier=tier)
        return {
            "40.1.1": {"qwen2.5": ("response", score_data, 2.5, False)}
        }

    def test_contains_model_name(self):
        table = re_eval.format_summary_table(
            self._build_all_scores(1), ["qwen2.5"], tier=1
        )
        self.assertIn("qwen2.5", table)

    def test_contains_tier(self):
        table = re_eval.format_summary_table(
            self._build_all_scores(2), ["qwen2.5"], tier=2
        )
        self.assertIn("Tier 2", table)

    def test_percentage_format(self):
        table = re_eval.format_summary_table(
            self._build_all_scores(1), ["qwen2.5"], tier=1
        )
        self.assertIn("%", table)

    def test_verse_count_shown(self):
        table = re_eval.format_summary_table(
            self._build_all_scores(1), ["qwen2.5"], tier=1
        )
        self.assertIn("1 verses", table)


if __name__ == "__main__":
    unittest.main()
