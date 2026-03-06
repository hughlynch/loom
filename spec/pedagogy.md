# Pedagogy: Teaching Knowledge to Humans and Agents

**Author:** Hugh Lynch, with Claude
**Date:** 2026-03-06
**Part of:** Loom — the ABWP Knowledge System
**Depends on:** Knowledge Acquisition (`spec/knowledge-acquisition.md`), Knowledge CI/CD (`spec/knowledge-ci.md`), Grove Rituals & Coaching (GROVE-RECONSTRUCTION-GUIDE.md)
**Applies to:** Weft (civic literacy), Cubby (journalistic context), Sil (personal learning), Mirabebe (child development), and any Grove system that teaches from a knowledge base
**See also:** Adversarial Resilience (`spec/loom-adversarial-resilience.md`)

---

## The Problem

The knowledge acquisition framework builds reliable knowledge.
The CI/CD pipeline compiles it into fast, testable snapshots.
But knowledge sitting in a database is inert. It becomes
useful only when it reaches a mind — human or agent — that
can understand, apply, and build on it.

Teaching is the hardest part. The same verified fact about
municipal bond financing needs to be explained differently to
a 12-year-old doing a civics project, a new community member
trying to understand their property tax, a Cubby reporter
covering a bond issuance, and a new Grove worker learning the
`weft.analyze.estimate_cost` skill. Same knowledge, four
radically different baselines, four different goals, four
different measures of success.

The challenge the user identified is precise: "countless
people and agents to educate from an infinitely varied
baseline." No single curriculum works. No fixed sequence of
topics fits every learner. The system must diagnose, adapt,
and verify — continuously — for each learner individually.

This document defines the workers, rituals, rubrics, and
schemas that make that possible.

---

## 1. Core Principles

Six principles govern pedagogy. They parallel the knowledge
acquisition principles (K1–K6) and Grove's design principles
(P1–P6). All three sets reinforce each other.

**P1. Meet the learner where they are.** Diagnostic assessment
before instruction. No assumptions about baseline. A worker
that skips diagnosis is like a doctor who skips examination —
any prescription is a guess. The system discovers what the
learner knows, what they don't, and what they think they know
but have wrong (misconceptions, which are the most dangerous
gap of all).

**P2. Teach structure, not just facts.** Knowledge has
architecture: prerequisites, dependencies, implications,
analogies. A learner who understands *why* budget cycles work
the way they do retains more than one who memorizes dates.
Concept maps make this structure explicit and navigable.

**P3. Preserve epistemic honesty.** When teaching from the
knowledge base, carry the confidence level through to
instruction. Never present a "contested" claim as settled.
Never present a "reported" finding as "verified." This is
the meta-skill: teaching learners to read confidence signals,
to ask "how do we know this?", to distinguish evidence from
assertion. A learner who trusts the system uncritically has
not been well taught.

**P4. Active recall over passive exposure.** Reading is not
learning. Retrieval practice is learning. The system asks
questions, poses scenarios, creates practice opportunities.
Spaced repetition ensures concepts stick. The measure of
teaching is not what was explained, but what the learner can
independently retrieve and apply.

**P5. Progression is earned, not scheduled.** Mastery-based
advancement, not time-based. A learner who demonstrates
understanding moves forward. One who doesn't gets different
instruction — a new analogy, a different example, a simpler
prerequisite — not the same explanation repeated louder. The
concept map determines what's next; the learner's mastery
determines when.

**P6. Teaching is observable and improvable.** Pedagogy workers
are coached just like any other Grove worker. Teaching quality
is measured through learner outcomes, not self-assessment.
Anti-patterns are named, detected, and remediated. The coaching
flywheel applies to teaching the same way it applies to coding
or data analysis.

---

## 2. The Learner Model

The system maintains a structured model of each learner:
what they know, how they learn, where they struggle, and
what's next.

### 2.1 Schema

```sql
-- Core learner identity
CREATE TABLE learners (
    learner_id      TEXT PRIMARY KEY,
    learner_type    TEXT NOT NULL,      -- human | agent
    community_id    TEXT,
    display_name    TEXT,
    created_at      TEXT NOT NULL,
    last_active     TEXT NOT NULL,
    preferences     TEXT               -- JSON: discovered learning preferences
);

-- Per-concept mastery tracking
CREATE TABLE mastery (
    learner_id      TEXT NOT NULL REFERENCES learners(learner_id),
    concept_id      TEXT NOT NULL REFERENCES concepts(concept_id),
    level           TEXT NOT NULL,      -- novice | developing | proficient | expert
    confidence      REAL NOT NULL,      -- 0.0-1.0, computed from assessment history
    last_assessed   TEXT,
    next_review     TEXT,              -- spaced repetition schedule
    attempts        INTEGER DEFAULT 0,
    misconceptions  TEXT,              -- JSON: identified wrong mental models
    PRIMARY KEY (learner_id, concept_id)
);

-- Learning session history
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,
    learner_id      TEXT NOT NULL REFERENCES learners(learner_id),
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    concepts_covered TEXT NOT NULL,     -- JSON array of concept_ids
    strategy_used   TEXT NOT NULL,      -- direct | socratic | example_driven |
                                       -- analogy | contradiction | practice
    assessments     TEXT,              -- JSON: questions asked, answers given, scores
    outcome         TEXT,              -- JSON: mastery changes resulting from session
    tutor_trace_id  TEXT               -- link to Grove cognitive trace for coaching
);

-- Learning path: personalized curriculum
CREATE TABLE learning_paths (
    path_id         TEXT PRIMARY KEY,
    learner_id      TEXT NOT NULL REFERENCES learners(learner_id),
    domain_id       TEXT NOT NULL,
    goal            TEXT NOT NULL,      -- what the learner is working toward
    current_concept TEXT,              -- where they are now
    remaining       TEXT NOT NULL,      -- JSON: ordered list of concept_ids
    completed       TEXT NOT NULL,      -- JSON: ordered list of concept_ids
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    status          TEXT NOT NULL       -- active | completed | paused | abandoned
);
```

### 2.2 Mastery levels

| Level | Meaning | Assessment criteria |
|-------|---------|-------------------|
| **Novice** | No demonstrated knowledge | Cannot answer basic questions about the concept |
| **Developing** | Partial understanding, may have misconceptions | Can answer some questions but makes systematic errors |
| **Proficient** | Solid understanding, can apply in familiar contexts | Answers correctly ≥80% of the time, can explain reasoning |
| **Expert** | Deep understanding, can apply in novel contexts and teach others | Answers correctly ≥95%, can handle edge cases and explain to others |

Mastery is not self-reported. It is computed from assessment
results over time. The `confidence` field (0.0–1.0) reflects
the system's confidence in the mastery level, based on
recency and consistency of assessments. A learner who was
proficient six months ago but hasn't been assessed since has
a decaying confidence score.

### 2.3 Discovering learning preferences

The system does not ask learners to self-report their
preferences ("are you a visual learner?"). Self-reported
learning styles are not well-supported by research. Instead,
the system discovers effective strategies empirically:

1. Start with direct instruction (the default)
2. Track comprehension outcomes per strategy
3. When direct instruction produces low comprehension,
   try example-driven or analogy-based
4. Record which strategies produce the best outcomes for
   this learner on this type of concept
5. Use accumulated data to select strategies for new concepts

The `preferences` field in the learner table stores discovered
patterns as JSON:

```json
{
  "effective_strategies": {
    "abstract_concepts": "example_driven",
    "procedural_knowledge": "direct",
    "contested_topics": "contradiction"
  },
  "engagement_signals": {
    "prefers_short_sessions": true,
    "asks_follow_up_questions": true,
    "responds_well_to_analogies": true
  }
}
```

---

## 3. Concept Maps: Knowledge as a Navigable DAG

Knowledge in the snapshot is organized as claims and chunks.
For pedagogy, it needs an additional layer: **concept maps**
that define what must be understood before what.

### 3.1 Schema

```sql
-- Concepts: teachable units of knowledge
CREATE TABLE concepts (
    concept_id      TEXT PRIMARY KEY,
    domain_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT NOT NULL,      -- from domain taxonomy
    depth           INTEGER NOT NULL,   -- 0 = foundational, higher = more advanced
    claim_ids       TEXT NOT NULL,      -- JSON: KB claims that comprise this concept
    chunk_ids       TEXT NOT NULL,      -- JSON: snapshot chunks for retrieval
    teach_time_minutes INTEGER,         -- estimated teaching time
    frontier        BOOLEAN DEFAULT 0   -- true if concept includes contested/emerging knowledge
);

-- Edges: prerequisite and relationship links
CREATE TABLE concept_edges (
    from_concept    TEXT NOT NULL REFERENCES concepts(concept_id),
    to_concept      TEXT NOT NULL REFERENCES concepts(concept_id),
    edge_type       TEXT NOT NULL,      -- prerequisite | builds_on | related |
                                       -- contrasts_with | applies_to
    strength        REAL DEFAULT 1.0,   -- 0.0-1.0: how essential is this edge?
    PRIMARY KEY (from_concept, to_concept)
);
```

### 3.2 Edge types

| Edge type | Meaning | Pedagogical implication |
|-----------|---------|----------------------|
| **prerequisite** | Must understand A before teaching B | Block advancement until A is proficient |
| **builds_on** | B extends A but A isn't strictly required | Prefer to teach A first, but can skip if learner demonstrates understanding of B directly |
| **related** | A and B cover similar territory | Teach together for contrast, or use one as an analogy for the other |
| **contrasts_with** | A and B are commonly confused | Explicitly teach the distinction |
| **applies_to** | A is a general principle; B is a specific application | Use B as an example when teaching A |

### 3.3 The frontier

The frontier is where verified knowledge ends and
contested/emerging knowledge begins. In the concept map,
frontier concepts are those whose linked claims include
"contested," "reported," or "unverified" confidence levels.

Teaching at the frontier is fundamentally different from
teaching established knowledge:

| Established knowledge | Frontier knowledge |
|----------------------|-------------------|
| "Here is how property tax assessment works" | "Here is the current debate about reassessment frequency" |
| Teach with confidence | Teach with explicit uncertainty |
| Assess on correctness | Assess on ability to evaluate evidence |
| Direct instruction works well | Contradiction-based strategy works best |
| Mastery = can explain and apply | Mastery = can articulate both positions and their evidence |

For scientific domains, the frontier is where the knowledge
acquisition system surfaces preprints, contested findings,
and emerging consensus. The pedagogy system teaches learners
to navigate this honestly — not to pick a side, but to
evaluate the evidence landscape.

### 3.4 Concept map maintenance

Concept maps are built and maintained by a dedicated worker
(`pedagogy.concepts.build`) that analyzes the knowledge
snapshot and proposes concept structures. Human curators
approve concept maps, because pedagogical organization is
a judgment call — there are many valid ways to structure the
same knowledge for teaching.

When the knowledge snapshot is rebuilt (via the CI/CD pipeline),
the concept map worker checks for:
- New claims that don't map to any concept (coverage gap)
- Claims whose confidence changed (may shift a concept's
  frontier status)
- Superseded claims (may obsolete or restructure a concept)
- New contradictions (may create frontier concepts)

---

## 4. Pedagogy Workers

Five workers handle the stages of teaching. Each is a Grove
worker with skills in the `pedagogy.*` namespace, coached
through the standard flywheel.

### 4.1 Worker definitions

| Worker | Skills | Role |
|--------|--------|------|
| **Diagnostician** | `pedagogy.diagnose`, `pedagogy.diagnose.quick` | Assesses learner's current knowledge state. Generates targeted questions from the concept map, evaluates answers, maps results onto mastery levels. `quick` variant does a fast 3-question screen; full variant does comprehensive assessment. |
| **Pathfinder** | `pedagogy.path.create`, `pedagogy.path.update` | Generates personalized learning paths through the concept graph. Respects prerequisites, incorporates learner goals, adapts when mastery assessments change the picture. |
| **Tutor** | `pedagogy.tutor.explain`, `pedagogy.tutor.socratic`, `pedagogy.tutor.example`, `pedagogy.tutor.analogy`, `pedagogy.tutor.contradiction` | Delivers instruction. Each skill variant implements a different teaching strategy. Selects strategy based on learner model, concept type, and historical effectiveness. Queries the knowledge snapshot for content. |
| **Examiner** | `pedagogy.examine.recall`, `pedagogy.examine.apply`, `pedagogy.examine.evaluate`, `pedagogy.examine.review` | Creates and evaluates assessments. `recall` tests factual retrieval. `apply` tests application to scenarios. `evaluate` tests ability to assess evidence (for frontier concepts). `review` handles spaced repetition check-ins. |
| **Coach** | `pedagogy.coach.review`, `pedagogy.coach.intervene` | Meta-level monitoring. Reviews learning progress over time, identifies stalls, recommends strategy changes. `intervene` triggers when a learner is stuck — switches strategies, suggests prerequisites, or escalates to human. |

### 4.2 Strategy selection

The Tutor selects a teaching strategy based on these inputs:

```
concept.depth         → deeper concepts benefit from example-driven
concept.frontier      → frontier concepts need contradiction-based
learner.mastery[concept] → novice needs direct, developing needs Socratic
learner.preferences   → discovered effective strategies
previous_attempts     → if direct failed, try analogy; if analogy failed, try example
```

Decision table:

| Concept type | Learner level | Recommended strategy |
|-------------|---------------|---------------------|
| Foundational fact | Novice | Direct instruction |
| Foundational fact | Developing (misconception detected) | Contradiction-based (to surface and correct misconception) |
| Procedural knowledge | Novice | Direct with worked examples |
| Procedural knowledge | Developing | Practice-and-feedback |
| Abstract principle | Novice | Example-driven (concrete first) |
| Abstract principle | Developing | Socratic (guide to generalization) |
| Frontier/contested | Any | Contradiction-based (present evidence, evaluate) |
| Novel domain for learner | Any | Analogy to familiar domain |
| Review/retention | Proficient+ | Spaced repetition recall |

---

## 5. Rituals

### 5.1 `pedagogy.assess` — Diagnostic assessment

```yaml
id: ritual.pedagogy.assess
version: 1.0.0
description: >
  Assess a learner's current knowledge state for a domain.
  Maps baseline onto the concept graph and creates a
  learner profile.

params:
  - name: learner_id
    type: string
    required: true
  - name: domain_id
    type: string
    required: true
  - name: assessment_depth
    type: string
    default: "standard"
    description: "quick (3 questions) | standard (10-15) | comprehensive (25+)"

steps:
  - id: load_concept_map
    skill: pedagogy.concepts.load
    context_map:
      domain_id: "{{ params.domain_id }}"

  - id: load_learner
    skill: pedagogy.learner.load
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"

  - id: diagnose
    skill: pedagogy.diagnose
    depends_on: [load_concept_map, load_learner]
    context_map:
      learner_id: "{{ params.learner_id }}"
      concept_map: "{{ steps.load_concept_map.result }}"
      existing_mastery: "{{ steps.load_learner.result.mastery }}"
      depth: "{{ params.assessment_depth }}"

  - id: create_path
    skill: pedagogy.path.create
    depends_on: [diagnose]
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"
      mastery_map: "{{ steps.diagnose.result.mastery }}"
      concept_map: "{{ steps.load_concept_map.result }}"
      learner_goal: "{{ steps.load_learner.result.goal }}"

output_map:
  mastery_map: "{{ steps.diagnose.result.mastery }}"
  misconceptions: "{{ steps.diagnose.result.misconceptions }}"
  learning_path: "{{ steps.create_path.result }}"
  recommended_start: "{{ steps.create_path.result.current_concept }}"
```

### 5.2 `pedagogy.teach` — Teaching session

```yaml
id: ritual.pedagogy.teach
version: 1.0.0
description: >
  Conduct a teaching session. Explains concepts, checks
  understanding, updates mastery, and interleaves review
  of previously learned material.

params:
  - name: learner_id
    type: string
    required: true
  - name: domain_id
    type: string
    required: true
  - name: session_duration_minutes
    type: integer
    default: 30
  - name: max_new_concepts
    type: integer
    default: 3

steps:
  - id: prepare
    skill: pedagogy.session.prepare
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"
      duration: "{{ params.session_duration_minutes }}"
      max_new: "{{ params.max_new_concepts }}"

  - id: teach_concepts
    skill: pedagogy.tutor.explain
    depends_on: [prepare]
    for_each: "{{ steps.prepare.result.session_plan }}"
    max_parallel: 1
    context_map:
      learner_id: "{{ params.learner_id }}"
      concept: "{{ item.concept }}"
      strategy: "{{ item.strategy }}"
      knowledge_chunks: "{{ item.chunks }}"
      is_review: "{{ item.is_review }}"

  - id: assess
    skill: pedagogy.examine.recall
    depends_on: [teach_concepts]
    for_each: "{{ steps.prepare.result.session_plan }}"
    max_parallel: 1
    context_map:
      learner_id: "{{ params.learner_id }}"
      concept: "{{ item.concept }}"

  - id: update_mastery
    skill: pedagogy.learner.update
    depends_on: [assess]
    context_map:
      learner_id: "{{ params.learner_id }}"
      assessment_results: "{{ steps.assess.result }}"
      teaching_results: "{{ steps.teach_concepts.result }}"

  - id: update_path
    skill: pedagogy.path.update
    depends_on: [update_mastery]
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"
      mastery_changes: "{{ steps.update_mastery.result }}"

output_map:
  concepts_taught: "{{ steps.teach_concepts.result | map('concept') }}"
  mastery_changes: "{{ steps.update_mastery.result }}"
  next_session_recommendation: "{{ steps.update_path.result.next }}"
  session_quality: "{{ steps.assess.result | map('score') | avg }}"
```

### 5.3 `pedagogy.examine` — Formal assessment

```yaml
id: ritual.pedagogy.examine
version: 1.0.0
description: >
  Formal assessment of learner knowledge. Generates
  calibrated questions, evaluates responses, updates
  mastery levels, and identifies misconceptions.

params:
  - name: learner_id
    type: string
    required: true
  - name: domain_id
    type: string
    required: true
  - name: concepts
    type: array
    required: false
    description: "Specific concepts to assess. If empty, auto-select based on path."
  - name: assessment_type
    type: string
    default: "mixed"
    description: "recall | apply | evaluate | mixed"

steps:
  - id: generate
    skill: pedagogy.examine.generate
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"
      concepts: "{{ params.concepts }}"
      assessment_type: "{{ params.assessment_type }}"

  - id: administer
    skill: pedagogy.examine.administer
    depends_on: [generate]
    context_map:
      learner_id: "{{ params.learner_id }}"
      questions: "{{ steps.generate.result.questions }}"

  - id: evaluate
    skill: pedagogy.examine.evaluate
    depends_on: [administer]
    context_map:
      learner_id: "{{ params.learner_id }}"
      questions: "{{ steps.generate.result.questions }}"
      responses: "{{ steps.administer.result.responses }}"

  - id: identify_misconceptions
    skill: pedagogy.examine.misconceptions
    depends_on: [evaluate]
    context_map:
      learner_id: "{{ params.learner_id }}"
      incorrect_responses: "{{ steps.evaluate.result.incorrect }}"

  - id: update
    skill: pedagogy.learner.update
    depends_on: [evaluate, identify_misconceptions]
    context_map:
      learner_id: "{{ params.learner_id }}"
      assessment_results: "{{ steps.evaluate.result }}"
      misconceptions: "{{ steps.identify_misconceptions.result }}"

output_map:
  score: "{{ steps.evaluate.result.score }}"
  mastery_changes: "{{ steps.update.result }}"
  misconceptions: "{{ steps.identify_misconceptions.result }}"
  concepts_mastered: "{{ steps.evaluate.result.mastered }}"
  concepts_needing_work: "{{ steps.evaluate.result.needs_work }}"
```

### 5.4 `pedagogy.coach.review` — Progress review

```yaml
id: ritual.pedagogy.coach.review
version: 1.0.0
description: >
  Periodic review of learner progress. Identifies stalls,
  recommends strategy changes, updates learning path.
  Triggered on schedule or when progress metrics plateau.

params:
  - name: learner_id
    type: string
    required: true
  - name: domain_id
    type: string
    required: true

steps:
  - id: analyze
    skill: pedagogy.coach.analyze
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"

  - id: diagnose_stalls
    skill: pedagogy.coach.diagnose_stalls
    depends_on: [analyze]
    context_map:
      trajectory: "{{ steps.analyze.result.trajectory }}"
      session_history: "{{ steps.analyze.result.sessions }}"

  - id: recommend
    skill: pedagogy.coach.recommend
    depends_on: [diagnose_stalls]
    context_map:
      learner_id: "{{ params.learner_id }}"
      stalls: "{{ steps.diagnose_stalls.result.stalls }}"
      current_strategies: "{{ steps.analyze.result.strategies_used }}"
      learner_preferences: "{{ steps.analyze.result.preferences }}"

  - id: update_path
    skill: pedagogy.path.update
    depends_on: [recommend]
    condition: "{{ steps.recommend.result.path_changes | length }}"
    context_map:
      learner_id: "{{ params.learner_id }}"
      domain_id: "{{ params.domain_id }}"
      recommended_changes: "{{ steps.recommend.result.path_changes }}"

output_map:
  trajectory: "{{ steps.analyze.result.trajectory }}"
  stalls_identified: "{{ steps.diagnose_stalls.result.stalls }}"
  recommendations: "{{ steps.recommend.result }}"
  path_updated: "{{ steps.update_path.result }}"
```

---

## 6. Spaced Repetition: The Retention Engine

Teaching a concept once is not enough. Without review,
knowledge decays. The system implements spaced repetition
using a variant of the SM-2 algorithm, adapted for concept
mastery rather than flashcard memorization.

### 6.1 Review scheduling

After a concept is taught and assessed, the system schedules
a review based on performance:

```
if assessment_score >= 0.95:
    next_review = last_review + (interval * 2.5)
elif assessment_score >= 0.80:
    next_review = last_review + (interval * 1.5)
elif assessment_score >= 0.60:
    next_review = last_review + interval
else:
    next_review = last_review + 1 day
    mastery_level = max(mastery_level - 1, "novice")
    interval = reset to 1 day
```

Initial interval: 1 day. Maximum interval: 180 days.

### 6.2 Review integration with teaching sessions

The `pedagogy.teach` ritual's `prepare` step interleaves
review items with new concepts:

```
session_plan = []

# 1. Review items due today (up to 40% of session time)
due_reviews = get_reviews_due(learner_id, today)
for concept in due_reviews[:max_reviews]:
    session_plan.append({concept, strategy: "recall", is_review: true})

# 2. New concepts from learning path (remaining 60%)
next_concepts = learning_path.remaining[:max_new]
for concept in next_concepts:
    session_plan.append({concept, strategy: select_strategy(...), is_review: false})
```

### 6.3 Duty: `pedagogy.review.schedule`

A scheduled duty that identifies learners with overdue
reviews and nudges them (for human learners) or
automatically conducts reviews (for agent learners):

```yaml
duty:
  id: duty.pedagogy.review
  interval_hours: 24
  skill: pedagogy.review.scan
  context:
    action: "identify_overdue_reviews"
    nudge_humans: true
    auto_review_agents: true
```

---

## 7. Teaching Agents

The same framework teaches both human learners and agent
learners. The differences are in delivery and assessment,
not in the underlying model.

### 7.1 Differences between human and agent learners

| Dimension | Human learner | Agent learner |
|-----------|--------------|---------------|
| **Assessment** | Conversational questions, scenario-based problems | Golden fixture evaluation, skill certification tests |
| **Instruction delivery** | Natural language explanation, analogies, examples | Prompt patches, few-shot examples, schema updates |
| **Strategy selection** | Varies widely by individual | Direct instruction + practice is usually most efficient |
| **Spaced repetition** | Critical — human memory decays | Less critical — agent knowledge is persistent, but model updates can cause regression |
| **Misconception correction** | Requires careful, face-saving approach | Direct prompt correction |
| **Mastery verification** | Examiner asks questions, evaluates answers | Run skill against fixture suite, measure correctness |
| **Progress motivation** | Encouragement, visible progress, intrinsic interest | Not applicable — agents don't need motivation |

### 7.2 Agent teaching as coaching flywheel extension

For agent learners, the pedagogy framework extends Grove's
coaching flywheel:

```
Coaching flywheel:
  Capture traces → Screen anti-patterns → Practice → Certify → Patch

Pedagogy extension:
  Diagnose gaps → Map to concept prerequisites → Teach (via prompt patches)
      → Examine (via fixtures) → Update mastery → Identify next skill
```

When a Grove worker fails certification for a skill, the
pedagogy system can diagnose *why*: is it a missing
prerequisite skill? A misconception about the tool schema?
A gap in domain knowledge? The Diagnostician maps the failure
to the concept graph and the Pathfinder creates a learning
path — which for an agent means a sequence of prompt patches
and practice sessions against fixtures.

### 7.3 Teaching new workers

When a new worker joins the system (e.g., a new Weft community
spins up and needs civic analysis workers), the pedagogy
system provides onboarding:

1. **Diagnose** — run the worker against the domain's fixture
   suite to establish baseline
2. **Path** — identify which skills need prompt patches based
   on failures
3. **Teach** — apply prompt patches for each skill gap
4. **Examine** — re-run fixtures, verify improvement
5. **Certify** — once thresholds are met, promote through
   trust environments

This is the same flow as coaching, but structured as a
pedagogical progression rather than ad-hoc patching.

---

## 8. Teaching Contested and Frontier Knowledge

This is where knowledge acquisition, CI/CD, and pedagogy
converge. The knowledge base contains claims at various
confidence levels. The snapshot bakes confidence into chunks.
The pedagogy system must teach each level honestly.

### 8.1 Teaching by confidence level

| KB confidence | Teaching approach | Framing language |
|--------------|------------------|-----------------|
| **Verified** | Teach as established fact | "According to [source], ..." |
| **Corroborated** | Teach with high confidence, note source diversity | "Multiple independent sources confirm ..." |
| **Reported** | Teach with appropriate hedging | "Based on available evidence, ... (one credible source)" |
| **Contested** | Present both positions with evidence | "There is disagreement on this. Position A holds ... based on [evidence]. Position B holds ... based on [evidence]." |
| **Unverified** | Acknowledge existence, note uncertainty | "This has been reported but not independently verified." |

### 8.2 Assessing frontier knowledge understanding

For frontier concepts, the Examiner uses the `evaluate`
assessment type instead of `recall`:

```json
{
  "question_type": "evaluate",
  "question": "Two analyses reach different conclusions about the impact of the proposed rezoning on property values. Analysis A (from the county assessor) predicts a 3-5% increase. Analysis B (from the neighborhood association) predicts a 2-4% decrease. What factors might explain the disagreement? What additional evidence would help resolve it?",
  "scoring_rubric": {
    "identifies_methodological_differences": 0.25,
    "identifies_source_perspectives": 0.25,
    "proposes_relevant_additional_evidence": 0.25,
    "avoids_premature_conclusion": 0.25
  }
}
```

Mastery of frontier knowledge is not "knows the right answer"
(there may not be one). It is "can articulate the positions,
evaluate the evidence, and identify what would resolve the
disagreement."

### 8.3 Scientific frontier pedagogy

For scientific domains, frontier teaching follows additional
rules:

1. **Distinguish consensus from frontier.** The concept map
   explicitly marks which concepts are established scientific
   consensus and which are active research questions.

2. **Teach the evidence hierarchy for science.** Peer-reviewed
   replicated findings > single peer-reviewed study > preprint >
   conference presentation > expert opinion. Learners should
   know where a claim sits in this hierarchy.

3. **Teach methodology, not just conclusions.** "This study
   found X using method Y on population Z" is more honest than
   "X is true." When methodology is contested, teach the
   methodological debate.

4. **Track retractions.** When the knowledge snapshot includes
   a retracted claim (marked as superseded), the pedagogy
   system teaches what changed and why — this is itself a
   valuable lesson in how science self-corrects.

---

## 9. Rubrics for Teaching Quality

Pedagogy workers are evaluated through the Grove coaching
flywheel. These rubrics define what "good teaching" looks
like, measured through learner outcomes.

### 9.1 Worker-level rubrics

| Dimension | Metric | Threshold | How measured |
|-----------|--------|-----------|-------------|
| **Diagnostic accuracy** | Assessment correctly predicts performance on untested concepts | ≥ 0.80 correlation | Compare diagnostic predictions to subsequent assessment results |
| **Explanation effectiveness** | Learner demonstrates understanding after instruction | ≥ 0.70 post-instruction assessment score | Examiner follow-up immediately after Tutor session |
| **Adaptive response** | Strategy changes when learner isn't progressing | Strategy switch within 2 failed attempts | Session history analysis |
| **Epistemic honesty** | Instruction preserves KB confidence levels | 100% — no contested claims taught as verified | Automated check: compare taught framing to chunk confidence |
| **Efficiency** | Concepts mastered per session hour | Domain-dependent baseline | Mastery changes / session duration |
| **Retention** | Performance on spaced repetition reviews | ≥ 0.75 average review score after 30 days | Review assessment results |
| **Misconception detection** | System identifies and corrects wrong mental models | ≥ 0.60 of misconceptions caught (hard to measure precisely) | Compare Examiner-detected errors to known misconception patterns |

### 9.2 System-level rubrics

| Dimension | Metric | How measured |
|-----------|--------|-------------|
| **Coverage** | What percentage of concepts in the domain have been successfully taught to at least one learner? | Mastery table analysis |
| **Equity** | Is teaching quality consistent across learner types and baselines? | Compare outcomes by learner cohort |
| **Knowledge currency** | Are learners being taught from the current snapshot, not stale knowledge? | Check snapshot version used in sessions vs. production version |
| **Path completion** | What percentage of learning paths reach completion? | Learning path status analysis |

---

## 10. Anti-patterns in Teaching

Named anti-patterns, following the coaching catalog convention.
Each has a signature (how the coaching flywheel detects it) and
a remediation (what prompt patch fixes it).

**1. Info dumping** (`info_dumping`)
Long unbroken explanations with no comprehension checks.
The Tutor explains for 500+ tokens without asking a question
or checking understanding.
*Signature:* Tutor output > 400 tokens between Examiner
interactions.
*Remediation:* Prompt patch: "After every 2-3 sentences of
explanation, check understanding with a brief question."

**2. False simplification** (`false_simplification`)
Removing nuance that changes the meaning of a claim. Teaching
a "contested" claim without mentioning the disagreement.
Teaching a "reported" claim as certain.
*Signature:* Confidence level in instruction does not match
confidence level in source chunk.
*Remediation:* Prompt patch: "Always include the confidence
level from the knowledge base. If a claim is contested,
present both positions."

**3. Premature abstraction** (`premature_abstraction`)
Teaching general principles before the learner has enough
examples to ground them. Jumping to "how municipal bonds
work in general" before showing a single concrete example.
*Signature:* Abstract concept taught to novice learner
without preceding concrete examples in the session.
*Remediation:* Prompt patch: "For novice learners, always
start with a concrete example before introducing the
general principle."

**4. Assumed prerequisite** (`assumed_prerequisite`)
Teaching concept X without verifying that prerequisite
concept Y was understood. Using terms or frameworks the
learner hasn't been taught.
*Signature:* Concept taught when prerequisite concepts in
the concept map have mastery < "proficient."
*Remediation:* Prompt patch: "Check the learner's mastery
of prerequisites before advancing. If prerequisites are
missing, teach them first."

**5. Echo chamber** (`echo_chamber`)
Only presenting supporting evidence for a contested claim.
The Tutor picks a side instead of presenting the
disagreement.
*Signature:* For contested concepts, instruction references
only supporting evidence, not contradicting evidence.
*Remediation:* Prompt patch: "For contested claims, always
present both the supporting and contradicting evidence with
their source tiers."

**6. Confidence inflation** (`confidence_inflation`)
Teaching "reported" or "contested" claims as "verified."
Using definitive language ("it is the case that...") for
uncertain knowledge.
*Signature:* Definitive framing language used for claims
with confidence < "corroborated."
*Remediation:* Same as false_simplification — carry
confidence through to language.

**7. Assessment-instruction mismatch** (`assessment_mismatch`)
Testing on material not covered in instruction, or covering
material never tested. The learner is asked about things they
weren't taught, or taught things that are never assessed.
*Signature:* Examiner concept set does not overlap with
Tutor concept set for the session.
*Remediation:* Prompt patch: "Assess only concepts covered
in the current or recent sessions."

**8. Plateau blindness** (`plateau_blindness`)
Continuing the same strategy when learner progress has
stalled. Three sessions with no mastery advancement, but
no strategy change.
*Signature:* ≥ 3 sessions on the same concept with no
mastery level change and no strategy change.
*Remediation:* Coach worker monitors trajectory and triggers
`pedagogy.coach.intervene` to force strategy change.

**9. Overconfidence calibration** (`overconfidence_calibration`)
Advancing a learner past a concept based on a single
good assessment when the learner's history on that concept
is inconsistent.
*Signature:* Mastery promoted to "proficient" when fewer
than 3 assessments on that concept, or when assessment
scores have high variance.
*Remediation:* Require minimum assessment count and
consistency before mastery promotion.

---

## 11. How This Maps to Grove

| Pedagogy concept | Grove implementation |
|-----------------|---------------------|
| Learner model | SQLite tables in community/personal KB |
| Concept maps | Extension of snapshot claim graph with prerequisite edges |
| Teaching strategies | Skill variants on the Tutor worker (`pedagogy.tutor.*`) |
| Diagnostic assessment | Diagnostician worker + `ritual.pedagogy.assess` |
| Learning paths | Pathfinder worker, stored in `learning_paths` table |
| Spaced repetition | Duty with interval trigger (`duty.pedagogy.review`) |
| Teaching quality metrics | Coaching flywheel traces on pedagogy workers |
| Anti-pattern detection | Coaching catalog extensions (9 new patterns) |
| Agent teaching | Coaching flywheel + prompt patching (existing infra) |
| Strategy selection | Deterministic rules in Tutor worker (not LLM judgment) |
| Frontier teaching | Direct integration with snapshot confidence levels |
| Human learner progress | Same mastery progression as worker trust environments |

### The parallel

| Grove trust (workers) | Pedagogy mastery (learners) |
|----------------------|---------------------------|
| Sandbox → Shadow → Canary → Production | Novice → Developing → Proficient → Expert |
| Promotion requires demonstrated reliability | Promotion requires demonstrated understanding |
| Demotion is instant on failure | Mastery can degrade on failed review |
| Certification is per-worker, per-skill, per-model | Mastery is per-learner, per-concept, per-domain |
| Coaching traces evaluate worker quality | Session traces evaluate teaching quality |
| Golden fixtures test correctness | Assessment questions test understanding |

---

## 12. Mirabebe Integration: Developmental Stages

The Mirabebe spec defines five developmental stages for
children's digital experience. The pedagogy framework maps
onto these stages:

| Mirabebe stage | Pedagogy role |
|---------------|--------------|
| **Nursery (0-12mo)** | No pedagogy — device is communication tool only |
| **Toddler (12-24mo)** | No active pedagogy — incidental learning through family interaction |
| **Family messaging (2-4yr)** | Pre-literacy concepts through family group participation |
| **First personal device (5-7yr)** | Teacher-administered concept maps, curriculum-aligned paths, the "class group IS the learning environment" principle |
| **Growing independence (8+yr)** | Expanding concept domains: classroom → school → community (Weft) → wider civic infrastructure (Cubby) |

At Stage 4, the teacher becomes the administrator of the
digital learning space. The pedagogy framework provides the
infrastructure:

- Teacher curates concept maps for their class domain
- System provides per-student diagnostics and learning paths
- Teacher sees dashboard of student mastery, not pretense
  of synchronized progress
- AI Tutor handles personalized instruction; teacher handles
  judgment, motivation, and group dynamics

---

## 13. Open Questions

**How much should the system adapt vs. how much should the
learner stretch?** Always teaching in the learner's preferred
strategy risks never developing their ability to learn in
other ways. A student who only receives example-driven
instruction never develops the skill of abstract reasoning.
The answer is probably to lead with effective strategies but
periodically challenge with less comfortable ones.

**How do you assess "understanding" vs. "memorization"?**
The recall assessment type tests retrieval. The apply type
tests transfer. But transfer is hard to measure automatically
— it requires novel scenarios, and novel scenario generation
is itself an LLM judgment that can be wrong. The Examiner
worker needs its own quality fixtures for assessment quality.

**How do you handle motivated misinformation from learners?**
In the community challenge process (knowledge-acquisition.md
Section 7.4), a learner can contest a claim. But what if a
learner deliberately gives wrong assessment answers to game
the mastery system? For agent learners this isn't a concern
(no motivation to game). For human learners, the answer is
probably that gaming your own mastery only hurts yourself —
the system doesn't gate real-world privileges on mastery
levels.

**When does personalization become a filter bubble?** A
learning path that only teaches what the learner is interested
in may produce citizens who understand their pet issue deeply
but have no awareness of how it connects to everything else.
The concept map's prerequisite edges help — they force breadth
as a condition of depth — but the balance between learner
choice and curricular structure is a genuine tension.

**Can pedagogy workers teach pedagogy?** If a community needs
human tutors (teachers, mentors, facilitators), can the system
teach them how to teach? This is meta-pedagogy — the concept
map would include teaching strategies as concepts, with
assessment based on the outcomes of the humans they teach.
Ambitious but worth exploring.

---

*The best teacher is not the one who knows the most. It is the
one who knows what the student doesn't know, meets them there,
and walks with them toward understanding — honestly, patiently,
and with the evidence visible. That is what this framework
encodes: not a curriculum, but the machinery to create the
right curriculum for each learner, from whatever baseline they
bring, through whatever knowledge the system has earned the
right to teach.*
