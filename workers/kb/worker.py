"""LoomKBWorker — knowledge base query and storage.

Provides the persistent storage layer for the Loom evidence graph. Uses
SQLite for storage with a schema supporting claims, evidence links,
provenance chains, and version history.
"""

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Anti-patterns from the spec
ANTI_PATTERN_ORPHAN_CLAIM = "orphan_claim"  # Claim without evidence link
ANTI_PATTERN_DANGLING_REF = "dangling_reference"  # Evidence link to missing source
ANTI_PATTERN_NO_PROVENANCE = "no_provenance"  # Claim without source chain

# SQLite schema for the evidence graph
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    category TEXT,
    confidence REAL DEFAULT 0.0,
    status TEXT DEFAULT 'unverified',
    source_tier TEXT,
    valid_from TEXT,
    valid_until TEXT,
    ttl_category TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    source_url TEXT,
    source_tier TEXT,
    content_hash TEXT,
    excerpt TEXT,
    retrieved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_versions (
    version_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    statement TEXT NOT NULL,
    confidence REAL,
    status TEXT,
    changed_by TEXT,
    change_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT,
    aliases TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    subject_id TEXT REFERENCES entities(entity_id),
    predicate TEXT NOT NULL,
    object_id TEXT REFERENCES entities(entity_id),
    claim_id TEXT REFERENCES claims(claim_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contradictions (
    contradiction_id TEXT PRIMARY KEY,
    claim_a_id TEXT REFERENCES claims(claim_id),
    claim_b_id TEXT REFERENCES claims(claim_id),
    nature TEXT,
    resolution TEXT,
    resolved_by TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_versions_claim ON claim_versions(claim_id);
CREATE INDEX IF NOT EXISTS idx_relationships_subject ON relationships(subject_id);
CREATE INDEX IF NOT EXISTS idx_relationships_object ON relationships(object_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_claims_category ON claims(category);
"""

DEFAULT_DB_PATH = "/home/hughlynch/loom/data/loom.db"


def _generate_id(prefix: str, content: str) -> str:
    """Generate a deterministic ID from content."""
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{h}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db(db_path: str = "") -> sqlite3.Connection:
    """Get a database connection, creating schema if needed."""
    path = db_path or os.environ.get("LOOM_DB_PATH", DEFAULT_DB_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


class LoomKBWorker(Worker):
    worker_type = "kb"

    @skill("loom.kb.search", "Semantic search over the evidence graph")
    def kb_search(self, handle):
        """Search the knowledge base for claims matching a query.

        Stub for semantic search. In production, this would use an
        embedding index for vector similarity search.

        Params (from handle.params):
            query (str): Search query.
            limit (int, optional): Maximum results (default 10).
            status_filter (str, optional): Filter by claim status.
            topic_filter (str, optional): Filter by topic/category.

        Returns:
            dict with results list, each containing claim_id, statement,
            confidence, evidence.
        """
        params = handle.params
        query = params.get("query", "")
        limit = params.get("limit", 10)
        status_filter = params.get("status_filter", "")

        if not query:
            return {"error": "query is required", "results": []}

        db = _get_db(params.get("db_path", ""))
        try:
            # Stub: simple LIKE search. Production would use vector similarity.
            sql = "SELECT * FROM claims WHERE statement LIKE ? "
            args = [f"%{query}%"]

            if status_filter:
                sql += "AND status = ? "
                args.append(status_filter)

            sql += "ORDER BY confidence DESC LIMIT ?"
            args.append(limit)

            rows = db.execute(sql, args).fetchall()

            results = []
            for row in rows:
                claim_id = row["claim_id"]
                evidence_rows = db.execute(
                    "SELECT * FROM evidence WHERE claim_id = ?", (claim_id,)
                ).fetchall()

                results.append({
                    "claim_id": claim_id,
                    "statement": row["statement"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "evidence": [dict(e) for e in evidence_rows],
                })

            return {"results": results, "query": query, "total": len(results)}
        finally:
            db.close()

    @skill("loom.kb.query_claim", "Get full claim with provenance chain")
    def kb_query_claim(self, handle):
        """Retrieve a full claim with its provenance chain and contradictions.

        Params (from handle.params):
            claim_id (str): The claim ID to look up.

        Returns:
            dict with claim, evidence_chain, contradictions.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")

        if not claim_id:
            return {"error": "claim_id is required"}

        db = _get_db(params.get("db_path", ""))
        try:
            row = db.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()

            if not row:
                return {"error": f"claim {claim_id} not found"}

            evidence_rows = db.execute(
                "SELECT * FROM evidence WHERE claim_id = ? ORDER BY created_at",
                (claim_id,),
            ).fetchall()

            contradiction_rows = db.execute(
                "SELECT * FROM contradictions "
                "WHERE claim_a_id = ? OR claim_b_id = ?",
                (claim_id, claim_id),
            ).fetchall()

            return {
                "claim": dict(row),
                "evidence_chain": [dict(e) for e in evidence_rows],
                "contradictions": [dict(c) for c in contradiction_rows],
            }
        finally:
            db.close()

    @skill("loom.kb.claim_history", "Get claim change history")
    def kb_claim_history(self, handle):
        """Retrieve the version history of a claim.

        Params (from handle.params):
            claim_id (str): The claim ID to look up.

        Returns:
            dict with claim_id, versions, evidence_chain.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")

        if not claim_id:
            return {"error": "claim_id is required"}

        db = _get_db(params.get("db_path", ""))
        try:
            versions = db.execute(
                "SELECT * FROM claim_versions WHERE claim_id = ? "
                "ORDER BY created_at DESC",
                (claim_id,),
            ).fetchall()

            evidence_rows = db.execute(
                "SELECT * FROM evidence WHERE claim_id = ? ORDER BY created_at",
                (claim_id,),
            ).fetchall()

            return {
                "claim_id": claim_id,
                "versions": [dict(v) for v in versions],
                "evidence_chain": [dict(e) for e in evidence_rows],
            }
        finally:
            db.close()

    @skill("loom.kb.store_claim", "Store a new claim with evidence links")
    def kb_store_claim(self, handle):
        """Store a new claim with its evidence links in the knowledge base.

        Params (from handle.params):
            statement (str): The claim statement.
            category (str, optional): Claim category.
            confidence (float, optional): Confidence score.
            status (str, optional): Claim status.
            source_tier (str, optional): Source tier (T1-T7).
            valid_from (str, optional): Validity start.
            valid_until (str, optional): Validity end.
            ttl_category (str, optional): TTL category.
            evidence (list, optional): List of evidence dicts with
                source_url, source_tier, content_hash, excerpt.

        Returns:
            dict with claim_id, stored (bool).
        """
        params = handle.params
        statement = params.get("statement", "")

        if not statement:
            return {"error": "statement is required", "stored": False}

        now = _now_iso()
        claim_id = _generate_id("claim", statement + now)

        db = _get_db(params.get("db_path", ""))
        try:
            db.execute(
                "INSERT INTO claims "
                "(claim_id, statement, category, confidence, status, "
                "source_tier, valid_from, valid_until, ttl_category, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    statement,
                    params.get("category", ""),
                    params.get("confidence", 0.0),
                    params.get("status", "unverified"),
                    params.get("source_tier", "T5"),
                    params.get("valid_from", now),
                    params.get("valid_until"),
                    params.get("ttl_category", ""),
                    now,
                    now,
                ),
            )

            # Store initial version
            version_id = _generate_id("ver", claim_id + now)
            db.execute(
                "INSERT INTO claim_versions "
                "(version_id, claim_id, statement, confidence, status, "
                "changed_by, change_reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    claim_id,
                    statement,
                    params.get("confidence", 0.0),
                    params.get("status", "unverified"),
                    "system",
                    "initial_store",
                    now,
                ),
            )

            # Store evidence links
            evidence_list = params.get("evidence", [])
            for ev in evidence_list:
                evidence_id = _generate_id(
                    "ev", claim_id + ev.get("source_url", "") + now
                )
                db.execute(
                    "INSERT INTO evidence "
                    "(evidence_id, claim_id, source_url, source_tier, "
                    "content_hash, excerpt, retrieved_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        evidence_id,
                        claim_id,
                        ev.get("source_url", ""),
                        ev.get("source_tier", ""),
                        ev.get("content_hash", ""),
                        ev.get("excerpt", ""),
                        ev.get("retrieved_at", now),
                        now,
                    ),
                )

            db.commit()
            return {"claim_id": claim_id, "stored": True}
        except Exception as e:
            db.rollback()
            return {"error": str(e), "stored": False}
        finally:
            db.close()


worker = LoomKBWorker(worker_id="loom-kb-1")

if __name__ == "__main__":
    worker.run()
