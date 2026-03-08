"""Tests for the event log (i12: event-sourced storage).

Verifies that state-changing KB operations emit the correct
events to the events table, and that events_since queries
work correctly.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "workers", "kb"))
import worker as kb_mod


class FakeHandle:
    """Minimal handle for testing skills."""
    def __init__(self, params):
        self.params = params


def make_db():
    """Create a temp DB and return its path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = kb_mod._get_db(path)
    conn.close()
    return path


def get_events(db_path, event_type=None):
    """Read events from the DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if event_type:
        rows = conn.execute(
            "SELECT * FROM events WHERE event_type = ? "
            "ORDER BY sequence",
            (event_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY sequence"
        ).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


class TestEventLogSchema(unittest.TestCase):
    def test_events_table_exists(self):
        db_path = make_db()
        try:
            conn = sqlite3.connect(db_path)
            tables = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='events'"
            ).fetchall()
            self.assertEqual(len(tables), 1)
            conn.close()
        finally:
            os.unlink(db_path)

    def test_events_table_columns(self):
        db_path = make_db()
        try:
            conn = sqlite3.connect(db_path)
            cols = conn.execute(
                "PRAGMA table_info(events)"
            ).fetchall()
            col_names = [c[1] for c in cols]
            expected = [
                "event_id", "sequence", "event_type",
                "aggregate_id", "aggregate_type", "payload",
                "domain_id", "created_at", "created_by",
            ]
            for name in expected:
                self.assertIn(name, col_names)
            conn.close()
        finally:
            os.unlink(db_path)


class TestStoreClaimEvents(unittest.TestCase):
    def test_new_claim_emits_integrated_event(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            result = w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "The sky is blue",
                "category": "science",
                "confidence": 0.7,
                "status": "reported",
                "source_tier": "T3",
                "evidence": [{
                    "source_url": "https://example.com",
                    "source_tier": "T3",
                    "excerpt": "Blue sky observed",
                }],
            }))
            self.assertTrue(result["stored"])

            events = get_events(db_path, "claim.integrated")
            self.assertEqual(len(events), 1)
            payload = json.loads(events[0]["payload"])
            self.assertEqual(
                payload["after"]["statement"],
                "The sky is blue")
            self.assertEqual(
                payload["after"]["confidence"], 0.7)
            self.assertEqual(payload["evidence_count"], 1)

            # Also check evidence.added event
            ev_events = get_events(
                db_path, "evidence.added")
            self.assertEqual(len(ev_events), 1)
        finally:
            os.unlink(db_path)

    def test_dedup_claim_emits_evidence_added(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            # Store initial claim
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Water is wet",
                "evidence": [{
                    "source_url": "https://a.com",
                    "source_tier": "T2",
                }],
            }))
            # Store duplicate with new evidence
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Water is wet",
                "evidence": [{
                    "source_url": "https://b.com",
                    "source_tier": "T3",
                }],
            }))

            events = get_events(db_path, "evidence.added")
            # First store: 1 evidence.added
            # Dedup path: 1 evidence.added
            self.assertGreaterEqual(len(events), 2)
        finally:
            os.unlink(db_path)


class TestUpdateClaimEvents(unittest.TestCase):
    def test_update_emits_claim_updated(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            result = w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Test claim",
                "confidence": 0.5,
                "status": "reported",
            }))
            claim_id = result["claim_id"]

            w.kb_update_claim(FakeHandle({
                "db_path": db_path,
                "claim_id": claim_id,
                "confidence": 0.85,
                "status": "corroborated",
                "change_reason": "second source confirmed",
            }))

            events = get_events(db_path, "claim.updated")
            self.assertEqual(len(events), 1)
            payload = json.loads(events[0]["payload"])
            self.assertEqual(
                payload["before"]["confidence"], 0.5)
            self.assertEqual(
                payload["after"]["confidence"], 0.85)
        finally:
            os.unlink(db_path)

    def test_confidence_level_crossing_emits_extra(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            result = w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Crossing test",
                "confidence": 0.3,
                "status": "reported",
            }))
            claim_id = result["claim_id"]

            # 0.3 (contested) -> 0.9 (verified) = crossing
            w.kb_update_claim(FakeHandle({
                "db_path": db_path,
                "claim_id": claim_id,
                "confidence": 0.9,
                "change_reason": "verified by T1 source",
            }))

            events = get_events(
                db_path, "claim.confidence_changed")
            self.assertGreaterEqual(len(events), 1)
            payload = json.loads(events[-1]["payload"])
            self.assertIn("level", payload["before"])
            self.assertIn("level", payload["after"])
            self.assertNotEqual(
                payload["before"]["level"],
                payload["after"]["level"])
        finally:
            os.unlink(db_path)


class TestContradictionEvents(unittest.TestCase):
    def test_contradiction_emits_events(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            r1 = w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Budget is $4M",
                "confidence": 0.7,
                "source_tier": "T3",
            }))
            r2 = w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Budget is $6M",
                "confidence": 0.7,
                "source_tier": "T3",
            }))

            w.kb_record_contradiction(FakeHandle({
                "db_path": db_path,
                "claim_a_id": r1["claim_id"],
                "claim_b_id": r2["claim_id"],
                "nature": "numeric_conflict",
            }))

            contra_events = get_events(
                db_path, "contradiction.created")
            self.assertEqual(len(contra_events), 1)

            conf_events = get_events(
                db_path, "claim.confidence_changed")
            # Both claims should get confidence changed
            self.assertGreaterEqual(len(conf_events), 2)
        finally:
            os.unlink(db_path)


class TestRetractSourceEvents(unittest.TestCase):
    def test_retraction_emits_cascade(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Fact from bad source",
                "confidence": 0.6,
                "evidence": [{
                    "source_url": "https://bad.com/article",
                    "source_tier": "T5",
                }],
            }))

            w.kb_retract_source(FakeHandle({
                "db_path": db_path,
                "source_url": "https://bad.com/article",
                "reason": "retracted",
                "detail": "Source found unreliable",
            }))

            # source.retracted event
            src_events = get_events(
                db_path, "source.retracted")
            self.assertEqual(len(src_events), 1)

            # evidence.retracted events
            ev_events = get_events(
                db_path, "evidence.retracted")
            self.assertGreaterEqual(len(ev_events), 1)

            # claim downgrade events
            conf_events = get_events(
                db_path, "claim.confidence_changed")
            self.assertGreaterEqual(len(conf_events), 1)
        finally:
            os.unlink(db_path)


class TestEventsSinceSkill(unittest.TestCase):
    def test_events_since_zero_returns_all(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Claim one",
            }))
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Claim two",
            }))

            result = w.kb_events_since(FakeHandle({
                "db_path": db_path,
                "since_sequence": 0,
            }))
            self.assertGreater(result["count"], 0)
            self.assertGreater(result["latest_sequence"], 0)
            # Payloads should be parsed dicts
            for evt in result["events"]:
                self.assertIsInstance(evt["payload"], dict)
        finally:
            os.unlink(db_path)

    def test_events_since_filters_by_sequence(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "First claim",
            }))

            # Get current max sequence
            result1 = w.kb_event_count(FakeHandle({
                "db_path": db_path,
            }))
            seq_after_first = result1["latest_sequence"]

            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Second claim",
            }))

            result2 = w.kb_events_since(FakeHandle({
                "db_path": db_path,
                "since_sequence": seq_after_first,
            }))
            # Should only see events from second claim
            for evt in result2["events"]:
                self.assertGreater(
                    evt["sequence"], seq_after_first)
        finally:
            os.unlink(db_path)

    def test_events_since_filters_by_type(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            w.kb_store_claim(FakeHandle({
                "db_path": db_path,
                "statement": "Test claim",
                "evidence": [{
                    "source_url": "https://x.com",
                    "source_tier": "T3",
                }],
            }))

            result = w.kb_events_since(FakeHandle({
                "db_path": db_path,
                "since_sequence": 0,
                "event_type": "claim.integrated",
            }))
            for evt in result["events"]:
                self.assertEqual(
                    evt["event_type"], "claim.integrated")
        finally:
            os.unlink(db_path)


class TestEventCount(unittest.TestCase):
    def test_empty_db_returns_zero(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            result = w.kb_event_count(FakeHandle({
                "db_path": db_path,
            }))
            self.assertEqual(result["total_events"], 0)
            self.assertEqual(result["latest_sequence"], 0)
        finally:
            os.unlink(db_path)


class TestSequenceMonotonicity(unittest.TestCase):
    def test_sequences_are_monotonic(self):
        db_path = make_db()
        try:
            w = kb_mod.LoomKBWorker(worker_id="test")
            for i in range(5):
                w.kb_store_claim(FakeHandle({
                    "db_path": db_path,
                    "statement": f"Claim number {i}",
                }))

            all_events = get_events(db_path)
            sequences = [e["sequence"] for e in all_events]
            # Strictly increasing
            for i in range(1, len(sequences)):
                self.assertGreater(
                    sequences[i], sequences[i - 1])
        finally:
            os.unlink(db_path)


class TestConfidenceLevel(unittest.TestCase):
    def test_level_boundaries(self):
        self.assertEqual(
            kb_mod._confidence_level(0.90), "verified")
        self.assertEqual(
            kb_mod._confidence_level(0.85), "verified")
        self.assertEqual(
            kb_mod._confidence_level(0.70), "corroborated")
        self.assertEqual(
            kb_mod._confidence_level(0.50), "reported")
        self.assertEqual(
            kb_mod._confidence_level(0.20), "contested")
        self.assertEqual(
            kb_mod._confidence_level(0.05), "unverified")
        self.assertEqual(
            kb_mod._confidence_level(0.0), "unverified")


if __name__ == "__main__":
    unittest.main()
