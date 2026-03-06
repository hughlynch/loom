# Prior Art: Legal Evidence and Content Provenance

**Part of:** Loom Prior Art Research
**See also:** `prior-art.md` (index)

---

## 1. Federal Rules of Evidence (US)

### The Hearsay Framework as a Tiering System

**Rule 802:** Hearsay is inadmissible unless an exception
applies. This is fundamentally a reliability tiering system:
first-hand testimony is most trusted; second-hand reporting
is presumptively excluded.

**Rule 803:** 23 enumerated exceptions where hearsay is
admissible. Each encodes a *reason* for reliability:
- **Business records** (803(6)) — reliable because kept
  routinely and systematically
- **Public records** — records of public offices
- **Excited utterances** — reliable because declarant had
  no time to fabricate
- **Recorded recollection** — made when memory was fresh
- **Learned treatises** — established authority in the field

**Design insight:** Loom's T1-T7 hierarchy should encode
*reasons for reliability*, not just rank. Why is T1 more
reliable than T6? Because government filings are systematic,
legally accountable, and independently auditable — not just
"because they're government."

### Expert Witness Qualification (Rule 702 / Daubert)

For expert testimony, four conditions:
(a) Testimony helps understand the evidence
(b) Rests on sufficient facts or data
(c) Product of reliable principles and methods (testable,
    peer-reviewed, known error rates, generally accepted)
(d) Expert reliably applied those methods to the facts

The trial judge acts as "gatekeeper."

**Design insight:** Distinguish *source credibility* from
*methodological soundness*. A peer-reviewed paper (T2) using
flawed methodology should score lower than expert analysis
(T4) using validated methods. Rule 702 is a methodology audit,
not a credential check.

### Chain of Custody (Rule 901)

Authentication requires: (1) integrity — evidence not
tampered with, (2) identity — same item collected,
(3) continuity — no unexplained gaps.

Every handler documented: who, when, under what conditions.
Minor gaps may not invalidate; significant gaps can exclude.

**Design insight:** Every Loom claim needs a provenance chain
showing: who created it, what source it derived from, what
transformations applied (summarization, extraction, inference),
who reviewed it. Gaps in the chain should reduce confidence.
Metadata about handling is as important as content.

### Best Evidence Rule (Rule 1002)

Original writing/recording required to prove its content.
Prefer primary sources over derived/summarized versions.

**Design insight:** Track degrees of separation from original.
Penalize claims that rely on interpretations of
interpretations. Store or link original source material.

---

## 2. Wikidata Sourcing Model

### Reference Structure

Data model: **Item → Statement → Value**, with qualifiers
(context) and references (sourcing).

Key reference properties:
- **P248 (stated in)** — source item (used 88M+ times)
- **P854 (reference URL)** — web URL (used 65M+ times)
- **P813 (retrieved)** — retrieval date (used 86M+ times)
- **P1476 (title)** — source work title
- **P7452 (reason for preferred rank)** — *why* a value
  was preferred

### Three-Rank System

- **Preferred** — most current/reliable. Used by default in
  queries. Requires P7452 justification for why preferred.
- **Normal** — default rank.
- **Deprecated** — known erroneous/outdated. Never used in
  queries unless requested. Value *preserved* (not deleted)
  for audit trail.

### Design Insights

1. **Multi-value with ranking**: allow multiple competing
   claims for the same assertion, ranked by confidence.
2. **Structured references**: distinguish source identity
   (what document) from source locator (where to find it).
   Every reference needs a retrieval timestamp.
3. **Deprecation over deletion**: mark superseded, never
   destroy. Preserves audit trail, explains what was once
   believed.
4. **Reason for rank**: require justification when elevating
   or demoting a claim's confidence level.

---

## 3. C2PA / Content Authenticity Initiative

Coalition for Content Provenance and Authenticity. Open
technical standard for embedding verifiable provenance in
digital content (images, video, audio, documents). Founded
by Adobe, Arm, Intel, Microsoft, Truepic.

### Technical Architecture

**Assertions** — atomic statements about an asset: creation
details, editing actions, AI/ML generation status, ingredient
sources. Serialized as CBOR.

**Claims** — wrap assertions with metadata. Critical
distinction:
- `created_assertions` — signer directly created these
- `gathered_assertions` — collected from other sources;
  signer does NOT vouch for these

**Claim Signatures** — X.509-based digital signatures with
trusted timestamps. Bind claim to signer identity.

**Manifests** — bundle assertions + claim + signature into
a verifiable unit.

**Manifest Store** — asset's complete provenance history.
When Asset A becomes an ingredient of Asset B, A's entire
manifest store copies into B's. Family-tree structure.

### Binding

- **Hard binding**: SHA-256 hashes bind manifest to content.
  Any modification breaks the hash.
- **Soft binding**: invisible watermarking for recovery when
  metadata stripped (e.g., by social media).

### Design Insights

1. **Created vs gathered**: Loom should distinguish claims a
   source *originated* from claims it *relayed*. Each relay
   hop should reduce confidence.
2. **Ingredient model**: when synthesizing from multiple
   sources, preserve full provenance of each ingredient.
   Family-tree model for provenance chains.
3. **Hard and soft binding**: hash knowledge claims for
   integrity verification; maintain index for recovery.
4. **Trust lists**: specific sources within a tier can be
   validated/accredited (analogous to C2PA signer trust list).
5. **Gap acknowledgment**: when provenance has gaps (manual
   entry without source chain), mark explicitly.

---

## 4. FAIR Data Principles

Findable, Accessible, Interoperable, Reusable. Published
Scientific Data 2016. 15 sub-principles emphasizing
machine-actionability.

### Key Sub-Principles for Loom

- **F1**: globally unique persistent identifiers (UUID, URI)
  for every claim, source, evidence chain
- **F3**: bidirectional linking — evidence metadata contains
  claim ID; claims link to evidence
- **A2**: metadata survives data — even if source goes offline,
  metadata persists (who published, when retrieved, what said)
- **I1**: formal knowledge representation — use shared
  vocabularies (Schema.org), not free-form text
- **I3**: qualified references — typed relationships (supports,
  contradicts, derived-from, supersedes), not bare links
- **R1.2**: detailed provenance as reusability prerequisite
- **R1.3**: adopt community standards (Schema.org, Dublin Core,
  PROV-O) rather than inventing proprietary schemas

---

## 5. Schema.org for Structured Knowledge

### Relevant Types

- **Claim**: text, appearance, firstAppearance, claimInterpreter
- **ClaimReview**: extends Review, adds claimReviewed,
  reviewRating, itemReviewed
- **Rating**: ratingValue, bestRating, worstRating, alternateName
- **MediaReview**: parallel to ClaimReview for media authenticity
- **CreativeWork**: base type for sources (articles, books,
  datasets)
- **ScholarlyArticle**: academic metadata

### Gap

Schema.org defines **no relationships between claims** — no
"supports," "contradicts," "derived-from." Loom needs its own
vocabulary for these, potentially proposable as Schema.org
extensions.

### Design Insight

Loom should export:
- Claims as Schema.org `Claim` objects
- Evidence assessments as `ClaimReview` objects
- Confidence as `Rating` objects
- Provenance as PROV-O or C2PA manifests

`firstAppearance` tracking: record when a claim was first
encountered across sources (priority tracking).

`claimInterpreter`: record not just the source but who
extracted/interpreted the claim from that source.

---

## Synthesis: Provenance Architecture

| Concept | Legal | Wikidata | C2PA | FAIR | Schema.org |
|---------|-------|----------|------|------|------------|
| Identity | Authentication (901) | P248 stated in | Manifest | F1 persistent ID | Claim.sameAs |
| Integrity | Chain of custody | Content hash | Hard binding (SHA-256) | — | — |
| Temporality | — | P813 retrieved | Trusted timestamps | A2 metadata survives | datePublished |
| Justification | — | P7452 reason | — | — | — |
| Relationships | — | Qualifiers | created vs gathered | I3 qualified refs | (gap) |
| Survival | Best evidence rule | Deprecated rank | Soft binding | A2 | — |
| Provenance | Chain of custody | References | Ingredient model | R1.2 | isBasedOn |

### Key Architectural Principles

1. **Encode reasons for reliability** — not just rank (FRE)
2. **Separate source credibility from methodology** (Rule 702)
3. **Provenance chains are first-class data** — as queryable,
   versioned, and validated as claims themselves (FAIR R1.2,
   C2PA, FRE chain of custody)
4. **Multi-value with ranking** — don't force single truth
   (Wikidata)
5. **Deprecate, never delete** (Wikidata, FRE)
6. **Separate creation from aggregation** — originated vs
   relayed (C2PA)
7. **Use standard vocabularies for export** (FAIR I1, Schema.org)
8. **Every reference needs a timestamp** (Wikidata P813,
   C2PA, FAIR A2)
