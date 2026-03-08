# Loom — The ABWP Knowledge System

Evidence-based knowledge acquisition, CI/CD, pedagogy,
and adversarial resilience. The machine that holds
evidence threads in tension and produces coherent,
trustworthy fabric from them.

Lives at `~/loom` (GitHub: `hughlynch/loom`).
Depends on **grove** (`hugh-lynch/grove`) for the
orchestrator, SDK, and generic workers, and
**grove-kit** (`hugh-lynch/grove-kit`) for shared
KB infrastructure.

## Build and Test Commands

```bash
# Go E2E tests
/usr/local/go/bin/go test -C /home/hughlynch/loom \
  ./test/e2e/ -count=1 -v

# Python unit tests
PYTHONPATH=/home/hughlynch/grove/python \
  python3 -m pytest /home/hughlynch/loom/test/ -v

# Lint Python workers
python3 -m py_compile workers/harvester/worker.py
python3 -m py_compile workers/extractor/worker.py
# ... etc
```

## Architecture

```
loom/
  workers/
    harvester/      Source retrieval (web, API, document)
    extractor/      Claim extraction from content (LLM-backed)
    classifier/     Source tier + topic + temporal classification
    corroborator/   Cross-reference against KB, contradiction detection
    adjudicator/    Contradiction resolution, challenge triage
    curator/        Human-in-the-loop review
    kb/             Evidence graph query and storage (SQLite)
    snapshot/       Knowledge snapshot build, test, promote
    tutor/          Adaptive pedagogy (assess, teach, verify)
    monitor/        System health (source rates, challenge health)

  schema/           Evidence graph SQL schema + migrations
  configs/          Evidence hierarchy, confidence rules, rubrics
  rituals/          Ritual DAGs (acquire, refresh, audit, contest, etc.)
  spec/             Design specs (4 founding documents)
  test/e2e/         Go E2E tests
  test/fixtures/    Golden test data
```

## Worker Skill Map

| Worker | Skills | Status |
|--------|--------|--------|
| Harvester | `harvest.web`, `harvest.api`, `harvest.document` | web+api real, document stub |
| Extractor | `extract.claims`, `extract.entities`, `extract.relationships` | all real (hybrid LLM + heuristic, i15) |
| Classifier | `classify.source_tier`, `classify.claim_type`, `classify.topic`, `classify.temporal_validity` | tier+claim_type+temporal real, topic stub |
| Corroborator | `corroborate.check`, `corroborate.find_contradictions`, `corroborate.claim_review`, `corroborate.structured_disagreement` | all real (deterministic) |
| Adjudicator | `adjudicate.resolve`, `adjudicate.escalate`, `adjudicate.triage_challenge`, `adjudicate.ach`, `adjudicate.devils_advocate`, `adjudicate.dung_semantics` | all real (deterministic) |
| Curator | `curate.review`, `curate.approve`, `curate.reject` | all stubs |
| KB | `loom.kb.search`, `loom.kb.query_claim`, `loom.kb.claim_history`, `loom.kb.store_claim`, `loom.kb.update_claim`, `loom.kb.find_similar`, `loom.kb.record_contradiction`, `loom.kb.retract_source`, `loom.kb.build_labels`, `loom.kb.sensitivity`, `loom.kb.expiring_claims`, `loom.kb.find_orphans`, `loom.kb.find_expired`, `loom.kb.stale_contradictions`, `loom.kb.source_health`, `loom.kb.integrity_report`, `loom.kb.events_since`, `loom.kb.event_count` | all real (SQLite + vector search, i12/i14) |
| Snapshot | `loom.snapshot.build`, `loom.snapshot.test`, `loom.snapshot.promote`, `loom.snapshot.query`, `loom.snapshot.check_trigger`, `loom.snapshot.build_if_needed` | all real (FTS5, quality gates, event-driven, i11/i13) |
| Tutor | `loom.tutor.assess`, `loom.tutor.teach`, `loom.tutor.verify` | all real (KB-backed, LLM optional, i16) |
| Monitor | `loom.monitor.source_rates`, `loom.monitor.challenge_health`, `loom.monitor.system_health` | all real (SQLite read-only, anomaly detection, i17) |

## Pipeline CLI

```bash
# Acquire claims from a URL
PYTHONPATH=~/grove/python python3 pipeline.py https://www.usa.gov/about-the-us

# With custom DB and claim limit
PYTHONPATH=~/grove/python python3 pipeline.py https://apnews.com/article/123 \
  --db /tmp/loom.db --max-claims 20
```

## Evidence Hierarchy (T1-T7)

| Tier | Type | Weight |
|------|------|--------|
| T1 | Primary records (gov filings, court records) | Highest |
| T2 | Institutional data (census, EPA, election results) | High |
| T3 | Authoritative reporting (newspapers, wire services) | Moderate-High |
| T4 | Expert analysis (academic papers, think tanks) | Moderate |
| T5 | Structured community input (verified resident reports) | Moderate |
| T6 | Unstructured digital content (blogs, social, forums) | Low |
| T7 | Anonymous/unverified | Lowest |

## Confidence Levels

verified > corroborated > reported > contested > unverified

Computed deterministically from the evidence graph (not LLM judgment).

## Rituals

| Ritual | Trigger | Purpose |
|--------|---------|---------|
| `knowledge.acquire` | On-demand | Full acquisition pipeline |
| `knowledge.refresh` | Scheduled (daily/weekly/monthly by tier) | Re-verify expiring claims |
| `knowledge.audit` | Scheduled (weekly) | Integrity check |
| `knowledge.cross_examine` | On-demand (high-stakes) | Active verification |
| `knowledge.contest` | Community challenge | Challenge process |
| `loom.snapshot.build` | After knowledge changes | Build immutable snapshot |
| `loom.post_mortem` | On significant error | Error investigation |

## Anti-patterns

### Knowledge acquisition
authority_laundering, consensus_manufacturing, temporal_confusion,
precision_theater, missing_denominator, survivorship_sourcing

### Adversarial defense
trust_by_assertion, neutrality_theater, error_burial,
challenge_suppression, authority_capture

## Bootstrapping (MCP Context)

```
manage_policy(action="set", preset="personal-permissive")

spawn_worker(command="python3",
    args=["workers/harvester/worker.py"],
    dir="/home/hughlynch/loom",
    env=["PYTHONPATH=/home/hughlynch/grove/python"],
    worker_id="loom-harvester-1")

# Repeat for each worker...
```

## Momentum State

State files:
- `rubric.json` — Change evaluation rubric (v2.0.0)
- `evaluations.jsonl` — Evaluation log (append-only)
- `spec/loom-design-journal.md` — Design journal
- `next-plan.md` — Current iteration plan

## Permission Profile

| Category | Pattern | Rationale |
|----------|---------|-----------|
| Grove MCP | `mcp__grove` | Orchestrator tools |
| Git | `Bash(git *)` | Momentum loop |
| Go | `Bash(/usr/local/go/bin/go *)` | E2E tests |
| Python | `Bash(python3 *)`, `Bash(PYTHONPATH=*)` | Worker execution |
| Utilities | `Bash(echo/ls/grep/wc *)` | Inspection |

## Model Configuration

| Variable | Scope | Default |
|----------|-------|---------|
| `LOOM_MODEL` | LLM-backed workers (extractor, tutor) | `claude-haiku-4-5-20251001` |
| `LOOM_MODEL_PRO` | High-stakes operations (adjudicator) | `claude-sonnet-4-6` |

## Dependencies

- **grove**: Orchestrator, Python SDK (`grove.uwp`)
- **grove-kit**: KB infrastructure, embeddings

## Reading Order

1. This file (AGENTS.md)
2. `spec/knowledge-acquisition.md` — Core framework
3. `spec/knowledge-ci.md` — Snapshot pipeline
4. `spec/pedagogy.md` — Teaching framework
5. `spec/loom-adversarial-resilience.md` — Threat model
6. `schema/evidence.sql` — Evidence graph schema
7. `workers/harvester/worker.py` — Entry point
8. `workers/corroborator/worker.py` — Confidence computation
9. `configs/evidence_hierarchy.json` — Tier definitions
