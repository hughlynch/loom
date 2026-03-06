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
