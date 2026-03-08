"""Tests for the monitor worker (i17).

Verifies source rate monitoring, challenge health, anomaly
detection, and composite system health reporting.
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

from workers.kb.worker import LoomKBWorker, _vector_indices
from workers.monitor.worker import (
    MonitorWorker,
    _source_rate_metrics,
    _detect_anomalies,
    _challenge_metrics,
    _db_stats,
    _snapshot_freshness,
    ANOMALY_LOW_TIER_WAVE,
    ANOMALY_SINGLE_ORIGIN,
    ANOMALY_TOPIC_FLOOD,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
)


class MockHandle:
    def __init__(self, params):
        self.params = params


def _make_db(claims=None):
    """Create a temp DB, optionally with claims."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _vector_indices.clear()
    kb = LoomKBWorker(worker_id="test")
    for data in (claims or []):
        kb.kb_store_claim(MockHandle({
            "db_path": path, **data,
        }))
    return path


class TestDetectAnomalies(unittest.TestCase):
    """Test anomaly detection logic."""

    def test_no_anomalies_when_empty(self):
        anomalies = _detect_anomalies({
            "total_new": 0, "tier_counts": {},
            "domain_counts": {}, "category_counts": {},
        })
        self.assertEqual(anomalies, [])

    def test_low_tier_wave(self):
        anomalies = _detect_anomalies({
            "total_new": 10,
            "tier_counts": {"T6": 4, "T7": 3, "T3": 3},
            "domain_counts": {},
            "category_counts": {},
        })
        types = [a["type"] for a in anomalies]
        self.assertIn(ANOMALY_LOW_TIER_WAVE, types)

    def test_no_wave_when_below_threshold(self):
        anomalies = _detect_anomalies({
            "total_new": 10,
            "tier_counts": {"T6": 2, "T7": 1, "T2": 7},
            "domain_counts": {},
            "category_counts": {},
        })
        types = [a["type"] for a in anomalies]
        self.assertNotIn(ANOMALY_LOW_TIER_WAVE, types)

    def test_single_origin_flood(self):
        anomalies = _detect_anomalies({
            "total_new": 10,
            "tier_counts": {},
            "domain_counts": {
                "spam.com": 8, "good.com": 2,
            },
            "category_counts": {},
        })
        types = [a["type"] for a in anomalies]
        self.assertIn(ANOMALY_SINGLE_ORIGIN, types)
        flood = [
            a for a in anomalies
            if a["type"] == ANOMALY_SINGLE_ORIGIN
        ][0]
        self.assertEqual(flood["domain"], "spam.com")

    def test_topic_flood(self):
        anomalies = _detect_anomalies({
            "total_new": 10,
            "tier_counts": {},
            "domain_counts": {},
            "category_counts": {
                "politics": 8, "science": 2,
            },
        })
        types = [a["type"] for a in anomalies]
        self.assertIn(ANOMALY_TOPIC_FLOOD, types)

    def test_small_sample_no_anomalies(self):
        """Don't flag anomalies with < 5 items."""
        anomalies = _detect_anomalies({
            "total_new": 3,
            "tier_counts": {"T7": 3},
            "domain_counts": {"spam.com": 3},
            "category_counts": {"politics": 3},
        })
        self.assertEqual(anomalies, [])


class TestSourceRateMetrics(unittest.TestCase):
    """Test source rate computation from DB."""

    def setUp(self):
        self.db_path = _make_db([
            {
                "statement": "Claim from gov source",
                "source_tier": "T1",
                "category": "budget",
                "evidence": [{
                    "source_url": "https://gov.example.com/1",
                    "source_tier": "T1",
                }],
            },
            {
                "statement": "Another gov claim here",
                "source_tier": "T1",
                "category": "budget",
                "evidence": [{
                    "source_url": "https://gov.example.com/2",
                    "source_tier": "T1",
                }],
            },
            {
                "statement": "News report about events",
                "source_tier": "T3",
                "category": "events",
                "evidence": [{
                    "source_url": "https://news.example.com/a",
                    "source_tier": "T3",
                }],
            },
        ])

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def test_counts_claims(self):
        metrics = _source_rate_metrics(
            self.db_path, window_hours=24)
        self.assertEqual(metrics["total_new"], 3)

    def test_tier_distribution(self):
        metrics = _source_rate_metrics(
            self.db_path, window_hours=24)
        self.assertEqual(
            metrics["tier_counts"].get("T1", 0), 2)
        self.assertEqual(
            metrics["tier_counts"].get("T3", 0), 1)

    def test_domain_distribution(self):
        metrics = _source_rate_metrics(
            self.db_path, window_hours=24)
        domains = metrics["domain_counts"]
        self.assertIn("gov.example.com", domains)

    def test_empty_db(self):
        fd, empty = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            metrics = _source_rate_metrics(
                empty, window_hours=24)
            self.assertEqual(metrics["total_new"], 0)
        finally:
            os.unlink(empty)


class TestChallengeMetrics(unittest.TestCase):
    """Test challenge health computation."""

    def setUp(self):
        self.db_path = _make_db([
            {
                "statement": "Budget is $4 million",
                "confidence": 0.7,
                "source_tier": "T3",
            },
            {
                "statement": "Budget is $6 million",
                "confidence": 0.7,
                "source_tier": "T3",
            },
        ])
        # Record a contradiction.
        kb = LoomKBWorker(worker_id="test")
        result1 = kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Test claim A for contradiction",
        }))
        result2 = kb.kb_store_claim(MockHandle({
            "db_path": self.db_path,
            "statement": "Test claim B for contradiction",
        }))
        # These may be deduped, so get IDs from search.
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        ids = [
            r["claim_id"]
            for r in conn.execute(
                "SELECT claim_id FROM claims LIMIT 2"
            ).fetchall()
        ]
        conn.close()
        if len(ids) >= 2:
            kb.kb_record_contradiction(MockHandle({
                "db_path": self.db_path,
                "claim_a_id": ids[0],
                "claim_b_id": ids[1],
                "nature": "numeric_conflict",
            }))

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def test_counts_contradictions(self):
        metrics = _challenge_metrics(
            self.db_path, window_days=30)
        self.assertGreaterEqual(
            metrics["total_contradictions"], 1)

    def test_unresolved_counted(self):
        metrics = _challenge_metrics(
            self.db_path, window_days=30)
        # All are unresolved (no resolved_at set).
        self.assertEqual(
            metrics["unresolved"],
            metrics["total_contradictions"])


class TestDbStats(unittest.TestCase):
    def test_counts_tables(self):
        db_path = _make_db([
            {"statement": "Stat test claim"},
        ])
        try:
            stats = _db_stats(db_path)
            self.assertGreaterEqual(stats["claims"], 1)
            self.assertGreater(stats["events"], 0)
            self.assertGreater(stats["db_size_kb"], 0)
        finally:
            _vector_indices.clear()
            os.unlink(db_path)

    def test_nonexistent_db(self):
        stats = _db_stats("/nonexistent/db.sqlite")
        self.assertEqual(stats["claims"], 0)


class TestSnapshotFreshness(unittest.TestCase):
    def test_no_snapshot_dir(self):
        result = _snapshot_freshness(
            "nonexistent",
            "/tmp/no-such-snapshots-dir")
        self.assertFalse(result["has_snapshot"])

    def test_with_snapshot(self):
        # Create a mock snapshot directory.
        import json
        snap_dir = tempfile.mkdtemp()
        domain_dir = os.path.join(snap_dir, "test")
        v1_dir = os.path.join(domain_dir, "v1")
        os.makedirs(v1_dir)
        manifest = {
            "version": "v1",
            "built_at": _make_recent_time(),
            "claim_count": 10,
            "event_sequence": 5,
        }
        with open(
            os.path.join(v1_dir, "manifest.json"), "w"
        ) as f:
            json.dump(manifest, f)

        result = _snapshot_freshness(
            "test", snap_dir)
        self.assertTrue(result["has_snapshot"])
        self.assertEqual(result["version"], "v1")
        self.assertEqual(result["claim_count"], 10)
        self.assertIsNotNone(result["age_hours"])

        import shutil
        shutil.rmtree(snap_dir)


def _make_recent_time():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class TestMonitorSourceRates(unittest.TestCase):
    """Test the source_rates skill."""

    def setUp(self):
        self.db_path = _make_db([
            {
                "statement": f"Claim {i} from various",
                "source_tier": "T3",
                "category": "general",
            }
            for i in range(3)
        ])
        self.monitor = MonitorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def test_returns_distribution(self):
        result = self.monitor.monitor_source_rates(
            MockHandle({"db_path": self.db_path}))
        self.assertEqual(
            result["total_new_claims"], 3)
        self.assertIn("tier_distribution", result)
        self.assertIn("anomalies", result)


class TestMonitorChallengeHealth(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db([
            {"statement": "Health test claim"},
        ])
        self.monitor = MonitorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def test_returns_metrics(self):
        result = self.monitor.monitor_challenge_health(
            MockHandle({"db_path": self.db_path}))
        self.assertIn("total_contradictions", result)
        self.assertIn("alerts", result)


class TestMonitorSystemHealth(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db([
            {"statement": "System health test"},
        ])
        self.monitor = MonitorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def test_returns_health_status(self):
        result = self.monitor.monitor_system_health(
            MockHandle({"db_path": self.db_path}))
        self.assertIn(
            result["overall_status"],
            ["healthy", "attention_needed", "degraded"])
        self.assertIn("db_stats", result)
        self.assertIn("snapshot_freshness", result)

    def test_healthy_without_snapshot(self):
        result = self.monitor.monitor_system_health(
            MockHandle({
                "db_path": self.db_path,
                "snapshots_dir": "/tmp/nonexistent",
            }))
        self.assertIn("no_snapshot", result["issues"])


if __name__ == "__main__":
    unittest.main()
