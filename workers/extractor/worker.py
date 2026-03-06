"""ExtractorWorker — pulls structured claims from raw content.

Responsible for decomposing unstructured text into atomic claims, named
entities, and relationships. Uses heuristic sentence segmentation and
pattern matching. LLM integration available when LOOM_MODEL is set.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Anti-patterns from the spec
ANTI_PATTERN_COMPOUND_CLAIM = "compound_claim"  # Bundling multiple assertions
ANTI_PATTERN_MISSING_EXCERPT = "missing_excerpt"  # Claim without source excerpt
ANTI_PATTERN_UNBOUNDED_TEMPORAL = "unbounded_temporal"  # No validity window

# Claim categories
CATEGORY_FACTUAL = "factual"
CATEGORY_STATISTICAL = "statistical"
CATEGORY_OPINION = "opinion"
CATEGORY_PROCEDURAL = "procedural"
CATEGORY_DEFINITIONAL = "definitional"
CATEGORY_CAUSAL = "causal"

# Entity types
ENTITY_PERSON = "person"
ENTITY_ORGANIZATION = "organization"
ENTITY_LOCATION = "location"
ENTITY_DATE = "date"
ENTITY_NUMBER = "number"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Sentence segmentation ---

_SENTENCE_END = re.compile(
    r'(?<=[.!?])\s+(?=[A-Z])'  # Split on sentence-ending punct followed by capital
)

_ABBREVS = {"Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Jr.", "Sr.",
            "Inc.", "Corp.", "Ltd.", "U.S.", "U.K.", "E.U.",
            "vs.", "etc.", "approx.", "est.", "Jan.", "Feb.",
            "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.",
            "Oct.", "Nov.", "Dec."}


def _segment_sentences(text: str) -> list[str]:
    """Split text into sentences using heuristic rules."""
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []

    # Split on sentence boundaries
    raw = _SENTENCE_END.split(text)

    # Rejoin abbreviation splits
    sentences = []
    buffer = ""
    for chunk in raw:
        if buffer:
            chunk = buffer + " " + chunk
            buffer = ""
        # Check if chunk ends with a known abbreviation
        words = chunk.rstrip().rsplit(None, 1)
        if len(words) > 1 and words[-1] in _ABBREVS:
            buffer = chunk
            continue
        sentences.append(chunk.strip())

    if buffer:
        sentences.append(buffer.strip())

    return [s for s in sentences if len(s) > 10]


# --- Claim filtering ---

_QUESTION_PATTERN = re.compile(r'\?$')
_COMMAND_PATTERN = re.compile(r'^(Click|Subscribe|Sign up|Follow|Share|Enter|Visit)\b', re.I)
_BOILERPLATE = re.compile(
    r'^(Copyright|All rights reserved|Terms of|Privacy|Cookie|'
    r'Advertisement|Loading|JavaScript|This site)\b', re.I
)
_TOO_SHORT = 20  # Minimum chars for a viable claim
_TOO_LONG = 500  # Maximum chars for an atomic claim


def _is_claim_candidate(sentence: str) -> bool:
    """Filter sentences that are unlikely to be factual claims."""
    s = sentence.strip()
    if len(s) < _TOO_SHORT or len(s) > _TOO_LONG:
        return False
    if _QUESTION_PATTERN.search(s):
        return False
    if _COMMAND_PATTERN.match(s):
        return False
    if _BOILERPLATE.match(s):
        return False
    # Must contain at least one noun-like word (capitalized or number)
    if not re.search(r'[A-Z][a-z]|\d', s):
        return False
    return True


def _categorize_claim(statement: str) -> str:
    """Assign a claim category using heuristic patterns."""
    if re.search(
        r'\b\d+(\.\d+)?%'
        r'|\b\d[\d,.]*\s*(million|billion|trillion|percent|degrees?|'
        r'millimeters?|kilometers?|meters?|miles?|tons?|pounds?|'
        r'dollars?|per year|per month|per day)\b',
        statement, re.I,
    ):
        return CATEGORY_STATISTICAL
    if re.search(r'\b(caused|because|due to|result of|led to)\b', statement, re.I):
        return CATEGORY_CAUSAL
    if re.search(r'\b(should|ought|best|worst|I think|I believe)\b', statement, re.I):
        return CATEGORY_OPINION
    if re.search(r'\b(defined as|means|refers to|is called)\b', statement, re.I):
        return CATEGORY_DEFINITIONAL
    if re.search(r'\b(must|shall|requires|procedure|step \d)\b', statement, re.I):
        return CATEGORY_PROCEDURAL
    return CATEGORY_FACTUAL


# --- Entity extraction ---

_PERSON_TITLE = re.compile(
    r'\b(?:President|Sen\.|Rep\.|Gov\.|Mayor|Chief|Director|Secretary|'
    r'Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
)
_ORG_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*'
    r'(?:\s+(?:Department|Agency|Commission|Bureau|Board|Council|'
    r'Institute|University|Corporation|Company|Foundation|Association'
    r')))\b'
)
_LOCATION_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*'
    r'(?:,\s*[A-Z]{2})?)\b'  # City, ST pattern
)
_DATE_PATTERN = re.compile(
    r'\b(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+\d{1,2},?\s*\d{4}\b'
    r'|\b\d{1,2}/\d{1,2}/\d{4}\b'
    r'|\b\d{4}-\d{2}-\d{2}\b'
)
_NUMBER_PATTERN = re.compile(
    r'\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|trillion))?'
    r'|\b\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|trillion|percent|%))\b'
)


def _extract_entities(text: str) -> list[dict]:
    """Extract named entities from text using regex patterns."""
    entities = []
    seen = set()

    for pattern, etype in [
        (_DATE_PATTERN, ENTITY_DATE),
        (_NUMBER_PATTERN, ENTITY_NUMBER),
        (_PERSON_TITLE, ENTITY_PERSON),
        (_ORG_PATTERN, ENTITY_ORGANIZATION),
    ]:
        for m in pattern.finditer(text):
            name = m.group().strip()
            if name not in seen and len(name) > 2:
                entities.append({"name": name, "type": etype})
                seen.add(name)

    return entities


class ExtractorWorker(Worker):
    worker_type = "extractor"

    @skill("extract.claims", "Extract atomic claims from content")
    def extract_claims(self, handle):
        """Extract atomic, verifiable claims from raw content.

        Uses sentence segmentation and heuristic filters to find
        claim-like sentences. Each claim is tagged with a category
        and includes the source excerpt for provenance.

        Params (from handle.params):
            content (str): The raw text content to extract from.
            source_tier (str, optional): Source tier (T1-T7).
            max_claims (int, optional): Maximum claims to extract (default 50).

        Returns:
            dict with claims list, each containing statement, category,
            excerpt.
        """
        params = handle.params
        content = params.get("content", "")
        source_tier = params.get("source_tier", "T5")
        max_claims = params.get("max_claims", 50)

        if not content:
            return {"error": "content is required", "claims": []}

        sentences = _segment_sentences(content)
        claims = []

        for sentence in sentences:
            if not _is_claim_candidate(sentence):
                continue

            category = _categorize_claim(sentence)
            claims.append({
                "statement": sentence,
                "category": category,
                "excerpt": sentence,
            })

            if len(claims) >= max_claims:
                break

        return {
            "claims": claims,
            "source_tier": source_tier,
            "total_sentences": len(sentences),
            "claims_extracted": len(claims),
            "extracted_at": _now_iso(),
        }

    @skill("extract.entities", "Extract named entities from content")
    def extract_entities(self, handle):
        """Extract named entities from content with type classification.

        Uses regex patterns for dates, numbers, titled persons, and
        organizations.

        Params (from handle.params):
            content (str): The raw text content.
            entity_types (list, optional): Filter to specific types.

        Returns:
            dict with entities list, each containing name, type.
        """
        params = handle.params
        content = params.get("content", "")
        type_filter = params.get("entity_types", [])

        if not content:
            return {"error": "content is required", "entities": []}

        entities = _extract_entities(content)

        if type_filter:
            entities = [e for e in entities if e["type"] in type_filter]

        return {
            "entities": entities,
            "total_found": len(entities),
            "extracted_at": _now_iso(),
        }

    @skill("extract.relationships", "Extract relationships between entities")
    def extract_relationships(self, handle):
        """Extract relationships between entities in the content.

        Stub: relationship extraction requires deeper NLP or LLM.

        Params (from handle.params):
            content (str): The raw text content.
            entities (list, optional): Pre-extracted entities.

        Returns:
            dict with relationships list.
        """
        params = handle.params
        content = params.get("content", "")

        if not content:
            return {"error": "content is required", "relationships": []}

        # Stub: relationship extraction is complex and benefits most
        # from LLM integration. Heuristic approach would need
        # dependency parsing which is beyond regex.
        return {
            "relationships": [],
            "note": "relationship extraction requires LLM integration",
            "extracted_at": _now_iso(),
        }


worker = ExtractorWorker(worker_id="loom-extractor-1")

if __name__ == "__main__":
    worker.run()
