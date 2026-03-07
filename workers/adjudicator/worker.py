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


    @skill("adjudicate.ach", "Analysis of Competing Hypotheses matrix")
    def ach_matrix(self, handle):
        """Build an ACH (Analysis of Competing Hypotheses) matrix.

        Evaluates each piece of evidence against each hypothesis,
        scoring consistency. The hypothesis most consistent with all
        evidence (and least inconsistent) is ranked highest.

        Params:
            hypotheses (list): List of hypothesis strings.
            evidence (list): List of evidence dicts with statement and
                optional weight (0-1, default 1.0).

        Returns:
            dict with matrix (hypothesis x evidence scores),
            rankings (hypotheses sorted by score), and the
            best hypothesis.
        """
        params = handle.params
        hypotheses = params.get("hypotheses", [])
        evidence = params.get("evidence", [])

        if len(hypotheses) < 2:
            return {"error": "Need at least 2 hypotheses"}
        if not evidence:
            return {"error": "Need at least 1 piece of evidence"}

        # Build consistency matrix
        # Each cell: "consistent" (C+), "inconsistent" (I-),
        # "neutral" (N), "very_inconsistent" (II--)
        matrix = {}
        scores = {}

        for h_idx, hypothesis in enumerate(hypotheses):
            h_key = f"H{h_idx + 1}"
            matrix[h_key] = {"hypothesis": hypothesis, "evidence_scores": []}
            scores[h_key] = 0.0

            for e_idx, ev in enumerate(evidence):
                consistency = ev.get("consistency", {}).get(h_key, "neutral")
                weight = ev.get("weight", 1.0)

                # Score: C+ = +1, N = 0, I- = -1, II-- = -2
                score_map = {
                    "consistent": 1.0,
                    "neutral": 0.0,
                    "inconsistent": -1.0,
                    "very_inconsistent": -2.0,
                }
                cell_score = score_map.get(consistency, 0.0) * weight

                matrix[h_key]["evidence_scores"].append({
                    "evidence": ev.get("statement", f"E{e_idx + 1}"),
                    "consistency": consistency,
                    "weighted_score": round(cell_score, 4),
                })
                scores[h_key] += cell_score

        # Rank hypotheses by score (higher = more consistent)
        rankings = sorted(
            [{"hypothesis_id": k, "hypothesis": matrix[k]["hypothesis"],
              "total_score": round(scores[k], 4)}
             for k in scores],
            key=lambda x: x["total_score"],
            reverse=True,
        )

        return {
            "matrix": matrix,
            "rankings": rankings,
            "best_hypothesis": rankings[0] if rankings else None,
            "analyzed_at": _now_iso(),
        }

    @skill("adjudicate.devils_advocate", "Challenge a claim with counter-arguments")
    def devils_advocate(self, handle):
        """Generate structured counter-arguments for a claim.

        Deterministic adversarial review based on claim properties.
        Identifies weaknesses in evidence chain, potential biases,
        and alternative explanations.

        Params:
            claim (dict): The claim with statement, source_tier,
                status, confidence, evidence (list).

        Returns:
            dict with challenges (list of structured objections),
            vulnerability_score (0-1), recommendation.
        """
        params = handle.params
        claim = params.get("claim", {})
        statement = claim.get("statement", "")
        source_tier = claim.get("source_tier", "T5")
        status = claim.get("status", "unverified")
        confidence = claim.get("confidence", 0.0)
        evidence = claim.get("evidence", [])

        if not statement:
            return {"error": "claim.statement is required"}

        challenges = []
        vulnerability = 0.0

        # Challenge 1: Source authority
        tier_rank = TIER_RANK.get(source_tier, 5)
        if tier_rank >= 4:
            challenges.append({
                "type": "source_authority",
                "severity": "high" if tier_rank >= 6 else "medium",
                "objection": f"Source tier {source_tier} has limited authority. "
                             f"Has this been verified by higher-tier sources?",
            })
            vulnerability += 0.2

        # Challenge 2: Single source
        if len(evidence) <= 1:
            challenges.append({
                "type": "single_source",
                "severity": "high",
                "objection": "Claim relies on a single source. "
                             "Independent corroboration is missing.",
            })
            vulnerability += 0.25

        # Challenge 3: No contradiction check
        if status in ("reported", "unverified"):
            challenges.append({
                "type": "unverified",
                "severity": "medium",
                "objection": "Claim has not been verified against "
                             "contradicting evidence in the knowledge base.",
            })
            vulnerability += 0.15

        # Challenge 4: High confidence without strong evidence
        if confidence > 0.80 and tier_rank >= 4:
            challenges.append({
                "type": "overconfidence",
                "severity": "high",
                "objection": f"Confidence {confidence:.2f} seems high for "
                             f"a {source_tier} source. Check for anchoring bias.",
            })
            vulnerability += 0.2

        # Challenge 5: Evidence independence
        if len(evidence) >= 2:
            urls = [e.get("source_url", "") for e in evidence]
            domains = set()
            for u in urls:
                parts = u.split("/")
                if len(parts) >= 3:
                    domains.add(parts[2])
            if len(domains) < len(evidence):
                challenges.append({
                    "type": "independence",
                    "severity": "medium",
                    "objection": "Multiple evidence items share a domain. "
                                 "Check for circular corroboration.",
                })
                vulnerability += 0.15

        vulnerability = min(1.0, vulnerability)

        if vulnerability >= 0.6:
            recommendation = "reject_or_downgrade"
        elif vulnerability >= 0.3:
            recommendation = "additional_verification_needed"
        else:
            recommendation = "claim_appears_robust"

        return {
            "claim_statement": statement,
            "challenges": challenges,
            "vulnerability_score": round(vulnerability, 4),
            "recommendation": recommendation,
            "analyzed_at": _now_iso(),
        }

    @skill("adjudicate.dung_semantics", "Compute grounded/preferred extensions")
    def dung_semantics(self, handle):
        """Compute Dung argumentation framework semantics.

        Given a set of arguments and attack relations, computes:
        - Grounded extension (most skeptical: smallest conflict-free set
          that defends itself)
        - Preferred extensions (maximally admissible sets)

        Params:
            arguments (list): List of argument IDs (strings).
            attacks (list): List of [attacker, target] pairs.

        Returns:
            dict with grounded extension and preferred extensions.
        """
        params = handle.params
        arguments = set(params.get("arguments", []))
        attacks = params.get("attacks", [])

        if not arguments:
            return {"error": "arguments is required"}

        # Build attack graph
        attackers_of = {a: set() for a in arguments}
        targets_of = {a: set() for a in arguments}
        for attacker, target in attacks:
            if attacker in arguments and target in arguments:
                attackers_of[target].add(attacker)
                targets_of[attacker].add(target)

        # Grounded semantics: iterative fixpoint
        # Start with unattacked arguments, then add args defended by current set
        def is_defended(arg, current_set):
            """An arg is defended if every attacker is attacked by current_set."""
            for attacker in attackers_of[arg]:
                if not any(
                    defender in current_set
                    for defender in attackers_of[attacker]
                ):
                    return False
            return True

        grounded = set()
        changed = True
        while changed:
            changed = False
            for arg in arguments:
                if arg not in grounded and is_defended(arg, grounded):
                    grounded.add(arg)
                    changed = True

        # Preferred semantics: maximal admissible sets
        # An admissible set is conflict-free and defends all its members
        def is_conflict_free(s):
            for a in s:
                for b in s:
                    if b in targets_of.get(a, set()):
                        return False
            return True

        def is_admissible(s):
            if not is_conflict_free(s):
                return False
            for arg in s:
                if not is_defended(arg, s):
                    return False
            return True

        # Find preferred extensions via powerset pruning
        # For small argument sets (< 15), enumerate subsets
        arg_list = sorted(arguments)
        if len(arg_list) > 15:
            # For large sets, just return grounded as approximation
            preferred = [sorted(grounded)]
        else:
            admissible_sets = []
            for mask in range(1 << len(arg_list)):
                subset = {arg_list[i] for i in range(len(arg_list))
                          if mask & (1 << i)}
                if is_admissible(subset):
                    admissible_sets.append(subset)

            # Preferred = maximal admissible (no proper superset is admissible)
            preferred = []
            for s in admissible_sets:
                if not any(s < other for other in admissible_sets):
                    preferred.append(sorted(s))

        return {
            "grounded_extension": sorted(grounded),
            "preferred_extensions": preferred,
            "arguments_count": len(arguments),
            "attacks_count": len(attacks),
            "computed_at": _now_iso(),
        }


worker = AdjudicatorWorker(worker_id="loom-adjudicator-1")

if __name__ == "__main__":
    worker.run()
