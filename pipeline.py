"""Loom acquisition pipeline: URL → stored claims with provenance.

Chains the workers: harvest → classify → extract → corroborate → store.
This module can be used standalone or invoked by the knowledge.acquire ritual.
"""

import os
import sys

# Ensure grove SDK is importable
sys.path.insert(0, os.path.join(os.path.expanduser("~"), "grove", "python"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workers.harvester.worker import HarvesterWorker, _compute_hash
from workers.classifier.worker import ClassifierWorker
from workers.extractor.worker import ExtractorWorker
from workers.corroborator.worker import (
    CorroboratorWorker, compute_confidence,
    STATUS_VERIFIED, STATUS_CORROBORATED, STATUS_REPORTED,
)
from workers.kb.worker import LoomKBWorker


def _print_result(result):
    """Pretty-print pipeline result."""
    if result.get("errors"):
        print(f"ERRORS: {result['errors']}")
        return

    s = result.get("summary", {})
    print(f"\nURL: {s.get('url', '?')}")
    print(f"Tier: {s.get('tier', '?')}")
    print(f"Claims stored: {s.get('claims_stored', 0)} / {s.get('claims_total', 0)}")
    print()

    for i, c in enumerate(result.get("claims", []), 1):
        status = c.get("status", "?")
        conf = c.get("confidence", 0)
        ctype = c.get("claim_type", "?")
        print(f"  [{i}] ({status}, {conf:.2f}, {ctype}) {c['statement'][:120]}")

    print()


class _Handle:
    """Minimal handle for direct worker invocation."""
    def __init__(self, params):
        self.params = params


def acquire(url: str, db_path: str = "", max_claims: int = 50) -> dict:
    """Run the full acquisition pipeline for a URL.

    Args:
        url: The URL to harvest and process.
        db_path: Path to SQLite database (optional, uses default).
        max_claims: Maximum claims to extract per source.

    Returns:
        dict with harvest, classification, claims (list of stored claims),
        and summary statistics.
    """
    harvester = HarvesterWorker(worker_id="pipeline-harvester")
    classifier = ClassifierWorker(worker_id="pipeline-classifier")
    extractor = ExtractorWorker(worker_id="pipeline-extractor")
    corroborator = CorroboratorWorker(worker_id="pipeline-corroborator")
    kb = LoomKBWorker(worker_id="pipeline-kb")

    result = {"url": url, "errors": []}

    # Step 1: Harvest
    harvest = harvester.harvest_web(_Handle({"url": url}))
    if "error" in harvest:
        result["errors"].append(f"harvest: {harvest['error']}")
        return result
    result["harvest"] = {
        "content_length": len(harvest.get("content", "")),
        "content_hash": harvest.get("content_hash", ""),
    }

    # Step 2: Classify source
    classification = classifier.classify_source_tier(
        _Handle({"url": url, "content": harvest["content"]})
    )
    result["classification"] = {
        "tier": classification["tier"],
        "tier_name": classification["tier_name"],
        "domain_verified": classification["domain_verified"],
    }

    # Step 3: Extract claims
    extraction = extractor.extract_claims(_Handle({
        "content": harvest["content"],
        "source_tier": classification["tier"],
        "max_claims": max_claims,
    }))
    result["extraction"] = {
        "total_sentences": extraction.get("total_sentences", 0),
        "claims_extracted": extraction.get("claims_extracted", 0),
    }

    # Step 4: Classify + corroborate + store each claim
    stored_claims = []
    for claim in extraction.get("claims", []):
        # Classify claim type
        claim_type = classifier.classify_claim_type(
            _Handle({"statement": claim["statement"]})
        )

        # Classify temporal validity
        temporal = classifier.classify_temporal_validity(
            _Handle({
                "statement": claim["statement"],
                "category": claim_type.get("claim_type", "factual"),
            })
        )

        # Corroborate against KB
        corr = corroborator.corroborate_check(_Handle({
            "statement": claim["statement"],
            "source_tier": classification["tier"],
        }))

        # Extract v2 confidence fields
        v2 = corr.get("confidence_v2", {})

        # Store in KB
        store_params = {
            "statement": claim["statement"],
            "category": claim.get("category", "factual"),
            "confidence": corr["confidence"],
            "status": corr["status"],
            "source_tier": classification["tier"],
            "claim_type": claim_type.get("claim_type", "empirical_fact"),
            "info_credibility": v2.get("credibility_modifier_label", "C6"),
            "analytic_confidence": v2.get("analytic_confidence", ""),
            "valid_from": temporal.get("valid_from"),
            "valid_until": temporal.get("valid_until"),
            "ttl_category": temporal.get("ttl_category"),
            "evidence": [{
                "source_url": url,
                "source_tier": classification["tier"],
                "content_hash": harvest["content_hash"],
                "excerpt": claim.get("excerpt", ""),
                "relationship": "supports",
                "inference": "verbatim",
                "directness": "direct",
            }],
        }
        if db_path:
            store_params["db_path"] = db_path

        store = kb.kb_store_claim(_Handle(store_params))

        stored_claims.append({
            "claim_id": store.get("claim_id"),
            "statement": claim["statement"],
            "category": claim.get("category"),
            "claim_type": claim_type.get("claim_type"),
            "status": corr["status"],
            "confidence": corr["confidence"],
            "stored": store.get("stored", False),
        })

    result["claims"] = stored_claims
    result["summary"] = {
        "url": url,
        "tier": classification["tier"],
        "claims_stored": sum(1 for c in stored_claims if c["stored"]),
        "claims_total": len(stored_claims),
    }

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Loom acquisition pipeline")
    parser.add_argument("url", help="URL to harvest and process")
    parser.add_argument("--db", default="", help="SQLite database path")
    parser.add_argument("--max-claims", type=int, default=20,
                        help="Max claims to extract (default: 20)")
    args = parser.parse_args()

    result = acquire(args.url, db_path=args.db, max_claims=args.max_claims)
    _print_result(result)
