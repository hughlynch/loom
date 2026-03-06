"""MonitorWorker — monitors Loom system health.

Responsible for detecting anomalies in source introduction rates,
monitoring the challenge process health, and flagging potential
manipulation attempts (e.g., coordinated low-tier source flooding).
"""

import os
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Alert severity levels
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# Anti-patterns from the spec
ANTI_PATTERN_SOURCE_FLOOD = "source_flood"  # Coordinated low-tier source injection
ANTI_PATTERN_STALE_CHALLENGES = "stale_challenges"  # Challenges not being resolved
ANTI_PATTERN_AUTO_CLOSE_ABUSE = "auto_close_abuse"  # Legitimate challenges auto-closed

# Anomaly types
ANOMALY_SPIKE = "spike"              # Sudden increase in source rate
ANOMALY_SINGLE_ORIGIN = "single_origin"  # Many sources from one origin
ANOMALY_TOPIC_FLOOD = "topic_flood"  # Concentrated topic injection
ANOMALY_LOW_TIER_WAVE = "low_tier_wave"  # Wave of T6/T7 sources


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MonitorWorker(Worker):
    worker_type = "monitor"

    @skill("loom.monitor.source_rates", "Check source introduction rates")
    def monitor_source_rates(self, handle):
        """Check source introduction rates for anomalies.

        Monitors the rate at which new sources are being introduced,
        flagging spikes, single-origin floods, topic concentration,
        and low-tier waves.

        Params (from handle.params):
            window_hours (int, optional): Monitoring window (default 24).
            threshold_multiplier (float, optional): Anomaly threshold as
                multiplier of baseline rate (default 3.0).

        Returns:
            dict with anomalies, new_origins_24h, flagged_topics.
        """
        params = handle.params
        window_hours = params.get("window_hours", 24)
        threshold_multiplier = params.get("threshold_multiplier", 3.0)

        # Stub: in production, queries the KB for source introduction
        # rates over the window, compares against the rolling baseline,
        # and flags anomalies.
        anomalies = []
        new_origins_24h = 0
        flagged_topics = []

        # Example anomaly structure:
        # {
        #     "type": ANOMALY_SPIKE,
        #     "severity": SEVERITY_WARNING,
        #     "detail": "Source introduction rate 5x baseline",
        #     "origin": "example.com",
        #     "window_hours": 24,
        #     "detected_at": _now_iso(),
        # }

        return {
            "anomalies": anomalies,
            "new_origins_24h": new_origins_24h,
            "flagged_topics": flagged_topics,
            "window_hours": window_hours,
            "threshold_multiplier": threshold_multiplier,
            "checked_at": _now_iso(),
        }

    @skill("loom.monitor.challenge_health", "Check challenge process health")
    def monitor_challenge_health(self, handle):
        """Check the health of the community challenge process.

        Monitors auto-close rates, submission rates, and average
        resolution times to detect issues like stale queues or
        excessive auto-closing.

        Params (from handle.params):
            window_days (int, optional): Monitoring window (default 30).

        Returns:
            dict with auto_close_rate, submission_rate,
            avg_resolution_time, alerts.
        """
        params = handle.params
        window_days = params.get("window_days", 30)

        # Stub: in production, queries challenge records over the window
        # and computes health metrics.
        auto_close_rate = 0.0   # Fraction of challenges auto-closed
        submission_rate = 0.0   # Challenges per day
        avg_resolution_time = 0.0  # Hours to resolve

        alerts = []

        # Health checks
        # 1. Auto-close rate too high suggests legitimate challenges
        #    are being dismissed
        if auto_close_rate > 0.9:
            alerts.append({
                "severity": SEVERITY_WARNING,
                "type": ANTI_PATTERN_AUTO_CLOSE_ABUSE,
                "detail": f"Auto-close rate {auto_close_rate:.0%} exceeds 90%",
            })

        # 2. Low submission rate might indicate the challenge system
        #    is not accessible
        if submission_rate < 0.1:
            alerts.append({
                "severity": SEVERITY_INFO,
                "type": "low_submission_rate",
                "detail": f"Challenge submission rate {submission_rate:.2f}/day",
            })

        # 3. High resolution time indicates stale queue
        if avg_resolution_time > 168:  # > 1 week
            alerts.append({
                "severity": SEVERITY_CRITICAL,
                "type": ANTI_PATTERN_STALE_CHALLENGES,
                "detail": f"Avg resolution time {avg_resolution_time:.0f}h "
                          f"exceeds 1 week",
            })

        return {
            "auto_close_rate": auto_close_rate,
            "submission_rate": submission_rate,
            "avg_resolution_time": avg_resolution_time,
            "alerts": alerts,
            "window_days": window_days,
            "checked_at": _now_iso(),
        }


worker = MonitorWorker(worker_id="loom-monitor-1")

if __name__ == "__main__":
    worker.run()
