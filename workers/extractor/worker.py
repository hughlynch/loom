"""ExtractorWorker — pulls structured claims from raw content.

Responsible for decomposing unstructured text into atomic claims, named
entities, and relationships. Hybrid extraction: LLM-backed when
LOOM_MODEL is set (or ANTHROPIC_API_KEY/GEMINI_API_KEY available),
heuristic fallback otherwise.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

log = logging.getLogger(__name__)

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
    r'Advertisement|Loading|JavaScript|This site|Yes No|'
    r'Comments or|Thank you for|Subscribe|Sign up|Share|'
    r'An official website|Secure \.gov|Here\'s how|'
    r'characters maximum|Close|Skip to|Menu|Navigation|'
    r'NO THANKS)\b', re.I
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


# --- LLM-backed extraction ---

_EXTRACTION_SYSTEM = """You are a fact extraction system. Your job is to \
extract atomic, verifiable claims from text.

For each claim, output a JSON object with:
- "statement": the claim as a single, self-contained sentence
- "category": one of: factual, statistical, causal, opinion, \
definitional, procedural
- "entities": list of {name, type} where type is person, \
organization, location, date, or number
- "confidence_hint": float 0-1, how verifiable this claim is

Output a JSON array of claim objects. Only extract claims that are:
- Atomic (one assertion per claim)
- Verifiable (can be checked against evidence)
- Substantive (not boilerplate, navigation, or metadata)

Do NOT include questions, commands, opinions presented as facts, \
or unverifiable assertions. Maximum 50 claims.

Output ONLY the JSON array, no other text."""

_EXTRACTION_PROMPT = """Extract all verifiable factual claims \
from the following text:

---
{content}
---

Output a JSON array of claim objects."""


def _resolve_model():
    """Resolve the extraction LLM model.

    Priority:
      1. LOOM_MODEL env var
      2. claude-haiku-4-5 (if ANTHROPIC_API_KEY set)
      3. gemini-2.5-flash (if GEMINI_API_KEY set)
      4. None (use heuristic fallback)
    """
    explicit = os.environ.get("LOOM_MODEL")
    if explicit:
        return explicit

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            __import__("anthropic")
            return "claude-haiku-4-5-20251001"
        except ImportError:
            pass

    if os.environ.get("GEMINI_API_KEY"):
        try:
            __import__("google.generativeai")
            return "gemini-2.5-flash"
        except ImportError:
            pass

    return None


def _call_llm(system, prompt, model_name):
    """Call an LLM API. Returns (text, error)."""
    if model_name.startswith("claude-"):
        return _call_anthropic(system, prompt, model_name)
    return _call_gemini(system, prompt, model_name)


def _call_anthropic(system, prompt, model_name):
    """Call the Anthropic API."""
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "ANTHROPIC_API_KEY not set"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name,
            max_tokens=4096,
            system=system,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return response.content[0].text, None
    except Exception as e:
        return None, str(e)


def _call_gemini(system, prompt, model_name):
    """Call the Gemini API."""
    try:
        import google.generativeai as genai
    except ImportError:
        return None, "google-generativeai not installed"

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY not set"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name,
            system_instruction=system,
        )
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
            ),
        )
        return response.text, None
    except Exception as e:
        return None, str(e)


def _parse_llm_claims(raw_text):
    """Parse LLM JSON output into claim dicts.

    Handles both clean JSON arrays and JSON wrapped
    in markdown code fences.
    """
    if not raw_text:
        return []

    text = raw_text.strip()

    # Strip markdown code fences.
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences).
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Failed to parse LLM output as JSON")
        return []

    if not isinstance(data, list):
        return []

    claims = []
    for item in data:
        if not isinstance(item, dict):
            continue
        statement = item.get("statement", "").strip()
        if not statement or len(statement) < 10:
            continue
        claims.append({
            "statement": statement,
            "category": item.get("category", "factual"),
            "excerpt": statement,
            "entities": item.get("entities", []),
            "confidence_hint": item.get(
                "confidence_hint", 0.5),
            "extraction_method": "llm",
        })
    return claims


def extract_claims_llm(content, model_name=None,
                       max_claims=50):
    """Extract claims using an LLM.

    Returns (claims_list, error_or_none). On error,
    returns ([], error_string) so caller can fall back
    to heuristic.
    """
    model = model_name or _resolve_model()
    if model is None:
        return [], "no LLM model available"

    prompt = _EXTRACTION_PROMPT.format(
        content=content[:8000])

    text, err = _call_llm(
        _EXTRACTION_SYSTEM, prompt, model)
    if err:
        return [], err

    claims = _parse_llm_claims(text)
    return claims[:max_claims], None


class ExtractorWorker(Worker):
    worker_type = "extractor"

    @skill("extract.claims", "Extract atomic claims from content")
    def extract_claims(self, handle):
        """Extract atomic, verifiable claims from raw content.

        Hybrid extraction: tries LLM first (when LOOM_MODEL
        or API keys are available), falls back to heuristic
        sentence segmentation. Set extraction_method="heuristic"
        to force heuristic mode.

        Params (from handle.params):
            content (str): The raw text content to extract from.
            source_tier (str, optional): Source tier (T1-T7).
            max_claims (int, optional): Max claims (default 50).
            extraction_method (str, optional): "auto", "llm",
                or "heuristic". Default "auto".

        Returns:
            dict with claims list, each containing statement,
            category, excerpt, and extraction_method.
        """
        params = handle.params
        content = params.get("content", "")
        source_tier = params.get("source_tier", "T5")
        max_claims = params.get("max_claims", 50)
        method = params.get("extraction_method", "auto")

        if not content:
            return {"error": "content is required", "claims": []}

        claims = []
        used_method = "heuristic"
        llm_error = None

        # Try LLM extraction first.
        if method in ("auto", "llm"):
            llm_claims, llm_error = extract_claims_llm(
                content,
                model_name=params.get("model"),
                max_claims=max_claims,
            )
            if llm_claims:
                claims = llm_claims
                used_method = "llm"
            elif method == "llm":
                # Forced LLM but failed.
                return {
                    "error": f"LLM extraction failed: "
                             f"{llm_error}",
                    "claims": [],
                }

        # Heuristic fallback.
        if not claims:
            sentences = _segment_sentences(content)
            for sentence in sentences:
                if not _is_claim_candidate(sentence):
                    continue
                category = _categorize_claim(sentence)
                claims.append({
                    "statement": sentence,
                    "category": category,
                    "excerpt": sentence,
                    "extraction_method": "heuristic",
                })
                if len(claims) >= max_claims:
                    break
            used_method = "heuristic"

        return {
            "claims": claims,
            "source_tier": source_tier,
            "claims_extracted": len(claims),
            "extraction_method": used_method,
            "llm_error": llm_error,
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

        Uses LLM when available, otherwise returns empty list
        (relationship extraction requires deeper NLP).

        Params (from handle.params):
            content (str): The raw text content.
            entities (list, optional): Pre-extracted entities.

        Returns:
            dict with relationships list.
        """
        params = handle.params
        content = params.get("content", "")

        if not content:
            return {
                "error": "content is required",
                "relationships": [],
            }

        model = _resolve_model()
        if model is None:
            return {
                "relationships": [],
                "note": "LLM required for relationship "
                        "extraction",
                "extracted_at": _now_iso(),
            }

        rel_system = (
            "Extract relationships between entities in "
            "the text. Output a JSON array of objects "
            "with: subject (str), predicate (str), "
            "object (str), claim_excerpt (str). "
            "Only output the JSON array."
        )
        prompt = f"Extract relationships from:\n\n{content[:4000]}"
        text, err = _call_llm(rel_system, prompt, model)
        if err:
            return {
                "relationships": [],
                "error": err,
                "extracted_at": _now_iso(),
            }

        try:
            raw = text.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()
            rels = json.loads(raw)
            if not isinstance(rels, list):
                rels = []
        except json.JSONDecodeError:
            rels = []

        return {
            "relationships": rels,
            "total_found": len(rels),
            "extracted_at": _now_iso(),
        }


worker = ExtractorWorker(worker_id="loom-extractor-1")

if __name__ == "__main__":
    worker.run()
