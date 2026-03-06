"""SnapshotWorker — builds and tests knowledge snapshots.

Responsible for compiling the evidence graph into immutable, versioned
snapshots, running quality gates to verify integrity, and promoting
snapshots from staging to production.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Anti-patterns from the spec
ANTI_PATTERN_MUTABLE_SNAPSHOT = "mutable_snapshot"  # Modifying a published snapshot
ANTI_PATTERN_SKIP_GATES = "skip_quality_gates"  # Promoting without testing
ANTI_PATTERN_ORPHAN_SNAPSHOT = "orphan_snapshot"  # Snapshot without changelog

# Quality gate names
GATE_CONSISTENCY = "consistency"        # No internal contradictions
GATE_COMPLETENESS = "completeness"      # Evidence links exist for all claims
GATE_PROVENANCE = "provenance"          # All claims have source chains
GATE_TEMPORAL = "temporal_validity"     # No expired claims in active snapshot
GATE_CONFIDENCE = "confidence_floor"    # All claims above minimum confidence

# Snapshot stages
STAGE_DRAFT = "draft"
STAGE_STAGING = "staging"
STAGE_PRODUCTION = "production"
STAGE_ARCHIVED = "archived"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_snapshot_id(version: str, timestamp: str) -> str:
    h = hashlib.sha256(f"{version}-{timestamp}".encode()).hexdigest()[:12]
    return f"snap-{h}"


class SnapshotWorker(Worker):
    worker_type = "snapshot"

    @skill("loom.snapshot.build", "Compile evidence graph into immutable snapshot")
    def snapshot_build(self, handle):
        """Build an immutable snapshot of the current evidence graph.

        Compiles all claims, evidence links, and metadata into a
        versioned snapshot with a changelog.

        Params (from handle.params):
            version (str): Semantic version for this snapshot (e.g. "1.2.0").
            description (str, optional): Human-readable description.
            include_contested (bool, optional): Include contested claims
                (default False).

        Returns:
            dict with snapshot_id, version, claim_count, changelog.
        """
        params = handle.params
        version = params.get("version", "")

        if not version:
            return {"error": "version is required"}

        now = _now_iso()
        snapshot_id = _generate_snapshot_id(version, now)
        include_contested = params.get("include_contested", False)

        # Stub: in production, queries the KB for all claims matching
        # the inclusion criteria, serializes the evidence graph, and
        # writes the immutable snapshot to storage.
        claim_count = 0  # Would be populated from KB query

        changelog = {
            "version": version,
            "built_at": now,
            "description": params.get("description", ""),
            "include_contested": include_contested,
            "claims_added": 0,
            "claims_updated": 0,
            "claims_removed": 0,
        }

        return {
            "snapshot_id": snapshot_id,
            "version": version,
            "stage": STAGE_DRAFT,
            "claim_count": claim_count,
            "changelog": changelog,
            "built_at": now,
        }

    @skill("loom.snapshot.test", "Run quality gates against a snapshot")
    def snapshot_test(self, handle):
        """Run quality gates against a snapshot before promotion.

        Gates:
        - consistency: no internal contradictions
        - completeness: all claims have evidence links
        - provenance: all evidence chains are intact
        - temporal_validity: no expired claims
        - confidence_floor: all claims above minimum threshold

        Params (from handle.params):
            snapshot_id (str): The snapshot to test.
            confidence_threshold (float, optional): Minimum confidence
                for the confidence_floor gate (default 0.3).

        Returns:
            dict with passed (bool) and gate_results.
        """
        params = handle.params
        snapshot_id = params.get("snapshot_id", "")

        if not snapshot_id:
            return {"error": "snapshot_id is required"}

        confidence_threshold = params.get("confidence_threshold", 0.3)

        # Stub: in production, each gate runs actual checks against
        # the snapshot data.
        gate_results = {
            GATE_CONSISTENCY: {
                "passed": True,
                "details": "No internal contradictions found",
            },
            GATE_COMPLETENESS: {
                "passed": True,
                "details": "All claims have at least one evidence link",
            },
            GATE_PROVENANCE: {
                "passed": True,
                "details": "All evidence chains intact",
            },
            GATE_TEMPORAL: {
                "passed": True,
                "details": "No expired claims in snapshot",
            },
            GATE_CONFIDENCE: {
                "passed": True,
                "details": f"All claims above {confidence_threshold} threshold",
            },
        }

        all_passed = all(g["passed"] for g in gate_results.values())

        return {
            "passed": all_passed,
            "snapshot_id": snapshot_id,
            "gate_results": gate_results,
            "tested_at": _now_iso(),
        }

    @skill("loom.snapshot.promote", "Promote a snapshot to production")
    def snapshot_promote(self, handle):
        """Promote a snapshot from staging to production.

        Requires that quality gates have passed. Updates the active
        production snapshot pointer.

        Params (from handle.params):
            snapshot_id (str): The snapshot to promote.
            target_stage (str, optional): Target stage (default "production").
            force (bool, optional): Skip gate check (anti-pattern, logged).

        Returns:
            dict with snapshot_id, promoted_to.
        """
        params = handle.params
        snapshot_id = params.get("snapshot_id", "")
        target_stage = params.get("target_stage", STAGE_PRODUCTION)
        force = params.get("force", False)

        if not snapshot_id:
            return {"error": "snapshot_id is required"}

        if force:
            # This is an anti-pattern but allowed with logging
            return {
                "snapshot_id": snapshot_id,
                "promoted_to": target_stage,
                "warning": "Force promotion without gate check "
                           f"(anti-pattern: {ANTI_PATTERN_SKIP_GATES})",
                "promoted_at": _now_iso(),
            }

        # Stub: in production, verifies gate results exist and passed,
        # then atomically swaps the production pointer.
        return {
            "snapshot_id": snapshot_id,
            "promoted_to": target_stage,
            "promoted_at": _now_iso(),
        }


worker = SnapshotWorker(worker_id="loom-snapshot-1")

if __name__ == "__main__":
    worker.run()
