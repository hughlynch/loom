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


# Information credibility levels (C1-C6, Admiralty Code axis 2)
CREDIBILITY_C1 = "C1"  # Confirmed by multiple independent sources
CREDIBILITY_C2 = "C2"  # Probably true — logical, consistent
CREDIBILITY_C3 = "C3"  # Possibly true — needs verification
CREDIBILITY_C4 = "C4"  # Doubtfully true — inconsistent
CREDIBILITY_C5 = "C5"  # Improbable — contradicts established facts
CREDIBILITY_C6 = "C6"  # Cannot be assessed

# Credibility modifiers for confidence
CREDIBILITY_MODIFIERS = {
    "C1": 1.0,    # Confirmed: full weight
    "C2": 0.85,   # Probably true
    "C3": 0.65,   # Possibly true
    "C4": 0.40,   # Doubtfully true
    "C5": 0.15,   # Improbable
    "C6": 0.50,   # Cannot assess: neutral
}

# GRADE adjustment factors
GRADE_DOWN_FACTORS = [
    "risk_of_bias",       # Methodology issues
    "inconsistency",      # Sources disagree
    "indirectness",       # Evidence doesn't directly address claim
    "imprecision",        # Vague/imprecise evidence
    "publication_bias",   # Incomplete evidence landscape
]
GRADE_UP_FACTORS = [
    "large_effect",       # Overwhelming evidence
    "dose_response",      # Gradient supports causation
    "confounding",        # Plausible confounders favor claim
]


def compute_confidence_v2(
    status: str,
    source_tier: str,
    info_credibility: str = "C6",
    independent_source_count: int = 1,
    grade_adjustments: list[dict] | None = None,
) -> dict:
    """Dual-axis confidence computation with GRADE adjustments.

    Returns dict with base_confidence, credibility_adjusted,
    grade_adjusted (final), and breakdown of adjustments applied.
    """
    # Step 1: Base confidence from tier × status (same as v1)
    base = compute_confidence(status, source_tier, independent_source_count)

    # Step 2: Credibility modifier (Admiralty axis 2)
    cred_mod = CREDIBILITY_MODIFIERS.get(info_credibility, 0.50)
    cred_adjusted = round(base * cred_mod, 4)

    # Step 3: GRADE adjustments
    adjustments_applied = []
    grade_delta = 0.0
    if grade_adjustments:
        for adj in grade_adjustments:
            factor = adj.get("factor", "")
            direction = adj.get("direction", "down")
            magnitude = adj.get("magnitude", 0.0)
            if direction == "down":
                grade_delta -= magnitude
            elif direction == "up":
                grade_delta += magnitude
            adjustments_applied.append({
                "factor": factor,
                "direction": direction,
                "magnitude": magnitude,
            })

    final = round(max(0.01, min(1.0, cred_adjusted + grade_delta)), 4)

    # Step 4: Derive IPCC-style analytic confidence
    if final >= 0.90:
        analytic_confidence = "very_high"
    elif final >= 0.70:
        analytic_confidence = "high"
    elif final >= 0.40:
        analytic_confidence = "medium"
    else:
        analytic_confidence = "low"

    return {
        "base_confidence": base,
        "credibility_modifier": cred_mod,
        "credibility_adjusted": cred_adjusted,
        "grade_delta": round(grade_delta, 4),
        "final_confidence": final,
        "analytic_confidence": analytic_confidence,
        "adjustments": adjustments_applied,
    }


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

        info_credibility = params.get("info_credibility", "C6")
        grade_adjustments = params.get("grade_adjustments", None)

        confidence = compute_confidence(
            status, source_tier,
            independent_source_count=max(1, independence_check["independent_count"]),
        )

        # Dual-axis confidence (v2) when credibility is provided
        confidence_v2 = compute_confidence_v2(
            status, source_tier,
            info_credibility=info_credibility,
            independent_source_count=max(1, independence_check["independent_count"]),
            grade_adjustments=grade_adjustments,
        )

        return {
            "status": status,
            "confidence": confidence,
            "confidence_v2": confidence_v2,
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


    @skill("corroborate.claim_review", "Export claim as Schema.org ClaimReview")
    def claim_review_export(self, handle):
        """Export a claim assessment as Schema.org ClaimReview JSON-LD.

        Params (from handle.params):
            claim (dict): Claim with statement, source_url, source_tier.
            assessment (dict): Output from corroborate.check.

        Returns:
            dict with claimReview JSON-LD object.
        """
        params = handle.params
        claim = params.get("claim", {})
        assessment = params.get("assessment", {})

        # Map internal status to ClaimReview alternateName
        status_to_rating = {
            STATUS_VERIFIED: "True",
            STATUS_CORROBORATED: "Mostly True",
            STATUS_REPORTED: "Unverified",
            STATUS_CONTESTED: "Disputed",
            STATUS_UNVERIFIED: "Not Rated",
        }

        # Map to numeric rating (1-5 scale per ClaimReview spec)
        status_to_numeric = {
            STATUS_VERIFIED: 5,
            STATUS_CORROBORATED: 4,
            STATUS_REPORTED: 3,
            STATUS_CONTESTED: 2,
            STATUS_UNVERIFIED: 1,
        }

        status = assessment.get("status", STATUS_UNVERIFIED)

        claim_review = {
            "@context": "https://schema.org",
            "@type": "ClaimReview",
            "datePublished": _now_iso(),
            "claimReviewed": claim.get("statement", ""),
            "itemReviewed": {
                "@type": "Claim",
                "text": claim.get("statement", ""),
                "appearance": {
                    "@type": "CreativeWork",
                    "url": claim.get("source_url", ""),
                },
            },
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": status_to_numeric.get(status, 1),
                "bestRating": 5,
                "worstRating": 1,
                "alternateName": status_to_rating.get(status, "Not Rated"),
            },
            "author": {
                "@type": "Organization",
                "name": "Loom Knowledge System",
            },
        }

        # Add confidence metadata as extension
        confidence_v2 = assessment.get("confidence_v2", {})
        if confidence_v2:
            claim_review["reviewRating"]["ratingExplanation"] = (
                f"Source tier: {claim.get('source_tier', 'unknown')}. "
                f"Analytic confidence: {confidence_v2.get('analytic_confidence', 'unknown')}. "
                f"Final score: {confidence_v2.get('final_confidence', 'N/A')}."
            )

        return {"claim_review": claim_review}

    @skill("corroborate.structured_disagreement", "Record structured disagreement")
    def structured_disagreement(self, handle):
        """Record a structured disagreement about a claim (IPCC-inspired).

        Maps evidence_strength x agreement_level to analytic confidence.

        Params (from handle.params):
            claim_id (str): The claim being disagreed about.
            evidence_strength (str): limited|medium|robust
            agreement_level (str): low|medium|high
            nature (str): factual|interpretive|temporal|definitional|methodological
            axis (str): What they disagree about.
            positions (list): List of dicts with position text and evidence_ids.

        Returns:
            dict with disagreement record and derived analytic confidence.
        """
        params = handle.params
        claim_id = params.get("claim_id", "")
        evidence_strength = params.get("evidence_strength", "limited")
        agreement_level = params.get("agreement_level", "low")
        nature = params.get("nature", "factual")
        axis = params.get("axis", "")
        positions = params.get("positions", [])

        if not claim_id:
            return {"error": "claim_id is required"}

        # IPCC confidence matrix: evidence_strength x agreement_level
        # -> analytic_confidence
        confidence_matrix = {
            ("robust", "high"): "very_high",
            ("robust", "medium"): "high",
            ("robust", "low"): "medium",
            ("medium", "high"): "high",
            ("medium", "medium"): "medium",
            ("medium", "low"): "low",
            ("limited", "high"): "medium",
            ("limited", "medium"): "low",
            ("limited", "low"): "low",
        }

        analytic_confidence = confidence_matrix.get(
            (evidence_strength, agreement_level), "low"
        )

        return {
            "claim_id": claim_id,
            "evidence_strength": evidence_strength,
            "agreement_level": agreement_level,
            "nature": nature,
            "axis": axis,
            "positions": positions,
            "analytic_confidence": analytic_confidence,
            "created_at": _now_iso(),
        }


worker = CorroboratorWorker(worker_id="loom-corroborator-1")

if __name__ == "__main__":
    worker.run()
