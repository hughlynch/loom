# Prior Art: Scientific Evidence Synthesis

**Part of:** Loom Prior Art Research
**See also:** `prior-art.md` (index)

---

## 1. Cochrane Systematic Reviews

Gold standard for evidence synthesis in healthcare. Rigorous,
pre-registered reviews that identify, appraise, and synthesize
all empirical evidence meeting pre-specified criteria.

### The Pipeline

1. **Protocol Development** — pre-register question (PICO:
   Population, Intervention, Comparator, Outcome), eligibility
   criteria, search strategy, analysis plan. Published *before*
   examining evidence. Peer-reviewed.

2. **Comprehensive Search** — multiple databases (MEDLINE,
   Embase, CENTRAL, trial registries). Mandatory unpublished
   literature search (mitigates publication bias).

3. **Study Selection** — 2+ reviewers independently screen
   titles/abstracts, then full texts. Disagreements resolved
   by discussion or third reviewer.

4. **Data Extraction** — standardized forms, dual extraction
   with reconciliation.

5. **Risk of Bias Assessment (RoB 2)** — structured assessment
   across five bias domains:
   - Randomization process
   - Deviations from intended interventions
   - Missing outcome data
   - Measurement of outcome
   - Selection of reported result

   Each domain uses signalling questions → algorithmic judgment:
   Low risk / Some concerns / High risk. High in ANY domain →
   High overall. Multiple "Some concerns" can escalate.

6. **Evidence Synthesis** — meta-analysis if studies are
   similar enough; narrative synthesis otherwise. Heterogeneity
   assessed via I² statistic.

7. **Conflict Handling** — pre-specified subgroup analyses,
   sensitivity analyses, meta-regression. Post-hoc
   explorations flagged as hypothesis-generating only.

8. **GRADE Assessment** — certainty of evidence for each
   outcome (see §2).

### What Makes It Gold Standard

- Pre-registration reduces reviewer bias
- Mandatory unpublished literature search
- Dual independent review at every stage
- Structured, algorithmic bias assessment
- Full decision documentation including exclusion reasons
- Living reviews (continuously updated)
- Strict conflict-of-interest policies

### Design Insights for Loom

- **Protocol-first**: define question and acceptance criteria
  *before* gathering evidence. Reduces confirmation bias.
- **Structured bias assessment per evidence unit**: five
  domains with signalling questions, not holistic impressions.
  Maps to Loom source evaluation dimensions.
- **Algorithmic confidence derivation**: RoB 2's question →
  judgment algorithm models how Loom should derive confidence
  from structured assessments.
- **Exclusion documentation**: track what sources were
  considered and rejected, with reasons. As important as
  what was included.

---

## 2. GRADE Framework

Grading of Recommendations Assessment, Development and
Evaluation. Used by Cochrane, WHO, 100+ organizations.

### Four Evidence Quality Levels

| Level | Definition |
|-------|-----------|
| **High** | Very confident true effect close to estimate |
| **Moderate** | Likely close, could be substantially different |
| **Low** | True effect may be substantially different |
| **Very Low** | True effect likely substantially different |

### Starting Points

- Randomized controlled trials start at **High**
- Observational studies start at **Low**

Study architecture determines starting point, not study count.

### Five Downgrading Factors

1. **Risk of Bias** — study limitations (randomization,
   blinding, dropout). Serious: −1, very serious: −2.
2. **Inconsistency** — unexplained variation across studies.
   I²: Low <40%, Moderate 40-60%, High >60%.
3. **Indirectness** — evidence doesn't directly address the
   question (different population, intervention, outcome).
4. **Imprecision** — wide confidence intervals, small samples,
   few events.
5. **Publication Bias** — selective publication of positive
   results (funnel plot asymmetry).

### Three Upgrading Factors (observational studies)

1. **Large effect** — RR >2 or <0.5: +1; RR >5 or <0.2: +2
2. **Dose-response gradient**
3. **Plausible residual confounding** — all confounders would
   reduce observed effect

### Design Insights for Loom

- **Source quality sets starting point; factors adjust**:
  T1 starts high, T6 starts low. Then apply up/down factors.
  This is more nuanced than fixed tiers.
- **Directness matters**: evidence that *directly* addresses
  the claim is stronger than analogical evidence, even from
  a higher-tier source.
- **Publication/reporting bias as first-class**: track whether
  the evidence landscape is likely complete or biased by
  selective reporting.
- **Inconsistency is diagnostic**: when sources disagree,
  explore *why* before downgrading. Pre-specified vs post-hoc
  explanations get different weight.

---

## 3. IPCC Confidence Language

Calibrated language for communicating scientific uncertainty.
Used across all IPCC Assessment Reports.

### Two Independent Dimensions

**Confidence** — qualitative validity assessment (5 levels):

| Level | Basis |
|-------|-------|
| Very high | Robust evidence, high agreement |
| High | Robust evidence + medium agreement; OR medium evidence + high agreement |
| Medium | Medium evidence, medium agreement |
| Low | Limited evidence + low agreement; OR medium evidence + low agreement |
| Very low | Limited evidence, low agreement |

Built from two sub-dimensions:
- **Evidence**: limited / medium / robust (type, amount,
  quality, consistency)
- **Agreement**: low / medium / high (consensus across
  scientific literature)

Creates a 3×3 matrix mapped to 5 confidence levels.

**Likelihood** — calibrated probability scale:

| Term | Probability |
|------|------------|
| Virtually certain | 99-100% |
| Extremely likely | 95-100% |
| Very likely | 90-100% |
| Likely | 66-100% |
| About as likely as not | 33-66% |
| Unlikely | 0-33% |
| Very unlikely | 0-10% |
| Exceptionally unlikely | 0-1% |

### Critical Rule

**Likelihood terms should only be used when confidence is
high or very high.** If confidence is medium or below, use
confidence language alone. Prevents false precision — don't
assign probability to something with limited evidence.

### Handling Disagreement

- Agreement sub-dimension explicitly captures disagreement
- Low agreement + robust evidence → medium confidence (not
  forced consensus)
- Minority positions get separate statements with own
  confidence
- Same evidence-agreement combination can get different
  confidence levels — it's a judgment framework

### Design Insights for Loom

- **Two-axis uncertainty model**: separate evidence strength
  from agreement level. Loom's "contested" only captures one
  scenario (strong evidence, low agreement). Limited-evidence-
  high-agreement and robust-evidence-low-agreement are
  fundamentally different.
- **Probability requires high confidence**: don't assign
  precise scores to claims with limited evidence.
- **Calibrated vocabulary**: "likely" must mean 66-100%, not
  a vague impression. Defined vocabulary prevents
  miscommunication.
- **Disagreement is data, not noise**: "contested" is a
  first-class state, not a defect waiting for resolution.

---

## 4. Evidence-Based Medicine Hierarchy

### The Evidence Pyramid (top to bottom)

| Level | Study Type | Rationale |
|-------|-----------|-----------|
| 1a | Systematic reviews / Meta-analyses | Aggregated, bias-controlled |
| 1b | Individual RCTs (large, well-designed) | Randomization controls confounding |
| 2a | Systematic reviews of cohort studies | Aggregated observational |
| 2b | Individual cohort studies | Prospective, no randomization |
| 3 | Case-control studies | Retrospective, selection bias risk |
| 4 | Case series / Case reports | No control group |
| 5 | Expert opinion / Mechanism-based reasoning | Highest bias |

### Critical Nuances

- Hierarchy applies primarily to **therapeutic questions**.
  For prognosis, cohort studies rank highest. For patient
  experience, qualitative studies are most appropriate.
- A well-conducted observational study can outrank a poorly
  conducted RCT. Hierarchy ranks *design potential*, not
  *actual quality*.
- Within-tier quality matters: quality assessment is needed
  in addition to tier placement.

### Design Insights for Loom

- **Hierarchy reflects bias susceptibility, not authority**:
  rank by how well methodology protects against error, not
  by prestige.
- **Aggregation beats individual**: synthesized multi-source
  conclusions outweigh any single source regardless of tier.
- **Context-dependent ranking**: different claim types may
  warrant different tier hierarchies.
- **Quality within tiers matters**: within-tier assessment
  needed, not just tier assignment.

---

## 5. PRISMA Guidelines

Preferred Reporting Items for Systematic Reviews and
Meta-Analyses. A reporting standard (27 items across 7
sections) for transparently documenting how a review was done.

### The Four-Phase Flow Diagram

1. **Identification** — records found, duplicates removed
2. **Screening** — title/abstract screening, exclusions
3. **Eligibility** — full-text assessment, exclusions with
   reasons
4. **Inclusion** — final included studies

### Design Insights for Loom

- **Provenance chains are flow diagrams**: record at every
  stage what evidence was considered, included, excluded,
  and why.
- **Transparent exclusion as important as inclusion**: track
  rejected sources with reasons.
- **Search documentation enables reproducibility**: document
  how evidence was gathered (queries, databases, dates).
- **Protocol registration**: support "claim investigations"
  registered before evidence gathering, reducing confirmation
  bias.
- **Synthesis method documentation**: record whether
  confidence was derived from quantitative aggregation,
  narrative synthesis, expert judgment, or algorithmic rules.

---

## Synthesis: Scientific Evidence Meets Loom

| Scientific Concept | Loom Mapping |
|-------------------|-------------|
| PICO protocol | Pre-specified claim investigation criteria |
| RoB 2 bias domains | Structured source evaluation dimensions |
| GRADE up/down factors | Confidence adjustment beyond base tier |
| IPCC evidence × agreement | Two-axis uncertainty model |
| IPCC likelihood restriction | Probability only when confidence ≥ high |
| EBM hierarchy | T1-T7 as bias-susceptibility ranking |
| Aggregation > individual | Synthesized evidence outweighs any source |
| PRISMA flow diagram | Provenance chain with exclusion tracking |
| Pre-registration | Investigation protocol before evidence |
| I² heterogeneity | Structured disagreement metrics |
| Publication bias | Coverage gap tracking |

### Key Architectural Principles

1. **Source tier is a starting point, not a verdict** — apply
   GRADE-like up/down factors based on directness,
   consistency, precision, and coverage.
2. **Structure the disagreement** — don't just flag "contested."
   Capture evidence strength × agreement level (IPCC model).
3. **Document the process, not just the conclusion** — PRISMA
   shows that the path to a conclusion is as important as the
   conclusion itself.
4. **Pre-specify, then evaluate** — define acceptance criteria
   before gathering evidence (Cochrane protocol model).
5. **Bias assessment is multi-dimensional** — decompose into
   specific domains rather than holistic judgment (RoB 2).
