# Knowledge Acquisition: A Framework for Building Reliable Knowledge from Unreliable Sources

**Author:** Hugh Lynch, with Claude
**Date:** 2026-03-06
**Part of:** Loom — the ABWP Knowledge System
**Applies to:** Cubby (civic journalism), Weft (community data), Shep (repo KB), Sil (personal KB), and any Grove worker that builds domain expertise from digital sources
**See also:** Knowledge CI/CD (`spec/knowledge-ci.md`), Pedagogy (`spec/pedagogy.md`), Adversarial Resilience (`spec/loom-adversarial-resilience.md`)

---

## The Problem

The digital world is the primary source for building domain
knowledge. It is also saturated with misinformation (wrong by
accident), disinformation (wrong by design), genuine expert
disagreement, outdated information that was once correct, correct
information presented without context, and context presented
without evidence.

Any system that acquires knowledge from digital sources and
presents it as authoritative — Cubby reporting on a city council
vote, Weft assembling a community portrait, Shep building a
codebase KB — must have a principled answer to the question:
*why should anyone trust what this system says?*

The answer cannot be "because the AI said so." That is the
epistemic equivalent of "because Google ranked it first." The
answer must be structural: the system's architecture makes
reliability visible, contestable, and improvable.

This document proposes strategies, rituals, and rubrics for
knowledge acquisition that apply across the ABWP ecosystem.

---

## 1. Core Principles

Six principles govern knowledge acquisition. They parallel
Grove's six design principles — both are about building
trustworthy systems from untrusted components.

**K1. Every claim has a provenance chain.** No fact enters the
knowledge base without a traceable path back to its source.
The chain records: where the information came from, when it
was retrieved, what transformations were applied (summarization,
extraction, classification), and what the original source
actually said. If the chain breaks, the claim is demoted, not
deleted — it becomes an unverified assertion rather than a
sourced fact.

**K2. Sources are first-class objects, not strings.** A source
is not a URL. It is a structured entity with: origin (who
published it), type (primary record, news report, opinion,
academic paper, social media post, government filing),
retrieval timestamp, content hash, and a reliability assessment
that evolves over time. Treating sources as objects enables
cross-referencing, contradiction detection, and source-level
reputation.

**K3. Confidence is explicit, not binary.** Every knowledge
claim carries a confidence level: verified, corroborated,
reported, contested, or unverified. The system never presents
contested information as settled. When experts genuinely
disagree, the system represents the disagreement rather than
picking a side. Confidence is computable from the evidence
graph, not a subjective LLM judgment.

**K4. Contradictions are features, not bugs.** When two sources
disagree, the system does not silently pick one. It records the
contradiction, links both sources, and surfaces it for
resolution — either by finding additional evidence, by
consulting authoritative primary sources, or by presenting
the disagreement transparently. Contradictions are the primary
signal for where knowledge needs work.

**K5. Freshness is a dimension of truth.** Information decays.
A city council member's voting record from 2023 may be accurate
but misleading if their positions shifted in 2025. Budget
numbers are only valid for a fiscal year. Population estimates
update annually. Every claim has a temporal validity window, and
the system actively identifies and re-verifies claims approaching
expiration.

**K6. Human judgment is the appeals court.** Automated
acquisition handles volume. Human curation handles judgment.
When the system encounters genuine ambiguity — contested
claims, contradictory primary sources, edge cases in
classification — it surfaces these for human review rather
than resolving them algorithmically. The human's resolution
becomes a training signal for future cases.

---

## 2. The Evidence Hierarchy

Not all sources are equal. The system maintains a hierarchy
that determines how much weight a source carries. Higher-tier
sources can override lower-tier sources when they conflict.

| Tier | Source Type | Examples | Weight |
|------|-----------|----------|--------|
| **T1: Primary records** | Official documents with legal standing | Government filings, court records, legislation text, certified meeting minutes, property records, inspection reports | Highest |
| **T2: Institutional data** | Structured data from authoritative institutions | Census data, EPA measurements, school enrollment figures, financial disclosures, election results | High |
| **T3: Authoritative reporting** | Journalism with editorial standards and accountability | Established newspapers, wire services (AP, Reuters), public broadcasting | Moderate-High |
| **T4: Expert analysis** | Domain expertise with credentials and methodology | Academic papers, think tank reports (with disclosed funding), professional associations | Moderate |
| **T5: Structured community input** | Verified local knowledge with identity accountability | Resident reports on Weft (verified identity), community board testimony, public comment (attributed) | Moderate |
| **T6: Unstructured digital content** | General web content without editorial standards | Blog posts, social media, forums, wikis (non-Wikipedia), press releases, marketing materials | Low |
| **T7: Anonymous/unverified** | Content with no accountability chain | Anonymous posts, unattributed claims, forwarded content with no original source | Lowest |

### Weight application rules

- A T1 source overrides any number of T6 sources on the same
  claim. The city's official budget document settles what the
  budget is, regardless of how many blog posts say otherwise.
- Multiple independent T3 sources corroborating each other
  elevate a claim's confidence above any single T3 source.
- A T6 source that *links to* a T1 source inherits no weight —
  the system follows the link and evaluates the T1 source
  directly. The intermediary is recorded for provenance but
  doesn't contribute authority.
- Source tier is not fixed per outlet — it is per claim. The New
  York Times reporting on a city council vote (T3) is different
  from its editorial board's opinion on what the council should
  do (T4/T6 depending on the claim).

---

## 3. The Acquisition Pipeline

Knowledge acquisition is a ritual — a DAG of workers, each
with a specific role, composed through Grove's ritual engine.

### 3.1 Workers

| Worker | Role | Key Skills |
|--------|------|------------|
| **Harvester** | Retrieves raw content from sources | `harvest.web`, `harvest.api`, `harvest.document` |
| **Extractor** | Pulls structured claims from raw content | `extract.claims`, `extract.entities`, `extract.relationships` |
| **Classifier** | Categorizes claims and sources | `classify.source_tier`, `classify.topic`, `classify.temporal_validity` |
| **Corroborator** | Cross-references claims against existing KB and other sources | `corroborate.check`, `corroborate.find_contradictions` |
| **Adjudicator** | Resolves contradictions using the evidence hierarchy | `adjudicate.resolve`, `adjudicate.escalate` |
| **Curator** | Human-in-the-loop review for contested or ambiguous claims | `curate.review`, `curate.approve`, `curate.reject` |

### 3.2 Ritual: `knowledge.acquire`

```yaml
id: ritual.knowledge.acquire
version: 1.0.0
description: >
  Acquire, validate, and integrate knowledge from a source
  into the knowledge base with full provenance.

params:
  - name: source_url
    type: string
    required: true
  - name: source_type
    type: string
    default: "auto"
  - name: community_id
    type: string
    required: true
  - name: topic_hint
    type: string
    required: false

steps:
  - id: harvest
    skill: harvest.web
    context_map:
      url: "{{ params.source_url }}"
      community_id: "{{ params.community_id }}"

  - id: classify_source
    skill: classify.source_tier
    depends_on: [harvest]
    context_map:
      content: "{{ steps.harvest.result.content }}"
      url: "{{ params.source_url }}"
      source_type: "{{ params.source_type }}"

  - id: extract
    skill: extract.claims
    depends_on: [harvest, classify_source]
    context_map:
      content: "{{ steps.harvest.result.content }}"
      source_tier: "{{ steps.classify_source.result.tier }}"
      topic_hint: "{{ params.topic_hint }}"

  - id: corroborate
    skill: corroborate.check
    depends_on: [extract]
    for_each: "{{ steps.extract.result.claims }}"
    context_map:
      claim: "{{ item }}"
      community_id: "{{ params.community_id }}"
      source_tier: "{{ steps.classify_source.result.tier }}"

  - id: adjudicate
    skill: adjudicate.resolve
    depends_on: [corroborate]
    context_map:
      corroboration_results: "{{ steps.corroborate.result }}"
      community_id: "{{ params.community_id }}"

  - id: escalate
    skill: curate.review
    depends_on: [adjudicate]
    condition: "{{ steps.adjudicate.result.contested | length }}"
    context_map:
      contested_claims: "{{ steps.adjudicate.result.contested }}"
      community_id: "{{ params.community_id }}"

output_map:
  integrated: "{{ steps.adjudicate.result.integrated }}"
  contested: "{{ steps.adjudicate.result.contested }}"
  rejected: "{{ steps.adjudicate.result.rejected }}"
  source_record: "{{ steps.classify_source.result }}"
```

---

## 4. Confidence Levels and the Evidence Graph

### 4.1 Confidence levels

| Level | Meaning | Requirements |
|-------|---------|-------------|
| **Verified** | Confirmed against primary records | Claim matches a T1 or T2 source directly, content hash verifiable |
| **Corroborated** | Multiple independent sources agree | 2+ independent sources at T3 or above, no contradicting sources at higher tier |
| **Reported** | Single credible source, no contradiction | 1 source at T3 or above, or 2+ at T4/T5, no contradicting evidence found |
| **Contested** | Sources disagree on this claim | At least one source supports and one contradicts; requires explicit representation of both positions |
| **Unverified** | Sourced but not cross-checked | Claim has provenance but has not been corroborated or checked against higher-tier sources |

### 4.2 Evidence graph schema

```sql
-- Source registry
CREATE TABLE sources (
    source_id       TEXT PRIMARY KEY,
    url             TEXT,
    origin          TEXT NOT NULL,     -- publisher/institution
    source_type     TEXT NOT NULL,     -- primary_record, news, opinion...
    tier            INTEGER NOT NULL,  -- 1-7 per hierarchy
    first_seen      TEXT NOT NULL,
    last_verified   TEXT NOT NULL,
    content_hash    TEXT,              -- SHA-256 of retrieved content
    reliability     REAL DEFAULT 0.5,  -- 0-1, updated over time
    metadata        TEXT               -- JSON: author, publication date, etc.
);

-- Claims: atomic knowledge assertions
CREATE TABLE claims (
    claim_id        TEXT PRIMARY KEY,
    statement       TEXT NOT NULL,     -- natural language assertion
    normalized      TEXT,              -- canonical form for dedup
    category        TEXT NOT NULL,
    confidence      TEXT NOT NULL,     -- verified/corroborated/reported/
                                      -- contested/unverified
    valid_from      TEXT,              -- temporal validity start
    valid_until     TEXT,              -- temporal validity end
    community_id    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    superseded_by   TEXT,              -- claim_id that replaced this
    chunk_ids       TEXT               -- JSON: linked KB chunks
);

-- Evidence links: connects claims to sources
CREATE TABLE evidence (
    evidence_id     TEXT PRIMARY KEY,
    claim_id        TEXT NOT NULL REFERENCES claims(claim_id),
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    relationship    TEXT NOT NULL,     -- supports, contradicts,
                                      -- partially_supports, contextualizes
    excerpt         TEXT,              -- relevant passage from source
    retrieved_at    TEXT NOT NULL,
    transformation  TEXT,              -- how claim was derived: verbatim,
                                      -- summarized, inferred, extracted
    UNIQUE(claim_id, source_id, relationship)
);

-- Contradictions: explicit disagreement records
CREATE TABLE contradictions (
    contradiction_id TEXT PRIMARY KEY,
    claim_a_id       TEXT NOT NULL REFERENCES claims(claim_id),
    claim_b_id       TEXT NOT NULL REFERENCES claims(claim_id),
    nature           TEXT NOT NULL,    -- factual, interpretive,
                                      -- temporal, definitional
    resolution       TEXT,             -- null until resolved
    resolved_by      TEXT,             -- source_id or curator_id
    resolved_at      TEXT,
    notes            TEXT
);
```

### 4.3 Confidence computation

Confidence is computed from the evidence graph, not assigned by
an LLM. The rules are deterministic:

```
if any T1/T2 source supports AND no T1/T2 source contradicts:
    confidence = "verified"

elif 2+ independent T3+ sources support AND none contradict at higher tier:
    confidence = "corroborated"

elif any source supports AND any source contradicts:
    confidence = "contested"
    → create contradiction record

elif 1 T3+ source supports OR 2+ T4/T5 sources support:
    confidence = "reported"

else:
    confidence = "unverified"
```

Independence is determined by publisher/origin. Two articles
from the same newspaper are not independent. An AP wire story
and a local paper that reprinted it are not independent. The
system tracks syndication chains.

---

## 5. Strategies for Common Threats

### 5.1 Misinformation (wrong by accident)

**Signal:** Claim conflicts with primary records or higher-tier
sources.

**Strategy:** Cross-reference against the evidence hierarchy.
When a lower-tier source contradicts a higher-tier source, the
system:
1. Records the contradiction
2. Defaults to the higher-tier source
3. Flags the lower-tier source's reliability for review
4. Does not delete the incorrect claim — marks it as
   superseded with a link to the correcting evidence

**Example:** A blog post claims the school budget increased 15%.
The district's published budget document shows 8%. The system
records both, marks the blog's claim as contradicted by T1
evidence, and surfaces the verified figure.

### 5.2 Disinformation (wrong by design)

**Signal:** Repeated false claims from the same source,
coordinated timing, claims that cannot be traced to any primary
source.

**Strategy:**
1. **Source reputation tracking.** Sources that repeatedly
   produce claims contradicted by higher-tier evidence see
   their reliability score degrade. Below a threshold, new
   claims from that source enter the KB as "unverified"
   regardless of content.
2. **Provenance depth.** Claims that cite other claims that cite
   other claims without ever reaching a primary source are
   flagged. The system measures *provenance depth* — how many
   hops to a T1/T2 source. Deep chains with no primary anchor
   are suspicious.
3. **Coordinated inauthenticity detection.** Multiple sources
   making the same novel claim within a short window, especially
   if the sources share origin characteristics (registered same
   day, similar naming patterns, no history), triggers a
   coordination flag.
4. **No automated suppression.** The system flags but never
   silently removes. Suppression is a human decision. The
   system's job is to make the evidence structure visible so
   humans can judge.

### 5.3 Genuine disagreement

**Signal:** Multiple credible sources at the same tier disagree.

**Strategy:** Represent the disagreement, don't resolve it.
The system:
1. Creates a contradiction record with `nature: "interpretive"`
   or `nature: "definitional"`
2. Presents both positions with their evidence
3. Identifies the *axis of disagreement* — what factual
   question, if answered, would resolve it
4. Links to relevant primary sources that might inform (but
   not settle) the debate
5. Tracks whether the disagreement is evolving (new evidence
   emerging) or stable (longstanding legitimate debate)

**Example:** Experts disagree on whether a proposed zoning
change will increase or decrease property values. The system
presents both analyses, their methodologies, the credentials
of the analysts, and the comparable cases each cites. It does
not pick a winner.

### 5.4 Outdated information

**Signal:** Claim's temporal validity window has expired, or
a newer source updates a previous claim.

**Strategy:**
1. Every claim has `valid_from` and `valid_until` fields.
   For time-bounded facts (budgets, population, officeholders),
   these are explicit. For unbounded facts, a default TTL is
   applied based on category.
2. A scheduled ritual (`knowledge.refresh`) scans for claims
   approaching expiration and re-harvests their sources.
3. When a newer version of a primary source is found, the old
   claim is marked `superseded_by` the new one. The old claim
   remains in the graph for historical queries but is no longer
   returned as current.

### 5.5 Context collapse

**Signal:** A factually correct claim is misleading without
context.

**Strategy:**
1. The Extractor worker extracts not just claims but
   *contextualizing relationships* — conditions, exceptions,
   temporal bounds, scope limitations.
2. Evidence links include a `contextualizes` relationship type
   for sources that don't support or contradict but provide
   necessary framing.
3. When a claim is surfaced to users, the system includes
   linked contextualizing evidence. "The crime rate dropped
   12%" is always presented alongside "based on reported
   incidents; reporting methodology changed in 2024."

---

## 6. Rubrics for Source Evaluation

When a new source enters the system, the Classifier worker
evaluates it against these rubrics. Each dimension is scored
independently.

### 6.1 Publisher credibility

| Signal | Score boost | Score penalty |
|--------|-----------|---------------|
| Established institution with editorial process | +2 | |
| Named author with verifiable credentials | +1 | |
| Corrections/retractions policy visible | +1 | |
| Funding/ownership disclosed | +1 | |
| No byline or institutional attribution | | -1 |
| Known history of retracted claims in our KB | | -2 |
| Content is primarily promotional/advocacy | | -1 |

### 6.2 Claim verifiability

| Signal | Score boost | Score penalty |
|--------|-----------|---------------|
| Cites primary sources that can be checked | +2 | |
| Includes specific dates, figures, names | +1 | |
| Methodology described for data claims | +1 | |
| Vague attribution ("experts say", "studies show") | | -2 |
| No sources cited | | -2 |
| Claims unverifiable by design (anonymous sources for non-safety matters) | | -1 |

### 6.3 Internal consistency

| Signal | Score boost | Score penalty |
|--------|-----------|---------------|
| Claims within the piece are consistent | +1 | |
| Headline matches body content | +1 | |
| Data in text matches data in cited sources | +1 | |
| Headline contradicts or exaggerates body | | -2 |
| Internal contradictions in the piece | | -2 |

### 6.4 Independence

| Signal | Score boost | Score penalty |
|--------|-----------|---------------|
| Publisher has no financial interest in the claim | +1 | |
| Source is not the subject of its own claims | +1 | |
| Publisher has direct financial interest in the claim | | -2 |
| Press release or marketing material | | -2 |

These scores feed into the source's `reliability` field and
inform tier assignment within the evidence hierarchy.

---

## 7. Rituals for Knowledge Maintenance

### 7.1 `knowledge.refresh` — Scheduled re-verification

Runs on a schedule (daily for T1/T2 sources, weekly for T3,
monthly for T4+). Re-harvests sources, checks for content
changes (via content hash comparison), and updates claims
whose sources have changed.

### 7.2 `knowledge.audit` — Periodic integrity check

Scans the evidence graph for:
- Claims with no supporting evidence (orphans)
- Sources that have gone offline (404s)
- Claims past their temporal validity with no refresh
- Contradictions that have been unresolved for >30 days
- Claims whose sole source has degraded reliability

### 7.3 `knowledge.cross_examine` — Active verification

When a claim is high-stakes (cited in a Cubby report, used
in a Weft proposal's cost estimate, or contested by a
community member), the system actively seeks additional
evidence:
1. Searches for the claim in sources not yet in the KB
2. Checks if the primary source has been updated
3. Looks for expert commentary or analysis
4. If the claim involves data, attempts to verify against
   the original dataset

This is the digital equivalent of a journalist making
confirmation calls. It is triggered on-demand, not on
every claim — the cost would be prohibitive.

### 7.4 `knowledge.contest` — Community challenge process

Any community member can contest a claim. The process:
1. Challenger submits the claim ID and their counter-evidence
2. System runs `knowledge.cross_examine` on the contested claim
3. If the counter-evidence introduces new sources at a higher
   tier, the claim's confidence is recomputed
4. If the result is ambiguous, it escalates to the Curator for
   human review
5. The resolution (with reasoning) is recorded and visible

This is the pull-request model applied to knowledge. Anyone
can challenge, the challenge is evaluated on evidence, and
the resolution is transparent.

---

## 8. Anti-patterns in Knowledge Acquisition

Named anti-patterns, following Grove's coaching convention.
Each has a signature and a remediation.

**1. Authority laundering** (`authority_laundering`)
A low-tier source cites a high-tier source, but the claim it
makes is not actually present in the cited source. The
intermediary borrows authority it hasn't earned.
*Detection:* Follow citation links and verify the cited source
actually supports the derived claim.
*Remediation:* Score the claim based on the intermediary's tier,
not the cited source's tier.

**2. Consensus manufacturing** (`consensus_manufacturing`)
Multiple sources making the same claim, but all tracing back to
a single original source. Appears to be corroboration but is
actually amplification.
*Detection:* Track syndication chains. Deduplicate sources by
origin and original publication date.
*Remediation:* Count as one source for corroboration purposes.

**3. Temporal confusion** (`temporal_confusion`)
Presenting outdated information as current, or mixing claims
from different time periods without noting the discrepancy.
*Detection:* Compare claim timestamps with `valid_until` fields
and flag mismatches.
*Remediation:* Require temporal context on all claims with
bounded validity.

**4. Precision theater** (`precision_theater`)
Presenting vague or estimated information with false precision.
"The project will cost $4,237,891" when the source says
"approximately $4.2 million."
*Detection:* Compare extracted numerical claims against source
excerpts for precision inflation.
*Remediation:* Preserve the precision level of the original
source.

**5. Missing denominator** (`missing_denominator`)
Presenting absolute numbers without the base rate or
comparison that makes them meaningful. "50 incidents reported"
without noting whether that's out of 100 or 100,000.
*Detection:* Flag numerical claims that lack a reference frame
(percentage, per-capita, year-over-year, compared to what).
*Remediation:* Attach contextualizing evidence that provides
the denominator.

**6. Survivorship sourcing** (`survivorship_sourcing`)
Only finding sources that support a claim because contradicting
sources are behind paywalls, taken offline, or not indexed.
*Detection:* Track source retrieval failures (404s, paywalls,
robot blocks) and flag claims where potential counter-evidence
was inaccessible.
*Remediation:* Note accessibility gaps in the evidence record.
Lower confidence when significant counter-evidence sources
were unreachable.

---

## 9. How This Maps to Grove

The knowledge acquisition framework is pure Grove
infrastructure. Nothing here requires new protocol methods
or orchestrator changes.

| Framework concept | Grove implementation |
|-------------------|---------------------|
| Evidence hierarchy | Configuration in the KB worker's taxonomy |
| Confidence computation | Deterministic logic in the Corroborator worker |
| Source registry | SQLite tables in the community KB |
| Acquisition pipeline | Ritual DAG (`ritual.knowledge.acquire`) |
| Contradiction detection | Corroborator worker skill |
| Human escalation | Curator worker with `requires_approval` grant |
| Scheduled refresh | Duty with interval trigger |
| Anti-pattern detection | Coaching catalog extensions |
| Community challenges | Weft proposal process with Groove review |
| Source reputation | Rolling reliability score, same pattern as worker health |

The parallel to Grove's trust environments is deliberate:

| Grove trust | Knowledge trust |
|-------------|-----------------|
| Sandbox → Shadow → Canary → Production | Unverified → Reported → Corroborated → Verified |
| Promotion requires demonstrated reliability | Confidence promotion requires additional evidence |
| Demotion is instant on failure | Confidence demotion is instant on contradiction |
| Certification is per-worker, per-skill, per-model | Reliability is per-source, per-topic, per-time-period |

---

## 10. Presentation Principles

How knowledge is presented to users is as important as how it
is acquired. The system follows these rules:

1. **Lead with confidence level.** Users see whether a claim is
   verified, corroborated, reported, or contested before they
   see the claim itself. Not buried in metadata — visible.

2. **Show your work.** Every claim links to its evidence. Users
   can follow the provenance chain to the original source.
   "Trust but verify" is a UI affordance, not a platitude.

3. **Represent disagreement explicitly.** When a claim is
   contested, the system presents both positions, their
   evidence, and what would resolve the disagreement. It never
   presents a false consensus.

4. **Distinguish fact from analysis.** "The council voted 4-3
   to approve the rezoning" is a fact. "The rezoning will
   increase traffic" is analysis. The system marks the
   distinction. Facts can be verified; analysis can be
   evaluated but not verified in the same way.

5. **Date everything.** Every claim shows when it was last
   verified. Users can immediately see whether they're looking
   at current information or stale data.

6. **No confidence inflation.** The system never presents
   something as more certain than its evidence supports. When
   in doubt, downgrade. The reputational cost of presenting
   an unverified claim as verified is far higher than the cost
   of presenting a verified claim as merely reported.

---

## 11. Open Questions

These are genuine design tensions without obvious right answers.
They will be resolved through pilot experience.

**How much transparency is too much?** Showing every evidence
link for every claim is honest but may overwhelm users who just
want to know what their council voted on. The right answer is
probably progressive disclosure — confidence badges on the
surface, full evidence graph on demand.

**Who curates the curators?** The community challenge process
assumes good-faith participants. A coordinated effort to flood
the system with bad-faith challenges could overwhelm human
reviewers. Rate limiting, reputation requirements for
challengers, and escalation to institutional partners are all
options; none are obviously correct.

**How do you handle the local knowledge gap?** Some of the most
important civic knowledge is not digital at all. It lives in
the memories of longtime residents, in unrecorded conversations,
in institutional knowledge that was never written down. The
system can provide tools for capturing this knowledge (T5
structured community input), but it cannot source it
automatically. This is a coverage gap, not a reliability gap,
but it matters.

**When does re-verification become surveillance?** Continuously
monitoring sources for changes is good epistemic hygiene. It is
also continuous web scraping. The system should respect
robots.txt, rate limits, and the spirit of public access — not
treat public records as a surveillance target.

---

*The best knowledge systems are not the ones that are always
right. They are the ones that know what they don't know, show
their evidence, and make it easy to correct them. That is what
peer review, judicial process, and Wikipedia's talk pages all
share. This framework applies the same pattern — traceable
evidence, structured disagreement, transparent confidence — to
the knowledge that communities need to govern themselves.*
