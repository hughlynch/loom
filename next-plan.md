# Loom — Next Plan

## History (i0-i13)

All four architectural recommendation phases implemented
across 9 momentum iterations, plus maintenance skills (i10),
snapshot build pipeline (i11), event-sourced storage (i12),
and event-driven snapshot builds (i13):

- Phase 1: Foundation (harvester, extractor, classifier,
  corroborator, KB, pipeline) — 5 iterations
- Phase 2: Dual-axis schema (C1-C6, GRADE, ClaimReview,
  structured disagreement, Toulmin) — 2 iterations
- Phase 3: Dependency network (ATMS labels, retraction
  propagation, sensitivity analysis) — 1 iteration
- Phase 4: Advanced reasoning (ACH, Devil's Advocacy,
  Dung semantics) — 1 iteration
- i10: Maintenance skills
- i11: Snapshot build pipeline (FTS5, quality gates, profiles)
- i12: Event-sourced storage (event log, emission, querying)
- i13: Event-driven snapshot builds (trigger policy, manifests)

146 tests, all green. Go E2E passes.

grove-kit vector abstraction also shipped (37 tests):
VectorBackend, FAISSBackend, StubBackend, GeminiEmbedder.

## i14 — Vector Search Integration (next)

Replace LIKE-based fuzzy matching in KB worker with grove-kit
VectorIndex for semantic search. This is the first consumer
of the grove-kit vector search abstraction.

### Steps

1. Add grove-kit dependency to Loom KB worker
   - Import VectorIndex, StubBackend/FAISSBackend, StubEmbedder/GeminiEmbedder
   - Initialize index alongside DB connection

2. Replace `kb_find_similar` LIKE query with vector search
   - Embed claim statements on store
   - Query by embedding on find_similar
   - Fall back to LIKE when vector index unavailable

3. Add vector index to snapshot build
   - Embed filtered claims during build
   - Save vector index alongside snapshot.sqlite
   - Update manifest: vector_backend = "faiss" or "stub"

4. Update snapshot query to support semantic search
   - Add `loom.snapshot.query_semantic` skill (or mode param)
   - Use VectorIndex.search() against snapshot's vector index

5. Tests
   - KB find_similar with stub vectors (deterministic)
   - Snapshot build includes vector artifacts
   - Semantic query returns relevant results

### Dependencies

- grove-kit kb/vector.py (already merged to main)
- GEMINI_API_KEY for real embeddings (falls back to stub)

## Future iterations

- Canary deployment routing for snapshot rollouts
- LLM-backed extraction (LOOM_MODEL)
- Tutor worker implementation (pedagogy spec)
- Monitor worker (source rates, challenge health)
- Curator worker (human-in-the-loop review)
- libSQL migration (gated on external maturity)

## has_next
true — i14: vector search integration
