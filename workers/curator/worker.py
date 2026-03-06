"""CuratorWorker — human-in-the-loop review for contested claims.

Responsible for presenting contested or escalated claims to human curators,
accepting approval or rejection decisions, and recording curator identity
for audit trails.
"""

import os
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Resolution types
RESOLUTION_APPROVED = "approved"
RESOLUTION_REJECTED = "rejected"
RESOLUTION_DEFERRED = "deferred"
RESOLUTION_MERGED = "merged"

# Anti-patterns from the spec
ANTI_PATTERN_RUBBER_STAMP = "rubber_stamp"  # Approving without review
ANTI_PATTERN_NO_AUDIT = "no_audit_trail"  # Decision without curator ID
ANTI_PATTERN_STALE_QUEUE = "stale_queue"  # Letting review queue grow unbounded


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CuratorWorker(Worker):
    worker_type = "curator"

    @skill("curate.review", "Present contested claims for human review")
    def curate_review(self, handle):
        """Present contested claims for human review.

        Retrieves the review queue and presents claims needing human
        judgment, sorted by priority.

        Params (from handle.params):
            queue_filter (str, optional): Filter by topic or priority.
            limit (int, optional): Maximum items to present (default 10).

        Returns:
            dict with reviewed (already reviewed) and pending (awaiting review).
        """
        params = handle.params
        limit = params.get("limit", 10)
        queue_filter = params.get("queue_filter", "")

        # Stub: in production, queries the escalation queue from the KB.
        reviewed = []
        pending = []

        # Example pending item structure:
        # {
        #     "escalation_id": "esc-001",
        #     "claim_a": {"statement": "...", "source_tier": "T3"},
        #     "claim_b": {"statement": "...", "source_tier": "T3"},
        #     "nature": "numeric_conflict",
        #     "priority": "high",
        #     "escalated_at": "2026-03-06T...",
        # }

        return {
            "reviewed": reviewed,
            "pending": pending,
            "queue_depth": len(pending),
            "filter_applied": queue_filter or "none",
            "retrieved_at": _now_iso(),
        }

    @skill("curate.approve", "Approve a claim resolution")
    def curate_approve(self, handle):
        """Approve a claim resolution after human review.

        Records the curator's identity and reasoning for the audit trail.

        Params (from handle.params):
            claim_id (str): ID of the claim to approve.
            resolution (str): Resolution detail (which claim prevails, etc.).
            curator_id (str): Identifier of the reviewing curator.
            notes (str, optional): Curator's reasoning or notes.

        Returns:
            dict with claim_id, resolution, curator_id.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")
        resolution = params.get("resolution", "")
        curator_id = params.get("curator_id", "")

        if not claim_id:
            return {"error": "claim_id is required"}
        if not curator_id:
            return {"error": "curator_id is required (audit trail)"}

        return {
            "claim_id": claim_id,
            "resolution": resolution or RESOLUTION_APPROVED,
            "curator_id": curator_id,
            "notes": params.get("notes", ""),
            "approved_at": _now_iso(),
        }

    @skill("curate.reject", "Reject a claim")
    def curate_reject(self, handle):
        """Reject a claim after human review.

        Records the curator's identity and rejection reason for the
        audit trail.

        Params (from handle.params):
            claim_id (str): ID of the claim to reject.
            reason (str): Reason for rejection.
            curator_id (str): Identifier of the reviewing curator.

        Returns:
            dict with claim_id, reason, curator_id.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")
        reason = params.get("reason", "")
        curator_id = params.get("curator_id", "")

        if not claim_id:
            return {"error": "claim_id is required"}
        if not curator_id:
            return {"error": "curator_id is required (audit trail)"}
        if not reason:
            return {"error": "reason is required for rejection"}

        return {
            "claim_id": claim_id,
            "reason": reason,
            "curator_id": curator_id,
            "rejected_at": _now_iso(),
        }


worker = CuratorWorker(worker_id="loom-curator-1")

if __name__ == "__main__":
    worker.run()
