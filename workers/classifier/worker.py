"""ClassifierWorker — categorizes claims and sources.

Responsible for assigning evidence tiers (T1-T7) to sources, classifying
claims by topic, and determining temporal validity windows. The tier system
follows a strict evidence hierarchy where higher tiers (T1) carry more
weight in adjudication.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
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

ANTI_PATTERN_TIER_INFLATION = "tier_inflation"  # Assigning higher tier than warranted
ANTI_PATTERN_DOMAIN_ONLY = "domain_only_classification"  # Relying solely on domain
ANTI_PATTERN_NO_TEMPORAL = "no_temporal_bounds"  # Omitting validity window

# Known T3 news domains (quality journalism with editorial standards)
T3_NEWS_DOMAINS = {
    "apnews.com", "reuters.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "washingtonpost.com", "wsj.com",
    "theguardian.com", "economist.com", "ft.com",
    "npr.org", "pbs.org", "propublica.org",
}

# Known T4 expert analysis domains
T4_EXPERT_DOMAINS = {
    "nature.com", "science.org", "sciencedirect.com",
    "springer.com", "wiley.com", "jstor.org",
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "brookings.edu", "rand.org", "pewresearch.org",
}

# Known T6 social/UGC domains
T6_SOCIAL_DOMAINS = {
    "reddit.com", "twitter.com", "x.com", "facebook.com",
    "tiktok.com", "instagram.com", "threads.net",
    "medium.com", "substack.com",
}

# Temporal TTL categories
TTL_PERMANENT = "permanent"       # Laws, historical facts
TTL_LONG_TERM = "long_term"       # Multi-year validity (policies, standards)
TTL_MEDIUM_TERM = "medium_term"   # Months to a year (statistics, reports)
TTL_SHORT_TERM = "short_term"     # Days to weeks (news, events)
TTL_EPHEMERAL = "ephemeral"       # Hours (weather, live data)

# Claim types (from architectural-recommendations.md §7)
CLAIM_TYPES = {
    "empirical_fact": {
        "description": "Verifiable factual claim",
        "assessment": "evidence_hierarchy",
        "ttl_default": TTL_PERMANENT,
        "example": "Council voted 4-3",
    },
    "statistical": {
        "description": "Quantitative claim with methodology",
        "assessment": "primary_data_methodology",
        "ttl_default": TTL_MEDIUM_TERM,
        "example": "Crime dropped 12%",
    },
    "causal": {
        "description": "Cause-effect relationship claim",
        "assessment": "grade_factors",
        "ttl_default": TTL_LONG_TERM,
        "example": "Rezoning caused traffic increase",
    },
    "prediction": {
        "description": "Forward-looking claim (not assessable for truth)",
        "assessment": "track_record",
        "ttl_default": TTL_SHORT_TERM,
        "example": "Budget will increase next year",
    },
    "opinion": {
        "description": "Value judgment (not assessable; attribute and present)",
        "assessment": "attribution_only",
        "ttl_default": TTL_SHORT_TERM,
        "example": "The policy is good",
    },
    "attribution": {
        "description": "Claim that someone said/did something",
        "assessment": "source_verification",
        "ttl_default": TTL_PERMANENT,
        "example": "Mayor said X at Tuesday meeting",
    },
    "temporal": {
        "description": "Time-bound claim with validity window",
        "assessment": "freshness_check",
        "ttl_default": TTL_MEDIUM_TERM,
        "example": "Population is 50,000",
    },
}

# Heuristic patterns for claim-type classification (no LLM needed)
import re as _re

_STATISTICAL_PATTERNS = [
    _re.compile(r'\b\d+(\.\d+)?%', _re.IGNORECASE),
    _re.compile(r'\b(increased|decreased|grew|dropped|rose|fell)\s+by\b', _re.IGNORECASE),
    _re.compile(r'\b(average|median|mean|total|rate|ratio)\b', _re.IGNORECASE),
    _re.compile(r'\b(million|billion|trillion)\b', _re.IGNORECASE),
]

_CAUSAL_PATTERNS = [
    _re.compile(r'\b(caused|because|due to|result of|led to|resulted in)\b', _re.IGNORECASE),
    _re.compile(r'\b(therefore|consequently|thus|hence)\b', _re.IGNORECASE),
]

_PREDICTION_PATTERNS = [
    _re.compile(r'\b(will|would|expected to|projected|forecast|likely to)\b', _re.IGNORECASE),
    _re.compile(r'\b(by 20\d\d|next year|in the future)\b', _re.IGNORECASE),
]

_OPINION_PATTERNS = [
    _re.compile(r'\b(should|ought|best|worst|good|bad|better|worse)\b', _re.IGNORECASE),
    _re.compile(r'\b(I think|I believe|in my opinion|arguably)\b', _re.IGNORECASE),
]

_ATTRIBUTION_PATTERNS = [
    _re.compile(r'\b(said|stated|announced|declared|claimed|according to)\b', _re.IGNORECASE),
    _re.compile(r'\b(tweeted|posted|wrote|testified)\b', _re.IGNORECASE),
]


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
        domain = domain_check["domain"]
        # Strip www. prefix for matching
        bare_domain = domain.lstrip("www.")

        if domain_check["is_gov"]:
            tier = "T1"
            domain_verified = True
        elif domain_check["is_edu"]:
            tier = "T2"
            domain_verified = True
        elif bare_domain in T3_NEWS_DOMAINS:
            tier = "T3"
            domain_verified = True
        elif bare_domain in T4_EXPERT_DOMAINS:
            tier = "T4"
            domain_verified = True
        elif bare_domain in T6_SOCIAL_DOMAINS:
            tier = "T6"
            domain_verified = True
        else:
            # Default: general web content
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

    @skill("classify.claim_type", "Classify a claim by type")
    def classify_claim_type(self, handle):
        """Classify a claim into one of the defined claim types.

        Uses heuristic pattern matching on the statement text.
        In production, this would be augmented with LLM classification.

        Params (from handle.params):
            statement (str): The claim statement.

        Returns:
            dict with claim_type, assessment_method, ttl_default,
            confidence, signals.
        """
        params = handle.params
        statement = params.get("statement", "")

        if not statement:
            return {"error": "statement is required"}

        # Score each type by pattern matches
        scores = {}
        signals = {}

        for pattern_list, ctype in [
            (_STATISTICAL_PATTERNS, "statistical"),
            (_CAUSAL_PATTERNS, "causal"),
            (_PREDICTION_PATTERNS, "prediction"),
            (_OPINION_PATTERNS, "opinion"),
            (_ATTRIBUTION_PATTERNS, "attribution"),
        ]:
            matches = []
            for p in pattern_list:
                m = p.search(statement)
                if m:
                    matches.append(m.group())
            scores[ctype] = len(matches)
            if matches:
                signals[ctype] = matches

        # Pick highest-scoring type, default to empirical_fact
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                claim_type = best
            else:
                claim_type = "empirical_fact"
        else:
            claim_type = "empirical_fact"

        # Check for temporal markers — override if present
        # A claim like "population is currently 340 million" is temporal
        # even though it contains statistical patterns
        temporal_markers = _re.findall(
            r'\b(currently|as of|now|today|this year|at present)\b',
            statement, _re.IGNORECASE,
        )
        if temporal_markers and claim_type in ("empirical_fact", "statistical"):
            claim_type = "temporal"
            signals["temporal"] = temporal_markers

        type_def = CLAIM_TYPES[claim_type]

        return {
            "claim_type": claim_type,
            "description": type_def["description"],
            "assessment_method": type_def["assessment"],
            "ttl_default": type_def["ttl_default"],
            "signals": signals,
            "classified_at": _now_iso(),
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

        # Compute actual expiry based on TTL category
        ttl_durations = {
            TTL_PERMANENT: None,
            TTL_LONG_TERM: timedelta(days=730),    # 2 years
            TTL_MEDIUM_TERM: timedelta(days=180),  # 6 months
            TTL_SHORT_TERM: timedelta(days=14),    # 2 weeks
            TTL_EPHEMERAL: timedelta(hours=6),
        }

        source_date_str = params.get("source_date", "")
        if source_date_str:
            try:
                valid_from = datetime.fromisoformat(source_date_str)
            except ValueError:
                valid_from = datetime.now(timezone.utc)
        else:
            valid_from = datetime.now(timezone.utc)

        duration = ttl_durations.get(ttl_category)
        valid_until = (valid_from + duration).isoformat() if duration else None

        return {
            "valid_from": valid_from.isoformat(),
            "valid_until": valid_until,
            "ttl_category": ttl_category,
            "ttl_days": duration.days if duration else None,
        }


worker = ClassifierWorker(worker_id="loom-classifier-1")

if __name__ == "__main__":
    worker.run()
