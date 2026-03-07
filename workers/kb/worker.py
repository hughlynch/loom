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
    info_credibility TEXT,
    evidence_strength TEXT DEFAULT 'limited',
    agreement_level TEXT DEFAULT 'low',
    analytic_confidence TEXT,
    claim_type TEXT,
    valid_from TEXT,
    valid_until TEXT,
    ttl_category TEXT,
    temporal_status TEXT DEFAULT 'current',
    superseded_by TEXT,
    superseded_reason TEXT,
    deprecation_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    source_url TEXT,
    source_tier TEXT,
    info_credibility TEXT,
    relationship TEXT DEFAULT 'supports',
    content_hash TEXT,
    excerpt TEXT,
    warrant TEXT,
    assumptions TEXT,
    inference TEXT DEFAULT 'verbatim',
    directness TEXT DEFAULT 'direct',
    upstream_source TEXT,
    retracted INTEGER DEFAULT 0,
    retracted_reason TEXT,
    retracted_at TEXT,
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

CREATE TABLE IF NOT EXISTS grade_adjustments (
    adjustment_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    factor TEXT NOT NULL,
    direction TEXT NOT NULL,
    magnitude REAL NOT NULL,
    justification TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disagreements (
    disagreement_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_strength TEXT NOT NULL,
    agreement_level TEXT NOT NULL,
    nature TEXT,
    axis TEXT,
    resolution_path TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disagreement_positions (
    position_id TEXT PRIMARY KEY,
    disagreement_id TEXT NOT NULL REFERENCES disagreements(disagreement_id),
    position TEXT NOT NULL,
    evidence_ids TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_grade_evidence ON grade_adjustments(evidence_id);
CREATE INDEX IF NOT EXISTS idx_disagreements_claim ON disagreements(claim_id);
CREATE INDEX IF NOT EXISTS idx_positions_disagreement ON disagreement_positions(disagreement_id);
CREATE INDEX IF NOT EXISTS idx_versions_claim ON claim_versions(claim_id);
CREATE INDEX IF NOT EXISTS idx_relationships_subject ON relationships(subject_id);
CREATE INDEX IF NOT EXISTS idx_relationships_object ON relationships(object_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_claims_category ON claims(category);

CREATE TABLE IF NOT EXISTS source_retractions (
    retraction_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT,
    retracted_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retractions_url ON source_retractions(source_url);

CREATE TABLE IF NOT EXISTS dependency_labels (
    label_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_ids TEXT NOT NULL,
    is_minimal INTEGER DEFAULT 1,
    is_valid INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_labels_claim ON dependency_labels(claim_id);
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
        db = _get_db(params.get("db_path", ""))
        try:
            # Deduplication: check for exact match first
            existing = db.execute(
                "SELECT claim_id FROM claims WHERE statement = ?",
                (statement,),
            ).fetchone()

            if existing:
                # Add new evidence to existing claim instead of duplicating
                claim_id = existing["claim_id"]
                evidence_list = params.get("evidence", [])
                for ev in evidence_list:
                    # Check if this exact evidence already exists
                    dup_ev = db.execute(
                        "SELECT evidence_id FROM evidence "
                        "WHERE claim_id = ? AND source_url = ?",
                        (claim_id, ev.get("source_url", "")),
                    ).fetchone()
                    if dup_ev:
                        continue
                    evidence_id = _generate_id(
                        "ev", claim_id + ev.get("source_url", "") + now
                    )
                    db.execute(
                        "INSERT INTO evidence "
                        "(evidence_id, claim_id, source_url, source_tier, "
                        "content_hash, excerpt, info_credibility, relationship, "
                        "warrant, inference, directness, upstream_source, "
                        "retrieved_at, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            evidence_id, claim_id,
                            ev.get("source_url", ""),
                            ev.get("source_tier", ""),
                            ev.get("content_hash", ""),
                            ev.get("excerpt", ""),
                            ev.get("info_credibility"),
                            ev.get("relationship", "supports"),
                            ev.get("warrant"),
                            ev.get("inference", "verbatim"),
                            ev.get("directness", "direct"),
                            ev.get("upstream_source"),
                            ev.get("retrieved_at", now), now,
                        ),
                    )

                # Update confidence if new evidence provides higher confidence
                new_conf = params.get("confidence", 0.0)
                if new_conf > 0:
                    current = db.execute(
                        "SELECT confidence FROM claims WHERE claim_id = ?",
                        (claim_id,),
                    ).fetchone()
                    if current and new_conf > current["confidence"]:
                        db.execute(
                            "UPDATE claims SET confidence = ?, updated_at = ? "
                            "WHERE claim_id = ?",
                            (new_conf, now, claim_id),
                        )

                db.commit()
                return {
                    "claim_id": claim_id,
                    "stored": True,
                    "deduplicated": True,
                }

            claim_id = _generate_id("claim", statement + now)

            db.execute(
                "INSERT INTO claims "
                "(claim_id, statement, category, confidence, status, "
                "source_tier, info_credibility, analytic_confidence, "
                "claim_type, valid_from, valid_until, ttl_category, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    statement,
                    params.get("category", ""),
                    params.get("confidence", 0.0),
                    params.get("status", "unverified"),
                    params.get("source_tier", "T5"),
                    params.get("info_credibility"),
                    params.get("analytic_confidence"),
                    params.get("claim_type"),
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
                    "content_hash, excerpt, info_credibility, relationship, "
                    "warrant, inference, directness, upstream_source, "
                    "retrieved_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        evidence_id,
                        claim_id,
                        ev.get("source_url", ""),
                        ev.get("source_tier", ""),
                        ev.get("content_hash", ""),
                        ev.get("excerpt", ""),
                        ev.get("info_credibility"),
                        ev.get("relationship", "supports"),
                        ev.get("warrant"),
                        ev.get("inference", "verbatim"),
                        ev.get("directness", "direct"),
                        ev.get("upstream_source"),
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


    @skill("loom.kb.find_similar", "Find claims similar to a statement")
    def kb_find_similar(self, handle):
        """Find claims in the KB that are similar to a given statement.

        Uses exact match and LIKE-based fuzzy matching. Returns matches
        with their current confidence and evidence.

        Params (from handle.params):
            statement (str): The statement to match against.
            threshold (float, optional): Minimum word overlap (0-1).

        Returns:
            dict with exact_matches and fuzzy_matches.
        """
        params = handle.params
        statement = params.get("statement", "")

        if not statement:
            return {"error": "statement is required"}

        db = _get_db(params.get("db_path", ""))
        try:
            # Exact match
            exact = db.execute(
                "SELECT * FROM claims WHERE statement = ?", (statement,)
            ).fetchall()

            # Fuzzy: match on significant words (3+ chars, not stopwords)
            stopwords = {"the", "a", "an", "is", "are", "was", "were",
                         "in", "on", "at", "to", "for", "of", "and",
                         "or", "but", "not", "with", "by", "from", "that"}
            words = [w.lower().strip(".,;:!?\"'()") for w in statement.split()
                     if len(w) > 2 and w.lower() not in stopwords]

            fuzzy = []
            if words:
                # Search for claims containing key words.
                # Use top non-numeric keywords for fuzzy match
                # (numbers vary, words indicate topic similarity)
                text_words = [w for w in words if not w.replace(",", "").isdigit()][:3]
                if not text_words:
                    text_words = words[:2]

                conditions = " AND ".join(
                    "statement LIKE ?" for _ in text_words
                )
                args = [f"%{w}%" for w in text_words]
                rows = db.execute(
                    f"SELECT * FROM claims WHERE {conditions} "
                    "AND statement != ? LIMIT 20",
                    args + [statement],
                ).fetchall()
                fuzzy = [dict(r) for r in rows]

            return {
                "exact_matches": [dict(r) for r in exact],
                "fuzzy_matches": fuzzy,
            }
        finally:
            db.close()

    @skill("loom.kb.record_contradiction", "Record a contradiction between claims")
    def kb_record_contradiction(self, handle):
        """Record a contradiction between two claims.

        Updates both claims to 'contested' status with reduced confidence.

        Params (from handle.params):
            claim_a_id (str): First claim ID.
            claim_b_id (str): Second claim ID.
            nature (str): Nature of contradiction (numeric_conflict,
                direct_negation, temporal_conflict, scope_conflict).

        Returns:
            dict with contradiction_id, recorded (bool).
        """
        params = handle.params
        claim_a_id = params.get("claim_a_id", "")
        claim_b_id = params.get("claim_b_id", "")
        nature = params.get("nature", "unspecified")

        if not claim_a_id or not claim_b_id:
            return {"error": "claim_a_id and claim_b_id required", "recorded": False}

        db = _get_db(params.get("db_path", ""))
        try:
            # Verify both claims exist
            a = db.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_a_id,)
            ).fetchone()
            b = db.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_b_id,)
            ).fetchone()
            if not a or not b:
                return {"error": "one or both claims not found", "recorded": False}

            # Check for existing contradiction
            existing = db.execute(
                "SELECT contradiction_id FROM contradictions "
                "WHERE (claim_a_id = ? AND claim_b_id = ?) "
                "OR (claim_a_id = ? AND claim_b_id = ?)",
                (claim_a_id, claim_b_id, claim_b_id, claim_a_id),
            ).fetchone()
            if existing:
                return {
                    "contradiction_id": existing["contradiction_id"],
                    "recorded": True,
                    "already_existed": True,
                }

            now = _now_iso()
            contradiction_id = _generate_id(
                "contra", claim_a_id + claim_b_id + now
            )

            db.execute(
                "INSERT INTO contradictions "
                "(contradiction_id, claim_a_id, claim_b_id, nature, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (contradiction_id, claim_a_id, claim_b_id, nature, now),
            )

            # Update both claims to contested status
            for cid in (claim_a_id, claim_b_id):
                row = db.execute(
                    "SELECT confidence, source_tier FROM claims WHERE claim_id = ?",
                    (cid,),
                ).fetchone()
                if row:
                    # Recompute confidence at contested level
                    tier = row["source_tier"] or "T5"
                    # Use contested floor from confidence rules
                    contested_floors = {
                        "T1": 0.40, "T2": 0.30, "T3": 0.20,
                        "T4": 0.15, "T5": 0.10, "T6": 0.05, "T7": 0.01,
                    }
                    new_conf = contested_floors.get(tier, 0.10)

                    db.execute(
                        "UPDATE claims SET status = 'contested', "
                        "confidence = ?, updated_at = ? WHERE claim_id = ?",
                        (new_conf, now, cid),
                    )

                    # Version record
                    ver_id = _generate_id("ver", cid + now + "contradiction")
                    db.execute(
                        "INSERT INTO claim_versions "
                        "(version_id, claim_id, statement, confidence, "
                        "status, changed_by, change_reason, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            ver_id, cid, row["source_tier"] or "",
                            new_conf, "contested", "system",
                            f"contradiction with {contradiction_id}", now,
                        ),
                    )

            db.commit()
            return {
                "contradiction_id": contradiction_id,
                "recorded": True,
            }
        except Exception as e:
            db.rollback()
            return {"error": str(e), "recorded": False}
        finally:
            db.close()

    @skill("loom.kb.update_claim", "Update an existing claim with new evidence")
    def kb_update_claim(self, handle):
        """Update an existing claim's confidence/status with new evidence.

        Creates a version record tracking the change, optionally adds new
        evidence links.

        Params (from handle.params):
            claim_id (str): The claim to update.
            confidence (float, optional): New confidence score.
            status (str, optional): New status.
            change_reason (str): Why this update is being made.
            evidence (list, optional): New evidence links to add.

        Returns:
            dict with claim_id, updated (bool), version_id.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")
        change_reason = params.get("change_reason", "")

        if not claim_id:
            return {"error": "claim_id is required", "updated": False}
        if not change_reason:
            return {"error": "change_reason is required", "updated": False}

        db = _get_db(params.get("db_path", ""))
        try:
            # Verify claim exists
            row = db.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
            if not row:
                return {"error": f"claim {claim_id} not found", "updated": False}

            now = _now_iso()

            # Build update fields
            updates = []
            values = []
            new_confidence = params.get("confidence")
            new_status = params.get("status")

            if new_confidence is not None:
                updates.append("confidence = ?")
                values.append(new_confidence)
            if new_status is not None:
                updates.append("status = ?")
                values.append(new_status)

            updates.append("updated_at = ?")
            values.append(now)
            values.append(claim_id)

            db.execute(
                f"UPDATE claims SET {', '.join(updates)} WHERE claim_id = ?",
                values,
            )

            # Create version record
            version_id = _generate_id("ver", claim_id + now + change_reason)
            db.execute(
                "INSERT INTO claim_versions "
                "(version_id, claim_id, statement, confidence, status, "
                "changed_by, change_reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    claim_id,
                    row["statement"],
                    new_confidence if new_confidence is not None else row["confidence"],
                    new_status if new_status is not None else row["status"],
                    "system",
                    change_reason,
                    now,
                ),
            )

            # Add new evidence links
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
            return {
                "claim_id": claim_id,
                "updated": True,
                "version_id": version_id,
            }
        except Exception as e:
            db.rollback()
            return {"error": str(e), "updated": False}
        finally:
            db.close()


    @skill("loom.kb.retract_source", "Retract a source and propagate")
    def kb_retract_source(self, handle):
        """Retract a source URL and propagate to dependent claims.

        Marks all evidence from this source as retracted. For claims that
        have NO remaining valid (non-retracted) evidence, downgrades
        status to 'unverified' and confidence to floor. Creates version
        records for all affected claims.

        Params:
            source_url (str): The source URL to retract.
            reason (str): retracted|corrected|expired|discredited
            detail (str, optional): Explanation.

        Returns:
            dict with retraction record, affected evidence count,
            affected claim count, downgraded claims.
        """
        params = handle.params
        source_url = params.get("source_url", "")
        reason = params.get("reason", "retracted")
        detail = params.get("detail", "")

        if not source_url:
            return {"error": "source_url is required"}

        now = _now_iso()
        db = _get_db(params.get("db_path", ""))
        try:
            # Record the retraction
            retraction_id = _generate_id("ret", source_url + now)
            db.execute(
                "INSERT INTO source_retractions "
                "(retraction_id, source_url, reason, detail, "
                "retracted_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (retraction_id, source_url, reason, detail, now, now),
            )

            # Mark all evidence from this source as retracted
            db.execute(
                "UPDATE evidence SET retracted = 1, retracted_reason = ?, "
                "retracted_at = ? WHERE source_url = ?",
                (reason, now, source_url),
            )
            affected_evidence = db.total_changes

            # Find claims that had evidence from this source
            affected_claims = db.execute(
                "SELECT DISTINCT claim_id FROM evidence "
                "WHERE source_url = ?",
                (source_url,),
            ).fetchall()

            downgraded = []
            for row in affected_claims:
                claim_id = row["claim_id"]
                # Check if any valid evidence remains
                valid_count = db.execute(
                    "SELECT COUNT(*) as cnt FROM evidence "
                    "WHERE claim_id = ? AND retracted = 0",
                    (claim_id,),
                ).fetchone()["cnt"]

                if valid_count == 0:
                    # No remaining evidence — downgrade
                    db.execute(
                        "UPDATE claims SET status = 'unverified', "
                        "confidence = 0.01, updated_at = ? "
                        "WHERE claim_id = ?",
                        (now, claim_id),
                    )
                    # Record version
                    version_id = _generate_id("ver", claim_id + now)
                    db.execute(
                        "INSERT INTO claim_versions "
                        "(version_id, claim_id, statement, confidence, "
                        "status, changed_by, change_reason, created_at) "
                        "SELECT ?, claim_id, statement, 0.01, "
                        "'unverified', 'retraction_propagation', ?, ? "
                        "FROM claims WHERE claim_id = ?",
                        (version_id,
                         f"Source retracted: {source_url}",
                         now, claim_id),
                    )
                    downgraded.append(claim_id)
                else:
                    # Recalculate: claims with fewer sources may lose
                    # corroboration status
                    claim = db.execute(
                        "SELECT status FROM claims WHERE claim_id = ?",
                        (claim_id,),
                    ).fetchone()
                    if claim and claim["status"] == "corroborated" and valid_count < 2:
                        db.execute(
                            "UPDATE claims SET status = 'reported', "
                            "updated_at = ? WHERE claim_id = ?",
                            (now, claim_id),
                        )

            # Invalidate dependency labels containing retracted evidence
            retracted_ev_ids = db.execute(
                "SELECT evidence_id FROM evidence "
                "WHERE source_url = ? AND retracted = 1",
                (source_url,),
            ).fetchall()
            for ev_row in retracted_ev_ids:
                ev_id = ev_row["evidence_id"]
                # Match labels containing this evidence_id in JSON array
                db.execute(
                    "UPDATE dependency_labels SET is_valid = 0 "
                    "WHERE evidence_ids LIKE ?",
                    (f'%"{ev_id}"%',),
                )

            db.commit()
            return {
                "retraction_id": retraction_id,
                "source_url": source_url,
                "reason": reason,
                "affected_evidence": affected_evidence,
                "affected_claims": len(affected_claims),
                "downgraded_claims": downgraded,
                "retracted_at": now,
            }
        except Exception as e:
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()

    @skill("loom.kb.build_labels", "Build ATMS dependency labels for a claim")
    def kb_build_labels(self, handle):
        """Build minimal dependency label sets for a claim.

        Each label is a minimal set of evidence IDs that independently
        supports the claim. If a label has all evidence valid, the claim
        is supported through that path.

        For simple cases (few evidence links), each individual piece of
        supporting evidence forms its own label. For claims with
        compound evidence, labels represent independent support paths.

        Params:
            claim_id (str): The claim to build labels for.

        Returns:
            dict with labels (list of support sets), valid_count,
            invalid_count.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")

        if not claim_id:
            return {"error": "claim_id is required"}

        now = _now_iso()
        db = _get_db(params.get("db_path", ""))
        try:
            # Get all supporting evidence for this claim
            evidence_rows = db.execute(
                "SELECT evidence_id, source_url, retracted, "
                "relationship FROM evidence "
                "WHERE claim_id = ? AND relationship = 'supports'",
                (claim_id,),
            ).fetchall()

            if not evidence_rows:
                return {
                    "claim_id": claim_id,
                    "labels": [],
                    "valid_count": 0,
                    "invalid_count": 0,
                }

            # Clear existing labels for this claim
            db.execute(
                "DELETE FROM dependency_labels WHERE claim_id = ?",
                (claim_id,),
            )

            # Build minimal labels: each individual piece of supporting
            # evidence is a minimal support set on its own
            labels = []
            valid_count = 0
            invalid_count = 0

            for ev in evidence_rows:
                ev_id = ev["evidence_id"]
                is_valid = 1 if not ev["retracted"] else 0
                label_id = _generate_id("lbl", claim_id + ev_id)

                evidence_ids_json = json.dumps([ev_id])
                db.execute(
                    "INSERT INTO dependency_labels "
                    "(label_id, claim_id, evidence_ids, is_minimal, "
                    "is_valid, created_at) VALUES (?, ?, ?, 1, ?, ?)",
                    (label_id, claim_id, evidence_ids_json, is_valid, now),
                )

                labels.append({
                    "label_id": label_id,
                    "evidence_ids": [ev_id],
                    "is_valid": bool(is_valid),
                })
                if is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1

            db.commit()
            return {
                "claim_id": claim_id,
                "labels": labels,
                "valid_count": valid_count,
                "invalid_count": invalid_count,
            }
        except Exception as e:
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()

    @skill("loom.kb.sensitivity", "What-if analysis for source retraction")
    def kb_sensitivity(self, handle):
        """Sensitivity analysis: what would happen if a source were retracted?

        Does NOT actually retract — simulates the impact. Reports which
        claims would lose all support and which would be downgraded.

        Params:
            source_url (str): The source URL to simulate retracting.

        Returns:
            dict with would_lose_all_support (claim IDs),
            would_lose_corroboration (claim IDs), unaffected count.
        """
        params = handle.params
        source_url = params.get("source_url", "")

        if not source_url:
            return {"error": "source_url is required"}

        db = _get_db(params.get("db_path", ""))
        try:
            # Find all claims with evidence from this source
            affected = db.execute(
                "SELECT DISTINCT claim_id FROM evidence "
                "WHERE source_url = ? AND retracted = 0",
                (source_url,),
            ).fetchall()

            would_lose_all = []
            would_lose_corroboration = []
            unaffected = 0

            for row in affected:
                claim_id = row["claim_id"]
                # Count valid evidence NOT from this source
                other_valid = db.execute(
                    "SELECT COUNT(*) as cnt FROM evidence "
                    "WHERE claim_id = ? AND retracted = 0 "
                    "AND source_url != ?",
                    (claim_id, source_url),
                ).fetchone()["cnt"]

                if other_valid == 0:
                    would_lose_all.append(claim_id)
                elif other_valid < 2:
                    # Would drop below corroboration threshold
                    claim = db.execute(
                        "SELECT status FROM claims WHERE claim_id = ?",
                        (claim_id,),
                    ).fetchone()
                    if claim and claim["status"] == "corroborated":
                        would_lose_corroboration.append(claim_id)
                    else:
                        unaffected += 1
                else:
                    unaffected += 1

            return {
                "source_url": source_url,
                "would_lose_all_support": would_lose_all,
                "would_lose_corroboration": would_lose_corroboration,
                "unaffected": unaffected,
                "total_affected_claims": len(affected),
            }
        finally:
            db.close()


    # -- Maintenance skills (backing the refresh + audit rituals) --

    @skill("loom.kb.expiring_claims", "Find claims approaching expiration")
    def kb_expiring_claims(self, handle):
        """Find claims whose valid_until date is within the expiry window.

        Params:
            expiry_window_days (int): How many days ahead to look (default 30).
            max_tier (int): Only check tiers <= this (default 7 = all).

        Returns:
            dict with expiring claims and their source URLs.
        """
        params = handle.params
        window = params.get("expiry_window_days", 30)
        max_tier = params.get("max_tier", 7)

        db = _get_db(params.get("db_path", ""))
        try:
            now = _now_iso()
            # SQLite date arithmetic: valid_until <= date('now', '+N days')
            rows = db.execute(
                "SELECT c.claim_id, c.statement, c.valid_until, "
                "c.source_tier, c.status, c.confidence, c.ttl_category "
                "FROM claims c "
                "WHERE c.valid_until IS NOT NULL "
                "AND c.valid_until != '' "
                "AND c.temporal_status = 'current' "
                "AND c.valid_until <= datetime('now', '+' || ? || ' days') "
                "AND CAST(SUBSTR(c.source_tier, 2) AS INTEGER) <= ? "
                "ORDER BY c.valid_until ASC",
                (window, max_tier),
            ).fetchall()

            claims = []
            for row in rows:
                # Get sources for each claim
                sources = db.execute(
                    "SELECT source_url, content_hash FROM evidence "
                    "WHERE claim_id = ? AND retracted = 0",
                    (row["claim_id"],),
                ).fetchall()

                claims.append({
                    "claim_id": row["claim_id"],
                    "statement": row["statement"],
                    "valid_until": row["valid_until"],
                    "source_tier": row["source_tier"],
                    "status": row["status"],
                    "ttl_category": row["ttl_category"],
                    "sources": [dict(s) for s in sources],
                })

            return {
                "expiring_count": len(claims),
                "claims": claims,
                "window_days": window,
                "checked_at": now,
            }
        finally:
            db.close()

    @skill("loom.kb.find_orphans", "Find claims with no evidence")
    def kb_find_orphans(self, handle):
        """Find claims that have no supporting evidence links.

        Returns:
            dict with orphan claims.
        """
        params = handle.params
        db = _get_db(params.get("db_path", ""))
        try:
            rows = db.execute(
                "SELECT c.claim_id, c.statement, c.status, c.confidence, "
                "c.source_tier, c.created_at "
                "FROM claims c "
                "LEFT JOIN evidence e ON c.claim_id = e.claim_id "
                "WHERE e.evidence_id IS NULL "
                "ORDER BY c.created_at DESC"
            ).fetchall()

            return {
                "orphan_count": len(rows),
                "orphans": [dict(r) for r in rows],
                "checked_at": _now_iso(),
            }
        finally:
            db.close()

    @skill("loom.kb.find_expired", "Find claims past their validity date")
    def kb_find_expired(self, handle):
        """Find claims whose valid_until has passed and are still 'current'.

        Returns:
            dict with expired claims.
        """
        params = handle.params
        db = _get_db(params.get("db_path", ""))
        try:
            rows = db.execute(
                "SELECT claim_id, statement, valid_until, source_tier, "
                "status, confidence, ttl_category "
                "FROM claims "
                "WHERE valid_until IS NOT NULL "
                "AND valid_until != '' "
                "AND valid_until <= datetime('now') "
                "AND temporal_status = 'current' "
                "ORDER BY valid_until ASC"
            ).fetchall()

            return {
                "expired_count": len(rows),
                "claims": [dict(r) for r in rows],
                "checked_at": _now_iso(),
            }
        finally:
            db.close()

    @skill("loom.kb.stale_contradictions", "Find unresolved contradictions")
    def kb_stale_contradictions(self, handle):
        """Find contradictions unresolved for longer than the configured window.

        Params:
            stale_days (int): Days after which unresolved = stale (default 30).

        Returns:
            dict with stale contradictions.
        """
        params = handle.params
        stale_days = params.get("stale_days", 30)

        db = _get_db(params.get("db_path", ""))
        try:
            rows = db.execute(
                "SELECT c.contradiction_id, c.claim_a_id, c.claim_b_id, "
                "c.nature, c.created_at, "
                "a.statement AS statement_a, b.statement AS statement_b "
                "FROM contradictions c "
                "JOIN claims a ON c.claim_a_id = a.claim_id "
                "JOIN claims b ON c.claim_b_id = b.claim_id "
                "WHERE c.resolved_at IS NULL "
                "AND c.created_at <= datetime('now', '-' || ? || ' days') "
                "ORDER BY c.created_at ASC",
                (stale_days,),
            ).fetchall()

            return {
                "stale_count": len(rows),
                "contradictions": [dict(r) for r in rows],
                "stale_threshold_days": stale_days,
                "checked_at": _now_iso(),
            }
        finally:
            db.close()

    @skill("loom.kb.source_health", "Check source URL availability")
    def kb_source_health(self, handle):
        """Check distinct source URLs for availability.

        Does a HEAD request to each unique source URL in the evidence
        table and reports which are offline (4xx, 5xx, timeout).

        Params:
            timeout (int): Request timeout in seconds (default 10).
            limit (int): Max URLs to check (default 100).

        Returns:
            dict with online, offline, and error counts.
        """
        import urllib.request
        import urllib.error

        params = handle.params
        timeout = params.get("timeout", 10)
        limit = params.get("limit", 100)

        db = _get_db(params.get("db_path", ""))
        try:
            rows = db.execute(
                "SELECT DISTINCT source_url FROM evidence "
                "WHERE source_url IS NOT NULL AND source_url != '' "
                "AND retracted = 0 "
                "LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            db.close()

        online = []
        offline = []
        errors = []

        for row in rows:
            url = row["source_url"]
            try:
                req = urllib.request.Request(url, method="HEAD")
                req.add_header("User-Agent", "Loom-HealthCheck/1.0")
                resp = urllib.request.urlopen(req, timeout=timeout)
                if resp.status < 400:
                    online.append({"url": url, "status": resp.status})
                else:
                    offline.append({"url": url, "status": resp.status})
            except urllib.error.HTTPError as e:
                offline.append({"url": url, "status": e.code})
            except Exception as e:
                errors.append({"url": url, "error": str(e)})

        return {
            "online_count": len(online),
            "offline_count": len(offline),
            "error_count": len(errors),
            "online": online,
            "offline": offline,
            "errors": errors,
            "checked_at": _now_iso(),
        }

    @skill("loom.kb.integrity_report", "Compile full integrity audit report")
    def kb_integrity_report(self, handle):
        """Run all audit checks and compile a single report.

        Combines: orphans, expired claims, stale contradictions,
        retracted sources, and label health.

        Params:
            stale_days (int): Contradiction staleness window (default 30).

        Returns:
            dict with all audit findings and summary counts.
        """
        params = handle.params

        # Run each check
        orphans = self.kb_find_orphans(handle)
        expired = self.kb_find_expired(handle)
        stale = self.kb_stale_contradictions(handle)

        # Count retracted evidence
        db = _get_db(params.get("db_path", ""))
        try:
            retracted_count = db.execute(
                "SELECT COUNT(*) as cnt FROM evidence WHERE retracted = 1"
            ).fetchone()["cnt"]

            total_claims = db.execute(
                "SELECT COUNT(*) as cnt FROM claims"
            ).fetchone()["cnt"]

            total_evidence = db.execute(
                "SELECT COUNT(*) as cnt FROM evidence"
            ).fetchone()["cnt"]

            # Claims with only retracted evidence (zombie claims)
            zombies = db.execute(
                "SELECT c.claim_id, c.statement FROM claims c "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM evidence e "
                "  WHERE e.claim_id = c.claim_id AND e.retracted = 0"
                ") AND EXISTS ("
                "  SELECT 1 FROM evidence e2 "
                "  WHERE e2.claim_id = c.claim_id"
                ")"
            ).fetchall()
        finally:
            db.close()

        health = "healthy"
        issues = (orphans["orphan_count"] + expired["expired_count"]
                  + stale["stale_count"] + len(zombies))
        if issues > total_claims * 0.2:
            health = "degraded"
        elif issues > 0:
            health = "needs_attention"

        return {
            "health": health,
            "summary": {
                "total_claims": total_claims,
                "total_evidence": total_evidence,
                "orphan_claims": orphans["orphan_count"],
                "expired_claims": expired["expired_count"],
                "stale_contradictions": stale["stale_count"],
                "retracted_evidence": retracted_count,
                "zombie_claims": len(zombies),
            },
            "orphans": orphans["orphans"],
            "expired": expired["claims"],
            "stale_contradictions": stale["contradictions"],
            "zombies": [dict(z) for z in zombies],
            "checked_at": _now_iso(),
        }


worker = LoomKBWorker(worker_id="loom-kb-1")

if __name__ == "__main__":
    worker.run()
