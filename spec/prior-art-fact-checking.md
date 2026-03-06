# Prior Art: Fact-Checking Standards

**Part of:** Loom Prior Art Research
**See also:** `prior-art.md` (index), `prior-art-intelligence.md`,
`prior-art-legal-provenance.md`, `prior-art-scientific.md`,
`prior-art-epistemic.md`

---

## 1. IFCN Code of Principles

The International Fact-Checking Network (Poynter Institute)
is the global certification standard for fact-checkers.

### Five Core Commitments

1. **Nonpartisanship and Fairness** — identical evidentiary
   standards regardless of who made a claim. No concentration
   on one political side. Staff cannot do policy advocacy.
   No party affiliation. Must disclose source interests.

2. **Transparency of Sources** — all significant evidence
   identified with enough detail for readers to replicate.
   Primary sources preferred over secondary. Key claim
   elements verified against multiple named sources.

3. **Transparency of Funding and Organization** — independent
   orgs must list all funding sources >5% of annual revenue.
   Organizational structure showing editorial control.
   Professional bios of editorial leaders. Easy contact.

4. **Transparency of Methodology** — published methodology
   covering selection, research, writing, publication. Claim
   selection based on reach and importance (not partisan
   targeting). Both supporting and contradicting evidence
   presented. Right of response to claim-makers.

5. **Open and Honest Corrections** — visible corrections
   policy. Major mistakes require revised conclusions.
   Corrections "openly and transparently, seeking as far as
   possible to ensure that users of the original see the
   correction."

### Certification Process

- Independent assessors evaluate against 31 specific criteria
- Advisory board reviews for fairness and consistency
- Certification lasts one year, requiring annual re-examination
- Used as gating by Facebook's Third-Party Fact-Checking Program

### Design Insights for Loom

- Five principles map to Loom metadata requirements: source
  transparency (provenance chains), methodology transparency
  (confidence assessment), corrections policy (revision handling)
- 31-criteria assessment could inform a credibility audit for
  Loom sources, helping place them in T1-T7
- Annual re-certification model: source tier ratings should
  not be permanent — periodic re-evaluation needed
- Nonpartisanship principle: track whether a source consistently
  applies the same evidentiary standard regardless of claim's
  political valence

---

## 2. ClaimReview Schema (Schema.org)

Structured data format for encoding fact-checks in
machine-readable markup. Created 2015 by Duke Reporters' Lab,
Google, Bing, Jigsaw, and the fact-checking community.

### Schema Structure

Extends Review > CreativeWork > Thing.

**Required fields:**
- `claimReviewed` (Text) — short summary (recommended <75 chars)
- `reviewRating` (Rating) — the assessment:
  - `alternateName` — human-readable ("True", "Mostly false")
  - `ratingValue` — numeric (1=False → 5=True)
  - `bestRating` / `worstRating` — scale bounds
- `url` — link to full fact-check article

**Recommended fields:**
- `author` — organization publishing the fact check
- `datePublished`
- `itemReviewed` (Claim) — the claim being evaluated:
  - `author` — who made the claim
  - `datePublished` — when claim entered public discourse
  - `appearance` / `firstAppearance` — where claim appeared
- `reviewBody` — full review text

### Platform Adoption

~40,500 articles tagged with ClaimReview in first 5 months of
2024. Seen 120M+ times in EU in 6-month period.

Google killed fact-checking snippets in Search results in 2025,
but Fact Check Explorer still supports ClaimReview. Markup
remains relevant for other platforms.

### Could Loom Produce ClaimReview?

Yes — strong fit:
- Claim text → `claimReviewed`
- Provenance chains → `itemReviewed.author`, `.datePublished`
- Confidence levels → `reviewRating.ratingValue` (verified=5,
  corroborated=4, reported=3, contested=2, unverified=1)
- T1-T7 hierarchy → `author` metadata of the ClaimReview

Makes Loom findings interoperable with the global fact-check
ecosystem.

---

## 3. Snopes

Oldest and largest fact-checking site (1994). IFCN signatory.

### Rating System

More granular than most:
- **True** / **Mostly True** / **Mixture** / **Mostly False** / **False**
- **Unproven** — evidence inconclusive or self-contradictory
- **Unfounded** — no demonstrable evidence found
- **Fake** — digitally manipulated media
- **Outdated** — once-true, no longer accurate
- **Miscaptioned** — real media, false context
- **Correct Attribution** / **Misattributed**
- **Scam** / **Legend**

### Research Process

1. Assign to editorial staff for preliminary research
2. Contact claim's source for elaboration
3. Contact relevant experts
4. Search published information (news, journals, books,
   archives, public records)
5. Additional staff contribute on complex claims
6. Final product passes through at least one editor

### Design Insights for Loom

- **"Unfounded" vs "Unproven"**: no evidence found vs.
  contradictory evidence. Loom's "unverified" conflates these
  — should distinguish them.
- **"Outdated"**: temporal validity as first-class concept.
  A claim can be True at T1 and False at T2.
- **"Miscaptioned" / "Misattributed"**: track attribution
  separately from content accuracy. Claims can be accurate
  in content but false in attribution.

---

## 4. PolitiFact

Nonprofit fact-checker owned by Poynter. IFCN signatory.
Pulitzer Prize 2009.

### Truth-O-Meter (6 levels)

- **TRUE** — accurate, nothing significant missing
- **MOSTLY TRUE** — accurate, needs clarification
- **HALF TRUE** — partially accurate, missing important details
- **MOSTLY FALSE** — element of truth, ignores critical facts
- **FALSE** — not accurate
- **PANTS ON FIRE** — not accurate, ridiculous claim

### Claim Selection Criteria

1. Verifiability — rooted in checkable fact (not opinion)
2. Significance — newsworthy, not trivial
3. Spread potential — likely to be repeated
4. Public curiosity — would a typical person wonder?
5. Balance — equal coverage of both parties

### Multi-Editor Review Process

1. Reporter researches and recommends a ruling
2. Assigning editor reviews with reporter
3. Panel of 3 editors votes (2 votes decide)
4. Panel considers: literal accuracy, alternative
   interpretations, evidence provided, precedent consistency

### Design Insights for Loom

- **Multi-editor voting**: high-stakes confidence assignments
  should require multiple independent evaluations. Maps to
  Loom's multi-curator consensus (adversarial resilience §7.3).
- **Precedent consideration**: when a new claim relates to
  previously assessed claims, surface those prior assessments
  for consistency.
- **Claim selection criteria**: could inform Loom's
  prioritization of which claims to invest in verifying.

---

## 5. Full Fact (UK)

UK's leading independent fact-checking charity. IFCN signatory.
Distinctive for its AI/NLP technology platform.

### Automated Fact-Checking Pipeline

1. **Data Collection** — news sites, live TV transcripts,
   podcasts, social media, radio, video
2. **Sentence Segmentation** — ~333,000 sentences/day on
   typical weekdays
3. **Claim-Type Classification** — BERT-based classifier
   (fine-tuned on 5,571 annotated sentences) distinguishes
   verifiable factual claims from predictions/opinions
4. **Claim Matching** — sentence vectorization + entity
   analysis for match/no-match prediction against previously
   fact-checked claims (repeat detection)
5. **Publication** — outputs include ClaimReview markup

### Corrections with Publishers

Distinctive "repeat detection" workflow: when a debunked claim
is repeated (e.g., by MPs), Full Fact proactively contacts
speakers to request corrections.

### Scale

Used by 40+ fact-checking organizations across 30 countries.
Supported monitoring of 12 national elections in 2024.

### Design Insights for Loom

- **Claim-type classification**: before assessing confidence,
  determine whether a statement is even a verifiable factual
  claim. BERT-based approach (verifiable fact vs. prediction
  vs. opinion) directly applicable.
- **Repeat detection / claim matching**: when new evidence
  enters, automatically match against existing KB for
  corroboration, contradiction, or mere repetition.
- **333,000 sentences/day throughput**: useful scale reference
  for Loom's ingestion pipeline.
- **ClaimReview as output**: confirms Loom should adopt
  ClaimReview as export format.

---

## Cross-Cutting Mapping

### Confidence Levels

| Loom | PolitiFact | Snopes | ClaimReview |
|------|-----------|--------|-------------|
| Verified | TRUE | True | 5 |
| Corroborated | MOSTLY TRUE | Mostly True | 4 |
| Reported | HALF TRUE | Mixture (partial) | 3 |
| Contested | MOSTLY FALSE / mixed | Mixture / Unproven | 2 |
| Unverified | N/A (not yet checked) | Unfounded / Unproven | 1 |

### Architectural Recommendations

1. **Temporal validity as first-class** — adopt Snopes'
   "Outdated" concept with explicit validity windows
2. **Attribution vs content accuracy** — track independently
3. **Multi-assessor adjudication** — PolitiFact's 3-editor
   voting for high-stakes confidence assignments
4. **Automatic claim matching** — Full Fact's BERT pipeline
   for corroboration/contradiction/repetition detection
5. **ClaimReview as export format** — interoperability with
   global fact-checking ecosystem
6. **Source re-certification** — IFCN's annual re-certification
   model for periodic tier review
7. **Claim-type classification** — filter verifiable facts
   from predictions/opinions before confidence assessment
