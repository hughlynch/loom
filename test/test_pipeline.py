"""End-to-end pipeline test: harvest → classify → corroborate → store.

Uses a golden fixture (pre-fetched .gov content) to exercise the full
pipeline without live HTTP requests. Tests that:
1. Classification assigns correct tier from domain
2. Corroboration computes deterministic confidence
3. KB stores claim with evidence and provenance
4. Stored claim is retrievable with full evidence chain
"""

import json
import os
import sys
import tempfile
import unittest

# Set up paths
LOOM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LOOM_DIR)
sys.path.insert(0, os.path.join(os.path.expanduser("~"), "grove", "python"))

from workers.harvester.worker import _compute_hash, _html_to_text
from workers.extractor.worker import (
    ExtractorWorker,
    _segment_sentences,
    _is_claim_candidate,
    _categorize_claim,
    _extract_entities,
)
from workers.classifier.worker import ClassifierWorker
from workers.corroborator.worker import (
    CorroboratorWorker,
    compute_confidence,
    compute_confidence_v2,
    STATUS_VERIFIED,
    STATUS_CORROBORATED,
    STATUS_REPORTED,
    STATUS_CONTESTED,
    STATUS_UNVERIFIED,
    CREDIBILITY_MODIFIERS,
)
from workers.kb.worker import LoomKBWorker
from workers.adjudicator.worker import AdjudicatorWorker


class MockHandle:
    """Mock grove skill handle for direct worker testing."""

    def __init__(self, params):
        self.params = params


def load_fixture(name):
    """Load a golden fixture by name."""
    path = os.path.join(LOOM_DIR, "test", "fixtures", f"{name}.json")
    with open(path) as f:
        return json.load(f)


class TestConfidenceRules(unittest.TestCase):
    """Test the deterministic confidence computation rules."""

    def test_verified_t1(self):
        score = compute_confidence(STATUS_VERIFIED, "T1")
        self.assertGreaterEqual(score, 0.95)
        self.assertLessEqual(score, 1.0)

    def test_verified_t2(self):
        score = compute_confidence(STATUS_VERIFIED, "T2")
        self.assertGreaterEqual(score, 0.85)
        self.assertLessEqual(score, 0.95)

    def test_corroborated_boost(self):
        base = compute_confidence(STATUS_CORROBORATED, "T3", 1)
        boosted = compute_confidence(STATUS_CORROBORATED, "T3", 3)
        self.assertGreater(boosted, base)

    def test_corroboration_diminishing_returns(self):
        boost_2 = compute_confidence(STATUS_CORROBORATED, "T3", 2)
        boost_5 = compute_confidence(STATUS_CORROBORATED, "T3", 5)
        boost_10 = compute_confidence(STATUS_CORROBORATED, "T3", 10)
        # Diminishing returns: gap between 2→5 > gap between 5→10
        gap_early = boost_5 - boost_2
        gap_late = boost_10 - boost_5
        self.assertGreaterEqual(gap_early, gap_late)

    def test_contested_uses_floor(self):
        score = compute_confidence(STATUS_CONTESTED, "T3")
        # Contested uses floor of range (0.20)
        self.assertAlmostEqual(score, 0.20, places=2)

    def test_unverified_t7_is_lowest(self):
        score = compute_confidence(STATUS_UNVERIFIED, "T7")
        self.assertLessEqual(score, 0.05)

    def test_tier_ordering(self):
        """Higher tiers should produce higher confidence at same status."""
        tiers = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
        for status in [STATUS_REPORTED, STATUS_CORROBORATED]:
            scores = [compute_confidence(status, t) for t in tiers]
            for i in range(len(scores) - 1):
                self.assertGreaterEqual(
                    scores[i], scores[i + 1],
                    f"{status}: {tiers[i]} ({scores[i]}) should >= "
                    f"{tiers[i+1]} ({scores[i+1]})"
                )


class TestConfidenceV2(unittest.TestCase):
    """Test dual-axis confidence computation with GRADE adjustments."""

    def test_credibility_modifier_reduces_confidence(self):
        """C5 (improbable) should significantly reduce confidence."""
        r1 = compute_confidence_v2(STATUS_VERIFIED, "T1", info_credibility="C1")
        r5 = compute_confidence_v2(STATUS_VERIFIED, "T1", info_credibility="C5")
        self.assertGreater(r1["final_confidence"], r5["final_confidence"])
        # C1 modifier is 1.0, C5 is 0.15 — big difference
        self.assertGreater(r1["final_confidence"], 0.90)
        self.assertLess(r5["final_confidence"], 0.20)

    def test_c6_is_neutral(self):
        """C6 (cannot assess) uses 0.50 modifier — neutral."""
        result = compute_confidence_v2(STATUS_REPORTED, "T3", info_credibility="C6")
        base = result["base_confidence"]
        self.assertAlmostEqual(
            result["credibility_adjusted"], base * 0.50, places=3
        )

    def test_grade_down_reduces(self):
        """GRADE down-adjustments reduce final confidence."""
        no_adj = compute_confidence_v2(STATUS_CORROBORATED, "T2", info_credibility="C1")
        with_adj = compute_confidence_v2(
            STATUS_CORROBORATED, "T2", info_credibility="C1",
            grade_adjustments=[
                {"factor": "risk_of_bias", "direction": "down", "magnitude": 0.10},
                {"factor": "inconsistency", "direction": "down", "magnitude": 0.05},
            ],
        )
        self.assertGreater(no_adj["final_confidence"], with_adj["final_confidence"])
        self.assertAlmostEqual(with_adj["grade_delta"], -0.15, places=3)

    def test_grade_up_increases(self):
        """GRADE up-adjustments increase final confidence."""
        base_result = compute_confidence_v2(STATUS_REPORTED, "T4", info_credibility="C2")
        boosted = compute_confidence_v2(
            STATUS_REPORTED, "T4", info_credibility="C2",
            grade_adjustments=[
                {"factor": "large_effect", "direction": "up", "magnitude": 0.10},
            ],
        )
        self.assertGreater(boosted["final_confidence"], base_result["final_confidence"])

    def test_analytic_confidence_levels(self):
        """Analytic confidence maps to IPCC-style labels."""
        high = compute_confidence_v2(STATUS_VERIFIED, "T1", info_credibility="C1")
        self.assertEqual(high["analytic_confidence"], "very_high")

        low = compute_confidence_v2(STATUS_UNVERIFIED, "T7", info_credibility="C5")
        self.assertEqual(low["analytic_confidence"], "low")

    def test_floor_at_001(self):
        """Final confidence never drops below 0.01."""
        result = compute_confidence_v2(
            STATUS_UNVERIFIED, "T7", info_credibility="C5",
            grade_adjustments=[
                {"factor": "risk_of_bias", "direction": "down", "magnitude": 0.50},
            ],
        )
        self.assertGreaterEqual(result["final_confidence"], 0.01)

    def test_returns_all_fields(self):
        """V2 result dict contains all expected fields."""
        result = compute_confidence_v2(STATUS_REPORTED, "T3")
        expected_keys = {
            "base_confidence", "credibility_modifier", "credibility_adjusted",
            "grade_delta", "final_confidence", "analytic_confidence", "adjustments",
        }
        self.assertEqual(set(result.keys()), expected_keys)


class TestClassification(unittest.TestCase):
    """Test source tier classification."""

    def setUp(self):
        self.classifier = ClassifierWorker(worker_id="test-classifier")

    def test_gov_domain_is_t1(self):
        result = self.classifier.classify_source_tier(
            MockHandle({"url": "https://www.census.gov/data/"})
        )
        self.assertEqual(result["tier"], "T1")
        self.assertTrue(result["domain_verified"])

    def test_edu_domain_is_t2(self):
        result = self.classifier.classify_source_tier(
            MockHandle({"url": "https://www.mit.edu/research/"})
        )
        self.assertEqual(result["tier"], "T2")
        self.assertTrue(result["domain_verified"])

    def test_generic_domain_is_t5(self):
        result = self.classifier.classify_source_tier(
            MockHandle({"url": "https://www.example.com/blog/post"})
        )
        self.assertEqual(result["tier"], "T5")
        self.assertFalse(result["domain_verified"])

    def test_mil_domain_is_t1(self):
        result = self.classifier.classify_source_tier(
            MockHandle({"url": "https://www.defense.mil/news/"})
        )
        self.assertEqual(result["tier"], "T1")

    def test_t3_news_domain(self):
        for domain in ["apnews.com", "reuters.com", "bbc.com", "nytimes.com"]:
            result = self.classifier.classify_source_tier(
                MockHandle({"url": f"https://www.{domain}/article/123"})
            )
            self.assertEqual(result["tier"], "T3", f"{domain} should be T3")
            self.assertTrue(result["domain_verified"])

    def test_t4_expert_domain(self):
        for domain in ["nature.com", "arxiv.org", "pewresearch.org"]:
            result = self.classifier.classify_source_tier(
                MockHandle({"url": f"https://{domain}/paper/456"})
            )
            self.assertEqual(result["tier"], "T4", f"{domain} should be T4")

    def test_t6_social_domain(self):
        for domain in ["reddit.com", "twitter.com", "medium.com"]:
            result = self.classifier.classify_source_tier(
                MockHandle({"url": f"https://www.{domain}/post/789"})
            )
            self.assertEqual(result["tier"], "T6", f"{domain} should be T6")

    def test_missing_url_errors(self):
        result = self.classifier.classify_source_tier(
            MockHandle({"url": ""})
        )
        self.assertIn("error", result)


class TestKBStorage(unittest.TestCase):
    """Test knowledge base storage and retrieval."""

    def setUp(self):
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(
            suffix=".db", delete=False
        )
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _params(self, **kwargs):
        kwargs["db_path"] = self.db_path
        return MockHandle(kwargs)

    def test_store_and_query(self):
        # Store a claim
        result = self.kb.kb_store_claim(self._params(
            statement="The sky is blue",
            category="factual",
            confidence=0.95,
            status="verified",
            source_tier="T1",
            evidence=[{
                "source_url": "https://www.noaa.gov/sky",
                "source_tier": "T1",
                "content_hash": "abc123",
                "excerpt": "The sky appears blue due to Rayleigh scattering.",
            }],
        ))
        self.assertTrue(result["stored"])
        claim_id = result["claim_id"]

        # Query it back
        query = self.kb.kb_query_claim(self._params(claim_id=claim_id))
        self.assertEqual(query["claim"]["statement"], "The sky is blue")
        self.assertEqual(query["claim"]["status"], "verified")
        self.assertAlmostEqual(query["claim"]["confidence"], 0.95)
        self.assertEqual(len(query["evidence_chain"]), 1)
        self.assertEqual(
            query["evidence_chain"][0]["source_url"],
            "https://www.noaa.gov/sky"
        )

    def test_version_tracking(self):
        result = self.kb.kb_store_claim(self._params(
            statement="Population is 340 million",
            status="reported",
        ))
        claim_id = result["claim_id"]

        history = self.kb.kb_claim_history(self._params(claim_id=claim_id))
        self.assertEqual(len(history["versions"]), 1)
        self.assertEqual(history["versions"][0]["change_reason"], "initial_store")

    def test_search(self):
        self.kb.kb_store_claim(self._params(
            statement="Water boils at 100 degrees Celsius",
            category="factual",
            confidence=0.99,
            status="verified",
        ))
        self.kb.kb_store_claim(self._params(
            statement="Ice melts at 0 degrees Celsius",
            category="factual",
            confidence=0.99,
            status="verified",
        ))

        results = self.kb.kb_search(self._params(query="boils"))
        self.assertGreaterEqual(len(results["results"]), 1)
        # With vector search, results may include non-keyword
        # matches ranked by embedding similarity. Verify at
        # least one result contains the query term.
        found = any(
            "boils" in r["statement"]
            for r in results["results"]
        )
        self.assertTrue(found)

    def test_missing_claim_errors(self):
        result = self.kb.kb_query_claim(
            self._params(claim_id="nonexistent-id")
        )
        self.assertIn("error", result)


class TestClaimTypeClassification(unittest.TestCase):
    """Test heuristic claim-type classification."""

    def setUp(self):
        self.classifier = ClassifierWorker(worker_id="test-classifier")

    def _classify(self, statement):
        return self.classifier.classify_claim_type(
            MockHandle({"statement": statement})
        )

    def test_statistical_claim(self):
        r = self._classify("Crime dropped 12% in 2025")
        self.assertEqual(r["claim_type"], "statistical")
        self.assertIn("statistical", r["signals"])

    def test_causal_claim(self):
        r = self._classify("The rezoning caused a traffic increase")
        self.assertEqual(r["claim_type"], "causal")

    def test_prediction_claim(self):
        r = self._classify("The budget will increase next year")
        self.assertEqual(r["claim_type"], "prediction")

    def test_opinion_claim(self):
        r = self._classify("I believe the policy is the best approach")
        self.assertEqual(r["claim_type"], "opinion")

    def test_attribution_claim(self):
        r = self._classify("The mayor said taxes will not increase")
        # "said" triggers attribution; "will" triggers prediction too
        # attribution pattern should fire
        self.assertIn(r["claim_type"], ("attribution", "prediction"))

    def test_temporal_claim(self):
        r = self._classify("The population is currently 340 million")
        self.assertEqual(r["claim_type"], "temporal")

    def test_empirical_fact_default(self):
        r = self._classify("The council voted 4-3 on the motion")
        self.assertEqual(r["claim_type"], "empirical_fact")

    def test_million_triggers_statistical(self):
        r = self._classify("The company earned 5 billion in revenue")
        self.assertEqual(r["claim_type"], "statistical")


class TestTemporalValidity(unittest.TestCase):
    """Test temporal validity computation."""

    def setUp(self):
        self.classifier = ClassifierWorker(worker_id="test-classifier")

    def test_permanent_has_no_expiry(self):
        r = self.classifier.classify_temporal_validity(
            MockHandle({"statement": "Water boils at 100C", "category": "factual"})
        )
        self.assertEqual(r["ttl_category"], "permanent")
        self.assertIsNone(r["valid_until"])
        self.assertIsNone(r["ttl_days"])

    def test_statistical_expires_in_6_months(self):
        r = self.classifier.classify_temporal_validity(
            MockHandle({
                "statement": "Crime rate is 5%",
                "category": "statistical",
                "source_date": "2026-01-01T00:00:00+00:00",
            })
        )
        self.assertEqual(r["ttl_category"], "medium_term")
        self.assertEqual(r["ttl_days"], 180)
        self.assertIn("2026-06-30", r["valid_until"])

    def test_opinion_expires_in_2_weeks(self):
        r = self.classifier.classify_temporal_validity(
            MockHandle({
                "statement": "The policy is good",
                "category": "opinion",
                "source_date": "2026-03-01T00:00:00+00:00",
            })
        )
        self.assertEqual(r["ttl_category"], "short_term")
        self.assertEqual(r["ttl_days"], 14)
        self.assertIn("2026-03-15", r["valid_until"])


class TestKBUpdate(unittest.TestCase):
    """Test KB claim update with version tracking."""

    def setUp(self):
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _params(self, **kwargs):
        kwargs["db_path"] = self.db_path
        return MockHandle(kwargs)

    def test_update_confidence(self):
        # Store initial claim
        store = self.kb.kb_store_claim(self._params(
            statement="Crime rate is 5%",
            confidence=0.50,
            status="reported",
        ))
        claim_id = store["claim_id"]

        # Update with new evidence
        update = self.kb.kb_update_claim(self._params(
            claim_id=claim_id,
            confidence=0.85,
            status="corroborated",
            change_reason="corroborated by second T3 source",
            evidence=[{
                "source_url": "https://www.reuters.com/crime-stats",
                "source_tier": "T3",
                "excerpt": "FBI data confirms 5% crime rate",
            }],
        ))
        self.assertTrue(update["updated"])

        # Verify update
        query = self.kb.kb_query_claim(self._params(claim_id=claim_id))
        self.assertAlmostEqual(query["claim"]["confidence"], 0.85)
        self.assertEqual(query["claim"]["status"], "corroborated")
        self.assertEqual(len(query["evidence_chain"]), 1)  # new evidence added

        # Verify version history
        history = self.kb.kb_claim_history(self._params(claim_id=claim_id))
        self.assertEqual(len(history["versions"]), 2)  # initial + update

    def test_update_missing_claim_errors(self):
        result = self.kb.kb_update_claim(self._params(
            claim_id="nonexistent",
            change_reason="test",
        ))
        self.assertFalse(result["updated"])
        self.assertIn("error", result)

    def test_update_requires_reason(self):
        result = self.kb.kb_update_claim(self._params(
            claim_id="some-id",
        ))
        self.assertFalse(result["updated"])


class TestMultiSourceCorroboration(unittest.TestCase):
    """Test corroboration boost from multiple independent sources."""

    def setUp(self):
        self.corroborator = CorroboratorWorker(worker_id="test-corr")
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _params(self, **kwargs):
        kwargs["db_path"] = self.db_path
        return MockHandle(kwargs)

    def test_corroboration_boost_with_independent_sources(self):
        """Verify that confidence increases with independent corroboration."""
        # Single T3 source → reported
        single = compute_confidence(STATUS_REPORTED, "T3", 1)

        # Two independent T3 sources → corroborated with boost
        two_sources = compute_confidence(STATUS_CORROBORATED, "T3", 2)

        # Three independent sources → higher
        three_sources = compute_confidence(STATUS_CORROBORATED, "T3", 3)

        self.assertGreater(two_sources, single,
                           "Corroboration should increase confidence")
        self.assertGreater(three_sources, two_sources,
                           "More sources should increase confidence further")

    def test_t1_plus_t3_stronger_than_t3_plus_t3(self):
        """Higher best-tier should produce higher confidence."""
        t1_corroborated = compute_confidence(STATUS_CORROBORATED, "T1", 2)
        t3_corroborated = compute_confidence(STATUS_CORROBORATED, "T3", 2)
        self.assertGreater(t1_corroborated, t3_corroborated)

    def test_many_t6_weaker_than_one_t1(self):
        """Many low-tier sources should NOT exceed a single high-tier source."""
        many_t6 = compute_confidence(STATUS_CORROBORATED, "T6", 10)
        one_t1 = compute_confidence(STATUS_REPORTED, "T1", 1)
        self.assertGreater(one_t1, many_t6,
                           "10 T6 sources should not beat 1 T1 source")

    def test_full_multi_source_pipeline(self):
        """End-to-end: store claim, add evidence, update, verify boost."""
        # Store initial claim from T3 source
        store = self.kb.kb_store_claim(self._params(
            statement="City population is 50,000",
            confidence=compute_confidence(STATUS_REPORTED, "T3"),
            status="reported",
            source_tier="T3",
            evidence=[{
                "source_url": "https://www.nytimes.com/city-data",
                "source_tier": "T3",
            }],
        ))
        claim_id = store["claim_id"]

        # Second source corroborates
        new_confidence = compute_confidence(STATUS_CORROBORATED, "T3", 2)
        self.kb.kb_update_claim(self._params(
            claim_id=claim_id,
            confidence=new_confidence,
            status="corroborated",
            change_reason="corroborated by independent T3 source",
            evidence=[{
                "source_url": "https://www.reuters.com/city-census",
                "source_tier": "T3",
            }],
        ))

        # Verify final state
        query = self.kb.kb_query_claim(self._params(claim_id=claim_id))
        self.assertEqual(query["claim"]["status"], "corroborated")
        self.assertGreater(
            query["claim"]["confidence"],
            compute_confidence(STATUS_REPORTED, "T3"),
        )
        self.assertEqual(len(query["evidence_chain"]), 2)


class TestSentenceSegmentation(unittest.TestCase):
    """Test heuristic sentence segmentation."""

    def test_basic_split(self):
        text = "The sky is blue. Water is wet. Fire is hot."
        sents = _segment_sentences(text)
        self.assertEqual(len(sents), 3)

    def test_abbreviation_handling(self):
        text = "Dr. Smith works at the U.S. Department of Energy. He studies climate."
        sents = _segment_sentences(text)
        # May split on "Dr." but should produce reasonable segments
        # The key check: we get at least the full substance
        full = " ".join(sents)
        self.assertIn("Smith", full)
        self.assertIn("Department of Energy", full)

    def test_short_fragments_filtered(self):
        text = "Yes. No. The quick brown fox jumps over the lazy dog."
        sents = _segment_sentences(text)
        # "Yes." and "No." are too short (< 10 chars)
        self.assertEqual(len(sents), 1)

    def test_empty_input(self):
        self.assertEqual(_segment_sentences(""), [])
        self.assertEqual(_segment_sentences("   "), [])


class TestClaimFiltering(unittest.TestCase):
    """Test claim candidate filtering."""

    def test_questions_rejected(self):
        self.assertFalse(_is_claim_candidate("What time is it?"))

    def test_commands_rejected(self):
        self.assertFalse(_is_claim_candidate("Click here to subscribe to our newsletter"))
        self.assertFalse(_is_claim_candidate("Subscribe for daily updates"))

    def test_boilerplate_rejected(self):
        self.assertFalse(_is_claim_candidate("Copyright 2026 All Rights Reserved"))
        self.assertFalse(_is_claim_candidate("Terms of Service and Privacy Policy"))

    def test_too_short_rejected(self):
        self.assertFalse(_is_claim_candidate("It is hot"))

    def test_valid_claim_accepted(self):
        self.assertTrue(_is_claim_candidate(
            "Global temperatures rose 1.5 degrees Celsius in 2025"
        ))

    def test_categorize_statistical(self):
        self.assertEqual(
            _categorize_claim("Crime dropped 12% last year"),
            "statistical"
        )

    def test_categorize_causal(self):
        self.assertEqual(
            _categorize_claim("The flooding was caused by heavy rains"),
            "causal"
        )

    def test_categorize_factual_default(self):
        self.assertEqual(
            _categorize_claim("The council approved the new zoning plan"),
            "factual"
        )


class TestEntityExtraction(unittest.TestCase):
    """Test heuristic entity extraction."""

    def test_extract_dates(self):
        entities = _extract_entities("The report was released on March 15, 2026.")
        dates = [e for e in entities if e["type"] == "date"]
        self.assertGreaterEqual(len(dates), 1)

    def test_extract_numbers(self):
        entities = _extract_entities("The project cost $4.5 million.")
        numbers = [e for e in entities if e["type"] == "number"]
        self.assertGreaterEqual(len(numbers), 1)

    def test_extract_titled_persons(self):
        entities = _extract_entities("President Joe Biden signed the bill.")
        persons = [e for e in entities if e["type"] == "person"]
        self.assertGreaterEqual(len(persons), 1)

    def test_extract_organizations(self):
        entities = _extract_entities(
            "The Environmental Protection Agency issued new regulations."
        )
        orgs = [e for e in entities if e["type"] == "organization"]
        self.assertGreaterEqual(len(orgs), 1)


class TestExtractorWorker(unittest.TestCase):
    """Test the extractor worker skills."""

    def setUp(self):
        self.extractor = ExtractorWorker(worker_id="test-extractor")

    def test_extract_claims_from_news(self):
        content = (
            "Global temperatures rose 1.5 degrees Celsius above "
            "pre-industrial levels for the first time in 2025. "
            "The WMO report found that the past decade was the "
            "warmest on record. Sea levels continued to rise at "
            "an accelerating pace, increasing by 4.6 millimeters per year."
        )
        result = self.extractor.extract_claims(
            MockHandle({"content": content, "source_tier": "T3"})
        )
        self.assertGreater(result["claims_extracted"], 0)
        # Should find statistical claims
        categories = {c["category"] for c in result["claims"]}
        self.assertIn("statistical", categories)

    def test_extract_entities_from_news(self):
        content = (
            "WMO Secretary General Celeste Saulo announced on "
            "January 10, 2026 that damages exceeded $380 billion."
        )
        result = self.extractor.extract_entities(
            MockHandle({"content": content})
        )
        self.assertGreater(result["total_found"], 0)

    def test_empty_content_errors(self):
        result = self.extractor.extract_claims(MockHandle({"content": ""}))
        self.assertIn("error", result)

    def test_max_claims_limit(self):
        # Long content that would produce many claims
        content = ". ".join(
            f"Fact number {i} is that the value is {i * 100} million"
            for i in range(1, 20)
        ) + "."
        result = self.extractor.extract_claims(
            MockHandle({"content": content, "max_claims": 5})
        )
        self.assertLessEqual(result["claims_extracted"], 5)


class TestAutomatedPipeline(unittest.TestCase):
    """Test the automated pipeline with golden fixtures."""

    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_news_fixture_pipeline(self):
        """Full pipeline with AP News fixture (T3 source)."""
        fixture = load_fixture("golden_news")
        source = fixture["source"]
        expected = fixture["expected"]

        # Import pipeline
        sys.path.insert(0, LOOM_DIR)
        from pipeline import acquire, _Handle
        from workers.harvester.worker import HarvesterWorker
        from workers.classifier.worker import ClassifierWorker
        from workers.extractor.worker import ExtractorWorker
        from workers.corroborator.worker import CorroboratorWorker
        from workers.kb.worker import LoomKBWorker

        # Run pipeline components manually with fixture content
        classifier = ClassifierWorker(worker_id="test")
        extractor = ExtractorWorker(worker_id="test")
        corroborator = CorroboratorWorker(worker_id="test")
        kb = LoomKBWorker(worker_id="test")

        # Classify
        classification = classifier.classify_source_tier(
            MockHandle({"url": source["url"]})
        )
        self.assertEqual(classification["tier"], expected["classification"]["tier"])

        # Extract
        extraction = extractor.extract_claims(
            MockHandle({
                "content": source["content"],
                "source_tier": classification["tier"],
            })
        )
        self.assertGreaterEqual(
            extraction["claims_extracted"],
            expected["extraction"]["min_claims"],
        )

        # Corroborate and store each claim
        for claim in extraction["claims"]:
            corr = corroborator.corroborate_check(MockHandle({
                "statement": claim["statement"],
                "source_tier": classification["tier"],
            }))
            self.assertEqual(corr["status"], expected["corroboration"]["status"])
            self.assertGreaterEqual(
                corr["confidence"],
                expected["corroboration"]["min_confidence"],
            )
            self.assertLessEqual(
                corr["confidence"],
                expected["corroboration"]["max_confidence"],
            )

            # Store
            store = kb.kb_store_claim(MockHandle({
                "db_path": self.db_path,
                "statement": claim["statement"],
                "category": claim["category"],
                "confidence": corr["confidence"],
                "status": corr["status"],
                "source_tier": classification["tier"],
                "evidence": [{
                    "source_url": source["url"],
                    "source_tier": classification["tier"],
                    "excerpt": claim["excerpt"],
                }],
            }))
            self.assertTrue(store["stored"])


class TestDeduplication(unittest.TestCase):
    """Test KB deduplication on store."""

    def setUp(self):
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _params(self, **kwargs):
        kwargs["db_path"] = self.db_path
        return MockHandle(kwargs)

    def test_exact_duplicate_merges(self):
        """Storing same statement twice should not create duplicate."""
        stmt = "The population is 340 million"
        r1 = self.kb.kb_store_claim(self._params(
            statement=stmt, source_tier="T1",
            evidence=[{"source_url": "https://census.gov/pop"}],
        ))
        r2 = self.kb.kb_store_claim(self._params(
            statement=stmt, source_tier="T3",
            evidence=[{"source_url": "https://nytimes.com/pop"}],
        ))
        self.assertTrue(r1["stored"])
        self.assertTrue(r2["stored"])
        self.assertTrue(r2.get("deduplicated", False))
        # Same claim_id
        self.assertEqual(r1["claim_id"], r2["claim_id"])

        # Should have 2 evidence links
        query = self.kb.kb_query_claim(self._params(claim_id=r1["claim_id"]))
        self.assertEqual(len(query["evidence_chain"]), 2)

    def test_same_url_evidence_not_duplicated(self):
        """Re-harvesting same URL should not add duplicate evidence."""
        stmt = "Water boils at 100 degrees"
        url = "https://noaa.gov/water"
        self.kb.kb_store_claim(self._params(
            statement=stmt, evidence=[{"source_url": url}],
        ))
        self.kb.kb_store_claim(self._params(
            statement=stmt, evidence=[{"source_url": url}],
        ))
        # Search for the claim
        search = self.kb.kb_search(self._params(query="boils"))
        claim_id = search["results"][0]["claim_id"]
        query = self.kb.kb_query_claim(self._params(claim_id=claim_id))
        # Only 1 evidence link (not 2)
        self.assertEqual(len(query["evidence_chain"]), 1)

    def test_higher_confidence_preserved(self):
        """Second store with higher confidence should update."""
        stmt = "The sky is blue"
        r1 = self.kb.kb_store_claim(self._params(
            statement=stmt, confidence=0.50,
        ))
        self.kb.kb_store_claim(self._params(
            statement=stmt, confidence=0.90,
        ))
        query = self.kb.kb_query_claim(self._params(claim_id=r1["claim_id"]))
        self.assertAlmostEqual(query["claim"]["confidence"], 0.90)


class TestContradictionDetection(unittest.TestCase):
    """Test contradiction detection and contested propagation."""

    def setUp(self):
        self.corroborator = CorroboratorWorker(worker_id="test-corr")
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _params(self, **kwargs):
        kwargs["db_path"] = self.db_path
        return MockHandle(kwargs)

    def test_numeric_contradiction_detected(self):
        """Claims with conflicting numbers should be flagged."""
        claims = [
            {"statement": "The project cost $4 million dollars"},
            {"statement": "The project cost $6 million dollars"},
        ]
        result = self.corroborator.find_contradictions(
            MockHandle({"claims": claims})
        )
        self.assertGreater(len(result["contradictions"]), 0)
        self.assertEqual(result["contradictions"][0]["nature"], "numeric_conflict")

    def test_similar_numbers_no_contradiction(self):
        """Numbers within 20% should not trigger contradiction."""
        claims = [
            {"statement": "Temperature was 98 degrees"},
            {"statement": "Temperature was 99 degrees"},
        ]
        result = self.corroborator.find_contradictions(
            MockHandle({"claims": claims})
        )
        self.assertEqual(len(result["contradictions"]), 0)

    def test_record_contradiction_updates_status(self):
        """Recording a contradiction should set both claims to contested."""
        r1 = self.kb.kb_store_claim(self._params(
            statement="Population is 50,000",
            confidence=0.85, status="corroborated", source_tier="T3",
        ))
        r2 = self.kb.kb_store_claim(self._params(
            statement="Population is 60,000",
            confidence=0.70, status="reported", source_tier="T3",
        ))

        # Record contradiction
        contra = self.kb.kb_record_contradiction(self._params(
            claim_a_id=r1["claim_id"],
            claim_b_id=r2["claim_id"],
            nature="numeric_conflict",
        ))
        self.assertTrue(contra["recorded"])

        # Both claims should now be contested
        q1 = self.kb.kb_query_claim(self._params(claim_id=r1["claim_id"]))
        q2 = self.kb.kb_query_claim(self._params(claim_id=r2["claim_id"]))
        self.assertEqual(q1["claim"]["status"], "contested")
        self.assertEqual(q2["claim"]["status"], "contested")

        # Confidence should have dropped
        self.assertLess(q1["claim"]["confidence"], 0.85)
        self.assertLess(q2["claim"]["confidence"], 0.70)

        # Contradiction should be in both claims' query results
        self.assertEqual(len(q1["contradictions"]), 1)
        self.assertEqual(len(q2["contradictions"]), 1)

    def test_duplicate_contradiction_not_created(self):
        """Recording same contradiction twice should not create duplicate."""
        r1 = self.kb.kb_store_claim(self._params(
            statement="X is 10", source_tier="T3",
        ))
        r2 = self.kb.kb_store_claim(self._params(
            statement="X is 20", source_tier="T3",
        ))
        c1 = self.kb.kb_record_contradiction(self._params(
            claim_a_id=r1["claim_id"], claim_b_id=r2["claim_id"],
            nature="numeric_conflict",
        ))
        c2 = self.kb.kb_record_contradiction(self._params(
            claim_a_id=r1["claim_id"], claim_b_id=r2["claim_id"],
            nature="numeric_conflict",
        ))
        self.assertTrue(c2.get("already_existed", False))
        self.assertEqual(c1["contradiction_id"], c2["contradiction_id"])

    def test_find_similar_claims(self):
        """KB find_similar should locate related claims."""
        self.kb.kb_store_claim(self._params(
            statement="City population is 50,000 residents",
        ))
        self.kb.kb_store_claim(self._params(
            statement="City population is 60,000 residents",
        ))
        self.kb.kb_store_claim(self._params(
            statement="The weather is sunny today",
        ))

        result = self.kb.kb_find_similar(self._params(
            statement="City population is 55,000 residents",
        ))
        # Should find the two population claims as similar matches
        # (key is "similar_matches" with vector search,
        #  was "fuzzy_matches" with LIKE fallback)
        matches = result.get(
            "similar_matches", result.get("fuzzy_matches", []))
        self.assertGreaterEqual(len(matches), 2)


class TestGoldenPipeline(unittest.TestCase):
    """End-to-end pipeline test using golden fixture."""

    def setUp(self):
        self.fixture = load_fixture("golden_gov")
        self.classifier = ClassifierWorker(worker_id="test-classifier")
        self.corroborator = CorroboratorWorker(worker_id="test-corroborator")
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(
            suffix=".db", delete=False
        )
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_full_pipeline(self):
        source = self.fixture["source"]
        expected = self.fixture["expected"]

        # Step 1: Harvest (use fixture content, skip HTTP)
        content = source["content"]
        content_hash = _compute_hash(content)
        harvest_result = {
            "url": source["url"],
            "content": content,
            "content_hash": content_hash,
            "metadata": {
                "status_code": source["status_code"],
                "content_type": source["content_type"],
            },
        }
        self.assertTrue(len(harvest_result["content"]) > 0)
        self.assertTrue(len(harvest_result["content_hash"]) == 64)  # SHA-256

        # Step 2: Classify source
        classify_result = self.classifier.classify_source_tier(
            MockHandle({"url": source["url"], "content": content})
        )
        self.assertEqual(classify_result["tier"], expected["classification"]["tier"])
        self.assertEqual(
            classify_result["domain_verified"],
            expected["classification"]["domain_verified"]
        )
        self.assertTrue(classify_result["domain_check"]["is_gov"])

        # Step 3: Corroborate (new claim, no KB matches yet)
        for claim in expected["claims"]:
            corr_result = self.corroborator.corroborate_check(
                MockHandle({
                    "statement": claim["statement"],
                    "source_tier": classify_result["tier"],
                })
            )
            # T1 source, no contradictions → verified
            self.assertEqual(
                corr_result["status"],
                expected["corroboration"]["status"]
            )
            self.assertGreaterEqual(
                corr_result["confidence"],
                expected["corroboration"]["confidence_min"]
            )
            self.assertLessEqual(
                corr_result["confidence"],
                expected["corroboration"]["confidence_max"]
            )

        # Step 4: Store claims in KB
        stored_ids = []
        for claim in expected["claims"]:
            store_result = self.kb.kb_store_claim(MockHandle({
                "db_path": self.db_path,
                "statement": claim["statement"],
                "category": claim["category"],
                "confidence": compute_confidence(STATUS_VERIFIED, "T1"),
                "status": "verified",
                "source_tier": "T1",
                "ttl_category": claim["ttl_category"],
                "evidence": [{
                    "source_url": source["url"],
                    "source_tier": "T1",
                    "content_hash": content_hash,
                    "excerpt": content[:200],
                }],
            }))
            self.assertTrue(store_result["stored"])
            stored_ids.append(store_result["claim_id"])

        # Step 5: Verify all claims are retrievable with evidence
        for claim_id in stored_ids:
            query = self.kb.kb_query_claim(MockHandle({
                "db_path": self.db_path,
                "claim_id": claim_id,
            }))
            self.assertNotIn("error", query)
            self.assertEqual(query["claim"]["status"], "verified")
            self.assertEqual(query["claim"]["source_tier"], "T1")
            self.assertEqual(len(query["evidence_chain"]), 1)
            self.assertEqual(
                query["evidence_chain"][0]["source_url"],
                source["url"]
            )

        # Step 6: Search should find stored claims
        search = self.kb.kb_search(MockHandle({
            "db_path": self.db_path,
            "query": "population",
        }))
        self.assertGreaterEqual(
            len(search["results"]), 2,
            "Should find at least 2 population-related claims"
        )

    def test_html_to_text_extraction(self):
        """Verify HTML stripping produces clean text."""
        html = (
            "<html><head><script>var x=1;</script>"
            "<style>body{color:red}</style></head>"
            "<body><h1>Title</h1><p>Paragraph one.</p>"
            "<p>Paragraph&amp;two.</p></body></html>"
        )
        text = _html_to_text(html)
        self.assertIn("Title", text)
        self.assertIn("Paragraph one.", text)
        self.assertIn("Paragraph&two.", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("<style>", text)
        self.assertNotIn("<h1>", text)

    def test_content_hash_determinism(self):
        """Same content must produce same hash."""
        content = "The population is 340 million"
        h1 = _compute_hash(content)
        h2 = _compute_hash(content)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

        # Different content → different hash
        h3 = _compute_hash(content + " people")
        self.assertNotEqual(h1, h3)


class TestClaimReviewExport(unittest.TestCase):
    """Test Schema.org ClaimReview export."""

    def setUp(self):
        self.corroborator = CorroboratorWorker(worker_id="test-corroborator")

    def test_verified_claim_review(self):
        result = self.corroborator.claim_review_export(MockHandle({
            "claim": {
                "statement": "US population is 340 million",
                "source_url": "https://census.gov/data",
                "source_tier": "T1",
            },
            "assessment": {
                "status": STATUS_VERIFIED,
                "confidence": 0.975,
                "confidence_v2": {
                    "final_confidence": 0.975,
                    "analytic_confidence": "very_high",
                },
            },
        }))
        cr = result["claim_review"]
        self.assertEqual(cr["@type"], "ClaimReview")
        self.assertEqual(cr["reviewRating"]["alternateName"], "True")
        self.assertEqual(cr["reviewRating"]["ratingValue"], 5)
        self.assertEqual(cr["claimReviewed"], "US population is 340 million")

    def test_contested_claim_review(self):
        result = self.corroborator.claim_review_export(MockHandle({
            "claim": {"statement": "Disputed claim"},
            "assessment": {"status": STATUS_CONTESTED},
        }))
        cr = result["claim_review"]
        self.assertEqual(cr["reviewRating"]["alternateName"], "Disputed")
        self.assertEqual(cr["reviewRating"]["ratingValue"], 2)

    def test_claim_review_has_schema_org_context(self):
        result = self.corroborator.claim_review_export(MockHandle({
            "claim": {"statement": "Test"},
            "assessment": {"status": STATUS_REPORTED},
        }))
        self.assertEqual(result["claim_review"]["@context"], "https://schema.org")


class TestStructuredDisagreement(unittest.TestCase):
    """Test IPCC-inspired structured disagreement model."""

    def setUp(self):
        self.corroborator = CorroboratorWorker(worker_id="test-corroborator")

    def test_robust_high_is_very_high(self):
        result = self.corroborator.structured_disagreement(MockHandle({
            "claim_id": "test-1",
            "evidence_strength": "robust",
            "agreement_level": "high",
            "nature": "factual",
        }))
        self.assertEqual(result["analytic_confidence"], "very_high")

    def test_limited_low_is_low(self):
        result = self.corroborator.structured_disagreement(MockHandle({
            "claim_id": "test-2",
            "evidence_strength": "limited",
            "agreement_level": "low",
            "nature": "interpretive",
        }))
        self.assertEqual(result["analytic_confidence"], "low")

    def test_medium_medium_is_medium(self):
        result = self.corroborator.structured_disagreement(MockHandle({
            "claim_id": "test-3",
            "evidence_strength": "medium",
            "agreement_level": "medium",
        }))
        self.assertEqual(result["analytic_confidence"], "medium")

    def test_requires_claim_id(self):
        result = self.corroborator.structured_disagreement(MockHandle({
            "evidence_strength": "robust",
            "agreement_level": "high",
        }))
        self.assertIn("error", result)

    def test_positions_passed_through(self):
        positions = [
            {"position": "Temperature rose 1.5C", "evidence_ids": ["e1", "e2"]},
            {"position": "Temperature rose 1.2C", "evidence_ids": ["e3"]},
        ]
        result = self.corroborator.structured_disagreement(MockHandle({
            "claim_id": "test-4",
            "evidence_strength": "medium",
            "agreement_level": "low",
            "nature": "factual",
            "axis": "magnitude of warming",
            "positions": positions,
        }))
        self.assertEqual(len(result["positions"]), 2)
        self.assertEqual(result["axis"], "magnitude of warming")


class TestDualAxisStorage(unittest.TestCase):
    """Test that dual-axis fields are stored and retrieved from KB."""

    def setUp(self):
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_claim_type_stored(self):
        result = self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Temperature rose 1.5 degrees",
            "claim_type": "statistical",
            "info_credibility": "C2",
            "analytic_confidence": "high",
            "evidence": [{
                "source_url": "https://nature.com/article/123",
                "source_tier": "T4",
                "relationship": "supports",
                "inference": "summarized",
                "directness": "direct",
            }],
        }))
        self.assertTrue(result["stored"])

        query = self.kb.kb_query_claim(MockHandle({
            "db_path": self.db_path,
            "claim_id": result["claim_id"],
        }))
        self.assertEqual(query["claim"]["claim_type"], "statistical")
        self.assertEqual(query["claim"]["info_credibility"], "C2")
        self.assertEqual(query["claim"]["analytic_confidence"], "high")

    def test_evidence_relationship_stored(self):
        result = self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Sea levels are rising",
            "evidence": [{
                "source_url": "https://nasa.gov/data",
                "source_tier": "T1",
                "relationship": "supports",
                "warrant": "Direct measurement from satellite altimetry",
                "inference": "calculated",
                "directness": "direct",
            }],
        }))
        self.assertTrue(result["stored"])

        query = self.kb.kb_query_claim(MockHandle({
            "db_path": self.db_path,
            "claim_id": result["claim_id"],
        }))
        ev = query["evidence_chain"][0]
        self.assertEqual(ev["relationship"], "supports")
        self.assertEqual(ev["inference"], "calculated")
        self.assertEqual(ev["directness"], "direct")


class TestSourceRetraction(unittest.TestCase):
    """Test ATMS-style retraction propagation."""

    def setUp(self):
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _store(self, statement, sources):
        """Helper: store claim with given source URLs."""
        evidence = [
            {"source_url": url, "source_tier": "T3", "relationship": "supports"}
            for url in sources
        ]
        return self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": statement,
            "confidence": 0.75,
            "status": "reported" if len(sources) == 1 else "corroborated",
            "evidence": evidence,
        }))

    def test_retract_sole_source_downgrades_claim(self):
        result = self._store("Claim A", ["https://source1.com/a"])
        claim_id = result["claim_id"]

        retraction = self.kb.kb_retract_source(MockHandle({
            "db_path": self.db_path,
            "source_url": "https://source1.com/a",
            "reason": "retracted",
            "detail": "Study was fabricated",
        }))

        self.assertIn(claim_id, retraction["downgraded_claims"])

        # Verify claim is now unverified
        query = self.kb.kb_query_claim(MockHandle({
            "db_path": self.db_path,
            "claim_id": claim_id,
        }))
        self.assertEqual(query["claim"]["status"], "unverified")
        self.assertAlmostEqual(query["claim"]["confidence"], 0.01)

    def test_retract_one_of_two_sources_keeps_claim(self):
        result = self._store("Claim B", [
            "https://source1.com/b",
            "https://source2.com/b",
        ])
        claim_id = result["claim_id"]

        retraction = self.kb.kb_retract_source(MockHandle({
            "db_path": self.db_path,
            "source_url": "https://source1.com/b",
            "reason": "corrected",
        }))

        self.assertNotIn(claim_id, retraction["downgraded_claims"])

        query = self.kb.kb_query_claim(MockHandle({
            "db_path": self.db_path,
            "claim_id": claim_id,
        }))
        # Downgraded from corroborated to reported (only 1 source left)
        self.assertEqual(query["claim"]["status"], "reported")

    def test_sensitivity_analysis(self):
        r1 = self._store("Only from src1", ["https://src1.com/x"])
        r2 = self._store("From both", [
            "https://src1.com/y",
            "https://src2.com/y",
        ])

        analysis = self.kb.kb_sensitivity(MockHandle({
            "db_path": self.db_path,
            "source_url": "https://src1.com/x",
        }))

        # src1.com/x is sole source for first claim
        self.assertIn(r1["claim_id"], analysis["would_lose_all_support"])

    def test_build_labels(self):
        result = self._store("Labeled claim", [
            "https://a.com/1",
            "https://b.com/1",
        ])
        claim_id = result["claim_id"]

        labels = self.kb.kb_build_labels(MockHandle({
            "db_path": self.db_path,
            "claim_id": claim_id,
        }))

        self.assertEqual(len(labels["labels"]), 2)
        self.assertEqual(labels["valid_count"], 2)
        self.assertEqual(labels["invalid_count"], 0)

    def test_retraction_invalidates_labels(self):
        result = self._store("Labeled claim 2", [
            "https://retractme.com/p",
            "https://keeper.com/p",
        ])
        claim_id = result["claim_id"]

        # Build labels first
        self.kb.kb_build_labels(MockHandle({
            "db_path": self.db_path,
            "claim_id": claim_id,
        }))

        # Retract one source
        self.kb.kb_retract_source(MockHandle({
            "db_path": self.db_path,
            "source_url": "https://retractme.com/p",
            "reason": "discredited",
        }))

        # Rebuild labels — should show 1 valid, 1 invalid
        labels = self.kb.kb_build_labels(MockHandle({
            "db_path": self.db_path,
            "claim_id": claim_id,
        }))
        self.assertEqual(labels["valid_count"], 1)
        self.assertEqual(labels["invalid_count"], 1)


class TestCorroborateCheckV2(unittest.TestCase):
    """Test that corroborate.check returns v2 confidence."""

    def setUp(self):
        self.corroborator = CorroboratorWorker(worker_id="test-corroborator")

    def test_check_includes_v2(self):
        result = self.corroborator.corroborate_check(MockHandle({
            "statement": "The Earth is round",
            "source_tier": "T1",
            "info_credibility": "C1",
        }))
        self.assertIn("confidence_v2", result)
        v2 = result["confidence_v2"]
        self.assertIn("final_confidence", v2)
        self.assertIn("analytic_confidence", v2)
        self.assertEqual(v2["credibility_modifier"], 1.0)

    def test_check_v2_default_c6(self):
        result = self.corroborator.corroborate_check(MockHandle({
            "statement": "Some claim",
            "source_tier": "T3",
        }))
        v2 = result["confidence_v2"]
        self.assertEqual(v2["credibility_modifier"], 0.50)


class TestACHMatrix(unittest.TestCase):
    """Test Analysis of Competing Hypotheses."""

    def setUp(self):
        self.adjudicator = AdjudicatorWorker(worker_id="test-adjudicator")

    def test_basic_ach(self):
        result = self.adjudicator.ach_matrix(MockHandle({
            "hypotheses": ["Rain caused flooding", "Dam failure caused flooding"],
            "evidence": [
                {
                    "statement": "Heavy rainfall recorded",
                    "weight": 1.0,
                    "consistency": {"H1": "consistent", "H2": "neutral"},
                },
                {
                    "statement": "Dam inspection found cracks",
                    "weight": 0.8,
                    "consistency": {"H1": "neutral", "H2": "consistent"},
                },
                {
                    "statement": "Flooding started upstream of dam",
                    "weight": 1.0,
                    "consistency": {"H1": "consistent", "H2": "inconsistent"},
                },
            ],
        }))
        self.assertIsNotNone(result["best_hypothesis"])
        # H1 should win: 2 consistent, 1 neutral vs H2: 1 consistent, 1 neutral, 1 inconsistent
        self.assertEqual(result["best_hypothesis"]["hypothesis_id"], "H1")

    def test_requires_two_hypotheses(self):
        result = self.adjudicator.ach_matrix(MockHandle({
            "hypotheses": ["Only one"],
            "evidence": [{"statement": "Something"}],
        }))
        self.assertIn("error", result)

    def test_rankings_ordered(self):
        result = self.adjudicator.ach_matrix(MockHandle({
            "hypotheses": ["A", "B", "C"],
            "evidence": [
                {
                    "statement": "E1",
                    "consistency": {
                        "H1": "very_inconsistent",
                        "H2": "consistent",
                        "H3": "neutral",
                    },
                },
            ],
        }))
        scores = [r["total_score"] for r in result["rankings"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestDevilsAdvocate(unittest.TestCase):
    """Test adversarial review."""

    def setUp(self):
        self.adjudicator = AdjudicatorWorker(worker_id="test-adjudicator")

    def test_weak_claim_gets_challenges(self):
        result = self.adjudicator.devils_advocate(MockHandle({
            "claim": {
                "statement": "Aliens built the pyramids",
                "source_tier": "T6",
                "status": "unverified",
                "confidence": 0.90,
                "evidence": [
                    {"source_url": "https://blog.example.com/aliens"},
                ],
            },
        }))
        # Should flag: low tier, single source, unverified, overconfidence
        self.assertGreaterEqual(len(result["challenges"]), 3)
        self.assertGreater(result["vulnerability_score"], 0.5)
        self.assertEqual(result["recommendation"], "reject_or_downgrade")

    def test_strong_claim_is_robust(self):
        result = self.adjudicator.devils_advocate(MockHandle({
            "claim": {
                "statement": "US population is 340 million",
                "source_tier": "T1",
                "status": "verified",
                "confidence": 0.97,
                "evidence": [
                    {"source_url": "https://census.gov/data"},
                    {"source_url": "https://bls.gov/stats"},
                ],
            },
        }))
        self.assertEqual(result["recommendation"], "claim_appears_robust")
        self.assertLess(result["vulnerability_score"], 0.3)

    def test_circular_corroboration_detected(self):
        result = self.adjudicator.devils_advocate(MockHandle({
            "claim": {
                "statement": "Some claim",
                "source_tier": "T3",
                "status": "corroborated",
                "confidence": 0.80,
                "evidence": [
                    {"source_url": "https://example.com/a"},
                    {"source_url": "https://example.com/b"},
                ],
            },
        }))
        types = [c["type"] for c in result["challenges"]]
        self.assertIn("independence", types)


class TestDungSemantics(unittest.TestCase):
    """Test Dung argumentation framework."""

    def setUp(self):
        self.adjudicator = AdjudicatorWorker(worker_id="test-adjudicator")

    def test_unattacked_in_grounded(self):
        """Unattacked arguments are always in the grounded extension."""
        result = self.adjudicator.dung_semantics(MockHandle({
            "arguments": ["a", "b", "c"],
            "attacks": [["a", "b"]],
        }))
        self.assertIn("a", result["grounded_extension"])
        self.assertIn("c", result["grounded_extension"])
        # b is attacked by a (which is unattacked), so b is out
        self.assertNotIn("b", result["grounded_extension"])

    def test_mutual_attack_empty_grounded(self):
        """Two arguments attacking each other: grounded is empty."""
        result = self.adjudicator.dung_semantics(MockHandle({
            "arguments": ["a", "b"],
            "attacks": [["a", "b"], ["b", "a"]],
        }))
        self.assertEqual(result["grounded_extension"], [])
        # Preferred should have {a} and {b}
        self.assertEqual(len(result["preferred_extensions"]), 2)

    def test_reinstatement(self):
        """a attacks b, b attacks c: a reinstates c."""
        result = self.adjudicator.dung_semantics(MockHandle({
            "arguments": ["a", "b", "c"],
            "attacks": [["a", "b"], ["b", "c"]],
        }))
        self.assertIn("a", result["grounded_extension"])
        self.assertIn("c", result["grounded_extension"])
        self.assertNotIn("b", result["grounded_extension"])

    def test_no_attacks_all_grounded(self):
        """With no attacks, all arguments are grounded."""
        result = self.adjudicator.dung_semantics(MockHandle({
            "arguments": ["x", "y", "z"],
            "attacks": [],
        }))
        self.assertEqual(sorted(result["grounded_extension"]), ["x", "y", "z"])


class TestMaintenanceSkills(unittest.TestCase):
    """Test KB maintenance/audit skills."""

    def setUp(self):
        self.kb = LoomKBWorker(worker_id="test-kb")
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_find_orphans_empty_db(self):
        result = self.kb.kb_find_orphans(MockHandle({
            "db_path": self.db_path,
        }))
        self.assertEqual(result["orphan_count"], 0)

    def test_find_orphans_detects_orphan(self):
        """Claim stored without evidence is an orphan."""
        result = self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Orphan claim with no evidence",
            "evidence": [],
        }))
        self.assertTrue(result["stored"])

        orphans = self.kb.kb_find_orphans(MockHandle({
            "db_path": self.db_path,
        }))
        self.assertEqual(orphans["orphan_count"], 1)
        self.assertEqual(orphans["orphans"][0]["statement"],
                         "Orphan claim with no evidence")

    def test_find_expired_none_when_fresh(self):
        result = self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Fresh claim",
            "valid_until": "2099-01-01T00:00:00",
            "evidence": [{"source_url": "https://example.com"}],
        }))
        expired = self.kb.kb_find_expired(MockHandle({
            "db_path": self.db_path,
        }))
        self.assertEqual(expired["expired_count"], 0)

    def test_find_expired_detects_past_due(self):
        result = self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Old claim",
            "valid_until": "2020-01-01T00:00:00",
            "evidence": [{"source_url": "https://example.com"}],
        }))
        expired = self.kb.kb_find_expired(MockHandle({
            "db_path": self.db_path,
        }))
        self.assertEqual(expired["expired_count"], 1)

    def test_stale_contradictions_none_initially(self):
        result = self.kb.kb_stale_contradictions(MockHandle({
            "db_path": self.db_path,
            "stale_days": 0,
        }))
        self.assertEqual(result["stale_count"], 0)

    def test_integrity_report_healthy(self):
        self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Healthy claim",
            "valid_until": "2099-01-01T00:00:00",
            "evidence": [{"source_url": "https://example.com"}],
        }))
        report = self.kb.kb_integrity_report(MockHandle({
            "db_path": self.db_path,
        }))
        self.assertEqual(report["health"], "healthy")
        self.assertEqual(report["summary"]["total_claims"], 1)
        self.assertEqual(report["summary"]["orphan_claims"], 0)

    def test_integrity_report_needs_attention(self):
        # Store an orphan and an expired claim
        self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Orphan",
            "evidence": [],
        }))
        self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Expired",
            "valid_until": "2020-01-01T00:00:00",
            "evidence": [{"source_url": "https://example.com"}],
        }))
        self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Good claim",
            "valid_until": "2099-01-01T00:00:00",
            "evidence": [{"source_url": "https://good.com"}],
        }))
        report = self.kb.kb_integrity_report(MockHandle({
            "db_path": self.db_path,
        }))
        self.assertIn(report["health"], ("needs_attention", "degraded"))
        self.assertGreater(report["summary"]["orphan_claims"]
                           + report["summary"]["expired_claims"], 0)

    def test_expiring_claims_within_window(self):
        # Claim expiring in 10 days
        from datetime import datetime, timezone, timedelta
        soon = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Expiring soon",
            "valid_until": soon,
            "evidence": [{"source_url": "https://example.com"}],
        }))
        result = self.kb.kb_expiring_claims(MockHandle({
            "db_path": self.db_path,
            "expiry_window_days": 30,
        }))
        self.assertEqual(result["expiring_count"], 1)

    def test_expiring_claims_outside_window(self):
        from datetime import datetime, timezone, timedelta
        far = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        self.kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Far future",
            "valid_until": far,
            "evidence": [{"source_url": "https://example.com"}],
        }))
        result = self.kb.kb_expiring_claims(MockHandle({
            "db_path": self.db_path,
            "expiry_window_days": 30,
        }))
        self.assertEqual(result["expiring_count"], 0)


if __name__ == "__main__":
    unittest.main()
