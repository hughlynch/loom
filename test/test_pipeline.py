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
    STATUS_VERIFIED,
    STATUS_CORROBORATED,
    STATUS_REPORTED,
    STATUS_CONTESTED,
    STATUS_UNVERIFIED,
)
from workers.kb.worker import LoomKBWorker


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
        self.assertEqual(len(results["results"]), 1)
        self.assertIn("boils", results["results"][0]["statement"])

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


if __name__ == "__main__":
    unittest.main()
