# Loom Storage Strategy

**Date:** 2026-03-08
**Status:** Spec (pre-implementation)
**Repo:** loom (`hughlynch/loom`)
**Related:**
- `grove-kit/spec/vector-search-abstraction.md` — pluggable vector search interface
- `loom/spec/knowledge-ci.md` — snapshot build/test/deploy pipeline
- `loom/spec/ecosystem-impact.md` — per-expert integration plan
- `abwp/spec/loom-deployment.md` — phased rollout across products

**Derived from:** Research on branch `claude/research-dolt-integration-rHJHB`
(6 commits, 513 lines analyzing Dolt, libSQL, event-sourced SQLite, and
SQLite+Git). This spec distills that research into an actionable plan.

---

## Decision

**Phase 1:** Event-sourced SQLite (no new dependencies)
**Phase 2:** libSQL migration (when vector search demand materializes)
**Ruled out:** Dolt (operational weight disproportionate to need)
**Ruled out:** SQLite+Git (textual diffs, not semantic)

---

## Context

Loom's evidence graph is stored in SQLite. The KB worker
(`workers/kb/worker.py`) makes ~58 raw `sqlite3` calls across
18 skills. This is **Loom's decision, not Grove's** — the
grove SDK (`grove.uwp`) is storage-agnostic, and no other
project depends on Loom's storage backend.

Current state after i11:
- `claim_versions` table: append-only version history
- Source retractions, contradiction records, ATMS labels: all
  append-only
- Snapshot builder: compiles evidence graph into versioned,
  immutable artifacts with FTS5
- Vector search: stubbed (`LIKE` queries in `kb.search` and
  `kb.find_similar`)

What's missing:
- Ordered event log (change events defined in knowledge-ci spec
  but no table or emitters exist)
- Vector embeddings (knowledge-ci spec mentions FAISS but it's
  not implemented)
- "Diff between version N and M" queries
- Event-driven build triggers

---

## Phase 1: Event-Sourced SQLite

### What

Formalize the event log that the knowledge-ci spec already
requires. This is ~200-300 lines of code — evolving what
exists, not building from scratch.

### Schema

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL,       -- monotonic, gapless
    event_type TEXT NOT NULL,         -- claim.integrated, etc.
    aggregate_id TEXT NOT NULL,       -- claim_id, source_url
    aggregate_type TEXT NOT NULL,     -- claim, source, evidence
    payload TEXT NOT NULL,            -- JSON: full before/after
    domain_id TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_events_seq ON events(sequence);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_aggregate ON events(aggregate_id);
CREATE INDEX idx_events_domain ON events(domain_id);
```

### Event Types

From knowledge-ci spec, formalized:

| Event | Aggregate | Emitted by |
|-------|-----------|------------|
| `claim.integrated` | claim | `kb.store_claim` |
| `claim.updated` | claim | `kb.update_claim` |
| `claim.superseded` | claim | `kb.update_claim` (when superseded_by set) |
| `claim.expired` | claim | `kb.find_expired` or monitor |
| `claim.confidence_changed` | claim | `kb.update_claim` (level boundary crossing) |
| `evidence.added` | evidence | `kb.store_claim` (evidence link) |
| `evidence.retracted` | evidence | `kb.retract_source` |
| `source.reliability_changed` | source | `kb.source_health` |
| `source.content_changed` | source | refresh duty |
| `source.retracted` | source | `kb.retract_source` |
| `contradiction.created` | contradiction | `kb.record_contradiction` |
| `contradiction.resolved` | contradiction | adjudicator |
| `label.invalidated` | dependency_label | `kb.retract_source` |

### Payload Format

Each event carries the full before/after state needed for
replay:

```json
{
    "before": {"confidence": 0.65, "status": "reported"},
    "after": {"confidence": 0.82, "status": "corroborated"},
    "reason": "Second independent source confirmed claim",
    "triggered_by": "corroborate.check"
}
```

### Diff Queries

"What changed between snapshot v47 and v48?" becomes:

```sql
SELECT * FROM events
WHERE sequence > :v47_sequence
  AND sequence <= :v48_sequence
  AND domain_id = :domain_id
ORDER BY sequence;
```

Snapshot manifests record the event sequence position at build
time:

```json
{
    "version": "v48",
    "event_sequence": 1847,
    "previous_event_sequence": 1802
}
```

### Build Trigger Integration

The snapshot builder's trigger policy (batch window, immediate
triggers, rate limits) evaluates against the event log:

```python
def should_build(domain_id, last_build_sequence):
    events = get_events_since(domain_id, last_build_sequence)
    if not events:
        return False
    # Immediate triggers bypass batch window
    immediate = [e for e in events
                 if e.event_type in IMMEDIATE_TRIGGERS]
    if immediate:
        return True
    # Batch: enough events and enough time
    return (len(events) >= MIN_CHANGES
            and age_seconds(events[0]) >= BATCH_WINDOW)
```

### Implementation

Changes to `workers/kb/worker.py`:

1. Add `events` table in migration `004_event_log.sql`
2. Add `_emit_event()` helper that inserts into events table
3. Wire `_emit_event()` into existing skill implementations:
   - `kb_store_claim` → `claim.integrated` + `evidence.added`
   - `kb_update_claim` → `claim.updated` (+ `claim.confidence_changed` if level crosses boundary)
   - `kb_record_contradiction` → `contradiction.created`
   - `kb_retract_source` → `source.retracted` + `evidence.retracted` + `label.invalidated`
4. Add `kb.events_since(sequence, domain_id)` skill for
   snapshot builder consumption
5. Update snapshot manifest to record event sequence position

The `claim_versions` table remains — it serves a different
purpose (human-readable audit trail). Events are the machine-
readable counterpart.

### What This Gets Us

- **Audit trail**: every state change is an event with
  before/after payload
- **Diffing**: events between two sequence positions = diff
- **Build triggers**: event-driven, not schedule-driven
- **Replay**: reconstruct graph state from event log (for
  testing, debugging, migration)
- **Zero new dependencies**: pure SQLite

---

## Phase 2: libSQL Migration

### Trigger

When **two or more** of these conditions are met:
- Cubby or Yohumps reaches the point where it needs vector
  search through Loom
- libSQL's Python bindings are production-quality
- libSQL/Limbo project stabilizes (one clear successor, not
  two competing forks)

### What Changes

1. Replace `sqlite3` with `libsql` in `workers/kb/worker.py`
   (drop-in compatible for existing queries)
2. Implement `SQLiteBackend` in grove-kit (see
   `grove-kit/spec/vector-search-abstraction.md`)
3. Loom's snapshot builder uses `VectorIndex` with
   `SQLiteBackend` — vectors stored as BLOB columns in
   chunks table
4. Snapshot artifact collapses to single file:
   ```
   snapshots/{domain_id}/v{version}/
     snapshot.db       # claims + chunks + vectors + FTS
     manifest.json     # version, backend, embedding model
   ```
5. `kb.search` and `kb.find_similar` become real vector search

### What Doesn't Change

- Evidence graph schema (sources, claims, evidence, etc.)
- Event log (events table, same schema)
- Confidence computation (deterministic, same rules)
- Snapshot build pipeline (resolve, collapse, filter, chunk,
  index, test, package) — same stages, different output format
- Quality gates (same tests, same thresholds)
- Domain profiles (same configuration)

### Migration Path

1. Add `libsql` as optional dependency
2. Implement `SQLiteBackend` in grove-kit
3. Build a snapshot with both backends, compare results
4. Golden fixtures must pass at same rates
5. Switch default backend in domain profile
6. Old FAISS-based snapshots remain valid (query router
   detects format from manifest `vector_backend` field)

---

## Why Not Dolt

Dolt was the original research focus. It has the best version
control primitives (branch, merge, diff, blame at cell level).
But:

1. **Operational weight**: requires `dolt sql-server` process
   (200MB Go binary). Loom currently deploys by copying a
   single `.db` file.
2. **Violates deployment constraint**: the deployment spec
   (`abwp/spec/loom-deployment.md`) explicitly says "no new
   containers, no new network topology, no new services."
3. **Redundant merge model**: Dolt's cell-level merge is
   elegant but Loom's adjudicator already handles contradiction
   resolution domain-specifically — and does it better, because
   it understands evidence semantics, not just data conflicts.
4. **No vector search**: Dolt is MySQL-compatible, so no
   pgvector. You'd need FAISS *alongside* Dolt — strictly
   worse than the current situation.
5. **Federation is distant**: Dolt's remote model is
   genuinely the best tool for cross-domain sync. But
   federation is specced, not implemented, and won't be
   for multiple iterations. Don't adopt infrastructure
   for a need that hasn't materialized.

Dolt remains a valid future option **if and when** multi-domain
federation becomes real and event log replication proves
insufficient.

---

## Why Not SQLite+Git

Versioning the database file in Git (export SQL dump, commit,
diff with `git diff`) was considered. Rejected because:

- Diffs are textual, not semantic (a confidence change from
  0.65 to 0.82 shows as a line diff, not "claim X confidence
  increased")
- Merge conflicts are SQL text conflicts, not evidence-level
  conflicts
- Doesn't scale past small databases
- Git's storage model isn't optimized for database files

The event log gives us everything Git would for auditing,
without the impedance mismatch.

---

## Snapshot Format (Backend-Agnostic)

The knowledge-ci spec previously hardcoded:
```
claims.sqlite + chunks.sqlite + chunks.faiss + chunks_fts.sqlite
```

Revised to be backend-dependent:

| Backend | Artifact |
|---------|----------|
| FAISS (current) | `snapshot.sqlite` + `vectors.faiss` + `id_map.json` |
| libSQL (Phase 2) | `snapshot.db` (all-in-one) |

The manifest records the backend:

```json
{
    "version": "v48",
    "domain_id": "cb7_manhattan",
    "vector_backend": "faiss",
    "embedding_model": "gemini-embedding-001",
    "embedding_dimensions": 768,
    "event_sequence": 1847,
    "files": ["snapshot.sqlite", "vectors.faiss", "id_map.json",
              "manifest.json", "integrity.sha256"]
}
```

Query routing detects backend from manifest and loads the
appropriate `VectorBackend` implementation from grove-kit.

---

## Impact on Ecosystem

### Loom (this repo)
- Phase 1: event log, ~200-300 lines, one iteration
- Phase 2: libSQL migration, backend swap, snapshot format change

### grove-kit
- Phase 1: vector search abstraction spec + implementation
  (see `grove-kit/spec/vector-search-abstraction.md`)
- Phase 2: `SQLiteBackend` implementation

### Experts (Geeni, Canopy, Cubby, Yohumps, Sil)
- Phase 1: no changes
- Phase 2: no changes (abstraction is opt-in)
- Phase 3: migrate to `VectorIndex` at own pace
  (see `loom/spec/ecosystem-impact.md` Phase 2-3)

### abwp specs
- knowledge-ci.md: snapshot format made backend-agnostic
- loom-deployment.md: vector backend referenced as pluggable
- geeni-loom-deployment.md: same

---

## Timeline

Phase 1 (event-sourced SQLite) is the next Loom iteration
(i12). It unblocks:
- Event-driven snapshot build triggers
- Diff queries for changelogs
- Replay for testing and migration validation

Phase 2 (libSQL) is gated on external conditions (libSQL
maturity, Cubby/Yohumps vector search need). Not scheduled.

---

## References

- Dolt research: `loom` branch `claude/research-dolt-integration-rHJHB`
- [libSQL](https://github.com/tursodatabase/libsql)
- [Turso / Limbo](https://turso.tech/)
- [FAISS](https://github.com/facebookresearch/faiss)
- grove-kit KB: `grove-kit/kb/` (embeddings, index_builder, knowledge_worker)
