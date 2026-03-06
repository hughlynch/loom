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
