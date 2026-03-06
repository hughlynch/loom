"""AdjudicatorWorker — resolves contradictions using the evidence hierarchy.

Responsible for taking corroboration results that contain contradictions
and producing resolutions. Higher-tier sources prevail over lower-tier
sources. Ambiguous cases are escalated for human review. Community
challenges are triaged automatically when the counter-source is a lower
tier than the challenged claim's source.
"""

import os
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Resolution actions
ACTION_ACCEPT_A = "accept_a"      # Claim A prevails
ACTION_ACCEPT_B = "accept_b"      # Claim B prevails
ACTION_CONTESTED = "contested"    # Both remain, marked contested
ACTION_ESCALATE = "escalate"      # Ambiguous, needs human review
ACTION_REJECT = "reject"          # Claim rejected (lower tier, contradicted)
ACTION_MERGE = "merge"            # Claims can be reconciled

# Anti-patterns from the spec
ANTI_PATTERN_MAJORITY_RULE = "majority_rule"  # Many low-tier sources != truth
ANTI_PATTERN_RECENCY_BIAS = "recency_bias"  # Newer != more correct
ANTI_PATTERN_SKIP_ESCALATION = "skip_escalation"  # Resolving ambiguity without human

# Tier rank for comparison (lower number = higher authority)
TIER_RANK = {
    "T1": 1, "T2": 2, "T3": 3, "T4": 4,
    "T5": 5, "T6": 6, "T7": 7,
}


def _compare_tiers(tier_a: str, tier_b: str) -> int:
    """Compare two tiers. Returns negative if A is higher authority,
    positive if B is, zero if equal."""
    return TIER_RANK.get(tier_a, 5) - TIER_RANK.get(tier_b, 5)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdjudicatorWorker(Worker):
    worker_type = "adjudicator"

    @skill("adjudicate.resolve", "Resolve contradictions from corroboration")
    def adjudicate_resolve(self, handle):
        """Resolve contradictions found during corroboration.

        Applies evidence hierarchy rules:
        - Higher tier source prevails over lower tier
        - Same tier with more independent corroboration prevails
        - Same tier, same corroboration -> escalate to human review
        - Claims within 1 tier of each other -> mark contested, escalate

        Params (from handle.params):
            contradictions (list): List of contradiction dicts from
                corroborate.find_contradictions, each with claim_a,
                claim_b, and nature.

        Returns:
            dict with integrated (accepted claims), contested (unresolved),
            rejected (overruled claims).
        """
        params = handle.params
        contradictions = params.get("contradictions", [])

        integrated = []
        contested = []
        rejected = []

        for contradiction in contradictions:
            claim_a = contradiction.get("claim_a", {})
            claim_b = contradiction.get("claim_b", {})
            nature = contradiction.get("nature", "unknown")

            tier_a = claim_a.get("source_tier", "T5")
            tier_b = claim_b.get("source_tier", "T5")

            tier_diff = _compare_tiers(tier_a, tier_b)

            if abs(tier_diff) >= 2:
                # Clear tier advantage: higher tier wins
                if tier_diff < 0:
                    integrated.append({
                        "claim": claim_a,
                        "action": ACTION_ACCEPT_A,
                        "reason": f"Source tier {tier_a} prevails over {tier_b}",
                    })
                    rejected.append({
                        "claim": claim_b,
                        "action": ACTION_REJECT,
                        "reason": f"Contradicted by higher-tier source ({tier_a})",
                    })
                else:
                    integrated.append({
                        "claim": claim_b,
                        "action": ACTION_ACCEPT_B,
                        "reason": f"Source tier {tier_b} prevails over {tier_a}",
                    })
                    rejected.append({
                        "claim": claim_a,
                        "action": ACTION_REJECT,
                        "reason": f"Contradicted by higher-tier source ({tier_b})",
                    })
            else:
                # Close tiers or same tier: mark contested, escalate
                contested.append({
                    "claim_a": claim_a,
                    "claim_b": claim_b,
                    "nature": nature,
                    "action": ACTION_CONTESTED,
                    "reason": f"Tiers {tier_a} vs {tier_b} too close to auto-resolve",
                    "needs_escalation": True,
                })

        return {
            "integrated": integrated,
            "contested": contested,
            "rejected": rejected,
            "resolved_at": _now_iso(),
        }

    @skill("adjudicate.escalate", "Escalate ambiguous cases for human review")
    def adjudicate_escalate(self, handle):
        """Escalate ambiguous contradictions for human review.

        Creates escalation records for claims that cannot be resolved
        automatically via the evidence hierarchy.

        Params (from handle.params):
            contested (list): Contested claim pairs from adjudicate.resolve.
            priority (str, optional): Escalation priority (high, medium, low).

        Returns:
            dict with escalated_claims and reason.
        """
        params = handle.params
        contested = params.get("contested", [])
        priority = params.get("priority", "medium")

        escalated_claims = []
        for item in contested:
            escalated_claims.append({
                "claim_a": item.get("claim_a"),
                "claim_b": item.get("claim_b"),
                "nature": item.get("nature", "unknown"),
                "priority": priority,
                "escalated_at": _now_iso(),
            })

        reason = (
            f"Escalated {len(escalated_claims)} contested claim pairs "
            f"that could not be resolved by evidence hierarchy alone"
        )

        return {
            "escalated_claims": escalated_claims,
            "reason": reason,
        }

    @skill("adjudicate.triage_challenge", "Triage a community challenge")
    def triage_challenge(self, handle):
        """Triage a community challenge to an existing claim.

        Auto-closes if the counter-source is a lower tier than the
        challenged claim's source. Otherwise, routes through full
        adjudication.

        Params (from handle.params):
            challenged_claim (dict): The claim being challenged, with
                source_tier field.
            counter_source (dict): The challenging source, with
                source_tier and statement fields.

        Returns:
            dict with action (auto_close, adjudicate, escalate) and reason.
        """
        params = handle.params
        challenged_claim = params.get("challenged_claim", {})
        counter_source = params.get("counter_source", {})

        if not challenged_claim or not counter_source:
            return {"error": "challenged_claim and counter_source are required"}

        claim_tier = challenged_claim.get("source_tier", "T5")
        counter_tier = counter_source.get("source_tier", "T7")

        tier_diff = _compare_tiers(claim_tier, counter_tier)

        if tier_diff < 0:
            # Original claim is higher tier: auto-close challenge
            action = "auto_close"
            reason = (
                f"Challenge dismissed: existing claim sourced at {claim_tier} "
                f"outranks counter-source at {counter_tier}"
            )
        elif tier_diff == 0:
            # Same tier: needs full adjudication
            action = "adjudicate"
            reason = (
                f"Same-tier challenge ({claim_tier} vs {counter_tier}): "
                f"requires full corroboration and adjudication"
            )
        else:
            # Counter-source is higher tier: escalate, claim may be overturned
            action = "escalate"
            reason = (
                f"Higher-tier challenge: counter-source ({counter_tier}) "
                f"outranks existing claim ({claim_tier})"
            )

        return {
            "action": action,
            "reason": reason,
            "claim_tier": claim_tier,
            "counter_tier": counter_tier,
            "triaged_at": _now_iso(),
        }


worker = AdjudicatorWorker(worker_id="loom-adjudicator-1")

if __name__ == "__main__":
    worker.run()
