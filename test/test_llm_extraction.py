"""Tests for LLM-backed claim extraction (i15).

Tests the LLM extraction path using mock responses,
plus the hybrid auto/heuristic/llm mode selection and
JSON parsing edge cases.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Set up paths
LOOM_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LOOM_DIR)
sys.path.insert(0, os.path.join(
    os.path.expanduser("~"), "grove", "python"))

from workers.extractor.worker import (
    ExtractorWorker,
    _parse_llm_claims,
    extract_claims_llm,
    _resolve_model,
    _EXTRACTION_SYSTEM,
)


class MockHandle:
    def __init__(self, params):
        self.params = params


# Sample LLM output (valid JSON array)
SAMPLE_LLM_OUTPUT = json.dumps([
    {
        "statement": "The city population grew 12% in 2025",
        "category": "statistical",
        "entities": [
            {"name": "12%", "type": "number"},
            {"name": "2025", "type": "date"},
        ],
        "confidence_hint": 0.8,
    },
    {
        "statement": "Mayor Johnson approved the budget",
        "category": "factual",
        "entities": [
            {"name": "Mayor Johnson", "type": "person"},
        ],
        "confidence_hint": 0.9,
    },
    {
        "statement": "The new park covers 50 acres",
        "category": "factual",
        "entities": [
            {"name": "50 acres", "type": "number"},
        ],
        "confidence_hint": 0.7,
    },
])

# LLM output wrapped in markdown fences
FENCED_LLM_OUTPUT = f"```json\n{SAMPLE_LLM_OUTPUT}\n```"


class TestParseLLMClaims(unittest.TestCase):
    """Test JSON parsing of LLM output."""

    def test_parse_valid_json(self):
        claims = _parse_llm_claims(SAMPLE_LLM_OUTPUT)
        self.assertEqual(len(claims), 3)
        self.assertEqual(
            claims[0]["statement"],
            "The city population grew 12% in 2025",
        )
        self.assertEqual(claims[0]["category"], "statistical")
        self.assertEqual(
            claims[0]["extraction_method"], "llm")

    def test_parse_fenced_json(self):
        """Handles markdown code fences around JSON."""
        claims = _parse_llm_claims(FENCED_LLM_OUTPUT)
        self.assertEqual(len(claims), 3)

    def test_parse_empty_string(self):
        claims = _parse_llm_claims("")
        self.assertEqual(claims, [])

    def test_parse_none(self):
        claims = _parse_llm_claims(None)
        self.assertEqual(claims, [])

    def test_parse_invalid_json(self):
        claims = _parse_llm_claims("not json at all")
        self.assertEqual(claims, [])

    def test_parse_non_array(self):
        claims = _parse_llm_claims('{"not": "array"}')
        self.assertEqual(claims, [])

    def test_parse_filters_short_statements(self):
        """Statements under 10 chars are filtered."""
        data = json.dumps([
            {"statement": "Short", "category": "factual"},
            {"statement": "This is a valid claim statement",
             "category": "factual"},
        ])
        claims = _parse_llm_claims(data)
        self.assertEqual(len(claims), 1)
        self.assertIn("valid claim", claims[0]["statement"])

    def test_parse_handles_missing_fields(self):
        """Missing optional fields get defaults."""
        data = json.dumps([
            {"statement": "A claim with minimal fields"},
        ])
        claims = _parse_llm_claims(data)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["category"], "factual")
        self.assertEqual(claims[0]["entities"], [])
        self.assertEqual(
            claims[0]["confidence_hint"], 0.5)

    def test_parse_skips_non_dict_items(self):
        data = json.dumps([
            "not a dict",
            {"statement": "Valid claim about something"},
        ])
        claims = _parse_llm_claims(data)
        self.assertEqual(len(claims), 1)


class TestResolveModel(unittest.TestCase):
    """Test model resolution logic."""

    def test_explicit_loom_model(self):
        with patch.dict(
            os.environ, {"LOOM_MODEL": "test-model"}
        ):
            self.assertEqual(
                _resolve_model(), "test-model")

    def test_no_keys_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove all relevant keys.
            env = {
                k: v for k, v in os.environ.items()
                if k not in (
                    "LOOM_MODEL", "ANTHROPIC_API_KEY",
                    "GEMINI_API_KEY",
                )
            }
            with patch.dict(os.environ, env, clear=True):
                self.assertIsNone(_resolve_model())


class TestExtractClaimsLLM(unittest.TestCase):
    """Test the extract_claims_llm function."""

    @patch("workers.extractor.worker._call_llm")
    def test_successful_extraction(self, mock_call):
        mock_call.return_value = (
            SAMPLE_LLM_OUTPUT, None)
        claims, err = extract_claims_llm(
            "Some content about the city",
            model_name="test-model",
        )
        self.assertIsNone(err)
        self.assertEqual(len(claims), 3)
        mock_call.assert_called_once()

    @patch("workers.extractor.worker._call_llm")
    def test_llm_error_returns_empty(self, mock_call):
        mock_call.return_value = (
            None, "API error: timeout")
        claims, err = extract_claims_llm(
            "Content", model_name="test-model",
        )
        self.assertEqual(claims, [])
        self.assertIn("timeout", err)

    def test_no_model_returns_error(self):
        with patch.dict(os.environ, {}, clear=True):
            env = {
                k: v for k, v in os.environ.items()
                if k not in (
                    "LOOM_MODEL", "ANTHROPIC_API_KEY",
                    "GEMINI_API_KEY",
                )
            }
            with patch.dict(os.environ, env, clear=True):
                claims, err = extract_claims_llm("Content")
                self.assertEqual(claims, [])
                self.assertIn("no LLM model", err)

    @patch("workers.extractor.worker._call_llm")
    def test_max_claims_limit(self, mock_call):
        many_claims = json.dumps([
            {"statement": f"Claim number {i} is here"}
            for i in range(100)
        ])
        mock_call.return_value = (many_claims, None)
        claims, err = extract_claims_llm(
            "Content", model_name="test",
            max_claims=5,
        )
        self.assertIsNone(err)
        self.assertEqual(len(claims), 5)


class TestHybridExtraction(unittest.TestCase):
    """Test the hybrid auto/llm/heuristic mode."""

    def setUp(self):
        self.extractor = ExtractorWorker(
            worker_id="test")

    @patch("workers.extractor.worker.extract_claims_llm")
    def test_auto_uses_llm_when_available(self, mock_llm):
        mock_llm.return_value = (
            [
                {
                    "statement": "LLM extracted claim "
                                 "about the topic",
                    "category": "factual",
                    "excerpt": "LLM extracted claim "
                               "about the topic",
                    "entities": [],
                    "confidence_hint": 0.8,
                    "extraction_method": "llm",
                },
            ],
            None,
        )
        result = self.extractor.extract_claims(
            MockHandle({
                "content": "Some text about the topic.",
            })
        )
        self.assertEqual(
            result["extraction_method"], "llm")
        self.assertEqual(len(result["claims"]), 1)

    @patch("workers.extractor.worker.extract_claims_llm")
    def test_auto_falls_back_to_heuristic(self, mock_llm):
        mock_llm.return_value = (
            [], "no LLM model available")
        result = self.extractor.extract_claims(
            MockHandle({
                "content": (
                    "The United States has a population "
                    "of 340 million people. "
                    "The capital is Washington D.C."
                ),
            })
        )
        self.assertEqual(
            result["extraction_method"], "heuristic")
        self.assertGreaterEqual(
            len(result["claims"]), 1)

    def test_forced_heuristic_skips_llm(self):
        """extraction_method=heuristic never calls LLM."""
        result = self.extractor.extract_claims(
            MockHandle({
                "content": (
                    "The United States has a population "
                    "of 340 million people."
                ),
                "extraction_method": "heuristic",
            })
        )
        self.assertEqual(
            result["extraction_method"], "heuristic")

    @patch("workers.extractor.worker.extract_claims_llm")
    def test_forced_llm_returns_error(self, mock_llm):
        mock_llm.return_value = (
            [], "no LLM model available")
        result = self.extractor.extract_claims(
            MockHandle({
                "content": "Some text here.",
                "extraction_method": "llm",
            })
        )
        self.assertIn("error", result)
        self.assertEqual(len(result["claims"]), 0)

    @patch("workers.extractor.worker.extract_claims_llm")
    def test_llm_error_field_populated(self, mock_llm):
        mock_llm.return_value = (
            [], "API rate limited")
        result = self.extractor.extract_claims(
            MockHandle({
                "content": (
                    "The population of Springfield "
                    "is 50000 residents."
                ),
            })
        )
        # Should fall back to heuristic.
        self.assertEqual(
            result["extraction_method"], "heuristic")
        self.assertEqual(
            result["llm_error"], "API rate limited")


class TestExtractionMethodField(unittest.TestCase):
    """Verify extraction_method is always present."""

    def setUp(self):
        self.extractor = ExtractorWorker(
            worker_id="test")

    def test_heuristic_claims_have_method(self):
        result = self.extractor.extract_claims(
            MockHandle({
                "content": (
                    "The Federal Reserve raised interest "
                    "rates by 0.25 percent."
                ),
                "extraction_method": "heuristic",
            })
        )
        for claim in result["claims"]:
            self.assertEqual(
                claim["extraction_method"], "heuristic")


if __name__ == "__main__":
    unittest.main()
