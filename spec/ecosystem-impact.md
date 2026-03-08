# Loom: Ecosystem Impact Analysis

How Loom changes every grove-built expert, and how each
expert feeds back into Loom.

---

## The Core Shift

Every grove-built expert currently builds domain knowledge
in its own way. Geeni has a FAISS+SQLite index of EE docs.
Canopy has bug pattern taxonomies per species. Shep builds
codebase KBs. Sil maintains a personal vault. Cubby and
Yohumps are in design.

Loom does not replace these. It provides the **shared
infrastructure** underneath them: provenance chains,
confidence levels, evidence graphs, deterministic trust
computation, snapshot versioning, and adversarial resilience.

Each expert becomes a **Loom consumer** — querying knowledge
snapshots at inference time instead of raw data — and a
**Loom producer** — contributing domain-specific evidence
through the acquisition pipeline.

---

## 1. Geeni (Earth Engine Expert)

### Current state
- `gee_knowledge` worker: FAISS+SQLite index over EE docs,
  forum Q&A pairs, API references
- Knowledge is ingested once, queried via semantic search
- No provenance tracking, no confidence levels, no freshness

### With Loom

**As consumer:**
- GEE API docs become T2 (institutional data from Google)
- Forum answers become T5 (structured community input) or T6
  (unstructured) depending on verification
- RAG context injection pulls from Loom snapshots instead of
  raw FAISS index — each retrieved chunk carries a confidence
  badge
- When Geeni answers "use ee.Image.normalizedDifference()",
  the provenance chain traces to the API reference (T2,
  verified) vs. a forum suggestion (T5, reported)
- Outdated API methods (deprecated in newer EE versions) are
  caught by temporal validity windows

**As producer:**
- Geeni's benchmark results (103 golden fixtures) become T2
  evidence for "what GEE code patterns work"
- Forum answers validated by the benchmark feed back as
  corroborated claims
- Failed benchmark cases identify knowledge gaps — claims
  that the system "knows" but can't apply correctly

**Impact on workers:**
- `gee_knowledge` worker gains a `loom.kb.search` dependency
  for snapshot queries (replaces raw FAISS for production)
- Raw FAISS index remains for development/benchmark (hot path)
- New skill: `gee.knowledge.contribute` — push validated
  patterns into Loom's evidence graph

**Impact on rituals:**
- `gee_quality_monitor.json` feeds monitoring data into
  `loom.monitor.source_rates` (EE API change detection)
- Benchmark runs trigger `knowledge.refresh` for GEE claims
  whose validity depends on API version

---

## 2. Canopy (Code Review Expert)

### Current state
- `knowledge` worker: shared bug pattern taxonomy + design
  pattern index (FAISS+SQLite)
- Species-specific KBs per language (oak/birch/etc.)
- Practice KBs built from inline review comments per project
- 264 golden fixtures across 6 languages

### With Loom

**As consumer:**
- Bug patterns become claims with confidence levels:
  - Patterns mined from 10+ repos with consistent findings →
    verified
  - Patterns from 2-3 repos → corroborated
  - Single-repo patterns → reported
- Species reviewers query Loom snapshots for language-specific
  patterns, getting confidence-weighted results
- "This is a null-deref risk" carries different weight when
  backed by 15 mined examples (verified) vs. a single
  observation (reported)
- Contradictions surface: when oak says "always check nil"
  but practice KB for a specific repo says "this interface
  guarantees non-nil", the contradiction is explicit

**As producer:**
- Every mined bug-fix pair is T2 evidence (primary records:
  actual code commits with git provenance)
- Human review comments harvested by `mine.harvest_human_reviews`
  become T5 evidence (structured community input from verified
  developers)
- Expert review findings become T4 (expert analysis with
  methodology — the species rubric)
- Comparison pipeline (human vs AI) produces corroboration
  data: when human and AI agree, confidence rises

**Impact on workers:**
- `knowledge` worker's `canopy.kb.search_patterns` and
  `canopy.kb.search_bugs` gain Loom-backed alternatives
  for production (raw FAISS for benchmark, Loom for review)
- Species `base.py` gains a `contribute_finding()` method
  that pushes validated findings into Loom
- Expert worker's `canopy.expert.build_kb` becomes a Loom
  acquisition ritual (harvest practice KB → extract claims →
  classify → store)

**Impact on rituals:**
- `mine_bugs.md` becomes a Loom Harvester source: each mined
  bug-fix pair flows through the acquisition pipeline
- `compare_human_ai.md` becomes a corroboration ritual:
  agreement between human and AI reviewers elevates confidence
- New duty: `duty.canopy.pattern_freshness` — revalidate
  language patterns when language versions change (Go 1.25
  may invalidate Go 1.23 patterns)

---

## 3. Shep (Codebase KB)

### Current state
- Builds per-repo knowledge bases from code analysis
- Indexes code structure, dependencies, patterns
- Used for onboarding new developers and agents to a codebase

### With Loom

**As consumer:**
- Code structure facts become T1 claims (primary records:
  the code itself is the source of truth, content-hashed)
- Dependency relationships → T2 (institutional data from
  package managers)
- Architecture decisions from docs/comments → T3-T4
  depending on attribution
- "This function does X" is verified against the actual AST
- Stale documentation (comments that don't match code) become
  contradictions: the T1 source (code) overrides the T4
  source (comment)

**As producer:**
- Codebase analysis produces high-confidence claims about
  code structure that other experts can reference
- Cross-repo patterns (same anti-pattern in multiple repos)
  feed into Canopy's bug taxonomy as corroborating evidence
- API surface analysis feeds into Geeni when analyzing
  GEE client libraries

**Impact on workers:**
- Shep's indexing pipeline becomes a Loom acquisition ritual
  with the codebase as a T1 source
- Content hashing enables automatic freshness: when code
  changes, affected claims are re-evaluated
- Shep's query interface returns Loom confidence levels:
  "this function signature is verified (matches code)" vs.
  "this function's purpose is reported (from doc comment)"

---

## 4. Sil (Personal KB)

### Current state
- Personal vault with encrypted storage
- Gmail, calendar, document integration
- OAuth-secured per-user data

### With Loom

**As consumer:**
- Personal knowledge inherits Loom's provenance model:
  "you learned X from source Y on date Z"
- When Sil's tutor teaches a concept, it draws from Loom
  snapshots with confidence levels visible
- Personal notes become T5/T6 sources with appropriate
  weight — your memory of a meeting is valuable context
  but doesn't override the official minutes (T1)

**As producer:**
- Personal research contributes to community knowledge
  through explicit opt-in: "share this finding with Weft"
- Sil's expert delegation (`ask_expert` tool) routes to
  domain experts (Geeni, Canopy) who query Loom
- Reading lists and research notes become evidence for
  pedagogy: what the learner has already studied

**Impact on workers:**
- Sil's vault workers gain Loom integration for knowledge
  items (not private data — only explicitly shared research)
- Tutor functionality delegates to Loom's pedagogy framework:
  `loom.tutor.assess` replaces ad-hoc baseline detection
- Calendar/email remain Sil-specific (private, not knowledge)

**Impact on rituals:**
- Personal learning paths are Loom pedagogy rituals
  parameterized per user
- "Morning briefing" can include Loom knowledge updates:
  "3 claims you follow were updated yesterday"

---

## 5. Cubby (Civic Journalism)

### Current state
- In design: AI-assisted local journalism
- Will report on city council votes, budgets, public records

### With Loom

**As consumer (primary consumer):**
- Cubby is Loom's flagship consumer. Every fact in a Cubby
  report must trace to the evidence graph
- Reporter workers query Loom snapshots, not raw sources
- Confidence levels are **visible in output**: readers see
  whether a claim is verified, corroborated, or reported
- Contradictions are **reported as news**: "Sources disagree
  on whether the project will cost $4M or $6M. Here's what
  each source says."

**As producer:**
- Reporting uncovers new sources: a FOIA response, a public
  comment at a meeting, a previously unknown budget document
- Each new source flows through the acquisition pipeline
- Community response to Cubby reports triggers the challenge
  process: "That's not what happened at the meeting" →
  `knowledge.contest`
- Reporter fact-checks are high-quality corroboration events

**Impact on architecture:**
- Cubby's reporting pipeline is a Loom ritual consumer:
  `knowledge.acquire` → `loom.snapshot.build` → reporter
  queries snapshot → article generation
- Cubby does not maintain its own KB — it queries Loom
- Cubby's editorial decisions (what to report, how to frame)
  are separate from Loom's evidence (what the sources say)

**Unique requirements Cubby places on Loom:**
- **Timeliness**: city council votes tonight, Cubby reports
  tomorrow. Snapshot build must be fast enough for news cycles
- **Attribution format**: Cubby needs evidence formatted for
  human readers, not agents. Provenance chains become
  "according to [source]" citations
- **Correction workflow**: when Cubby publishes a correction,
  the correction flows back into Loom as a post-mortem

---

## 6. Yohumps (Civic Engagement)

### Current state
- In design: voter information, representative lookup,
  legislative tracking
- Uses Congress.gov API for federal data

### With Loom

**As consumer:**
- Legislator voting records → T1 (primary records from
  congress.gov, state legislature sites)
- Bill text → T1 (official legislation)
- Legislator positions → T3-T5 (reported from news,
  campaign materials, public statements)
- "How did my representative vote?" is a verified claim
  backed by T1 evidence
- "What does my representative think about X?" is a
  reported/contested claim — Loom surfaces the evidence
  rather than asserting a position

**As producer:**
- Constituent interactions (questions asked, issues raised)
  become T5 evidence for community priorities
- Verified voter information becomes reusable across
  communities (one congress.gov harvest serves all users)

**Impact on architecture:**
- Yohumps' Congress.gov API worker becomes a Loom Harvester
  specialization: `harvest.api` with congress.gov-specific
  parsing
- Legislative tracking is a `knowledge.refresh` duty
  parameterized for legislative sources
- Zip-code lookup results are cached as verified claims
  (redistricting changes trigger temporal validity expiry)

---

## Cross-cutting Impacts

### 1. Shared evidence graph

Multiple experts contribute to and consume from the same
evidence graph. This enables:

- **Cross-domain corroboration**: Geeni validates a GEE
  pattern, Canopy finds the same pattern in a Go client
  library → corroboration across experts
- **Knowledge reuse**: Shep indexes a codebase, Canopy
  reviews PRs against it, Geeni answers questions about
  it — all querying the same Loom snapshot
- **Contradiction surfacing**: when experts disagree (Shep
  says function X does Y, Canopy says it's a bug pattern),
  the disagreement is explicit and traceable

### 2. Unified pedagogy

Every expert that teaches — Geeni explaining EE concepts,
Canopy explaining code review findings, Sil tutoring a
user, Cubby providing civic context — uses Loom's pedagogy
framework:

- **Consistent assessment**: `loom.tutor.assess` works the
  same whether teaching GEE or civic processes
- **Shared concept maps**: prerequisites and dependencies
  are tracked in Loom, enabling cross-domain learning paths
- **Adaptive difficulty**: all tutoring adapts to the
  learner's demonstrated mastery level

### 3. Unified adversarial resilience

Every expert inherits Loom's defenses:

- Evidence hierarchy protects against poisoning regardless
  of whether the poison targets GEE docs or civic records
- Challenge process applies to any claim in any expert's
  domain
- Error post-mortems follow the same template whether the
  error was in code review or voter information
- Anti-pattern monitoring catches `authority_laundering`
  in any domain

### 4. Model routing integration

Loom workers can specify `model_preference` on steps:

- Extraction (LLM-heavy): `most_capable` or `sonnet`
- Classification (rules-heavy, LLM-light): `fastest` or
  `flash`
- Adjudication (judgment-heavy): `most_capable` or `opus`
- Tutoring (generation-heavy): `sonnet`
- Monitoring (deterministic): `deterministic` (no LLM)

### 5. Coaching flywheel

Loom workers participate in grove's coaching flywheel:

- Harvester anti-patterns: fetching blocked sources,
  ignoring robots.txt, duplicate harvests
- Extractor anti-patterns: claim inflation, precision
  theater, missing context
- Classifier anti-patterns: tier inflation (classifying
  blogs as T3), domain verification bypass
- Corroborator anti-patterns: false independence
  (counting syndicated sources as independent)
- Curator anti-patterns: partisan_resolution,
  authority_override (from adversarial spec)

---

## Migration Path

Existing experts don't need to migrate all at once.
The integration is incremental:

**Phase 1 — Schema + core workers (Loom standalone)**
Loom works independently. No existing expert changes.

**Phase 2 — KB worker integration**
Experts that have knowledge workers (geeni `gee_knowledge`,
canopy `knowledge`) migrate to grove-kit's `VectorIndex`
abstraction (see `grove-kit/spec/vector-search-abstraction.md`).
FAISS backend for development/benchmark. Loom snapshots
(FAISS or libSQL backend) for production queries. The
abstraction makes the backend swap a configuration change,
not a code rewrite.

**Phase 3 — Acquisition pipeline integration**
Expert-specific ingestion (geeni doc ingestion, canopy bug
mining) flows through Loom's acquisition pipeline. This adds
provenance, confidence, and freshness tracking to existing
knowledge.

**Phase 4 — Pedagogy integration**
Experts that teach (geeni, sil, cubby) delegate to Loom's
tutor framework. Assessment and mastery tracking become
shared infrastructure.

**Phase 5 — Adversarial hardening**
Challenge process, rate limiting, and curator accountability
activate. Relevant mainly for community-facing experts
(cubby, yohumps, weft).

---

## What Does NOT Change

- **Worker ownership**: each expert owns its domain workers.
  Geeni's GEE expert is not a Loom worker. It *queries* Loom.
- **Domain logic**: how Canopy reviews code, how Geeni
  generates EE scripts — this is expert business logic,
  not knowledge infrastructure
- **Private data**: Sil's vault, user emails, calendar —
  private data stays in Sil. Loom handles *knowledge*, not
  *personal data*
- **Deployment**: each expert deploys independently. Loom
  is a dependency, not a monolith
- **Benchmarks**: golden fixtures remain per-expert. Loom
  adds a shared quality framework on top, it doesn't
  replace domain-specific evaluation
