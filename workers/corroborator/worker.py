"""CorroboratorWorker — cross-references claims against the knowledge base.

Responsible for checking new claims against existing knowledge, finding
corroboration or contradiction, and computing confidence scores using
deterministic rules based on evidence hierarchy.
"""

import os
import re
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Confidence status values (deterministic computation)
STATUS_VERIFIED = "verified"          # T1/T2 source, no contradictions
STATUS_CORROBORATED = "corroborated"  # Multiple independent sources agree
STATUS_REPORTED = "reported"          # Single source, no contradiction
STATUS_CONTESTED = "contested"        # Contradicting claims exist
STATUS_UNVERIFIED = "unverified"      # No corroboration, low-tier source

# Anti-patterns from the spec
ANTI_PATTERN_CIRCULAR_CORROBORATION = "circular_corroboration"  # Same source cited as independent
ANTI_PATTERN_QUANTITY_OVER_QUALITY = "quantity_over_quality"  # Many T6 != one T1
ANTI_PATTERN_MISSING_INDEPENDENCE = "missing_independence_check"  # No source independence check

# Confidence score rules (deterministic)
# These map (status, source_tier) to confidence ranges.
CONFIDENCE_RULES = {
    STATUS_VERIFIED: {
        "T1": (0.95, 1.0),
        "T2": (0.85, 0.95),
    },
    STATUS_CORROBORATED: {
        # Multiple independent sources — score depends on best source tier
        "T1": (0.90, 0.98),
        "T2": (0.80, 0.92),
        "T3": (0.70, 0.85),
        "T4": (0.60, 0.78),
        "T5": (0.50, 0.70),
        "T6": (0.30, 0.50),
        "T7": (0.15, 0.35),
    },
    STATUS_REPORTED: {
        # Single source, no contradiction
        "T1": (0.80, 0.90),
        "T2": (0.65, 0.80),
        "T3": (0.50, 0.65),
        "T4": (0.40, 0.55),
        "T5": (0.25, 0.40),
        "T6": (0.10, 0.25),
        "T7": (0.05, 0.15),
    },
    STATUS_CONTESTED: {
        # Contradictions exist — confidence bounded low
        "T1": (0.40, 0.60),
        "T2": (0.30, 0.50),
        "T3": (0.20, 0.40),
        "T4": (0.15, 0.30),
        "T5": (0.10, 0.25),
        "T6": (0.05, 0.15),
        "T7": (0.01, 0.10),
    },
    STATUS_UNVERIFIED: {
        # Default for uncorroborated low-tier sources
        "T1": (0.50, 0.70),  # Unusual: T1 should be at least reported
        "T2": (0.40, 0.60),
        "T3": (0.25, 0.40),
        "T4": (0.15, 0.30),
        "T5": (0.10, 0.20),
        "T6": (0.05, 0.10),
        "T7": (0.01, 0.05),
    },
}


def compute_confidence(status: str, source_tier: str,
                       independent_source_count: int = 1) -> float:
    """Deterministic confidence computation from the spec.

    Rules:
    - verified: T1/T2 source, no contradictions -> 0.85-1.0
    - corroborated: 2+ independent sources agree -> tier-based range,
      boosted by count (diminishing returns)
    - reported: single source, no contradiction -> tier-based range
    - contested: contradictions exist -> bounded low
    - unverified: no corroboration, low-tier -> lowest range

    The independence check is critical: sources that share a common
    upstream source do NOT count as independent.

    Args:
        status: One of the STATUS_* constants.
        source_tier: Best source tier (T1-T7).
        independent_source_count: Number of independent sources.

    Returns:
        Confidence score between 0.0 and 1.0.
    """
    tier_rules = CONFIDENCE_RULES.get(status, CONFIDENCE_RULES[STATUS_UNVERIFIED])
    score_range = tier_rules.get(source_tier, tier_rules.get("T5", (0.10, 0.20)))

    low, high = score_range
    base = (low + high) / 2.0

    # Corroboration boost: each independent source adds diminishing value
    if status == STATUS_CORROBORATED and independent_source_count > 1:
        boost = min(0.15, 0.05 * (independent_source_count - 1))
        base = min(high, base + boost)

    # Contestation penalty: more contradictions reduce confidence
    if status == STATUS_CONTESTED:
        base = low  # Use floor when contested

    return round(base, 4)


def _check_independence(source_a: dict, source_b: dict) -> bool:
    """Check if two sources are editorially independent.

    Stub implementation. In production, this checks:
    - Different parent organizations
    - Different geographic origin
    - Different wire service feeds
    - No common upstream source

    Returns:
        True if sources appear independent.
    """
    domain_a = source_a.get("domain", "")
    domain_b = source_b.get("domain", "")
    # Simple heuristic: different domains = independent (oversimplified)
    return domain_a != domain_b


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CorroboratorWorker(Worker):
    worker_type = "corroborator"

    @skill("corroborate.check", "Check a claim against existing KB")
    def corroborate_check(self, handle):
        """Check a claim against the existing knowledge base.

        Searches for matching and contradicting claims, performs source
        independence verification, and computes deterministic confidence.

        Params (from handle.params):
            statement (str): The claim statement to check.
            source_tier (str): Source tier of the new claim (T1-T7).
            source_info (dict, optional): Source metadata for independence check.
            content_hash (str, optional): Content hash for dedup.

        Returns:
            dict with status, confidence, matching_claims, contradicting_claims,
            independence_check.
        """
        params = handle.params
        statement = params.get("statement", "")
        source_tier = params.get("source_tier", "T5")

        if not statement:
            return {"error": "statement is required"}

        # Stub: in production, this queries the KB via semantic search
        # to find matching and contradicting claims.
        matching_claims = []
        contradicting_claims = []

        # Determine status based on matches/contradictions
        if contradicting_claims:
            status = STATUS_CONTESTED
        elif len(matching_claims) >= 2:
            status = STATUS_CORROBORATED
        elif source_tier in ("T1", "T2") and not contradicting_claims:
            status = STATUS_VERIFIED
        else:
            # Single source with no contradictions = reported.
            # "Unverified" is reserved for claims with no source at all
            # or where verification was not attempted.
            status = STATUS_REPORTED

        # Independence check (stub: no matches to check against)
        independence_check = {
            "sources_checked": 0,
            "independent_count": 0,
            "circular_references_found": False,
        }

        confidence = compute_confidence(
            status, source_tier,
            independent_source_count=max(1, independence_check["independent_count"]),
        )

        return {
            "status": status,
            "confidence": confidence,
            "matching_claims": matching_claims,
            "contradicting_claims": contradicting_claims,
            "independence_check": independence_check,
            "checked_at": _now_iso(),
        }

    @skill("corroborate.find_contradictions", "Scan for contradictions in claims")
    def find_contradictions(self, handle):
        """Scan a set of claims for internal contradictions.

        Performs pairwise comparison of claims to find logical
        contradictions, noting the nature of each contradiction.

        Params (from handle.params):
            claims (list): List of claim dicts with statement and metadata.

        Returns:
            dict with contradictions list, each containing claim_a, claim_b,
            and nature of the contradiction.
        """
        params = handle.params
        claims = params.get("claims", [])

        if len(claims) < 2:
            return {"contradictions": [], "note": "Need at least 2 claims"}

        contradictions = []

        # Extract numbers from claims for numeric conflict detection
        def _extract_numbers(text):
            """Find numbers with optional units in text."""
            matches = re.findall(
                r'(\d[\d,]*(?:\.\d+)?)\s*'
                r'(million|billion|trillion|thousand|percent|%|'
                r'degrees?|dollars?)?',
                text, re.IGNORECASE,
            )
            results = []
            for num_str, unit in matches:
                try:
                    val = float(num_str.replace(",", ""))
                    unit = unit.lower().rstrip("s") if unit else ""
                    # Normalize multipliers
                    if unit == "thousand":
                        val *= 1_000
                        unit = ""
                    elif unit == "million":
                        val *= 1_000_000
                        unit = ""
                    elif unit == "billion":
                        val *= 1_000_000_000
                        unit = ""
                    elif unit == "trillion":
                        val *= 1_000_000_000_000
                        unit = ""
                    results.append((val, unit))
                except ValueError:
                    continue
            return results

        # Pairwise comparison
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                a = claims[i]
                b = claims[j]
                stmt_a = a.get("statement", "")
                stmt_b = b.get("statement", "")

                # Check for numeric contradictions
                nums_a = _extract_numbers(stmt_a)
                nums_b = _extract_numbers(stmt_b)

                for na_val, na_unit in nums_a:
                    for nb_val, nb_unit in nums_b:
                        # Same unit (including both dimensionless) with
                        # significantly different values
                        if na_unit == nb_unit and na_val != 0 and nb_val != 0:
                            ratio = max(na_val, nb_val) / min(na_val, nb_val)
                            if ratio > 1.2:  # >20% difference
                                contradictions.append({
                                    "claim_a": a,
                                    "claim_b": b,
                                    "nature": "numeric_conflict",
                                    "detail": f"{na_val} {na_unit} vs {nb_val} {nb_unit}",
                                })
                                break  # One contradiction per pair is enough
                    else:
                        continue
                    break

        return {
            "contradictions": contradictions,
            "claims_compared": len(claims),
            "pairs_checked": len(claims) * (len(claims) - 1) // 2,
            "checked_at": _now_iso(),
        }


worker = CorroboratorWorker(worker_id="loom-corroborator-1")

if __name__ == "__main__":
    worker.run()
