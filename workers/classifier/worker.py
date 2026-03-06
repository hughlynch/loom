"""ClassifierWorker — categorizes claims and sources.

Responsible for assigning evidence tiers (T1-T7) to sources, classifying
claims by topic, and determining temporal validity windows. The tier system
follows a strict evidence hierarchy where higher tiers (T1) carry more
weight in adjudication.
"""

import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from grove.uwp import Worker, skill

# Evidence hierarchy tiers (T1 = highest authority)
TIER_T1 = {
    "tier": "T1",
    "name": "Official Primary Source",
    "description": "Government records, court filings, official statistics, "
                   "peer-reviewed publications. Authoritative and verifiable.",
    "domains": [".gov", ".mil", ".judiciary"],
    "confidence_floor": 0.95,
}

TIER_T2 = {
    "tier": "T2",
    "name": "Institutional Record",
    "description": "Academic institutions, established research bodies, "
                   "international organizations. High credibility with "
                   "editorial oversight.",
    "domains": [".edu", ".ac."],
    "confidence_floor": 0.85,
}

TIER_T3 = {
    "tier": "T3",
    "name": "Quality Journalism",
    "description": "Major news organizations with editorial standards, "
                   "fact-checking processes, and correction policies.",
    "domains": [],
    "confidence_floor": 0.70,
}

TIER_T4 = {
    "tier": "T4",
    "name": "Expert Analysis",
    "description": "Domain expert commentary, professional publications, "
                   "industry reports from credentialed authors.",
    "domains": [],
    "confidence_floor": 0.60,
}

TIER_T5 = {
    "tier": "T5",
    "name": "General Web",
    "description": "General web content, blogs, wikis. Variable quality, "
                   "requires corroboration.",
    "domains": [],
    "confidence_floor": 0.40,
}

TIER_T6 = {
    "tier": "T6",
    "name": "Social Media",
    "description": "Social media posts, forums, comments. Low baseline "
                   "reliability, useful for leads not conclusions.",
    "domains": [],
    "confidence_floor": 0.20,
}

TIER_T7 = {
    "tier": "T7",
    "name": "Anonymous / Unverifiable",
    "description": "Anonymous sources, unattributed claims, content without "
                   "provenance. Lowest tier, requires extensive corroboration.",
    "domains": [],
    "confidence_floor": 0.05,
}

TIERS = {
    "T1": TIER_T1,
    "T2": TIER_T2,
    "T3": TIER_T3,
    "T4": TIER_T4,
    "T5": TIER_T5,
    "T6": TIER_T6,
    "T7": TIER_T7,
}

# Anti-patterns from the spec
ANTI_PATTERN_TIER_INFLATION = "tier_inflation"  # Assigning higher tier than warranted
ANTI_PATTERN_DOMAIN_ONLY = "domain_only_classification"  # Relying solely on domain
ANTI_PATTERN_NO_TEMPORAL = "no_temporal_bounds"  # Omitting validity window

# Temporal TTL categories
TTL_PERMANENT = "permanent"       # Laws, historical facts
TTL_LONG_TERM = "long_term"       # Multi-year validity (policies, standards)
TTL_MEDIUM_TERM = "medium_term"   # Months to a year (statistics, reports)
TTL_SHORT_TERM = "short_term"     # Days to weeks (news, events)
TTL_EPHEMERAL = "ephemeral"       # Hours (weather, live data)


def _check_domain(url: str) -> dict:
    """Check if the URL's domain matches known T1/T2 domain patterns.

    Returns:
        dict with {is_gov: bool, is_edu: bool, domain: str, tld: str}
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    is_gov = any(domain.endswith(d) for d in [".gov", ".mil"])
    is_edu = any(d in domain for d in [".edu", ".ac."])

    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""

    return {
        "is_gov": is_gov,
        "is_edu": is_edu,
        "domain": domain,
        "tld": tld,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClassifierWorker(Worker):
    worker_type = "classifier"

    @skill("classify.source_tier", "Classify a source into T1-T7 evidence tier")
    def classify_source_tier(self, handle):
        """Classify a source into the T1-T7 evidence hierarchy.

        Uses domain verification for T1/T2 (checking .gov/.edu domains),
        then applies rubric scoring for content quality indicators.

        Params (from handle.params):
            url (str): Source URL to classify.
            content (str, optional): Source content for quality analysis.
            metadata (dict, optional): Source metadata (author, publication).

        Returns:
            dict with tier, tier_name, confidence, domain_verified,
            rubric_scores.
        """
        params = handle.params
        url = params.get("url", "")
        content = params.get("content", "")

        if not url:
            return {"error": "url is required"}

        # Domain verification for T1/T2
        domain_check = _check_domain(url)

        # Deterministic domain-based classification
        if domain_check["is_gov"]:
            tier = "T1"
            domain_verified = True
        elif domain_check["is_edu"]:
            tier = "T2"
            domain_verified = True
        else:
            # Stub: in production, LLM + heuristics analyze content quality,
            # editorial standards, author credentials, etc.
            tier = "T5"
            domain_verified = False

        tier_def = TIERS[tier]

        # Rubric scores (stub: would be computed from content analysis)
        rubric_scores = {
            "editorial_oversight": 0.5,
            "author_credentials": 0.5,
            "citation_quality": 0.5,
            "correction_policy": 0.5,
            "factual_density": 0.5,
        }

        return {
            "tier": tier,
            "tier_name": tier_def["name"],
            "confidence": tier_def["confidence_floor"],
            "domain_verified": domain_verified,
            "domain_check": domain_check,
            "rubric_scores": rubric_scores,
        }

    @skill("classify.topic", "Classify claims by topic")
    def classify_topic(self, handle):
        """Classify claims into topic categories and subtopics.

        Params (from handle.params):
            claims (list): List of claim statements to classify.
            content (str, optional): Source content for context.

        Returns:
            dict with topic, subtopics.
        """
        params = handle.params
        claims = params.get("claims", [])

        if not claims:
            return {"error": "claims list is required"}

        # Stub: in production, LLM classifies into topic taxonomy.
        return {
            "topic": "general",
            "subtopics": ["unclassified"],
            "claim_count": len(claims),
            "classified_at": _now_iso(),
        }

    @skill("classify.temporal_validity", "Determine temporal validity window")
    def classify_temporal_validity(self, handle):
        """Determine the temporal validity window for a claim.

        Analyzes claim content to determine when the claim became valid,
        when it expires (if ever), and what TTL category it falls into.

        Params (from handle.params):
            statement (str): The claim statement.
            category (str, optional): Claim category (factual, statistical, etc.).
            source_date (str, optional): Date of the source.

        Returns:
            dict with valid_from, valid_until, ttl_category.
        """
        params = handle.params
        statement = params.get("statement", "")
        category = params.get("category", "factual")

        if not statement:
            return {"error": "statement is required"}

        # Stub: in production, LLM analyzes the claim to determine
        # temporal bounds. Category provides hints:
        # - statistical claims are typically medium_term
        # - procedural claims are long_term
        # - factual/historical claims may be permanent
        ttl_map = {
            "statistical": TTL_MEDIUM_TERM,
            "procedural": TTL_LONG_TERM,
            "factual": TTL_PERMANENT,
            "definitional": TTL_PERMANENT,
            "opinion": TTL_SHORT_TERM,
            "causal": TTL_LONG_TERM,
        }

        ttl_category = ttl_map.get(category, TTL_MEDIUM_TERM)

        return {
            "valid_from": params.get("source_date", _now_iso()),
            "valid_until": None if ttl_category == TTL_PERMANENT else _now_iso(),
            "ttl_category": ttl_category,
        }


worker = ClassifierWorker(worker_id="loom-classifier-1")

if __name__ == "__main__":
    worker.run()
