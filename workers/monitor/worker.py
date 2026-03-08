"""MonitorWorker — monitors Loom system health.

Tracks source introduction rates, challenge process health,
and overall system health. Queries the KB evidence graph and
event log to detect anomalies and report actionable metrics.
"""

import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from grove.uwp import Worker, skill

# Alert severity levels
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# Anomaly types
ANOMALY_SPIKE = "spike"
ANOMALY_SINGLE_ORIGIN = "single_origin"
ANOMALY_TOPIC_FLOOD = "topic_flood"
ANOMALY_LOW_TIER_WAVE = "low_tier_wave"

# Anti-patterns
ANTI_PATTERN_SOURCE_FLOOD = "source_flood"
ANTI_PATTERN_STALE_CHALLENGES = "stale_challenges"
ANTI_PATTERN_AUTO_CLOSE_ABUSE = "auto_close_abuse"

DEFAULT_DB_PATH = os.environ.get(
    "LOOM_DB_PATH",
    os.path.join(
        os.path.expanduser("~"),
        "loom", "data", "loom.db"),
)
DEFAULT_SNAPSHOTS_DIR = os.environ.get(
    "LOOM_SNAPSHOTS_DIR",
    os.path.join(
        os.path.expanduser("~"),
        "loom", "data", "snapshots"),
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _now_dt():
    return datetime.now(timezone.utc)


def _parse_dt(s):
    """Parse ISO datetime, return None on failure."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _get_db(db_path):
    """Open DB read-only. Returns conn or None."""
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(
        f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _source_rate_metrics(db_path, window_hours=24):
    """Compute source introduction rate metrics.

    Returns dict with tier_counts, domain_counts,
    category_counts, total_new, and per-tier rates.
    """
    conn = _get_db(db_path)
    if conn is None:
        return {
            "total_new": 0, "tier_counts": {},
            "domain_counts": {}, "category_counts": {},
        }

    cutoff = (_now_dt() - timedelta(
        hours=window_hours)).isoformat()

    try:
        # Claims created in window.
        rows = conn.execute(
            "SELECT source_tier, category, claim_id "
            "FROM claims WHERE created_at >= ?",
            (cutoff,),
        ).fetchall()

        tier_counts = Counter()
        category_counts = Counter()
        for r in rows:
            tier_counts[r["source_tier"] or "unknown"] += 1
            category_counts[r["category"] or "unknown"] += 1

        # Evidence source domains in window.
        ev_rows = conn.execute(
            "SELECT source_url FROM evidence "
            "WHERE created_at >= ?",
            (cutoff,),
        ).fetchall()

        domain_counts = Counter()
        for e in ev_rows:
            url = e["source_url"] or ""
            if "://" in url:
                domain = url.split("://", 1)[1].split(
                    "/", 1)[0]
            else:
                domain = url.split("/", 1)[0]
            if domain:
                domain_counts[domain] += 1

        return {
            "total_new": len(rows),
            "tier_counts": dict(tier_counts),
            "domain_counts": dict(domain_counts),
            "category_counts": dict(category_counts),
        }
    except sqlite3.OperationalError:
        return {
            "total_new": 0, "tier_counts": {},
            "domain_counts": {}, "category_counts": {},
        }
    finally:
        conn.close()


def _detect_anomalies(metrics, threshold_mult=3.0):
    """Detect anomalies in source rate metrics."""
    anomalies = []
    tier_counts = metrics.get("tier_counts", {})
    domain_counts = metrics.get("domain_counts", {})
    category_counts = metrics.get("category_counts", {})
    total = metrics.get("total_new", 0)

    if total == 0:
        return anomalies

    # Low-tier wave: T6+T7 > 50% of total.
    low_tier = (
        tier_counts.get("T6", 0)
        + tier_counts.get("T7", 0)
    )
    if low_tier > total * 0.5 and total >= 5:
        anomalies.append({
            "type": ANOMALY_LOW_TIER_WAVE,
            "severity": SEVERITY_WARNING,
            "detail": (
                f"Low-tier sources (T6+T7) are "
                f"{low_tier}/{total} "
                f"({low_tier/total:.0%})"),
            "count": low_tier,
        })

    # Single-origin flood: one domain > 50% of evidence.
    if domain_counts:
        top_domain = max(
            domain_counts, key=domain_counts.get)
        top_count = domain_counts[top_domain]
        total_evidence = sum(domain_counts.values())
        if (top_count > total_evidence * 0.5
                and total_evidence >= 5):
            anomalies.append({
                "type": ANOMALY_SINGLE_ORIGIN,
                "severity": SEVERITY_WARNING,
                "detail": (
                    f"Domain '{top_domain}' accounts "
                    f"for {top_count}/{total_evidence} "
                    f"evidence items"),
                "domain": top_domain,
                "count": top_count,
            })

    # Topic flood: one category > 60% of claims.
    if category_counts:
        top_cat = max(
            category_counts, key=category_counts.get)
        top_cat_count = category_counts[top_cat]
        if (top_cat_count > total * 0.6
                and total >= 5):
            anomalies.append({
                "type": ANOMALY_TOPIC_FLOOD,
                "severity": SEVERITY_INFO,
                "detail": (
                    f"Category '{top_cat}' accounts "
                    f"for {top_cat_count}/{total} claims"),
                "category": top_cat,
                "count": top_cat_count,
            })

    return anomalies


def _challenge_metrics(db_path, window_days=30):
    """Compute challenge (contradiction) health metrics."""
    conn = _get_db(db_path)
    if conn is None:
        return {
            "total_contradictions": 0,
            "resolved": 0,
            "unresolved": 0,
            "avg_age_hours": 0,
        }

    cutoff = (_now_dt() - timedelta(
        days=window_days)).isoformat()

    try:
        rows = conn.execute(
            "SELECT * FROM contradictions "
            "WHERE created_at >= ?",
            (cutoff,),
        ).fetchall()

        total = len(rows)
        resolved = sum(
            1 for r in rows if r["resolved_at"])
        unresolved = total - resolved

        # Average age of unresolved contradictions.
        ages = []
        now = _now_dt()
        for r in rows:
            if not r["resolved_at"]:
                created = _parse_dt(r["created_at"])
                if created:
                    age_h = (now - created).total_seconds() / 3600
                    ages.append(age_h)

        avg_age = (
            sum(ages) / len(ages) if ages else 0.0)

        return {
            "total_contradictions": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "avg_age_hours": avg_age,
            "resolution_rate": (
                resolved / total if total > 0 else 1.0),
        }
    except sqlite3.OperationalError:
        return {
            "total_contradictions": 0,
            "resolved": 0,
            "unresolved": 0,
            "avg_age_hours": 0,
        }
    finally:
        conn.close()


def _db_stats(db_path):
    """Get basic DB statistics."""
    conn = _get_db(db_path)
    if conn is None:
        return {
            "claims": 0, "evidence": 0,
            "events": 0, "contradictions": 0,
            "db_size_kb": 0,
        }

    try:
        stats = {}
        for table in [
            "claims", "evidence", "events",
            "contradictions",
        ]:
            try:
                row = conn.execute(
                    f"SELECT COUNT(*) as n FROM {table}"
                ).fetchone()
                stats[table] = row["n"]
            except sqlite3.OperationalError:
                stats[table] = 0

        path = db_path or DEFAULT_DB_PATH
        stats["db_size_kb"] = (
            os.path.getsize(path) // 1024
            if os.path.exists(path) else 0
        )
        return stats
    finally:
        conn.close()


def _snapshot_freshness(domain_id="default",
                        snapshots_dir=None):
    """Check snapshot freshness for a domain."""
    snap_dir = snapshots_dir or DEFAULT_SNAPSHOTS_DIR
    domain_dir = os.path.join(snap_dir, domain_id)

    if not os.path.isdir(domain_dir):
        return {
            "has_snapshot": False,
            "age_hours": None,
            "version": None,
        }

    # Find latest version.
    versions = sorted([
        d for d in os.listdir(domain_dir)
        if d.startswith("v") and os.path.isdir(
            os.path.join(domain_dir, d))
    ])
    if not versions:
        return {
            "has_snapshot": False,
            "age_hours": None,
            "version": None,
        }

    latest = versions[-1]
    manifest_path = os.path.join(
        domain_dir, latest, "manifest.json")
    if not os.path.exists(manifest_path):
        return {
            "has_snapshot": True,
            "age_hours": None,
            "version": latest,
        }

    with open(manifest_path) as f:
        manifest = json.load(f)

    built_at = _parse_dt(manifest.get("built_at"))
    age_hours = None
    if built_at:
        age_hours = (
            _now_dt() - built_at
        ).total_seconds() / 3600

    return {
        "has_snapshot": True,
        "age_hours": age_hours,
        "version": latest,
        "claim_count": manifest.get("claim_count", 0),
        "event_sequence": manifest.get(
            "event_sequence", 0),
    }


class MonitorWorker(Worker):
    worker_type = "monitor"

    @skill("loom.monitor.source_rates",
           "Check source introduction rates")
    def monitor_source_rates(self, handle):
        """Check source introduction rates for anomalies.

        Queries the KB for claims and evidence created
        within the monitoring window, computes tier/domain/
        category distributions, and flags anomalies.

        Params:
            db_path (str, optional): KB database path.
            window_hours (int, optional): Window (default 24).
            threshold_multiplier (float, optional): Anomaly
                threshold multiplier (default 3.0).

        Returns:
            dict with metrics, anomalies, alerts.
        """
        p = handle.params
        db_path = p.get("db_path", "")
        window = p.get("window_hours", 24)
        threshold = p.get("threshold_multiplier", 3.0)

        metrics = _source_rate_metrics(
            db_path, window)
        anomalies = _detect_anomalies(
            metrics, threshold)

        return {
            "total_new_claims": metrics["total_new"],
            "tier_distribution": metrics["tier_counts"],
            "domain_distribution": metrics[
                "domain_counts"],
            "category_distribution": metrics[
                "category_counts"],
            "anomalies": anomalies,
            "window_hours": window,
            "checked_at": _now_iso(),
        }

    @skill("loom.monitor.challenge_health",
           "Check challenge process health")
    def monitor_challenge_health(self, handle):
        """Check the health of the contradiction/challenge
        resolution process.

        Params:
            db_path (str, optional): KB database path.
            window_days (int, optional): Window (default 30).

        Returns:
            dict with metrics and alerts.
        """
        p = handle.params
        db_path = p.get("db_path", "")
        window = p.get("window_days", 30)

        metrics = _challenge_metrics(db_path, window)
        alerts = []

        # Stale challenges: avg age > 1 week.
        if metrics["avg_age_hours"] > 168:
            alerts.append({
                "severity": SEVERITY_CRITICAL,
                "type": ANTI_PATTERN_STALE_CHALLENGES,
                "detail": (
                    f"Average unresolved contradiction "
                    f"age is "
                    f"{metrics['avg_age_hours']:.0f}h "
                    f"(>168h threshold)"),
            })

        # Low resolution rate.
        rate = metrics.get("resolution_rate", 1.0)
        if (rate < 0.5
                and metrics["total_contradictions"] >= 3):
            alerts.append({
                "severity": SEVERITY_WARNING,
                "type": "low_resolution_rate",
                "detail": (
                    f"Resolution rate is {rate:.0%} "
                    f"({metrics['resolved']}/"
                    f"{metrics['total_contradictions']})"),
            })

        return {
            **metrics,
            "alerts": alerts,
            "window_days": window,
            "checked_at": _now_iso(),
        }

    @skill("loom.monitor.system_health",
           "Composite system health report")
    def monitor_system_health(self, handle):
        """Composite system health combining all monitors.

        Reports DB statistics, event log growth, snapshot
        freshness, and overall health classification.

        Params:
            db_path (str, optional): KB database path.
            domain_id (str, optional): Domain to check.
            snapshots_dir (str, optional): Snapshots root.

        Returns:
            dict with db_stats, snapshot_freshness,
            source_health, challenge_health, and
            overall_status.
        """
        p = handle.params
        db_path = p.get("db_path", "")
        domain_id = p.get("domain_id", "default")

        stats = _db_stats(db_path)
        freshness = _snapshot_freshness(
            domain_id,
            p.get("snapshots_dir"),
        )
        source_metrics = _source_rate_metrics(
            db_path, 24)
        source_anomalies = _detect_anomalies(
            source_metrics)
        challenge = _challenge_metrics(db_path, 30)

        # Overall health classification.
        issues = []
        if not freshness["has_snapshot"]:
            issues.append("no_snapshot")
        elif (freshness["age_hours"] is not None
              and freshness["age_hours"] > 48):
            issues.append("stale_snapshot")

        if challenge["avg_age_hours"] > 168:
            issues.append("stale_challenges")

        critical_anomalies = [
            a for a in source_anomalies
            if a.get("severity") == SEVERITY_CRITICAL
        ]
        if critical_anomalies:
            issues.append("critical_anomalies")

        if not issues:
            status = "healthy"
        elif any(
            i in issues
            for i in ("critical_anomalies",
                      "stale_challenges")
        ):
            status = "degraded"
        else:
            status = "attention_needed"

        return {
            "overall_status": status,
            "issues": issues,
            "db_stats": stats,
            "snapshot_freshness": freshness,
            "source_anomaly_count": len(
                source_anomalies),
            "challenge_metrics": {
                "total": challenge[
                    "total_contradictions"],
                "unresolved": challenge["unresolved"],
                "resolution_rate": challenge.get(
                    "resolution_rate", 1.0),
            },
            "checked_at": _now_iso(),
        }


worker = MonitorWorker(worker_id="loom-monitor-1")

if __name__ == "__main__":
    worker.run()
