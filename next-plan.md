# Loom — Next Plan

## History (i0-i15)

- Phase 1-4: Foundation through advanced reasoning (9 iterations)
- i10: Maintenance skills
- i11: Snapshot build pipeline
- i12: Event-sourced storage
- i13: Event-driven snapshot builds
- i14: Vector search integration (grove-kit VectorIndex)
- i15: LLM-backed hybrid extraction

181 tests, all green.

## i16 — Tutor Worker (next)

Implement the tutor worker from the pedagogy spec
(`spec/pedagogy.md`). The tutor is the teaching interface
for Loom's knowledge — it adapts to learner level, uses
Socratic questioning, and verifies understanding.

### Steps

1. Implement `loom.tutor.assess` skill
   - Evaluate learner's current knowledge level on a topic
   - Query KB for claims in the topic domain
   - Generate assessment questions from claims
   - Score responses against KB evidence

2. Implement `loom.tutor.teach` skill
   - Adaptive explanation based on learner level
   - Use KB claims as source of truth
   - Cite evidence for each teaching point
   - LLM-backed explanation generation

3. Implement `loom.tutor.verify` skill
   - Post-teaching verification quiz
   - Compare learner responses to KB claims
   - Track knowledge gaps for follow-up

4. Tests
   - Mock LLM responses for deterministic testing
   - Verify KB integration (claims used in teaching)
   - Test level adaptation

### Dependencies

- LOOM_MODEL for LLM-backed teaching (stub without)
- KB worker for claim retrieval

## Future iterations

- Snapshot vector index (embed claims during build)
- Monitor worker (source rates, challenge health)
- Curator worker (human-in-the-loop review)
- libSQL migration (gated on external maturity)

## has_next
true — i16: tutor worker
