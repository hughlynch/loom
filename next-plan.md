# Loom — Next Plan

## History (i0-i11)

All four architectural recommendation phases implemented
across 9 momentum iterations, plus maintenance skills (i10)
and snapshot build pipeline (i11):

- Phase 1: Foundation (harvester, extractor, classifier,
  corroborator, KB, pipeline) — 5 iterations
- Phase 2: Dual-axis schema (C1-C6, GRADE, ClaimReview,
  structured disagreement, Toulmin) — 2 iterations
- Phase 3: Dependency network (ATMS labels, retraction
  propagation, sensitivity analysis) — 1 iteration
- Phase 4: Advanced reasoning (ACH, Devil's Advocacy,
  Dung semantics) — 1 iteration
- i10: Maintenance skills
- i11: Snapshot build pipeline

112+ tests, all green. Go E2E passes.

## i12 — Event-Sourced Storage (next)

Formalize the event log required by knowledge-ci.md.
See `spec/storage-strategy.md` for full rationale.

### Steps

1. Add `schema/migrations/004_event_log.sql` with events
   table (event_id, sequence, event_type, aggregate_id,
   aggregate_type, payload, domain_id, created_at, created_by)

2. Add `_emit_event()` helper in `workers/kb/worker.py`

3. Wire into existing skills:
   - `kb_store_claim` → `claim.integrated` + `evidence.added`
   - `kb_update_claim` → `claim.updated` (+ `claim.confidence_changed`)
   - `kb_record_contradiction` → `contradiction.created`
   - `kb_retract_source` → `source.retracted` + `evidence.retracted`

4. Add `kb.events_since(sequence, domain_id)` skill

5. Update snapshot manifest to record `event_sequence`

6. Tests: event emission, event querying, diff between
   snapshot versions via event log

### Dependencies

- None (pure SQLite, no new deps)

### Parallel work (grove-kit)

grove-kit `loom/vector-search-abstraction` branch:
- Implement `VectorBackend`, `EmbeddingProvider`, `VectorIndex`
- Implement `FAISSBackend` wrapping existing `IndexBuilder`
- Implement `GeminiEmbedder` wrapping existing `embeddings.py`
- Implement `StubBackend` and `StubEmbedder`

## Future iterations

- Vector search via grove-kit VectorIndex (replaces LIKE stubs)
- Canary deployment routing for snapshot rollouts
- LLM-backed extraction (LOOM_MODEL)
- Tutor worker implementation (pedagogy spec)
- Monitor worker (source rates, challenge health)
- Curator worker (human-in-the-loop review)
- libSQL migration (gated on external maturity)

## has_next
true — i12: event-sourced storage
