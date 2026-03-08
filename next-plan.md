# Loom — Next Plan

## History (i0-i16)

- Phase 1-4: Foundation through advanced reasoning (9 iterations)
- i10: Maintenance skills
- i11: Snapshot build pipeline
- i12: Event-sourced storage
- i13: Event-driven snapshot builds
- i14: Vector search integration (grove-kit VectorIndex)
- i15: LLM-backed hybrid extraction
- i16: Tutor worker (assess, teach, verify with KB integration)

217 tests, all green.

## i17 — Monitor Worker (next)

Implement the monitor worker for system health tracking.
Currently stubbed with `source_rates` and `challenge_health`
skills.

### Steps

1. Implement `loom.monitor.source_rates`
   - Track claim acquisition rates per source tier
   - Detect stale sources (no new claims in N days)
   - Report tier distribution health

2. Implement `loom.monitor.challenge_health`
   - Track contradiction resolution rates
   - Monitor open challenges and their age
   - Report challenge backlog health

3. Implement `loom.monitor.system_health`
   - Composite health score combining all monitors
   - DB size, event log growth, snapshot freshness
   - Alert thresholds

4. Tests

### Dependencies

- KB worker (source data)
- Snapshot worker (freshness data)

## Future iterations

- Snapshot vector index (embed claims during build)
- Curator worker (human-in-the-loop review)
- Learner persistence (DB schema for tutor)
- libSQL migration (gated on external maturity)
- Update AGENTS.md skill map to reflect all changes

## has_next
true — i17: monitor worker
