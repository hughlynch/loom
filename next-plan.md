# Loom — Next Plan

## History (i0-i14)

All four architectural recommendation phases implemented
across 9 momentum iterations, plus infrastructure and
integration work:

- Phase 1: Foundation (5 iterations)
- Phase 2: Dual-axis schema (2 iterations)
- Phase 3: Dependency network (1 iteration)
- Phase 4: Advanced reasoning (1 iteration)
- i10: Maintenance skills
- i11: Snapshot build pipeline (FTS5, quality gates, profiles)
- i12: Event-sourced storage (event log, emission, querying)
- i13: Event-driven snapshot builds (trigger policy, manifests)
- i14: Vector search integration (grove-kit VectorIndex)

160 tests, all green. Go E2E passes.

## i15 — LLM-Backed Extraction (next)

Replace heuristic claim extraction with LLM-backed extraction
for higher quality. The heuristic extractor (regex/sentence
segmentation) catches explicit factual assertions but misses
implicit claims, complex inferences, and nuanced relationships.

### Steps

1. Add LLM extraction skill to extractor worker
   - Use LOOM_MODEL env var (default: claude-haiku-4-5)
   - Structured output: list of claims with category,
     confidence hint, entities, relationships
   - Prompt: role=fact_extractor, extract verifiable claims

2. Hybrid mode: LLM + heuristic
   - LLM extraction as primary when LOOM_MODEL is set
   - Heuristic as fallback when no API key / no LLM
   - Merge results (dedup by statement similarity)

3. Entity and relationship extraction via LLM
   - Replace regex-based entity extraction
   - Extract typed relationships between entities

4. Tests
   - Mock LLM responses for deterministic testing
   - Compare LLM vs heuristic on golden fixtures
   - Verify structured output parsing

### Dependencies

- LOOM_MODEL env var (or ANTHROPIC_API_KEY)
- grove-kit claude or gemini worker for LLM calls

## Future iterations

- Snapshot vector index (embed claims during build)
- Canary deployment routing for snapshot rollouts
- Tutor worker implementation (pedagogy spec)
- Monitor worker (source rates, challenge health)
- Curator worker (human-in-the-loop review)
- libSQL migration (gated on external maturity)

## has_next
true — i15: LLM-backed extraction
