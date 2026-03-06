# Loom Design Journal

## 2026-03-06: Project inception

Loom created as a standalone repo from specs originally
developed in abwp (commit 091c17d on branch
claude/knowledge-acquisition-system-RJu7y).

Four founding specs:
- knowledge-acquisition.md — evidence hierarchy, provenance, confidence
- knowledge-ci.md — snapshot build/test/deploy pipeline
- pedagogy.md — adaptive teaching framework
- loom-adversarial-resilience.md — threat model and defenses

Scaffolded with 10 workers, 7 rituals, evidence graph schema,
and configuration files. All workers follow the grove UWP
pattern (Python, grove.uwp SDK).

Next: Phase 1 foundation — get the core acquisition pipeline
working end-to-end with a single golden fixture.

## 2026-03-06: Prior art research complete

Comprehensive research across 5 domains, 20+ systems:

**Fact-checking:** IFCN Code of Principles, ClaimReview
schema, Snopes, PolitiFact, Full Fact AI. Key finding:
ClaimReview as export format; claim-type classification
before confidence (Full Fact's BERT pipeline); multi-editor
voting for high-stakes adjudication (PolitiFact).

**Intelligence:** Admiralty Code dual-axis model, ICD 203
analytic standards, structured analytic techniques (ACH),
Sherman Kent estimative language. Key finding: T1-T7
conflates source reliability with information credibility.
Dual-axis evaluation needed. Confidence ≠ probability
(ICD 203). Verbal probability terms are dangerously ambiguous
(Kent found "probable" interpreted as 20-95%).

**Scientific:** Cochrane systematic reviews, GRADE framework,
IPCC confidence language, EBM hierarchy, PRISMA. Key finding:
source tier is a starting point, not a verdict — GRADE-like
up/down factors adjust. IPCC's evidence×agreement matrix
(3×3→5 confidence levels) is more expressive than binary
"contested." Probability terms require high confidence.

**Legal/provenance:** Federal Rules of Evidence, Wikidata,
C2PA, FAIR data principles, Schema.org. Key finding:
hearsay hierarchy encodes *reasons* for reliability (not
just rank). Chain of custody = provenance chains. Wikidata's
deprecate-never-delete model. C2PA's created vs gathered
distinction. FAIR demands persistent IDs and standard
vocabularies.

**Epistemic:** Bayesian epistemology, Dung argumentation,
TMS/ATMS, Toulmin model, justification logic. Key finding:
Loom's evidence graph IS a truth maintenance system. ATMS
labels enable "what-if" queries. Toulmin reveals a gap:
Loom tracks THAT evidence supports a claim but not WHY
(the warrant). Justification logic's Realization Theorem
proves provenance is epistemologically necessary, not
bookkeeping.

Synthesized into 10 architectural recommendations with
4-phase implementation plan. See `architectural-recommendations.md`.

Next: Apply Phase 1 recommendations (ClaimReview export,
claim-type classification, process documentation, temporal
model, source re-certification) without architecture changes.
Then Phase 2 dual-axis schema upgrade.

## 2026-03-06: Phase 1 foundation complete (momentum i0)

Core pipeline working end-to-end: harvest → classify →
corroborate → store → query. Golden fixture test exercises
the full chain with census.gov content.

Real implementations:
- harvest.web: HTTP fetch, HTML→text, SHA-256 content hash
- classify.source_tier: domain-verified T1/T2
- corroborate.check: deterministic confidence (tier×status)
- KB: SQLite evidence graph with version tracking

44 Go E2E + 19 Python pipeline tests, all green.

## 2026-03-06: Momentum i1 — widen the pipeline

Made harvest.api real (HTTP with JSON parsing, method/headers/
body support). Expanded classifier domain lists: T3 news
(AP, Reuters, BBC, NYT, etc.), T4 expert (Nature, arXiv,
Pew, etc.), T6 social (Reddit, Twitter, Medium, etc.).
22 Python tests now.

Design decision: domain-based classification is a fast first
pass. The rubric scoring (editorial_oversight, author_credentials,
etc.) remains stubbed — it needs content analysis (LLM or
heuristic) which is iteration 2+ work. Domain lists are
deliberately conservative: better to default T5 and upgrade
via rubric than to over-classify.
