"""Tests for vector search integration (i14).

Verifies that the KB worker uses grove-kit VectorIndex for
semantic search, with auto-reindexing, proper fallback to
LIKE queries when vector search is unavailable, and that
search results include the search_method field.
"""

import os
import sys
import tempfile
import unittest

# Set up paths
LOOM_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LOOM_DIR)
sys.path.insert(0, os.path.join(
    os.path.expanduser("~"), "grove", "python"))

from workers.kb.worker import (
    LoomKBWorker,
    _get_vector_index,
    _vector_search,
    _reindex_all,
    _vector_indices,
    _VECTOR_AVAILABLE,
)


class MockHandle:
    def __init__(self, params):
        self.params = params


class TestVectorAvailability(unittest.TestCase):
    """Verify grove-kit vector module is importable."""

    def test_vector_available(self):
        self.assertTrue(_VECTOR_AVAILABLE)


class TestVectorIndexCreation(unittest.TestCase):
    """Test lazy vector index creation."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        # Clear cached indices.
        _vector_indices.clear()

    def tearDown(self):
        _vector_indices.clear()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_get_vector_index_returns_index(self):
        idx = _get_vector_index(self.db_path)
        self.assertIsNotNone(idx)
        self.assertEqual(idx.count(), 0)

    def test_index_is_cached(self):
        idx1 = _get_vector_index(self.db_path)
        idx2 = _get_vector_index(self.db_path)
        self.assertIs(idx1, idx2)

    def test_different_dbs_get_different_indices(self):
        fd2, db2 = tempfile.mkstemp(suffix=".db")
        os.close(fd2)
        try:
            idx1 = _get_vector_index(self.db_path)
            idx2 = _get_vector_index(db2)
            self.assertIsNot(idx1, idx2)
        finally:
            os.unlink(db2)


class TestVectorSearchIntegration(unittest.TestCase):
    """Test vector search through KB worker skills."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _vector_indices.clear()
        self.kb = LoomKBWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_store_claim_indexes_vector(self):
        """Storing a claim adds it to the vector index."""
        self.kb.kb_store_claim(self._params(
            statement="The population of Springfield is 50000",
            confidence=0.7,
        ))
        idx = _get_vector_index(self.db_path)
        self.assertEqual(idx.count(), 1)

    def test_multiple_claims_indexed(self):
        """Multiple claims are all indexed."""
        for i in range(5):
            self.kb.kb_store_claim(self._params(
                statement=f"Claim number {i} about topic {i}",
            ))
        idx = _get_vector_index(self.db_path)
        self.assertEqual(idx.count(), 5)

    def test_search_uses_vector_method(self):
        """kb_search reports vector search method."""
        self.kb.kb_store_claim(self._params(
            statement="The city council approved the budget",
            confidence=0.7,
        ))
        result = self.kb.kb_search(self._params(
            query="city council budget approval",
        ))
        self.assertEqual(
            result["search_method"], "vector")
        self.assertGreaterEqual(len(result["results"]), 1)

    def test_find_similar_uses_vector_method(self):
        """kb_find_similar reports vector search method."""
        self.kb.kb_store_claim(self._params(
            statement="Revenue grew 15% year over year",
        ))
        self.kb.kb_store_claim(self._params(
            statement="Profits increased 12% annually",
        ))
        result = self.kb.kb_find_similar(self._params(
            statement="Revenue growth was 20% this year",
        ))
        self.assertEqual(
            result["search_method"], "vector")
        self.assertIn("similar_matches", result)

    def test_find_similar_excludes_exact(self):
        """Exact matches excluded from similar_matches."""
        self.kb.kb_store_claim(self._params(
            statement="The sky is blue",
        ))
        self.kb.kb_store_claim(self._params(
            statement="The ocean is blue",
        ))
        result = self.kb.kb_find_similar(self._params(
            statement="The sky is blue",
        ))
        self.assertEqual(len(result["exact_matches"]), 1)
        for m in result["similar_matches"]:
            self.assertNotEqual(
                m["statement"], "The sky is blue")

    def test_search_with_status_filter(self):
        """Vector search respects status_filter."""
        self.kb.kb_store_claim(self._params(
            statement="Claim A about testing",
            status="verified",
            confidence=0.9,
        ))
        self.kb.kb_store_claim(self._params(
            statement="Claim B about testing",
            status="contested",
            confidence=0.3,
        ))
        result = self.kb.kb_search(self._params(
            query="testing",
            status_filter="verified",
        ))
        for r in result["results"]:
            self.assertEqual(r["status"], "verified")


class TestAutoReindex(unittest.TestCase):
    """Test auto-reindexing when index is empty but DB has claims."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _vector_indices.clear()
        self.kb = LoomKBWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_reindex_populates_empty_index(self):
        """_reindex_all fills the index from existing DB claims."""
        # Store claims (which indexes them).
        self.kb.kb_store_claim(self._params(
            statement="First claim",
        ))
        self.kb.kb_store_claim(self._params(
            statement="Second claim",
        ))

        # Clear and recreate the index.
        _vector_indices.clear()
        idx = _get_vector_index(self.db_path)
        self.assertEqual(idx.count(), 0)

        count = _reindex_all(self.db_path)
        self.assertEqual(count, 2)
        self.assertEqual(idx.count(), 2)

    def test_search_auto_reindexes(self):
        """Search auto-reindexes when index is empty."""
        self.kb.kb_store_claim(self._params(
            statement="Auto reindex test claim",
        ))

        # Clear the index but keep the DB.
        _vector_indices.clear()

        # Search should still work (triggers reindex).
        result = self.kb.kb_search(self._params(
            query="auto reindex",
        ))
        self.assertEqual(
            result["search_method"], "vector")
        self.assertGreaterEqual(len(result["results"]), 1)

    def test_vector_search_empty_db(self):
        """_vector_search returns None for empty DB."""
        result = _vector_search(self.db_path, "anything")
        self.assertIsNone(result)


class TestDedupDoesNotDuplicateIndex(unittest.TestCase):
    """Verify that dedup path doesn't add duplicate vectors."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _vector_indices.clear()
        self.kb = LoomKBWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_dedup_does_not_add_vector(self):
        """Dedup (same statement) doesn't add a second vector."""
        self.kb.kb_store_claim(self._params(
            statement="Water is wet",
            evidence=[{
                "source_url": "https://a.com",
                "source_tier": "T3",
            }],
        ))
        self.kb.kb_store_claim(self._params(
            statement="Water is wet",
            evidence=[{
                "source_url": "https://b.com",
                "source_tier": "T3",
            }],
        ))
        idx = _get_vector_index(self.db_path)
        # Only one vector (from the first store).
        self.assertEqual(idx.count(), 1)


if __name__ == "__main__":
    unittest.main()
