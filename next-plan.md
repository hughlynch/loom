# Loom — Next Plan

## Phase 2: Dual-Axis Schema + LLM Extraction

From architectural-recommendations.md Phase 2 (schema change):

1. **Information credibility axis (C1-C6)** — Add second axis
   alongside source reliability (T1-T7). Each evidence link
   gets an independent credibility assessment.

2. **LLM-backed extraction** — Replace heuristic extractor with
   LLM calls (LOOM_MODEL) for higher-quality claim extraction.
   Keep heuristic as fallback when no API key is set.

3. **GRADE-like adjustment factors** — Add up/down modifiers to
   confidence computation: risk_of_bias, inconsistency,
   indirectness, imprecision, publication_bias (down);
   large_effect, dose_response (up).

4. **Structured disagreement model** — Replace binary "contested"
   with evidence_strength × agreement_level matrix (IPCC-inspired).

5. **ClaimReview export** — Schema.org ClaimReview format for
   interoperability with fact-checking ecosystem.

## has_next
true — Phase 2 is clearly scoped and builds on proven foundation.
Natural pause point between phases.
