"""ExtractorWorker — pulls structured claims from raw content using LLM.

Responsible for decomposing unstructured text into atomic claims, named
entities, and relationships. Each claim is a single, verifiable statement
with temporal bounds and a source excerpt for provenance.
"""

import json
import os
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
ENTITY_EVENT = "event"
ENTITY_CONCEPT = "concept"
ENTITY_PRODUCT = "product"
ENTITY_DATE = "date"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExtractorWorker(Worker):
    worker_type = "extractor"

    @skill("extract.claims", "Extract atomic claims from content")
    def extract_claims(self, handle):
        """Extract atomic, verifiable claims from raw content.

        Uses LLM to decompose text into individual claims, each tagged with
        category, temporal validity bounds, and the source excerpt that
        supports it.

        Params (from handle.params):
            content (str): The raw text content to extract from.
            source_tier (str, optional): Source tier (T1-T7) for context.
            topic_hint (str, optional): Topic hint to guide extraction.
            max_claims (int, optional): Maximum number of claims to extract.

        Returns:
            dict with claims list, each containing statement, category,
            valid_from, valid_until, excerpt.
        """
        params = handle.params
        content = params.get("content", "")
        source_tier = params.get("source_tier", "T5")
        topic_hint = params.get("topic_hint", "")

        if not content:
            return {"error": "content is required", "claims": []}

        # Stub: in production, this calls an LLM with a structured extraction
        # prompt that enforces atomic claims and requires excerpts.
        # The prompt would include the source_tier and topic_hint for context.
        claims = [
            {
                "statement": f"[stub] Extracted claim from content (tier={source_tier})",
                "category": CATEGORY_FACTUAL,
                "valid_from": _now_iso(),
                "valid_until": None,
                "excerpt": content[:200] if content else "",
            }
        ]

        return {
            "claims": claims,
            "source_tier": source_tier,
            "topic_hint": topic_hint,
            "extracted_at": _now_iso(),
        }

    @skill("extract.entities", "Extract named entities from content")
    def extract_entities(self, handle):
        """Extract named entities from content with type classification.

        Params (from handle.params):
            content (str): The raw text content to extract from.
            entity_types (list, optional): Filter to specific entity types.

        Returns:
            dict with entities list, each containing name, type, aliases.
        """
        params = handle.params
        content = params.get("content", "")

        if not content:
            return {"error": "content is required", "entities": []}

        # Stub: in production, LLM extracts entities with alias resolution.
        entities = [
            {
                "name": "[stub] Example Entity",
                "type": ENTITY_CONCEPT,
                "aliases": [],
            }
        ]

        return {
            "entities": entities,
            "extracted_at": _now_iso(),
        }

    @skill("extract.relationships", "Extract relationships between entities")
    def extract_relationships(self, handle):
        """Extract relationships between entities in the content.

        Produces subject-predicate-object triples with supporting evidence
        excerpts.

        Params (from handle.params):
            content (str): The raw text content.
            entities (list, optional): Pre-extracted entities to constrain.

        Returns:
            dict with relationships list, each containing subject, predicate,
            object, evidence.
        """
        params = handle.params
        content = params.get("content", "")

        if not content:
            return {"error": "content is required", "relationships": []}

        # Stub: in production, LLM identifies relationships between
        # entities found in the text, producing structured triples.
        relationships = [
            {
                "subject": "[stub] Entity A",
                "predicate": "relates_to",
                "object": "[stub] Entity B",
                "evidence": content[:200] if content else "",
            }
        ]

        return {
            "relationships": relationships,
            "extracted_at": _now_iso(),
        }


worker = ExtractorWorker(worker_id="loom-extractor-1")

if __name__ == "__main__":
    worker.run()
