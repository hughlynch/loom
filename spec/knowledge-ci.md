# Knowledge CI/CD: Building and Deploying Knowledge Snapshots

**Author:** Hugh Lynch, with Claude
**Date:** 2026-03-06
**Part of:** Loom — the ABWP Knowledge System
**Depends on:** Knowledge Acquisition (`spec/knowledge-acquisition.md`), Grove Rituals (GROVE-RECONSTRUCTION-GUIDE.md Section 8), Trust Environments (Section 12), Coaching Flywheel (Section 13)
**Consumed by:** Pedagogy workers, Cubby reporters, Weft data views, Sil personal KB, Shep codebase queries
**See also:** Adversarial Resilience (`spec/loom-adversarial-resilience.md`)

---

## The Problem

The knowledge acquisition framework (`knowledge-acquisition.md`)
builds reliable knowledge through evidence hierarchies,
provenance chains, confidence computation, and contradiction
tracking. This infrastructure is essential for *building* trust
in knowledge. It is expensive for *using* knowledge.

Every time a Cubby reporter answers a question about a city
council vote, or a pedagogy Tutor explains a budget process, or
a Weft worker surfaces community data, the system should not
re-traverse the evidence graph, re-compute confidence from
scratch, or re-resolve contradictions that were settled last
Tuesday. That is the equivalent of recompiling your application
from source on every HTTP request.

The evidence graph is source code. What workers query at
inference time should be a compiled, tested, versioned artifact:
a **knowledge snapshot**.

---

## Design Principles

**C1. The evidence graph is the source of truth.** Snapshots are
derived artifacts. When they disagree with the evidence graph,
the snapshot is wrong, not the graph. You can always rebuild
from source.

**C2. Snapshots are immutable and versioned.** Snapshot v47 is
always the same. You can diff v47 against v46, audit what
changed, and roll back if a bad build shipped. No in-place
mutation. Append-only version history.

**C3. Every build is tested.** Quality gates run against every
snapshot before it can be promoted. Golden fixtures — known
questions with verified answers — are the test suite. If the
snapshot can't answer them correctly, the build fails.

**C4. Deployment follows trust progression.** Snapshots move
through staging → canary → production, the same path as Grove
workers. Bad snapshots are caught before they reach users.

**C5. Builds are triggered, not scheduled.** Knowledge changes
(new claims, resolved contradictions, expired validity windows)
trigger builds. Quiet periods produce no builds. Active periods
produce frequent builds. The system builds when the knowledge
changes, not when the clock ticks.

**C6. The pipeline is composed of Grove rituals.** No special
infrastructure. The build, test, and deploy stages are workers
with skills, composed into ritual DAGs. The same coaching
flywheel that improves other workers improves the build
pipeline.

---

## Architecture

```
Evidence Graph (source of truth)
    │
    ├── claim integrated          ─┐
    ├── contradiction resolved     │ change events
    ├── source reliability changed │ (trigger builds)
    ├── temporal validity expired  │
    ├── source content changed    ─┘
    │
    ▼
Build Pipeline (ritual: knowledge.build)
    │
    ├── resolve: compute current confidence levels
    ├── collapse: merge superseded claim chains
    ├── filter: apply temporal validity, remove expired
    ├── chunk: generate retrieval-optimized segments
    ├── index: build vector embeddings + FTS indexes
    ├── test: run golden fixtures against the snapshot
    │
    ▼
Knowledge Snapshot (immutable, versioned artifact)
    │
    ├── staging:    full test suite, no user traffic
    ├── canary:     subset of queries routed here
    ├── production: all queries served from this snapshot
    │
    ▼
Workers query the snapshot, not the evidence graph
```

---

## 1. Change Events and Build Triggers

The evidence graph emits change events when its state changes.
The build pipeline watches for these events and decides whether
to trigger a build.

### 1.1 Change event types

| Event | Source | Significance |
|-------|--------|-------------|
| `claim.integrated` | Acquisition pipeline completed | New knowledge entered the graph |
| `claim.superseded` | Newer claim replaced an older one | Existing knowledge updated |
| `contradiction.resolved` | Adjudicator or Curator resolved a disagreement | Contested → verified/corroborated |
| `contradiction.created` | Corroborator found conflicting evidence | New disagreement discovered |
| `source.reliability_changed` | Source reliability score crossed a threshold | May affect confidence of dependent claims |
| `source.content_changed` | Refresh ritual detected content change at URL | Source material updated |
| `claim.expired` | Temporal validity window closed | Knowledge may be stale |
| `claim.confidence_changed` | New evidence shifted a claim's confidence level | Presentation may need updating |

### 1.2 Build trigger policy

Not every change event triggers a build. The trigger policy
batches changes and evaluates significance.

```yaml
trigger_policy:
  # Batch window: accumulate changes for this duration
  # before evaluating whether to build
  batch_window_seconds: 300  # 5 minutes

  # Minimum changes to trigger a build
  min_changes: 1

  # Always build immediately for these events
  # (bypass batching)
  immediate_triggers:
    - contradiction.resolved
    - claim.confidence_changed  # only when crossing a level boundary

  # Maximum time between builds, even with no changes
  # (ensures freshness checks are applied)
  max_build_interval_hours: 24

  # Minimum time between builds (rate limit)
  min_build_interval_seconds: 600  # 10 minutes
```

### 1.3 Distributed knowledge and federated builds

Knowledge is distributed across communities, domains, and
products. Each knowledge domain maintains its own evidence
graph and builds its own snapshots. Cross-domain references
are handled through **snapshot dependencies**.

```yaml
# A Weft community KB might depend on federal data
snapshot_dependencies:
  - domain: "federal.congress"
    min_version: 47
    pin: false      # use latest compatible

  - domain: "state.virginia"
    min_version: 12
    pin: false

  - domain: "local.arlington"
    # This is the primary domain; no external dep
    primary: true
```

When a dependency publishes a new snapshot, downstream
domains receive a `dependency.updated` event and can trigger
their own rebuilds. The dependency graph is a DAG — no cycles.

**Federation rules:**
- Each domain owns its evidence graph and snapshot pipeline
- Cross-domain claims reference snapshots by domain + version
- A domain can pin to a specific dependency version or track
  latest
- Builds fail if a required dependency version is unavailable
- Dependency snapshots are pulled, not pushed — the consuming
  domain decides when to incorporate upstream changes

---

## 2. The Build Pipeline

### 2.1 Workers

| Worker | Skill | Role |
|--------|-------|------|
| **Resolver** | `kb.build.resolve` | Computes current confidence levels for all claims from the evidence graph |
| **Collapser** | `kb.build.collapse` | Merges superseded claim chains into current claims, preserving history links |
| **Filter** | `kb.build.filter` | Removes expired claims, applies domain-specific inclusion rules |
| **Chunker** | `kb.build.chunk` | Generates retrieval-optimized text segments from resolved claims with confidence metadata |
| **Indexer** | `kb.build.index` | Builds vector embeddings and full-text search indexes (FTS5) from chunks. Vector backend is pluggable via grove-kit `VectorIndex` — see `grove-kit/spec/vector-search-abstraction.md` |
| **Tester** | `kb.build.test` | Runs golden fixtures against the built snapshot to verify correctness |
| **Packager** | `kb.build.package` | Assembles the snapshot artifact with version, manifest, and integrity hashes |

### 2.2 Ritual: `knowledge.build`

```yaml
id: ritual.knowledge.build
version: 1.0.0
description: >
  Build a knowledge snapshot from the evidence graph.
  Triggered by change events or scheduled refresh.

params:
  - name: domain_id
    type: string
    required: true
  - name: triggered_by
    type: string
    required: true
    description: "change_event | scheduled | manual"
  - name: change_events
    type: array
    required: false
    description: "List of change events that triggered this build"
  - name: previous_version
    type: integer
    required: false
    description: "Version of the currently deployed snapshot"

steps:
  - id: resolve
    skill: kb.build.resolve
    context_map:
      domain_id: "{{ params.domain_id }}"
      change_events: "{{ params.change_events }}"

  - id: collapse
    skill: kb.build.collapse
    depends_on: [resolve]
    context_map:
      domain_id: "{{ params.domain_id }}"
      resolved_claims: "{{ steps.resolve.result.claims }}"

  - id: filter
    skill: kb.build.filter
    depends_on: [collapse]
    context_map:
      domain_id: "{{ params.domain_id }}"
      collapsed_claims: "{{ steps.collapse.result.claims }}"

  - id: resolve_deps
    skill: kb.build.resolve_dependencies
    context_map:
      domain_id: "{{ params.domain_id }}"
    # runs in parallel with resolve/collapse/filter
    # (independent of claim processing)

  - id: chunk
    skill: kb.build.chunk
    depends_on: [filter, resolve_deps]
    context_map:
      domain_id: "{{ params.domain_id }}"
      claims: "{{ steps.filter.result.claims }}"
      dependencies: "{{ steps.resolve_deps.result.snapshots }}"

  - id: index
    skill: kb.build.index
    depends_on: [chunk]
    context_map:
      domain_id: "{{ params.domain_id }}"
      chunks: "{{ steps.chunk.result.chunks }}"

  - id: test
    skill: kb.build.test
    depends_on: [index]
    context_map:
      domain_id: "{{ params.domain_id }}"
      snapshot_path: "{{ steps.index.result.snapshot_path }}"
      previous_version: "{{ params.previous_version }}"

  - id: package
    skill: kb.build.package
    depends_on: [test]
    condition: "{{ steps.test.result.passed }}"
    context_map:
      domain_id: "{{ params.domain_id }}"
      snapshot_path: "{{ steps.index.result.snapshot_path }}"
      test_report: "{{ steps.test.result }}"
      previous_version: "{{ params.previous_version }}"

output_map:
  version: "{{ steps.package.result.version }}"
  snapshot_path: "{{ steps.package.result.artifact_path }}"
  test_report: "{{ steps.test.result }}"
  build_failed: "{{ steps.test.result.passed | not }}"
  changelog: "{{ steps.package.result.changelog }}"
```

---

## 3. The Snapshot Artifact

A snapshot is a self-contained, immutable package containing
everything a worker needs to answer questions without touching
the evidence graph.

### 3.1 Artifact structure

The snapshot format depends on the vector search backend.
See `spec/storage-strategy.md` for the full rationale and
`grove-kit/spec/vector-search-abstraction.md` for the
pluggable backend interface.

**With FAISS backend (current default):**
```
snapshots/{domain_id}/v{version}/
  manifest.json        # version, build metadata, dependency versions
  snapshot.sqlite      # resolved claims, chunks, FTS5 index
  vectors.faiss        # vector index for semantic search
  id_map.json          # FAISS index → chunk_id mapping
  changelog.json       # diff from previous version
  test_report.json     # golden fixture results
  integrity.sha256     # hash of all files in the artifact
```

**With libSQL backend (future, single-file):**
```
snapshots/{domain_id}/v{version}/
  manifest.json        # version, build metadata, dependency versions
  snapshot.db          # claims, chunks, vectors, FTS — all in one
  changelog.json       # diff from previous version
  test_report.json     # golden fixture results
  integrity.sha256     # hash of all files in the artifact
```

The manifest records the backend so query routing can load
the correct `VectorBackend` implementation.

### 3.2 Manifest schema

```json
{
  "version": 48,
  "domain_id": "local.arlington",
  "built_at": "2026-03-06T14:30:00Z",
  "triggered_by": "change_event",
  "change_events": ["claim.integrated:c-4892", "contradiction.resolved:x-17"],
  "previous_version": 47,
  "evidence_graph_hash": "sha256:abc123...",
  "dependencies": [
    {"domain": "federal.congress", "version": 51},
    {"domain": "state.virginia", "version": 14}
  ],
  "stats": {
    "total_claims": 12847,
    "claims_added": 3,
    "claims_updated": 1,
    "claims_removed": 0,
    "confidence_distribution": {
      "verified": 4201,
      "corroborated": 3892,
      "reported": 3104,
      "contested": 847,
      "unverified": 803
    },
    "total_chunks": 18432,
    "vector_backend": "faiss",
    "embedding_model": "gemini-embedding-001",
    "embedding_dimensions": 768
  },
  "test_results": {
    "fixtures_run": 200,
    "fixtures_passed": 200,
    "fixtures_failed": 0,
    "regression_tests_passed": true
  }
}
```

### 3.3 Chunk schema

Chunks are the unit of retrieval. Each chunk carries its
confidence metadata so consumers never need to look it up.

```sql
CREATE TABLE chunks (
    chunk_id        TEXT PRIMARY KEY,
    claim_ids       TEXT NOT NULL,     -- JSON array of source claim IDs
    content         TEXT NOT NULL,     -- retrieval-optimized text
    confidence      TEXT NOT NULL,     -- verified/corroborated/reported/
                                      -- contested/unverified
    category        TEXT NOT NULL,     -- from domain taxonomy
    valid_from      TEXT,
    valid_until     TEXT,
    source_summary  TEXT,             -- human-readable source attribution
    embedding       BLOB,             -- vector embedding (backend-dependent)
    metadata        TEXT              -- JSON: additional context
);
```

The key design: **confidence is baked into the chunk**, not
looked up at query time. When a worker retrieves chunks to
answer a question, the confidence level is right there. The
pedagogy Tutor can immediately decide whether to teach this
as established fact or as a contested position.

---

## 4. Golden Fixtures: The Test Suite

Golden fixtures are the knowledge equivalent of unit tests.
Each fixture is a question-answer pair with a known correct
answer, derived from verified (T1/T2) sources.

### 4.1 Fixture schema

```json
{
  "fixture_id": "f-001",
  "domain_id": "local.arlington",
  "question": "What was Arlington County's FY2026 general fund budget?",
  "expected_answer": "$1.47 billion",
  "expected_confidence": "verified",
  "source_claim_ids": ["c-1234"],
  "category": "governance.budget",
  "fixture_type": "factual",
  "created_at": "2026-01-15",
  "last_verified": "2026-03-01"
}
```

### 4.2 Fixture types

| Type | What it tests | Example |
|------|-------------|---------|
| **Factual** | Can the snapshot retrieve the correct fact? | "Who is the current county board chair?" |
| **Confidence** | Does the snapshot report the correct confidence level? | "Is the claim about the new transit line verified or reported?" |
| **Contradiction** | Does the snapshot correctly represent a disagreement? | "What are the two positions on the proposed rezoning?" |
| **Temporal** | Does the snapshot correctly filter by time? | "What was the 2024 tax rate?" (should not return 2025 rate) |
| **Regression** | Did a claim that was correct in v(N-1) stay correct in v(N)? | Auto-generated from previous passing fixtures |
| **Negative** | Does the snapshot correctly say "I don't know" when it should? | "What is the Mayor of Arlington?" (Arlington has no mayor) |

### 4.3 Test pass criteria

```yaml
test_criteria:
  # All fixtures must pass for the build to succeed
  factual_accuracy: 1.0       # 100% — no wrong facts

  # Confidence must match expected level
  confidence_accuracy: 0.95   # 95% — some tolerance for
                               # edge cases in confidence
                               # computation

  # No regressions: claims correct in previous version
  # must remain correct
  regression_pass_rate: 1.0   # 100% — no regressions

  # Negative fixtures: system must correctly decline
  negative_accuracy: 0.95     # 95%
```

A build that fails these criteria is not packaged. The build
ritual's `package` step has a `condition` that checks
`steps.test.result.passed`. Failed builds produce a test
report but no artifact.

### 4.4 Fixture maintenance

Fixtures are themselves knowledge — they can become outdated.
The `knowledge.refresh` ritual (from knowledge-acquisition.md)
includes a step to re-verify fixtures whose source claims have
been updated. When a fixture's expected answer changes because
the underlying fact changed (new budget year, new officeholder),
the fixture is updated, not deleted.

Fixture creation is partially automated: when a claim reaches
"verified" confidence, the system can generate candidate
fixtures. A human curator approves them. This keeps the test
suite growing with the knowledge base.

---

## 5. Deployment Pipeline

### 5.1 Deployment stages

Snapshots follow Grove's trust progression pattern:

```
Build passes tests
    │
    ▼
Staging (automatic)
    │ — full test suite re-run in production-like environment
    │ — diff report generated against current production snapshot
    │ — no user traffic
    │
    ▼
Canary (automatic if staging passes)
    │ — subset of queries (10%) served from new snapshot
    │ — answer quality compared to production snapshot
    │ — rollback if quality degrades
    │ — monitoring period: configurable (default 1 hour)
    │
    ▼
Production (automatic if canary holds, or manual approval)
    │ — all queries served from new snapshot
    │ — previous snapshot retained for rollback
    │
    ▼
Archive (after N+2 versions deployed)
    │ — old snapshots archived, not deleted
    │ — can be restored for historical queries
```

### 5.2 Ritual: `knowledge.deploy`

```yaml
id: ritual.knowledge.deploy
version: 1.0.0
description: >
  Deploy a built knowledge snapshot through staging, canary,
  and production.

params:
  - name: domain_id
    type: string
    required: true
  - name: snapshot_version
    type: integer
    required: true
  - name: snapshot_path
    type: string
    required: true
  - name: auto_promote
    type: boolean
    default: true
    description: "Auto-promote through stages if quality holds"

steps:
  - id: stage
    skill: kb.deploy.stage
    context_map:
      domain_id: "{{ params.domain_id }}"
      snapshot_path: "{{ params.snapshot_path }}"
      version: "{{ params.snapshot_version }}"

  - id: stage_test
    skill: kb.build.test
    depends_on: [stage]
    context_map:
      domain_id: "{{ params.domain_id }}"
      snapshot_path: "{{ steps.stage.result.staged_path }}"
      environment: "staging"

  - id: canary
    skill: kb.deploy.canary
    depends_on: [stage_test]
    condition: "{{ steps.stage_test.result.passed }}"
    context_map:
      domain_id: "{{ params.domain_id }}"
      version: "{{ params.snapshot_version }}"
      traffic_percentage: 10
      monitoring_minutes: 60

  - id: promote
    skill: kb.deploy.promote
    depends_on: [canary]
    condition: "{{ steps.canary.result.quality_held }}"
    context_map:
      domain_id: "{{ params.domain_id }}"
      version: "{{ params.snapshot_version }}"

  - id: archive
    skill: kb.deploy.archive
    depends_on: [promote]
    context_map:
      domain_id: "{{ params.domain_id }}"
      keep_versions: 3

output_map:
  deployed_version: "{{ steps.promote.result.version }}"
  rollback_version: "{{ steps.promote.result.previous_version }}"
  canary_report: "{{ steps.canary.result }}"
```

### 5.3 Rollback

Rollback is instant: point the query router at the previous
snapshot version. No rebuild required. The previous snapshot
is immutable and still on disk.

```yaml
id: ritual.knowledge.rollback
version: 1.0.0

params:
  - name: domain_id
    type: string
    required: true
  - name: target_version
    type: integer
    required: true
  - name: reason
    type: string
    required: true

steps:
  - id: verify_exists
    skill: kb.deploy.verify_snapshot
    context_map:
      domain_id: "{{ params.domain_id }}"
      version: "{{ params.target_version }}"

  - id: rollback
    skill: kb.deploy.promote
    depends_on: [verify_exists]
    condition: "{{ steps.verify_exists.result.exists }}"
    context_map:
      domain_id: "{{ params.domain_id }}"
      version: "{{ params.target_version }}"
      rollback: true
      reason: "{{ params.reason }}"

output_map:
  rolled_back_to: "{{ params.target_version }}"
  reason: "{{ params.reason }}"
```

### 5.4 Canary quality monitoring

During the canary window, the system compares answers from the
canary snapshot against the production snapshot for the same
queries:

| Metric | Threshold | Action on breach |
|--------|-----------|-----------------|
| Answer accuracy (vs. known fixtures) | ≥ 99% | Auto-rollback |
| Confidence level agreement with production | ≥ 95% | Flag for review |
| Retrieval latency (p99) | ≤ 1.5x production | Flag for review |
| New "I don't know" responses vs. production | ≤ 2% increase | Flag for review |

Any auto-rollback generates an incident report with the
specific queries that failed, linked to the changelog for
root cause analysis.

---

## 6. The Query Router

Workers don't know about snapshot versions. They query the
knowledge base through a skill (`kb.query`) that the query
router resolves to the correct snapshot.

### 6.1 Query flow

```
Worker calls kb.query(domain_id, question)
    │
    ▼
Query Router
    │
    ├── looks up active snapshot version for domain
    ├── routes 10% to canary (if active)
    │
    ▼
Snapshot v48 (or canary v49)
    │
    ├── vector search (via grove-kit VectorIndex) + FTS5
    ├── returns chunks with baked-in confidence
    │
    ▼
Worker receives answer with confidence metadata
```

### 6.2 Query skill

```python
@skill("kb.query", "1.0.0",
       description="Query the knowledge base",
       permissions=["READ"])
def query(self, context, handle):
    domain_id = context["domain_id"]
    question = context["question"]
    top_k = context.get("top_k", 5)
    min_confidence = context.get("min_confidence", "unverified")

    # Router resolves to active snapshot
    snapshot = self.router.resolve(domain_id)

    # Search
    chunks = snapshot.search(question, top_k=top_k,
                             min_confidence=min_confidence)

    return {
        "chunks": chunks,
        "snapshot_version": snapshot.version,
        "domain_id": domain_id
    }
```

Consumers never specify a snapshot version. They get the
current production version (or canary, if selected). This
decouples knowledge consumers from the build/deploy cycle
completely.

---

## 7. Changelog and Diff

Every snapshot includes a changelog: what changed from the
previous version. This serves three purposes:

1. **Audit** — what knowledge changed and why
2. **Communication** — downstream consumers can see what's new
3. **Debugging** — when a canary fails, the changelog points
   to the root cause

### 7.1 Changelog schema

```json
{
  "from_version": 47,
  "to_version": 48,
  "built_at": "2026-03-06T14:30:00Z",
  "triggered_by": ["claim.integrated:c-4892"],
  "changes": [
    {
      "type": "claim_added",
      "claim_id": "c-4892",
      "statement": "Arlington County approved $2.1M for the Lubber Run bridge replacement",
      "confidence": "verified",
      "source": "Arlington County Board meeting minutes, 2026-03-04"
    },
    {
      "type": "confidence_changed",
      "claim_id": "c-3201",
      "statement": "Proposed Route 50 bus rapid transit line",
      "old_confidence": "reported",
      "new_confidence": "corroborated",
      "reason": "Second independent source (Washington Post, 2026-03-05) confirmed VDOT study findings"
    },
    {
      "type": "contradiction_resolved",
      "contradiction_id": "x-17",
      "resolution": "County budget document (T1) confirms the project cost is $8.3M, not $12M as reported by local blog",
      "winning_claim": "c-2847",
      "losing_claim": "c-2901"
    }
  ],
  "stats": {
    "claims_added": 1,
    "claims_updated": 1,
    "claims_removed": 0,
    "contradictions_resolved": 1,
    "confidence_changes": 1
  }
}
```

---

## 8. Adapting Rituals and Rubrics per Domain

Different knowledge domains have different build
characteristics. A civic KB (Weft) has different freshness
requirements than a scientific frontier KB or a codebase KB
(Shep). The pipeline accommodates this through **domain
profiles** — configuration that tunes the rituals without
changing their structure.

### 8.1 Domain profiles

```yaml
# Civic community KB (Weft)
domain_profile: civic
  build_triggers:
    batch_window_seconds: 300
    immediate_triggers: [contradiction.resolved]
  test_criteria:
    factual_accuracy: 1.0
    regression_pass_rate: 1.0
  deploy:
    canary_traffic: 0.10
    canary_duration_minutes: 60
    auto_promote: true
  freshness:
    default_ttl_days: 90
    categories:
      governance.budget: 365     # annual
      governance.elections: 730  # biennial
      community.events: 30      # monthly refresh

# Scientific frontier KB
domain_profile: scientific
  build_triggers:
    batch_window_seconds: 3600   # hourly batches (papers publish in bursts)
    immediate_triggers: [contradiction.resolved, claim.confidence_changed]
  test_criteria:
    factual_accuracy: 1.0
    confidence_accuracy: 0.90   # more tolerance — frontier is inherently uncertain
    regression_pass_rate: 0.98  # some regression expected as understanding evolves
  deploy:
    canary_traffic: 0.10
    canary_duration_minutes: 120  # longer canary for higher stakes
    auto_promote: false            # human approval for science
  freshness:
    default_ttl_days: 365
    categories:
      preprint: 30               # preprints should be re-checked monthly
      peer_reviewed: 730         # peer-reviewed papers are more stable
      dataset: 365               # datasets update annually

# Codebase KB (Shep)
domain_profile: codebase
  build_triggers:
    batch_window_seconds: 60     # near-real-time after code changes
    immediate_triggers: [claim.integrated]
  test_criteria:
    factual_accuracy: 1.0
    regression_pass_rate: 1.0
  deploy:
    canary_traffic: 0.0          # no canary for code KBs — too fast-moving
    auto_promote: true
  freshness:
    default_ttl_days: 30         # code changes fast
    categories:
      architecture: 90           # architecture docs are more stable
      api: 30                    # API docs change with code
      review_practices: 180      # review norms change slowly

# Personal KB (Sil)
domain_profile: personal
  build_triggers:
    batch_window_seconds: 60
    immediate_triggers: [claim.integrated]
  test_criteria:
    factual_accuracy: 0.95       # personal knowledge is fuzzier
    regression_pass_rate: 0.95
  deploy:
    canary_traffic: 0.0
    auto_promote: true
  freshness:
    default_ttl_days: 180
```

### 8.2 Extensible rubrics

The test suite (golden fixtures) is the primary quality gate,
but domain profiles can add additional rubrics:

```yaml
# Additional rubrics for scientific domains
rubrics:
  - id: citation_coverage
    description: >
      What percentage of claims in the snapshot cite at least
      one peer-reviewed source?
    threshold: 0.80
    action_on_breach: warn  # don't fail the build, but flag it

  - id: frontier_labeling
    description: >
      Are claims at the frontier (within 12 months of publication,
      fewer than 3 independent confirmations) correctly labeled
      as "reported" or "unverified"?
    threshold: 0.95
    action_on_breach: fail  # this one matters — frontier must be honest

  - id: retraction_coverage
    description: >
      Have retracted papers been identified and their claims
      demoted or removed?
    threshold: 1.0
    action_on_breach: fail
```

---

## 9. Distributed Build Coordination

Knowledge is distributed across communities and domains.
Each domain runs its own build pipeline. Coordination
happens through snapshot dependencies and event propagation.

### 9.1 Dependency resolution

```
federal.congress (v51)
    │
    ├─── state.virginia (v14, depends on federal.congress ≥ v50)
    │        │
    │        └─── local.arlington (v48, depends on state.virginia ≥ v12)
    │
    └─── state.maryland (v22, depends on federal.congress ≥ v48)
             │
             └─── local.takoma_park (v31, depends on state.maryland ≥ v20)
```

When `federal.congress` publishes v52:
1. `state.virginia` receives `dependency.updated` event
2. Its build triggers with the new dependency version
3. If its build succeeds and deploys, `local.arlington`
   receives `dependency.updated` and builds in turn
4. Changes cascade down the DAG, but each domain decides
   independently when and whether to incorporate them

### 9.2 Cross-domain query federation

When a worker queries `local.arlington` and the answer
involves federal data (e.g., "What federal grants has
Arlington received?"), the query router can federate:

```
kb.query(domain="local.arlington",
         question="Federal grants received")
    │
    ▼
Local snapshot → finds claim referencing federal.congress:v51
    │
    ▼
Federated lookup → federal.congress snapshot
    │
    ▼
Combined result with provenance from both domains
```

Federation is transparent to the calling worker. The query
router handles it based on cross-domain references in the
claim graph.

---

## 10. How This Maps to Grove

| CI/CD concept | Grove implementation |
|--------------|---------------------|
| Change events | Orchestrator notifications from acquisition workers |
| Build triggers | Duty with event-based trigger (not just interval) |
| Build pipeline | Ritual DAG (`ritual.knowledge.build`) |
| Build workers | Standard Grove workers with `kb.build.*` skills |
| Golden fixtures | Same pattern as Canopy's 264 fixtures, Geeni's 62 |
| Snapshot versions | Numbered artifacts on filesystem/PVC |
| Staging/canary/production | Trust environments applied to data, not workers |
| Rollback | Pointer swap to previous immutable artifact |
| Quality monitoring | Coaching flywheel traces on build workers |
| Domain profiles | Configuration per community/domain KB |
| Dependency graph | Snapshot manifest + event propagation |
| Query routing | Thin skill layer resolving domain → active snapshot |

The deployment pipeline for knowledge snapshots mirrors the
deployment pipeline for workers. This is deliberate: Grove
already has the machinery for progressive trust, quality
gates, and instant rollback. Applying it to knowledge
artifacts requires no new infrastructure, only new workers
and rituals.

---

## 11. Open Questions

**How large can a snapshot get?** A well-populated civic KB
might have 50,000 claims and 100,000 chunks. Current backends
(FAISS, libSQL) handle this easily. But a scientific frontier
KB for all of biology
could have millions of claims. At some point, snapshots need
to be sharded by subdomain. The domain profile system
supports this, but the sharding strategy is unspecified.

**Should snapshots be shared across communities?** Two Weft
communities in the same state share state-level knowledge.
Should they share a state-level snapshot, or each build their
own copy? Shared snapshots save compute but create coupling.
Independent copies waste storage but isolate failures. The
dependency system supports both — this is a deployment
decision, not an architectural one.

**How do you version the embedding model?** When the embedding
model changes (e.g., from `text-embedding-3-small` to a
successor), all vector indexes must be rebuilt. This is a
breaking change that affects every snapshot. The manifest
records the embedding model, so the system can detect
incompatibility, but the migration path (rebuild all snapshots
vs. run dual indexes during transition) is unspecified.

**What about real-time knowledge?** Some facts change faster
than any build pipeline can follow (stock prices, weather,
live election results). These should not be in the snapshot
at all — they should be fetched live from authoritative APIs.
The boundary between "snapshot-worthy" and "fetch-live" is
domain-specific and needs clearer guidance.

---

*The evidence graph gives knowledge its integrity. The snapshot
gives knowledge its speed. The build pipeline gives knowledge
its reliability. Together, they make it possible to serve
trustworthy knowledge at the scale and latency that workers
and users need — without sacrificing the rigor that makes the
knowledge worth trusting in the first place.*
