"""SnapshotWorker — builds, tests, promotes, and queries knowledge snapshots.

Compiles the evidence graph into immutable, versioned, FTS5-indexed
snapshots. Runs quality gates, promotes snapshots to production, and
serves FTS5 queries against promoted snapshots.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Import deterministic confidence computation.
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), ".."),
)
from corroborator.worker import compute_confidence

# Event types that trigger immediate builds (bypass batch).
IMMEDIATE_TRIGGERS = {
    "contradiction.resolved",
    "claim.confidence_changed",
}

# Default trigger policy (overridable via domain profile).
DEFAULT_TRIGGER_POLICY = {
    "batch_window_seconds": 300,
    "min_changes": 1,
    "max_interval_seconds": 86400,
    "min_interval_seconds": 600,
}

# Quality gate names
GATE_CONSISTENCY = "consistency"
GATE_COMPLETENESS = "completeness"
GATE_PROVENANCE = "provenance"
GATE_TEMPORAL = "temporal_validity"
GATE_CONFIDENCE = "confidence_floor"

# Default paths
DEFAULT_DB_PATH = os.environ.get(
    "LOOM_DB_PATH",
    os.path.join(os.path.expanduser("~"), "loom", "data", "loom.db"),
)
DEFAULT_SNAPSHOTS_DIR = os.environ.get(
    "LOOM_SNAPSHOTS_DIR",
    os.path.join(os.path.expanduser("~"), "loom", "data", "snapshots"),
)

# Domain profiles
_PROFILES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "configs", "domain_profiles.json",
)
_profiles_cache = None


def _load_profiles():
    global _profiles_cache
    if _profiles_cache is not None:
        return _profiles_cache
    try:
        with open(_PROFILES_PATH) as f:
            _profiles_cache = json.load(f).get("profiles", {})
    except (FileNotFoundError, json.JSONDecodeError):
        _profiles_cache = {}
    return _profiles_cache


def _get_profile(name):
    profiles = _load_profiles()
    return profiles.get(name, profiles.get("default", {
        "confidence_floor": 0.3,
        "include_contested": False,
        "default_ttl_days": 90,
    }))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _row_get(row, key, default=None):
    """Safe get from sqlite3.Row (which lacks .get())."""
    try:
        val = row[key]
        return val if val is not None else default
    except (IndexError, KeyError):
        return default


def _get_event_sequence(db_path, domain_id="default"):
    """Get the latest event sequence from the source DB."""
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT MAX(sequence) as mx FROM events "
            "WHERE domain_id = ?",
            (domain_id,),
        ).fetchone()
        if row and row["mx"] is not None:
            return row["mx"]
        # Try without domain filter (for 'default' domain).
        row = conn.execute(
            "SELECT MAX(sequence) as mx FROM events",
        ).fetchone()
        return row["mx"] if row and row["mx"] else 0
    except sqlite3.OperationalError:
        # events table may not exist yet
        return 0
    finally:
        conn.close()


def _get_events_since(db_path, since_seq, domain_id="default"):
    """Get events since a sequence number."""
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM events "
            "WHERE sequence > ? "
            "ORDER BY sequence ASC",
            (since_seq,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _last_build_time(domain_id, snapshots_dir=None):
    """Get the build timestamp and event_sequence of the
    most recent snapshot for a domain. Returns (time, seq)."""
    snap_dir = snapshots_dir or DEFAULT_SNAPSHOTS_DIR
    domain_dir = os.path.join(snap_dir, domain_id)
    if not os.path.isdir(domain_dir):
        return None, 0

    existing = sorted([
        d for d in os.listdir(domain_dir)
        if d.startswith("v") and os.path.isdir(
            os.path.join(domain_dir, d),
        )
    ])
    if not existing:
        return None, 0

    last_dir = os.path.join(domain_dir, existing[-1])
    manifest_path = os.path.join(last_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None, 0

    with open(manifest_path) as f:
        manifest = json.load(f)

    built_at = manifest.get("built_at")
    event_seq = manifest.get("event_sequence", 0)
    return built_at, event_seq


def should_build(domain_id, db_path=None,
                 snapshots_dir=None, profile_name=None):
    """Evaluate whether a snapshot build should be triggered.

    Returns a dict with should_build (bool), reason, and
    the change events that would be included.
    """
    profile = _get_profile(profile_name or domain_id)
    policy = profile.get(
        "trigger_policy", DEFAULT_TRIGGER_POLICY)
    batch_window = policy.get(
        "batch_window_seconds", 300)
    min_changes = policy.get("min_changes", 1)
    max_interval = policy.get(
        "max_interval_seconds", 86400)
    min_interval = policy.get(
        "min_interval_seconds", 600)

    last_time_str, last_seq = _last_build_time(
        domain_id, snapshots_dir)

    events = _get_events_since(db_path, last_seq, domain_id)
    if not events:
        # Check max_interval (freshness gate).
        if last_time_str:
            try:
                last_dt = datetime.fromisoformat(last_time_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(
                        tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc)
                       - last_dt).total_seconds()
                if age > max_interval:
                    return {
                        "should_build": True,
                        "reason": "max_interval_exceeded",
                        "age_seconds": age,
                        "events": [],
                        "event_count": 0,
                    }
            except (ValueError, TypeError):
                pass
        return {
            "should_build": False,
            "reason": "no_changes",
            "events": [],
            "event_count": 0,
        }

    # Check min_interval (rate limit).
    if last_time_str:
        try:
            last_dt = datetime.fromisoformat(last_time_str)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(
                    tzinfo=timezone.utc)
            since_last = (datetime.now(timezone.utc)
                          - last_dt).total_seconds()
        except (ValueError, TypeError):
            since_last = float("inf")
    else:
        since_last = float("inf")

    # Immediate triggers bypass batch window and min_interval.
    immediate = [
        e for e in events
        if e.get("event_type") in IMMEDIATE_TRIGGERS
    ]
    if immediate:
        return {
            "should_build": True,
            "reason": "immediate_trigger",
            "triggered_by": [
                e["event_type"] for e in immediate],
            "events": events,
            "event_count": len(events),
        }

    # Rate limit check.
    if since_last < min_interval:
        return {
            "should_build": False,
            "reason": "min_interval_not_reached",
            "seconds_remaining": min_interval - since_last,
            "events": events,
            "event_count": len(events),
        }

    # Batch: enough events and enough time since first event.
    if len(events) < min_changes:
        return {
            "should_build": False,
            "reason": "below_min_changes",
            "event_count": len(events),
            "min_changes": min_changes,
            "events": events,
        }

    # Check batch window: first event must be old enough.
    first_event_time = events[0].get("created_at", "")
    if first_event_time:
        try:
            first_dt = datetime.fromisoformat(first_event_time)
            if first_dt.tzinfo is None:
                first_dt = first_dt.replace(
                    tzinfo=timezone.utc)
            event_age = (datetime.now(timezone.utc)
                         - first_dt).total_seconds()
            if event_age < batch_window:
                return {
                    "should_build": False,
                    "reason": "batch_window_not_elapsed",
                    "seconds_remaining": (
                        batch_window - event_age),
                    "events": events,
                    "event_count": len(events),
                }
        except (ValueError, TypeError):
            pass

    return {
        "should_build": True,
        "reason": "batch_ready",
        "events": events,
        "event_count": len(events),
    }


def _open_source_db(db_path):
    """Open the source evidence graph database (read-only)."""
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_superseded(conn, claim_id, seen=None):
    """Follow superseded_by chain to find current claim_id."""
    if seen is None:
        seen = set()
    if claim_id in seen:
        return claim_id  # cycle guard
    seen.add(claim_id)
    row = conn.execute(
        "SELECT superseded_by FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row and row["superseded_by"]:
        return _resolve_superseded(conn, row["superseded_by"], seen)
    return claim_id


SNAPSHOT_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    statement     TEXT NOT NULL,
    confidence    REAL NOT NULL,
    status        TEXT NOT NULL,
    category      TEXT,
    source_tier   TEXT,
    claim_type    TEXT,
    valid_from    TEXT,
    valid_until   TEXT,
    source_summary TEXT,
    metadata      TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id   TEXT PRIMARY KEY,
    claim_id      TEXT NOT NULL,
    source_url    TEXT,
    source_tier   TEXT,
    excerpt       TEXT,
    relationship  TEXT,
    FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    statement,
    category,
    source_summary,
    content=claims,
    content_rowid=rowid
);

CREATE TABLE IF NOT EXISTS snapshot_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def build_snapshot(domain_id, db_path=None, profile_name=None,
                   previous_version=None, snapshots_dir=None,
                   triggered_by=None, change_events=None):
    """Build a snapshot from the evidence graph. Returns build result dict.

    This is the core build function, usable both from the worker skill
    and from the CLI wrapper.
    """
    profile = _get_profile(profile_name or domain_id)
    confidence_floor = profile.get("confidence_floor", 0.3)
    include_contested = profile.get("include_contested", False)
    default_ttl_days = profile.get("default_ttl_days", 90)

    src = _open_source_db(db_path)
    if src is None:
        return {"error": f"Source database not found: {db_path or DEFAULT_DB_PATH}"}

    now = _now_iso()
    now_dt = datetime.now(timezone.utc)

    # --- 1. Resolve: query all claims + evidence ---
    claims_raw = src.execute(
        "SELECT * FROM claims",
    ).fetchall()

    evidence_raw = src.execute(
        "SELECT * FROM evidence",
    ).fetchall()

    # Build evidence index by claim_id.
    evidence_by_claim = {}
    for ev in evidence_raw:
        cid = ev["claim_id"]
        if cid not in evidence_by_claim:
            evidence_by_claim[cid] = []
        evidence_by_claim[cid].append(ev)

    # --- 2. Collapse: follow superseded_by chains ---
    superseded_ids = set()
    for c in claims_raw:
        if c["superseded_by"]:
            superseded_ids.add(c["claim_id"])

    # Resolve chains: find the terminal claim for each superseded one.
    # We keep only terminal (non-superseded) claims.
    current_claims = [
        c for c in claims_raw
        if c["claim_id"] not in superseded_ids
    ]

    # --- 3. Filter ---
    filtered = []
    for c in current_claims:
        # Skip expired claims.
        valid_until = c["valid_until"]
        if valid_until:
            try:
                exp = datetime.fromisoformat(valid_until)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now_dt:
                    continue
            except (ValueError, TypeError):
                pass

        # Recompute confidence from evidence.
        claim_evidence = evidence_by_claim.get(c["claim_id"], [])
        # Count non-retracted supporting evidence.
        supporting = [
            e for e in claim_evidence
            if not e["retracted"]
            and (e["relationship"] or "supports") == "supports"
        ]
        source_tier = c["source_tier"] or "T5"
        status = c["status"] or "reported"
        n_sources = len(supporting) if supporting else 1
        confidence = compute_confidence(status, source_tier, n_sources)

        # Apply confidence floor.
        if confidence < confidence_floor:
            continue

        # Exclude contested if profile says so.
        if status == "contested" and not include_contested:
            continue

        # Build source summary from evidence.
        source_urls = [
            e["source_url"] for e in claim_evidence
            if e["source_url"]
        ]
        source_summary = "; ".join(source_urls[:3])
        if len(source_urls) > 3:
            source_summary += f" (+{len(source_urls) - 3} more)"

        filtered.append({
            "claim_id": c["claim_id"],
            "statement": c["statement"],
            "confidence": confidence,
            "status": status,
            "category": c["category"],
            "source_tier": source_tier,
            "claim_type": _row_get(c, "claim_type"),
            "valid_from": c["valid_from"],
            "valid_until": valid_until,
            "source_summary": source_summary,
            "metadata": json.dumps({
                "original_confidence": c["confidence"],
                "evidence_count": len(claim_evidence),
            }),
        })

    # Collect evidence for filtered claims.
    filtered_ids = {c["claim_id"] for c in filtered}
    filtered_evidence = []
    for ev in evidence_raw:
        if ev["claim_id"] in filtered_ids:
            filtered_evidence.append({
                "evidence_id": ev["evidence_id"],
                "claim_id": ev["claim_id"],
                "source_url": _row_get(ev, "source_url"),
                "source_tier": _row_get(ev, "source_tier"),
                "excerpt": _row_get(ev, "excerpt"),
                "relationship": _row_get(ev, "relationship", "supports"),
            })

    src.close()

    # --- 4. Determine version ---
    snap_dir = snapshots_dir or DEFAULT_SNAPSHOTS_DIR
    domain_dir = os.path.join(snap_dir, domain_id)
    os.makedirs(domain_dir, exist_ok=True)

    # Capture previous build's event sequence BEFORE creating new dir.
    _, prev_event_seq = _last_build_time(domain_id, snap_dir)

    # Auto-increment version from existing snapshots.
    existing = sorted([
        d for d in os.listdir(domain_dir)
        if d.startswith("v") and os.path.isdir(
            os.path.join(domain_dir, d),
        )
    ]) if os.path.isdir(domain_dir) else []
    if existing:
        last = existing[-1]  # e.g. "v3"
        try:
            version = int(last[1:]) + 1
        except ValueError:
            version = 1
    else:
        version = 1

    version_str = f"v{version}"
    version_dir = os.path.join(domain_dir, version_str)
    os.makedirs(version_dir, exist_ok=True)

    # --- 5. Build snapshot SQLite with FTS5 ---
    snap_path = os.path.join(version_dir, "snapshot.sqlite")
    snap_conn = sqlite3.connect(snap_path)
    snap_conn.executescript(SNAPSHOT_SCHEMA)

    # Insert claims.
    for c in filtered:
        snap_conn.execute(
            "INSERT INTO claims "
            "(claim_id, statement, confidence, status, category, "
            "source_tier, claim_type, valid_from, valid_until, "
            "source_summary, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                c["claim_id"], c["statement"], c["confidence"],
                c["status"], c["category"], c["source_tier"],
                c["claim_type"], c["valid_from"], c["valid_until"],
                c["source_summary"], c["metadata"],
            ),
        )

    # Insert evidence.
    for ev in filtered_evidence:
        snap_conn.execute(
            "INSERT INTO evidence "
            "(evidence_id, claim_id, source_url, source_tier, "
            "excerpt, relationship) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                ev["evidence_id"], ev["claim_id"],
                ev["source_url"], ev["source_tier"],
                ev["excerpt"], ev["relationship"],
            ),
        )

    # Populate FTS5 index.
    snap_conn.execute(
        "INSERT INTO claims_fts(rowid, statement, category, source_summary) "
        "SELECT rowid, statement, category, source_summary FROM claims",
    )

    # Compute integrity hash.
    hash_data = json.dumps(
        [c["claim_id"] for c in filtered], sort_keys=True,
    )
    integrity = hashlib.sha256(hash_data.encode()).hexdigest()

    # Write snapshot metadata.
    meta = {
        "version": version_str,
        "domain_id": domain_id,
        "built_at": now,
        "claim_count": len(filtered),
        "evidence_count": len(filtered_evidence),
        "profile": profile_name or domain_id,
        "confidence_floor": confidence_floor,
        "include_contested": include_contested,
        "integrity_sha256": integrity,
    }
    for k, v in meta.items():
        snap_conn.execute(
            "INSERT INTO snapshot_meta (key, value) VALUES (?, ?)",
            (k, json.dumps(v) if not isinstance(v, str) else v),
        )

    snap_conn.commit()
    snap_conn.close()

    # --- 6. Write manifest and integrity ---
    # Record event sequence at build time for diffing.
    event_seq = _get_event_sequence(db_path, domain_id)

    manifest = {
        "version": version_str,
        "domain_id": domain_id,
        "built_at": now,
        "triggered_by": triggered_by or "manual",
        "change_events": change_events or [],
        "event_sequence": event_seq,
        "previous_event_sequence": prev_event_seq,
        "claim_count": len(filtered),
        "evidence_count": len(filtered_evidence),
        "profile": profile_name or domain_id,
        "vector_backend": "none",
        "files": ["snapshot.sqlite", "manifest.json",
                  "integrity.sha256"],
    }
    with open(os.path.join(version_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    with open(os.path.join(version_dir, "integrity.sha256"), "w") as f:
        f.write(integrity)

    # --- 7. Changelog ---
    changelog = {
        "version": version_str,
        "built_at": now,
        "claims_total": len(filtered),
        "superseded_excluded": len(superseded_ids),
    }
    if previous_version:
        prev_dir = os.path.join(domain_dir, previous_version)
        prev_snap = os.path.join(prev_dir, "snapshot.sqlite")
        if os.path.exists(prev_snap):
            prev_conn = sqlite3.connect(prev_snap)
            prev_conn.row_factory = sqlite3.Row
            prev_ids = {
                r["claim_id"]
                for r in prev_conn.execute(
                    "SELECT claim_id FROM claims",
                ).fetchall()
            }
            prev_conn.close()
            curr_ids = filtered_ids
            changelog["added"] = len(curr_ids - prev_ids)
            changelog["removed"] = len(prev_ids - curr_ids)
            changelog["retained"] = len(curr_ids & prev_ids)

    with open(os.path.join(version_dir, "changelog.json"), "w") as f:
        json.dump(changelog, f, indent=2)

    return {
        "version": version_str,
        "snapshot_path": version_dir,
        "claim_count": len(filtered),
        "evidence_count": len(filtered_evidence),
        "changelog": changelog,
        "manifest": manifest,
        "built_at": now,
    }


def test_snapshot(snapshot_path, domain_id, profile_name=None,
                  fixture_dir=None):
    """Run quality gates against a built snapshot. Returns test result dict."""
    profile = _get_profile(profile_name or domain_id)
    confidence_floor = profile.get("confidence_floor", 0.3)
    include_contested = profile.get("include_contested", False)

    snap_db = os.path.join(snapshot_path, "snapshot.sqlite")
    if not os.path.exists(snap_db):
        return {"error": f"Snapshot not found: {snap_db}"}

    conn = sqlite3.connect(snap_db)
    conn.row_factory = sqlite3.Row

    gate_results = {}

    # Gate 1: Consistency — no contested claims if profile excludes them.
    if not include_contested:
        contested = conn.execute(
            "SELECT COUNT(*) as n FROM claims WHERE status = 'contested'",
        ).fetchone()["n"]
        gate_results[GATE_CONSISTENCY] = {
            "passed": contested == 0,
            "details": f"{contested} contested claims found"
            if contested else "No contested claims",
        }
    else:
        gate_results[GATE_CONSISTENCY] = {
            "passed": True,
            "details": "Profile allows contested claims",
        }

    # Gate 2: Completeness — all claims have >= 1 evidence link.
    orphans = conn.execute(
        "SELECT COUNT(*) as n FROM claims c "
        "LEFT JOIN evidence e ON c.claim_id = e.claim_id "
        "WHERE e.evidence_id IS NULL",
    ).fetchone()["n"]
    gate_results[GATE_COMPLETENESS] = {
        "passed": orphans == 0,
        "details": f"{orphans} claims without evidence"
        if orphans else "All claims have evidence",
    }

    # Gate 3: Provenance — no evidence rows with null source_url.
    null_sources = conn.execute(
        "SELECT COUNT(*) as n FROM evidence "
        "WHERE source_url IS NULL OR source_url = ''",
    ).fetchone()["n"]
    gate_results[GATE_PROVENANCE] = {
        "passed": null_sources == 0,
        "details": f"{null_sources} evidence rows missing source_url"
        if null_sources else "All evidence has source URLs",
    }

    # Gate 4: Temporal — no expired claims.
    now_str = _now_iso()
    expired = conn.execute(
        "SELECT COUNT(*) as n FROM claims "
        "WHERE valid_until IS NOT NULL AND valid_until < ?",
        (now_str,),
    ).fetchone()["n"]
    gate_results[GATE_TEMPORAL] = {
        "passed": expired == 0,
        "details": f"{expired} expired claims"
        if expired else "No expired claims",
    }

    # Gate 5: Confidence floor.
    below_floor = conn.execute(
        "SELECT COUNT(*) as n FROM claims WHERE confidence < ?",
        (confidence_floor,),
    ).fetchone()["n"]
    gate_results[GATE_CONFIDENCE] = {
        "passed": below_floor == 0,
        "details": f"{below_floor} claims below {confidence_floor}"
        if below_floor else f"All claims >= {confidence_floor}",
    }

    # Optional: golden fixtures.
    fixture_results = None
    fix_dir = fixture_dir or os.path.join(
        os.path.dirname(__file__), "..", "..", "test", "fixtures", domain_id,
    )
    if os.path.isdir(fix_dir):
        fixture_results = []
        for fname in sorted(os.listdir(fix_dir)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(fix_dir, fname)) as f:
                fixture = json.load(f)
            query = fixture.get("query", "")
            expected = fixture.get("expected_claim", "")
            if not query:
                continue
            rows = conn.execute(
                "SELECT c.statement FROM claims_fts "
                "JOIN claims c ON claims_fts.rowid = c.rowid "
                "WHERE claims_fts MATCH ? LIMIT 5",
                (query,),
            ).fetchall()
            found = any(
                expected.lower() in r["statement"].lower()
                for r in rows
            )
            fixture_results.append({
                "query": query,
                "expected": expected,
                "found": found,
            })

    conn.close()

    all_passed = all(g["passed"] for g in gate_results.values())
    return {
        "passed": all_passed,
        "gate_results": gate_results,
        "fixture_results": fixture_results,
        "tested_at": _now_iso(),
    }


def query_snapshot(domain_id, query, top_k=5, min_confidence=0.0,
                   snapshots_dir=None):
    """Query a promoted snapshot using FTS5. Returns result dict."""
    snap_dir = snapshots_dir or DEFAULT_SNAPSHOTS_DIR
    current_dir = os.path.join(snap_dir, domain_id, "current")

    # Follow symlink or direct path.
    if not os.path.isdir(current_dir):
        return {"error": f"No promoted snapshot for {domain_id}"}

    snap_db = os.path.join(current_dir, "snapshot.sqlite")
    if not os.path.exists(snap_db):
        return {"error": f"Snapshot database not found: {snap_db}"}

    conn = sqlite3.connect(snap_db)
    conn.row_factory = sqlite3.Row

    # Sanitize query for FTS5 — remove special chars.
    fts_query = " ".join(
        w for w in query.split()
        if len(w) >= 2
    )
    if not fts_query:
        conn.close()
        return {"results": [], "query": query}

    # Quote each term for FTS5 safety.
    terms = fts_query.split()
    safe_query = " OR ".join(f'"{t}"' for t in terms)

    try:
        rows = conn.execute(
            "SELECT c.claim_id, c.statement, c.confidence, "
            "c.status, c.category, c.source_tier, "
            "c.source_summary, c.claim_type, rank "
            "FROM claims_fts "
            "JOIN claims c ON claims_fts.rowid = c.rowid "
            "WHERE claims_fts MATCH ? "
            "ORDER BY rank "
            "LIMIT ?",
            (safe_query, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return {"results": [], "query": query, "error": "FTS5 query failed"}

    results = []
    for r in rows:
        if r["confidence"] < min_confidence:
            continue
        results.append({
            "claim_id": r["claim_id"],
            "statement": r["statement"],
            "confidence": r["confidence"],
            "status": r["status"],
            "category": r["category"],
            "source_tier": r["source_tier"],
            "source_summary": r["source_summary"],
            "claim_type": r["claim_type"],
            "score": abs(r["rank"]),
        })

    conn.close()
    return {"results": results, "query": query, "count": len(results)}


class SnapshotWorker(Worker):
    worker_type = "snapshot"

    @skill("loom.snapshot.build", "Compile evidence graph into versioned FTS5 snapshot")
    def snapshot_build(self, handle):
        """Build an immutable snapshot of the current evidence graph.

        Params:
            domain_id (str): Domain identifier.
            db_path (str, optional): Source evidence graph DB.
            profile (str, optional): Domain profile name.
            previous_version (str, optional): For changelog.
            triggered_by (str, optional): What triggered
                this build (change_event|scheduled|manual).
            change_events (list, optional): Event summaries
                that triggered this build.
        """
        p = handle.params
        domain_id = p.get("domain_id", "")
        if not domain_id:
            return {"error": "domain_id is required"}

        handle.progress(10, "resolving evidence graph")
        result = build_snapshot(
            domain_id=domain_id,
            db_path=p.get("db_path"),
            profile_name=p.get("profile"),
            previous_version=p.get("previous_version"),
            snapshots_dir=p.get("snapshots_dir"),
            triggered_by=p.get("triggered_by"),
            change_events=p.get("change_events"),
        )
        handle.progress(100, "done")
        return result

    @skill("loom.snapshot.test", "Run quality gates against a snapshot")
    def snapshot_test(self, handle):
        """Run quality gates against a snapshot before promotion.

        Params:
            snapshot_path (str): Path to the snapshot version directory.
            domain_id (str): Domain identifier.
        """
        p = handle.params
        snapshot_path = p.get("snapshot_path", "")
        domain_id = p.get("domain_id", "")
        if not snapshot_path:
            return {"error": "snapshot_path is required"}
        if not domain_id:
            return {"error": "domain_id is required"}

        handle.progress(10, "running quality gates")
        result = test_snapshot(
            snapshot_path=snapshot_path,
            domain_id=domain_id,
            profile_name=p.get("profile"),
        )
        handle.progress(100, "done")
        return result

    @skill("loom.snapshot.promote", "Promote a snapshot to current")
    def snapshot_promote(self, handle):
        """Promote a snapshot version to current via symlink.

        Params:
            snapshot_path (str): Path to the snapshot version directory.
            domain_id (str): Domain identifier.
        """
        p = handle.params
        snapshot_path = p.get("snapshot_path", "")
        domain_id = p.get("domain_id", "")
        if not snapshot_path or not domain_id:
            return {"error": "snapshot_path and domain_id are required"}

        snapshots_dir = p.get("snapshots_dir") or DEFAULT_SNAPSHOTS_DIR
        domain_dir = os.path.join(snapshots_dir, domain_id)
        current_link = os.path.join(domain_dir, "current")

        # Remove existing symlink/dir.
        if os.path.islink(current_link):
            os.unlink(current_link)
        elif os.path.isdir(current_link):
            shutil.rmtree(current_link)

        # Create relative symlink.
        version_name = os.path.basename(snapshot_path)
        os.symlink(version_name, current_link)

        # Update manifest with promotion timestamp.
        manifest_path = os.path.join(snapshot_path, "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
            manifest["promoted_at"] = _now_iso()
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

        return {
            "promoted_to": current_link,
            "snapshot_path": snapshot_path,
            "domain_id": domain_id,
            "promoted_at": _now_iso(),
        }

    @skill("loom.snapshot.query", "Search promoted snapshot using FTS5")
    def snapshot_query(self, handle):
        """Query a promoted snapshot using FTS5 full-text search.

        Params:
            domain_id (str): Domain identifier.
            query (str): Search query.
            top_k (int, optional): Max results (default 5).
            min_confidence (float, optional): Minimum confidence filter.
        """
        p = handle.params
        domain_id = p.get("domain_id", "")
        query = p.get("query", "")
        if not domain_id or not query:
            return {"error": "domain_id and query are required"}

        return query_snapshot(
            domain_id=domain_id,
            query=query,
            top_k=p.get("top_k", 5),
            min_confidence=p.get("min_confidence", 0.0),
            snapshots_dir=p.get("snapshots_dir"),
        )


    @skill("loom.snapshot.check_trigger",
           "Check if a snapshot build should be triggered")
    def snapshot_check_trigger(self, handle):
        """Evaluate the event log against the trigger policy.

        Uses the domain profile's trigger_policy (or defaults)
        to decide whether enough has changed since the last
        build to warrant a new snapshot.

        Params:
            domain_id (str): Domain identifier.
            db_path (str, optional): Source evidence graph DB.
            profile (str, optional): Domain profile name.
            snapshots_dir (str, optional): Snapshots root.

        Returns:
            dict with should_build (bool), reason, events.
        """
        p = handle.params
        domain_id = p.get("domain_id", "")
        if not domain_id:
            return {"error": "domain_id is required"}

        return should_build(
            domain_id=domain_id,
            db_path=p.get("db_path"),
            snapshots_dir=p.get("snapshots_dir"),
            profile_name=p.get("profile"),
        )

    @skill("loom.snapshot.build_if_needed",
           "Build a snapshot only if trigger policy says so")
    def snapshot_build_if_needed(self, handle):
        """Check trigger policy and build if warranted.

        Combines check_trigger + build into one call. Returns
        the build result if built, or the trigger check result
        if not.

        Params:
            domain_id (str): Domain identifier.
            db_path (str, optional): Source evidence graph DB.
            profile (str, optional): Domain profile name.
            snapshots_dir (str, optional): Snapshots root.
        """
        p = handle.params
        domain_id = p.get("domain_id", "")
        if not domain_id:
            return {"error": "domain_id is required"}

        trigger = should_build(
            domain_id=domain_id,
            db_path=p.get("db_path"),
            snapshots_dir=p.get("snapshots_dir"),
            profile_name=p.get("profile"),
        )

        if not trigger.get("should_build"):
            return {
                "built": False,
                "trigger": trigger,
            }

        # Determine previous version for changelog.
        snap_dir = (p.get("snapshots_dir")
                    or DEFAULT_SNAPSHOTS_DIR)
        domain_dir = os.path.join(snap_dir, domain_id)
        prev_version = None
        if os.path.isdir(domain_dir):
            existing = sorted([
                d for d in os.listdir(domain_dir)
                if d.startswith("v") and os.path.isdir(
                    os.path.join(domain_dir, d))
            ])
            if existing:
                prev_version = existing[-1]

        # Summarize change events for the manifest.
        change_summaries = []
        for e in trigger.get("events", [])[:20]:
            change_summaries.append(
                f"{e.get('event_type')}:"
                f"{e.get('aggregate_id', '')}")

        handle.progress(10, "building triggered snapshot")
        result = build_snapshot(
            domain_id=domain_id,
            db_path=p.get("db_path"),
            profile_name=p.get("profile"),
            previous_version=prev_version,
            snapshots_dir=p.get("snapshots_dir"),
            triggered_by=trigger.get("reason"),
            change_events=change_summaries,
        )
        result["built"] = True
        result["trigger"] = trigger
        handle.progress(100, "done")
        return result


worker = SnapshotWorker(worker_id="loom-snapshot-1")

if __name__ == "__main__":
    worker.run()
