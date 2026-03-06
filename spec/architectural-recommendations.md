# Loom: Architectural Recommendations from Prior Art

**Synthesizes findings from:** Ground News, AP, arXiv,
Wikipedia, IFCN, ClaimReview, Snopes, PolitiFact, Full Fact,
Admiralty Code, ICD 203, Structured Analytic Techniques,
Sherman Kent, Cochrane, GRADE, IPCC, EBM hierarchy, PRISMA,
Federal Rules of Evidence, Wikidata, C2PA, FAIR, Schema.org,
Bayesian epistemology, Dung argumentation, Truth Maintenance
Systems, Toulmin model, epistemic/justification logic

---

## 1. Upgrade T1-T7 to a Dual-Axis System

**Sources:** Admiralty Code, ICD 203, GRADE, IPCC

The current single-axis T1-T7 hierarchy conflates source
reliability with information credibility. Every domain
studied separates these.

### Proposed: Source Reliability × Information Credibility

**Source Reliability (T1-T7, retained)**
Who said it? How trustworthy is this source in general?

**Information Credibility (C1-C6, new)**
How credible is *this specific claim* from this source?

- C1: Confirmed — verified by multiple independent sources
- C2: Probably true — unconfirmed but logical, consistent
- C3: Possibly true — reasonably logical, needs verification
- C4: Doubtfully true — inconsistent, unconfirmed
- C5: Improbable — contradicts established facts
- C6: Cannot be assessed — insufficient context

The two axes are evaluated **independently**. A T1 source
can produce C4 information. A T6 source can provide C1 facts.
The diagonal collapse problem (87% correlation in practice)
requires active countermeasures: separate evaluation steps
and mandatory justification when axes diverge.

### Impact on Confidence Computation

Current: tier → confidence (single path)
Proposed: (tier × credibility) → base confidence → GRADE
adjustments → final confidence

```
base_confidence = f(source_reliability, info_credibility)

# GRADE-like adjustment factors
adjusted = base_confidence
  - risk_of_bias_penalty        # methodology issues
  - inconsistency_penalty       # sources disagree
  - indirectness_penalty        # evidence doesn't directly address claim
  - imprecision_penalty         # vague/imprecise evidence
  - publication_bias_penalty    # incomplete evidence landscape
  + large_effect_bonus          # overwhelming evidence
  + dose_response_bonus         # gradient supports causation
  + confounding_adjustment      # plausible confounders favor claim
```

---

## 2. Three-Dimensional Knowledge Claims

**Sources:** ICD 203, Sherman Kent, IPCC, Toulmin

Each claim should carry four independent dimensions:

```
claim:
  # Dimension 1: Source (Admiralty axis 1)
  source_reliability: T2        # who said it

  # Dimension 2: Credibility (Admiralty axis 2)
  info_credibility: C1          # how credible is this assertion

  # Dimension 3: Confidence (ICD 203)
  analytic_confidence: high     # how good is the evidence base
  evidence_strength: robust     # IPCC: limited/medium/robust
  agreement_level: high         # IPCC: low/medium/high

  # Dimension 4: Probability (Kent/ODNI, only when confidence ≥ high)
  probability: 0.92             # numeric
  probability_range: [0.87, 0.97]  # with uncertainty bounds
  probability_verbal: "very likely"  # ODNI 7-level display

  # Structural (Toulmin)
  warrant: "..."                # WHY evidence supports claim
  rebuttal_conditions: [...]    # when claim would NOT hold
  assumptions: [...]            # declared premises (SATs)
```

**Critical rule from IPCC:** probability/likelihood terms
should only be used when confidence is high or very high.
Don't assign precise scores to claims with limited evidence.

**Critical rule from ICD 203:** never conflate confidence
(evidence quality) with probability (event likelihood) in
the same field.

---

## 3. Evidence Graph as Dependency Network

**Sources:** TMS (ATMS), Bayesian networks, Dung frameworks,
justification logic, C2PA, FRE chain of custody

### ATMS-Style Labels

For each claim, track the **minimal sets of evidence** that
support it, not just the confidence level:

```
claim: "School budget increased 8%"
  confidence: verified
  labels:
    - {T1:budget_doc_2025, T2:finance_audit_2025}  # minimal set 1
    - {T1:budget_doc_2025, T3:city_reporter_article} # minimal set 2
  nogoods:
    - {T6:blog_post_123, T1:budget_doc_2025}  # contradictory
```

This enables:
- **"What-if" queries**: remove evidence Y, recompute
- **Sensitivity analysis**: which evidence is load-bearing?
- **Precise retraction**: discredit a source → know exactly
  which claims are affected
- **Independence tracking**: detect when "independent" sources
  share common upstream

### Retraction Propagation

When evidence is invalidated:
1. Mark evidence as invalidated
2. Dependency-directed search: find all claims whose *every*
   minimal label set includes the invalidated evidence
3. Recompute confidence for affected claims only
4. Propagate downstream (claims that depend on affected claims)
5. Log all changes with timestamps and reasons

This is TMS dependency-directed backtracking applied to
knowledge management.

### Evidence Independence

**From Bayesian networks:** two evidence links from the same
upstream source are NOT independent. Track syndication chains,
citation chains, and data provenance to detect:
- Two news articles citing the same press release
- Two papers using the same dataset
- Two analyses by the same author published in different venues

Independence matters because corroboration requires
*genuinely independent* confirmation.

---

## 4. Structured Disagreement Model

**Sources:** IPCC, GRADE, Dung frameworks, Snopes

Replace the binary "contested" flag with a structured
disagreement model:

```
disagreement:
  evidence_strength: robust      # IPCC: how much evidence exists
  agreement_level: low           # IPCC: how much sources agree
  nature: interpretive           # factual/interpretive/temporal/
                                 # definitional/methodological
  axis: "cost estimate method"   # WHAT they disagree about
  positions:
    - position: "Project costs $4M"
      support: [{source: T1:budget, credibility: C2}]
    - position: "Project costs $6M"
      support: [{source: T4:analysis, credibility: C3}]
  resolution_path: "Compare methodologies"  # what would resolve it
  pre_specified: true            # was this disagreement anticipated?
```

This captures six distinct situations that "contested"
currently conflates:

| Evidence | Agreement | Meaning |
|----------|-----------|---------|
| Robust | High | Not contested — verified/corroborated |
| Robust | Medium | Mostly settled, some dissent |
| Robust | Low | **Genuine controversy** — lots of evidence, experts disagree |
| Limited | High | Emerging consensus, needs more evidence |
| Limited | Medium | Early stage, inconclusive |
| Limited | Low | **Unknown** — we don't know enough to say |

---

## 5. Warrant and Reasoning Tracking

**Sources:** Toulmin, justification logic, ICD 203 Standard #3

Loom currently tracks THAT evidence supports a claim. It
should also track WHY (the warrant) and UNDER WHAT
ASSUMPTIONS (declared premises).

### Evidence Link Schema Extension

```sql
-- Current
evidence.relationship: supports | contradicts | ...

-- Proposed additions
evidence.warrant      TEXT,  -- reasoning connecting evidence to claim
evidence.assumptions  TEXT,  -- JSON: declared premises for this link
evidence.inference    TEXT,  -- type: verbatim | summarized | inferred |
                             --       calculated | analogical
evidence.directness   TEXT,  -- direct | indirect_population |
                             --   indirect_intervention | analogical
```

When `inference` is `inferred` or `analogical`, the warrant
becomes mandatory — the system must explain WHY this
non-obvious connection holds.

When `directness` is not `direct`, GRADE-like downgrading
applies automatically.

---

## 6. ClaimReview Export and Interoperability

**Sources:** Schema.org, Full Fact, IFCN, FAIR

Loom should produce and consume standard formats:

### Export

- **Claims** → Schema.org `Claim` objects
- **Evidence assessments** → `ClaimReview` objects
- **Confidence** → `Rating` objects with defined scale
- **Provenance** → PROV-O ontology or C2PA manifests
- **Relationships** → Loom-defined vocabulary (supports,
  contradicts, supersedes, derived-from, corroborates) —
  propose as Schema.org extensions

### Import / Consume

- **ClaimReview feeds** from IFCN-certified fact-checkers
  → ingest as T4 evidence (expert analysis with disclosed
  methodology)
- **Wikidata references** → follow P854 URLs to primary
  sources, evaluate at own tier
- **Wikipedia citations** → follow to primary sources,
  not trust Wikipedia as authoritative

### Identifiers (FAIR F1)

Every claim, source, evidence link, and contradiction needs
a globally unique, persistent identifier. UUIDs internally,
URIs for external reference.

---

## 7. Claim-Type Classification

**Sources:** Full Fact, Snopes, EBM hierarchy

Before confidence assessment, classify each claim:

| Type | Assessment Method | Example |
|------|------------------|---------|
| **Empirical fact** | Evidence hierarchy, provenance | "Council voted 4-3" |
| **Statistical claim** | Primary data, methodology audit | "Crime dropped 12%" |
| **Causal claim** | GRADE-like factors, confounding | "Rezoning caused traffic" |
| **Prediction** | Not assessable for truth; track record | "Budget will increase" |
| **Opinion/value** | Not assessable; attribute and present | "The policy is good" |
| **Attribution** | Source verification | "Mayor said X" |
| **Temporal** | Validity window, freshness | "Population is 50,000" |

Different claim types may warrant different tier hierarchies
(EBM insight: hierarchy shifts by question type). Predictions
and opinions should never receive "verified" confidence.

---

## 8. Process Documentation

**Sources:** PRISMA, Cochrane, FAIR R1.2

The *process* of knowledge construction must be as
transparent as the conclusion. For each knowledge claim,
document:

1. **Search protocol**: what was searched, when, with what
   queries (PRISMA identification phase)
2. **Screening**: what sources were found, which were
   included, which excluded and why (PRISMA flow diagram)
3. **Assessment method**: how confidence was derived —
   algorithmic rules, human judgment, or hybrid (PRISMA
   synthesis method)
4. **Pre-specification**: were acceptance criteria defined
   before or after seeing the evidence? (Cochrane protocol,
   GRADE pre-specification). Post-hoc criteria are flagged
   as hypothesis-generating.

This enables:
- Reproducibility (anyone can re-run the same search)
- Auditability (track bias in the construction process)
- Trust (the system shows its work at the process level)

---

## 9. Temporal and Deprecation Model

**Sources:** Snopes ("Outdated"), Wikidata (deprecated rank),
IPCC, GRADE

### Enhanced Temporal Model

```sql
claims.valid_from       TEXT,  -- when claim became true
claims.valid_until      TEXT,  -- when claim expires/expired
claims.temporal_status  TEXT,  -- current | outdated | superseded
claims.superseded_by    TEXT,  -- claim_id of replacement
claims.superseded_reason TEXT, -- why it was superseded
claims.deprecation_date TEXT,  -- when marked deprecated
```

Following Wikidata: **deprecate, never delete.** Outdated
claims are preserved with full audit trail. They answer
"what was believed and when" — important for historical
queries and error analysis.

### Freshness Duties

| Source tier | Refresh interval | Rationale |
|------------|-----------------|-----------|
| T1-T2 | Daily | Primary records may be updated |
| T3 | Weekly | News cycle refresh |
| T4 | Monthly | Expert analysis evolves slowly |
| T5-T7 | Quarterly | Low-tier sources checked less often |

---

## 10. Source Re-Certification

**Sources:** IFCN (annual), coaching flywheel, Snopes

Source tier ratings should not be permanent. Periodic
re-evaluation based on:

1. **Track record**: sources that repeatedly produce claims
   contradicted by higher-tier evidence → reliability degrades
2. **Methodology changes**: source changes its editorial
   process → re-evaluate
3. **Coverage gaps**: source stops covering a domain →
   relevance degrades
4. **Anti-pattern triggers**: `consensus_manufacturing`,
   `authority_laundering` detected → immediate review

Map to grove coaching flywheel: source reliability scores
evolve like worker health scores.

---

## Implementation Priority

### Phase 1 (Foundation) — No architecture change needed
- ClaimReview export format
- Claim-type classification in Extractor
- Process documentation in provenance chains
- Temporal validity and deprecation model
- Source re-certification duties

### Phase 2 (Dual-Axis) — Schema change
- Add information credibility (C1-C6) axis
- GRADE-like adjustment factors in Corroborator
- Structured disagreement model replacing binary "contested"
- Warrant field on evidence links

### Phase 3 (Dependency Network) — Architecture change
- ATMS-style minimal label sets per claim
- Retraction propagation algorithm
- Evidence independence tracking
- Sensitivity analysis queries ("what-if")

### Phase 4 (Advanced)
- ACH-style hypothesis matrices for contested claims
- Automated adversarial review (Devil's Advocacy)
- Bayesian propagation for continuous confidence
- Dung semantics for contradiction resolution (grounded
  vs preferred views)
