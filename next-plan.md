# Loom — Next Plan

## Phases 1-4 Complete

All four architectural recommendation phases have been
implemented across 9 momentum iterations:

- Phase 1: Foundation (harvester, extractor, classifier,
  corroborator, KB, pipeline) — 5 iterations
- Phase 2: Dual-axis schema (C1-C6, GRADE, ClaimReview,
  structured disagreement, Toulmin) — 2 iterations
- Phase 3: Dependency network (ATMS labels, retraction
  propagation, sensitivity analysis) — 1 iteration
- Phase 4: Advanced reasoning (ACH, Devil's Advocacy,
  Dung semantics) — 1 iteration

103 tests, all green. Go E2E passes.

## Potential next work

- LLM-backed extraction (replace heuristic extractor with
  LOOM_MODEL for higher-quality claim extraction)
- Tutor worker implementation (pedagogy spec)
- Snapshot build/test/promote pipeline
- Monitor worker (source rates, challenge health)
- Curator worker (human-in-the-loop review)
- Full ritual DAG execution via grove orchestrator

## has_next
false — all architectural recommendation phases are complete.
Remaining work is operational (LLM integration, pedagogy,
monitoring) and would be a new planning cycle.
