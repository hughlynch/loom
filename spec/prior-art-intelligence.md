# Prior Art: Intelligence Community Source Grading

**Part of:** Loom Prior Art Research
**See also:** `prior-art.md` (index)

---

## 1. Admiralty Code / NATO Source Grading

Two-axis intelligence grading method originating in 1939
British Naval Intelligence. Adopted by NATO via AJP-2.1 and
STANAG 2511. Used by NATO nations and Five Eyes.

### The Reliability × Credibility Matrix

Two-character notation (e.g., "B3") combining independently
assessed dimensions:

**Source Reliability (A-F) — Who said it?**
- **A** — Completely reliable: proven accuracy, no doubts
- **B** — Usually reliable: generally trustworthy, minor issues
- **C** — Fairly reliable: some demonstrated validity
- **D** — Not usually reliable: significant doubt
- **E** — Unreliable: lacks authenticity, history of invalid info
- **F** — Reliability cannot be judged: new/unknown source

**Information Credibility (1-6) — What was said?**
- **1** — Confirmed: verified by multiple independent sources
- **2** — Probably true: unconfirmed but logical and consistent
- **3** — Possibly true: reasonably logical, needs verification
- **4** — Doubtfully true: inconsistent, unconfirmed
- **5** — Improbable: illogical, contradicts established facts
- **6** — Cannot be assessed: insufficient context

### The Diagonal Collapse Problem

Baker et al. (1968): 87% of ratings fell along the diagonal
(A1, B2, C3...). Analysts unconsciously conflate source trust
with information quality despite the two-axis design. This is
the primary failure mode.

### Design Insight for Loom

Loom's single-axis T1-T7 conflates "who said it" with "how
credible is the claim." The Admiralty Code demonstrates these
are fundamentally different questions. A T1 source can produce
low-credibility information; an unknown source can provide
confirmed facts.

**Recommendation:** Adopt dual-axis evaluation. T1-T7 as the
source reliability axis. Add a second axis for information
credibility (confirmed → cannot be assessed). Enforce
independence between axes with separate evaluation steps and
mandatory justification when axes diverge. The F/6 grades
("cannot be judged") acknowledge legitimate uncertainty about
the rating itself.

---

## 2. ICD 203: US Intelligence Community Analytic Standards

Establishes analytic standards for all US IC products.
Issued 2007, revised 2015 by DNI.

### Nine Analytic Tradecraft Standards

1. Describes quality and reliability of sources
2. Addresses and expresses uncertainties
3. Distinguishes information from assumptions/judgments
4. Incorporates analysis of alternatives
5. Demonstrates relevance, addresses implications
6. Uses clear and logical argumentation
7. Explains change to or consistency of judgments
8. Makes accurate judgments
9. Incorporates effective visuals

### Confidence vs Probability (Critical Distinction)

ICD 203 **prohibits** combining confidence and likelihood in
the same sentence:

- **Confidence** = how much you trust your own assessment
  (based on source quality, quantity, consistency)
- **Probability** = how likely the event/development is

You can have "high confidence" that something is "unlikely"
(good sources agree it won't happen), or "low confidence"
that something is "likely" (fragmentary evidence suggests it).

### Three Confidence Levels

- **High**: multiple trustworthy sources, minimal conflict
- **Moderate**: credibly sourced, plausible, insufficient
  corroboration for higher
- **Low**: uncertain source credibility, scant/fragmented/
  poorly corroborated

### Design Insight for Loom

Loom should not conflate "how sure am I about this claim"
with "how good is my evidence." Each claim should carry:
(a) source tier (T1-T7), (b) information credibility (1-6),
(c) analytic confidence (high/moderate/low), and
(d) probability range where applicable.

Tradecraft Standard #3 (distinguish information from judgment):
provenance chains should mark transitions from evidence to
inference. Every inference step should declare assumptions.

Standard #7 (explain changes): track judgment evolution over
time, not just current state.

Standard #4 (analysis of alternatives): don't just store the
winning hypothesis — document what alternatives were considered
and why rejected.

---

## 3. Structured Analytic Techniques (SATs)

Formalized reasoning methods developed by CIA to counteract
cognitive biases. Three categories: diagnostic, contrarian,
imaginative.

### Key Techniques

**Analysis of Competing Hypotheses (ACH):**
1. Brainstorm all reasonable hypotheses
2. List all significant evidence
3. Create matrix: hypotheses × evidence
4. Rate each evidence item as Consistent/Inconsistent/Neutral
   for each hypothesis
5. Focus on *disproving* hypotheses, not proving one
6. Tally inconsistencies to identify weakest hypotheses
7. Test sensitivity to critical evidence
8. Identify missing evidence and deception possibilities

**Key Assumptions Check:** List all stated and unstated
premises, challenge each under different conditions.

**Devil's Advocacy:** Build the best possible case against
a dominant consensus. Must be clearly labeled.

**Red Team Analysis:** Independent team adopts adversary's
perspective to identify vulnerabilities.

**High-Impact/Low-Probability Analysis:** Focus on unlikely
but consequential events. Identify pathways and triggers.
(Berlin Wall, Shah's fall, Soviet collapse were all considered
low-probability.)

### Design Insight for Loom

- **ACH is directly automatable**: a matrix of evidence ×
  hypotheses with consistency ratings. Loom could implement
  this as a data structure for contested claims.
- **Key Assumptions Check**: every inference should declare
  its assumptions; assumptions should be periodically
  re-evaluated.
- **Devil's Advocacy / Red Teaming**: automated adversarial
  review passes that attempt to disprove high-confidence
  claims.
- **Low-probability preservation**: maintain unlikely-but-
  consequential hypotheses with indicator watchlists rather
  than pruning them.

---

## 4. Sherman Kent: Estimative Language

CIA Office of National Estimates head. Published "Words of
Estimative Probability" (1964). Key finding: analysts
interpreted "probable" as anywhere from 20% to 95%.

### Kent's Scale (1964)

| Term | Central Value | Range |
|------|--------------|-------|
| Certain | 100% | — |
| Almost certain | ~93% | 87-99% |
| Probable / Likely | ~75% | 63-87% |
| Chances about even | ~50% | 40-60% |
| Probably not / Unlikely | ~30% | 20-40% |
| Almost certainly not | ~7% | 2-12% |
| Impossible | 0% | — |

### Modern ODNI Scale (Current US IC Standard)

| Term | Range |
|------|-------|
| Almost no chance | 1-5% |
| Very unlikely / Remote | 5-20% |
| Unlikely / Probably not | 20-45% |
| Roughly even chance | 45-55% |
| Likely / Probable | 55-80% |
| Very likely / Highly probable | 80-95% |
| Almost certain / Nearly certain | 95-99% |

### Design Insight for Loom

Verbal probability terms are interpreted with dangerous
variability. Loom should:

1. **Store confidence as numeric ranges, not verbal labels.**
   0.75 ± 0.12 is more precise than "probable."
2. **Map verbal labels to numeric ranges for display** using
   the ODNI 7-level scale (most institutional adoption,
   tightest definitions).
3. **Never conflate probability with confidence** (per ICD 203).
4. **Track provenance of the estimate itself** — who assigned
   it, based on what evidence, when.

---

## Synthesis: Three-Dimensional Knowledge Claims

Combining all four systems, each Loom claim should carry:

```
claim:
  statement: "The school budget increased 8%"
  source_reliability: T1        # Admiralty axis 1: who said it
  information_credibility: 1    # Admiralty axis 2: confirmed
  analytic_confidence: high     # ICD 203: how good is evidence
  probability: 0.95 ± 0.04     # Kent/ODNI: likelihood range
  assumptions: [...]            # SATs: declared premises
  alternatives_considered: [...] # ACH: rejected hypotheses
  provenance:
    evidence_steps: [...]       # ICD 203 Standard #3
    inference_steps: [...]      # marked transitions
  judgment_history: [...]       # ICD 203 Standard #7
```
