# Prior Art: Epistemic and Argumentation Frameworks

**Part of:** Loom Prior Art Research
**See also:** `prior-art.md` (index)

---

## 1. Bayesian Epistemology

Beliefs as *credences* (subjective probabilities 0-1).
Bayes' Theorem for updating on evidence.

### Core Norms

- **Probabilism**: credences satisfy probability axioms
- **Conditionalization**: update via Bayes' Theorem:
  `Cr(H|E) = [Cr(E|H) × Cr(H)] / Cr(E)`
- **Dutch Book arguments**: non-probabilistic credences
  create guaranteed betting losses

### Bayesian Networks

DAGs where nodes = variables, edges = conditional
dependencies. Each node carries a conditional probability
table. Markov condition: each node is conditionally
independent of non-descendants given parents.

Propagation algorithms (variable elimination, belief
propagation) compute updated marginals when evidence
nodes are instantiated.

### The Problem of Priors

Deepest divide in Bayesian epistemology. Subjective Bayesians:
any coherent prior is permissible. Objective Bayesians: add
the Principle of Indifference (paradox-prone). "Merging of
opinions" theorems show convergence over time regardless of
starting priors.

### Design Insights for Loom

- **Loom's discrete levels are coarse-grained Bayesian
  posteriors.** "Verified" ≈ very high posterior from
  high-quality evidence. Deterministic rules encoding
  domain-expert priors about source reliability.
- **Independence structure matters**: evidence from
  independent sources is more powerful than correlated
  evidence. Two T3 sources citing the same T1 upstream
  ≠ two independent T3 sources. Loom must track whether
  evidence chains share common ancestors.
- **The prior problem validates Loom's approach**: T1-T7 is
  an explicit, auditable encoding of what Bayesians leave
  implicit. A strength, not a limitation.
- **Propagation algorithms are relevant**: when new evidence
  enters, confidence updates must propagate through the
  graph. Bayesian belief propagation provides proven
  algorithms for this.
- **Sensitivity analysis**: "which evidence links are
  load-bearing for this claim's current confidence?"

---

## 2. Dung Argumentation Frameworks

Abstract argumentation (Dung 1995): graph of arguments
connected by attack relations.

### Formal Definition

AF = (Args, Attacks) where Attacks is a binary relation.

- **Conflict-free set**: no member attacks another member
- **Defense**: S defends a if for every b attacking a, some
  member of S attacks b
- **Admissible**: conflict-free + defends all its members

### Semantics

- **Grounded extension** (skeptical): least fixed point.
  Start with unattacked arguments, iteratively add defended.
  Exactly one per framework. Accept only what you must.
- **Preferred extensions** (credulous): maximal admissible
  sets. Accept as much as consistently possible.
- **Stable extensions**: conflict-free sets that attack
  everything outside them. Not guaranteed to exist.

Relationship: stable ⊂ preferred ⊂ complete ⊂ admissible
⊂ conflict-free.

### Bipolar Argumentation Frameworks (BAFs)

Extend Dung with a **support** relation: (Args, Attacks,
Supports). Three interpretations:
- Deductive: accepting a implies accepting b
- Necessary: accepting a is required for accepting b
- Evidential: arguments need positive support to stand

### Design Insights for Loom

- **Contradictions are attack relations.** Loom's "contested"
  claims are arguments with active attacks. Dung provides
  rigorous resolution semantics.
- **Choose semantics deliberately**: grounded (skeptical,
  conservative) vs preferred (credulous, accept maximal
  consistent sets). For reliability-focused Loom, grounded
  is natural for default confidence; preferred for exploring
  alternative interpretations.
- **BAF support = evidence links**: the BAF notion that
  arguments need positive evidential support mirrors Loom's
  model exactly. Evidence links ARE the support relation.
- **Defense function F ≈ confidence computation**: given
  accepted evidence, compute which claims are supported at
  each level. Iterate to fixed point for consistency.
- **Secondary attack**: A supports B, C attacks A → C
  indirectly undermines B. Loom should propagate source
  discrediting through evidence chains.

---

## 3. Truth Maintenance Systems (TMS)

Dependency networks tracking not just what is believed but
*why* — justifications connecting premises to conclusions.

### JTMS (Justification-based, Doyle 1979)

- Nodes labeled IN (believed) or OUT
- Justifications have in-list (must be IN) and out-list
  (must be OUT)
- **Dependency-directed backtracking**: when contradiction
  reached, trace justifications to find responsible
  assumptions. Far more efficient than blind backtracking.
- Limitation: single context. Switching assumptions requires
  complete relabeling.

### ATMS (Assumption-based, de Kleer 1986)

- Nodes labeled with **environments** (sets of assumptions
  under which the node holds)
- **Nogoods**: inconsistent environments. Supersets also
  inconsistent.
- Labels guarantee: soundness, consistency, minimality,
  completeness
- **Maintains all contexts simultaneously**. "Context
  switching is free, most backtracking avoided."
- Supports non-monotonic reasoning: default assumptions
  held tentatively, withdrawn when contradictions emerge.

### Design Insights for Loom

**This is the most directly relevant framework.**

- **Loom's evidence graph IS a dependency network.** Each
  claim believed because of specific evidence links
  (justifications). TMS is the theoretical foundation.
- **Retraction propagation**: when evidence is discredited,
  all downstream claims must be re-evaluated.
  Dependency-directed backtracking tells you *exactly* which
  claims are affected, avoiding full re-evaluation.
- **ATMS multi-context enables "what-if" queries**: "what
  would claim X's confidence be without evidence Y?" "what
  are the minimal evidence sets supporting claim X?" These
  are exactly ATMS label queries.
- **Nogoods = contradiction handling**: conflicting evidence
  combinations are nogoods. ATMS propagates: claims depending
  on both conflicting sources inherit inconsistency.
- **ATMS labels implement provenance**: track not just
  "corroborated" but "corroborated under {evidence A from
  T1, evidence B from T3}" — making provenance fully explicit
  and queryable.
- **Non-monotonic reasoning supports evolving knowledge**:
  beliefs held tentatively, new information can retract
  previous conclusions without logical contradiction.

---

## 4. Toulmin Model of Argumentation

Practical framework for argument structure (1958). Designed
for how arguments actually work in law, science, everyday
reasoning.

### Six Components

1. **Claim** — the conclusion being argued for
2. **Data (Grounds)** — evidence supporting the claim
3. **Warrant** — reasoning connecting data to claim (the
   inferential bridge; *why* data supports claim)
4. **Backing** — evidence supporting the warrant itself
5. **Qualifier** — degree of certainty ("probably",
   "certainly", "in most cases")
6. **Rebuttal** — conditions under which claim would not hold

Complete argument: "Given [data], since [warrant] (on account
of [backing]), [qualifier] [claim], unless [rebuttal]."

### Design Insights for Loom

Direct mapping to Loom's evidence structure:

| Toulmin | Loom |
|---------|------|
| Claim | Knowledge claim |
| Data | Evidence links (source material) |
| Warrant | **GAP** — reasoning connecting evidence to claim |
| Backing | Tier metadata (why T1-T7 is trustworthy) |
| Qualifier | Confidence level |
| Rebuttal | Contradicting evidence / known limitations |

**The warrant is Loom's biggest gap.** Loom tracks that
evidence E supports claim C, but does it track *how* or
*why*? The warrant is the inferential step. Making warrants
explicit enables detecting when reasoning steps are flawed
even if evidence is sound.

**Rebuttals formalize the "contested" state.** Track not
just contradicting evidence but the specific conditions
under which the claim fails.

---

## 5. Epistemic Logic

Modal logic formalizing knowledge (K_a P) and belief (B_a P)
using possible-worlds semantics (Kripke models).

### Key Systems

- **S5** (knowledge): reflexive (factive: K→P), transitive
  (positive introspection), symmetric (negative introspection)
- **KD45** (belief): not factive (can believe falsehoods),
  but consistent (can't believe P and ¬P simultaneously)

### Justification Logic (Artemov)

Replaces implicit modal operator with explicit justification
terms: t:P ("t justifies P"). Key axioms:
- Application: s:(A→B) → (t:A → [s·t]:B)
- Sum: s:A → [s+t]:A (justification aggregation)
- Factivity: t:A → A

**Realization Theorem**: every S4 theorem can be realized
with explicit justification terms. Provenance contains
strictly more information than "this is known."

### The Gettier Problem

JTB (Justified True Belief) is insufficient for knowledge.
Gettier cases: justified true belief where justification is
"accidentally" correct. Justification logic addresses this
by tracking specific justification paths.

### Design Insights for Loom

- **Loom operates in KD45 (belief), not S5 (knowledge).**
  It represents beliefs with varying confidence, not absolute
  knowledge. Consistency axiom: never simultaneously assert
  a claim as both verified and contested.
- **Justification logic = provenance chains.** t:P is exactly
  "evidence chain E supports claim C." Application axiom
  formalizes how evidence links compose. Sum axiom formalizes
  how corroboration strengthens confidence.
- **Realization Theorem validates provenance**: explicit
  justification (provenance) contains strictly more info than
  implicit modality ("this is known"). Provenance is
  epistemologically necessary, not mere bookkeeping.
- **Gettier warning**: two sources agreeing because they share
  the same flawed upstream ≠ genuine corroboration. Track
  whether evidence chains share common ancestors.
- **Introspection enables meta-reasoning**: Loom can reason
  about its own confidence: "we are confident this is verified
  because..." Supports auditability.

---

## Synthesis: What These Frameworks Tell Loom

### The Evidence Graph is the Right Abstraction

All five frameworks converge:
- Bayesian: DAG of conditional dependencies
- Dung: directed graph of attack/support
- TMS: dependency network of justifications
- Toulmin: structured argument with warrant chains
- Justification logic: proof terms tracking composition

### Deterministic Rules are Defensible

Bayesian epistemology shows the continuous alternative but
also its costs: problem of priors, logical omniscience,
computational complexity. Loom's discrete levels with
deterministic rules are more tractable, more auditable, and
avoid the prior problem by encoding source reliability
judgments directly into the tier system.

### Three Additions Loom Should Consider

1. **Explicit warrants** (Toulmin): not just "E supports C"
   but "E supports C *because* [reasoning W]." Enables
   detecting flawed reasoning even with sound evidence.

2. **ATMS-style multi-context labels** (TMS): for each claim,
   track the *minimal sets of evidence* supporting it.
   Enables "what-if" queries, sensitivity analysis, precise
   retraction.

3. **Independence tracking** (Bayesian): distinguish genuinely
   independent evidence from evidence sharing common upstream.
   Two independent T3 sources > two T3 sources citing the
   same T1.

### Semantic Choice

Loom should expose two views:
- **Grounded confidence** (Dung skeptical): what survives all
  challenges. Conservative. Default for publication.
- **Preferred confidence** (Dung credulous): what holds in
  each maximal consistent interpretation. For exploration.
