# Loom: Prior Art and External Systems

How existing credibility, fact-checking, and knowledge systems
inform Loom's architecture. Each section documents what the
system does, how it relates to Loom, and what design insights
it yields.

---

## 1. Ground News (News Aggregation + Bias Rating)

**What it is:** Canadian news aggregator (2020) that surfaces
how the same story is covered differently across outlets.

**Methodology:**
- Bias ratings averaged from three third-party monitors:
  AllSides, Ad Fontes Media, Media Bias/Fact Check
- 7-point bias scale: Far Left → Center → Far Right
- Factuality scores from Ad Fontes + MBFC: 5-tier
  (Very High → Very Low)
- Blindspot reports: stories covered by one political side
  but not the other
- Ratings are per-publication, not per-article

**Design insights for Loom:**
- **Meta-rating pattern**: Ground News doesn't assess
  credibility itself — it aggregates specialist assessments.
  Loom's Classifier worker could incorporate third-party
  credibility ratings (MBFC, Ad Fontes, AllSides) as inputs
  rather than building all rubric evaluation from scratch.
- **Selection bias as signal**: Ground News's blindspot
  reports surface what *isn't* covered. Loom could track
  coverage gaps — topics where only T6/T7 sources exist
  and T1-T3 sources are absent.
- **Tier mapping**: Ground News itself would be T4 for Loom
  (expert analysis with disclosed methodology). Its bias
  ratings are useful metadata for Loom's source evaluation
  rubrics (independence, publisher_credibility dimensions).

**Sources:**
- https://ground.news/rating-system
- https://mediabiasfactcheck.com/ground-news/

---

## 2. Associated Press (Wire Service Editorial Standards)

**What it is:** Global wire service with one of the most
rigorous published editorial standards in journalism.

**Standards:**
- **Sourcing**: only authoritative sources. Anonymous sources
  only when they provide vital *information* (not opinion),
  when there's no other way, and when the source is
  knowledgeable and reliable.
- **Accuracy**: no altering quotations, even for grammar.
  Same care for context as for accuracy.
- **Corrections**: "fully, quickly and ungrudgingly."
- **Independence**: no paying newsmakers. No political
  activity by staff. Avoid conflicts of interest.
- **Verification**: internet content vetted to AP standards,
  attributed to original source.

**Design insights for Loom:**
- AP is the archetype of a T3 source: authoritative reporting
  with editorial process, named accountability, visible
  corrections policy.
- AP's sourcing rules map directly to Loom's
  `claim_verifiability` rubric signals: cites primary
  sources (+2), named author (+1), corrections policy (+1).
- AP's "corrections — fully, quickly, ungrudgingly" is the
  same spirit as Loom's "corrections are a celebrated
  feature" (adversarial resilience §8.3).
- The AP pattern validates Loom's approach: show provenance,
  attribute everything, correct publicly.

**Sources:**
- https://members.newsleaders.org/resources-ethics-ap
- https://accountablejournalism.org/ethics-codes/news-values-and-principles

---

## 3. arXiv (Preprint Server)

**What it is:** Preprint distribution platform for scientific
papers. Not peer-reviewed.

**Moderation (not review):**
- "The arXiv moderation process is not a peer-review process."
- Volunteer moderators (terminal degree holders) check:
  originality, scholarly standards, professional tone,
  proper formatting, and whether it's actually research.
- ~1% rejection rate. Bar is "plausibly science by a
  plausible scientist," not "this is correct."
- No credibility assessment. No editorial stance on content.
- Recent CS restriction: review/position papers must have
  completed peer review elsewhere first (LLM-generated
  paper flooding response).
- Accepts: research articles, theses, proceedings, lecture
  notes, comments. Rejects: abstracts-only, course projects,
  proposals, slides, undergraduate research.
- AI disclosure required for text-to-text generative AI
  usage in methodology sections.

**Design insights for Loom:**
- arXiv exposes a gap in the evidence hierarchy: **tier
  should attach to the claim's evidence chain, not the
  platform.** The same arXiv paper can span T4 to T6
  depending on its methodology, data, and replication status.
- K6 ("tier is per claim not per outlet") already implies
  this, but science makes it acute. A preprint citing
  primary datasets (T2), with methodology (T4), independently
  replicated (corroborated) is very different from a preprint
  with no data and no replication.
- **Peer review is a corroboration event, not a tier change.**
  A preprint that passes peer review hasn't changed content —
  it's gained corroboration from domain experts. In Loom's
  model, peer review should promote a claim from `reported`
  to `corroborated`, not change the source's tier.
- arXiv's CS restriction is a real-world example of the
  flooding attack vector from Loom's adversarial resilience
  spec — and arXiv's response (require prior peer review)
  mirrors Loom's quarantine pattern.

**Sources:**
- https://info.arxiv.org/help/moderation/index.html
- https://info.arxiv.org/help/policies/content-types.html
- https://blog.arxiv.org/2025/10/31/attention-authors-updated-practice-for-review-articles-and-position-papers-in-arxiv-cs-category/

---

## 4. Wikipedia (Collaborative Encyclopedia)

**What it is:** Collaborative encyclopedia with 60M+ articles
built by volunteer editors under three core content policies.

**Core policies:**
- **Verifiability**: every claim must be attributable to a
  reliable published source.
- **No original research**: report what sources say, don't
  synthesize new conclusions.
- **Neutral point of view**: represent all significant views
  fairly, without editorial position.

**AI/LLM policy (as of 2025-2026):**
- **G15 speedy deletion**: LLM-generated pages without human
  review can be immediately deleted (Aug 2025).
- **LLM-assisted editing allowed** if: disclosed in edit
  summary (name + version), all text verified by human,
  complies with all standard policies.
- **LLM-generated articles banned**: can't submit raw LLM
  output.
- **Semi-automated editing** (human in loop) does not require
  bot approval.
- **WikiProject AI Cleanup**: active community project
  identifying and removing AI-generated content.

**Bot policy:**
- Full automation requires BAG (Bot Approvals Group) approval.
- Approved bots restricted to mechanical tasks (link fixing,
  category updates, vandalism reversion) — not content.
- Semi-automated tools with human review: no approval needed.

**Design insights for Loom:**

*Loom should NOT be a mass Wikipedia editor because:*
1. Policy prohibits AI-generated content without human review.
2. It contradicts Loom's own `trust_by_assertion` anti-pattern.
3. Wikipedia's epistemology ("verifiability, not truth")
   differs from Loom's (evidence-weighted confidence).

*The right model: Loom as a tool for human editors:*
- **Find uncited claims**: surface Wikipedia claims where Loom
  has T1/T2 evidence but Wikipedia has weak or no citations.
- **Draft sourced edits**: Loom surfaces provenance chains;
  human editors verify and submit under their own accounts.
- **Validate submissions**: editors query Loom to check
  whether a new edit has supporting evidence.
- **Detect contradictions**: flag where Wikipedia says X but
  T1/T2 sources say Y.
- **Monitor freshness**: surface claims citing outdated data
  when newer primary sources exist.

*Wikipedia as a Loom source:*
- Wikipedia articles themselves → T6 (user-generated, no
  editorial board, anyone can edit).
- Wikipedia's *cited sources* → evaluated at their own tier.
  Follow the citations to primary sources.
- Wikipedia as a **discovery engine**: its citations point to
  primary sources Loom should harvest directly. This is
  `authority_laundering` in reverse — follow the citations
  instead of borrowing the authority.

*Proposed worker:*
```
workers/wikipedia/worker.py
  - wp.find_uncited: find WP claims Loom can source
  - wp.check_claim: validate a WP claim against evidence graph
  - wp.suggest_edit: draft a sourced edit for human review
  - wp.harvest_citations: extract cited sources from WP articles
    and feed them into Loom's acquisition pipeline at proper tier
  - wp.monitor_freshness: find stale WP claims Loom can update
```

**Sources:**
- https://en.wikipedia.org/wiki/Wikipedia:Verifiability
- https://en.wikipedia.org/wiki/Wikipedia:Large_language_models
- https://en.wikipedia.org/wiki/Wikipedia:Bot_policy
- https://en.wikipedia.org/wiki/Wikipedia:WikiProject_AI_Cleanup
- https://wikimediafoundation.org/news/2025/10/02/the-3-building-blocks-of-trustworthy-information-lessons-from-wikipedia/

---

## Summary: Design Principles Confirmed and Discovered

| Insight | Source | Impact on Loom |
|---------|--------|----------------|
| Meta-rating > self-rating | Ground News | Classifier can incorporate third-party ratings |
| Tier is per-claim, not per-platform | arXiv | Science sources require claim-level evaluation |
| Peer review = corroboration event | arXiv | Maps to confidence promotion, not tier change |
| Corrections as feature, not failure | AP | Already in adversarial resilience spec — validated |
| Human mediation for external systems | Wikipedia | Loom suggests, humans act — never direct edits |
| Citation following > platform trust | Wikipedia | Harvest citations, evaluate originals at their own tier |
| Flooding is a real attack | arXiv CS | Quarantine pattern validated by real-world precedent |
| Selection bias as signal | Ground News | Track coverage gaps, not just content quality |

---

## Deep Research (Separate Documents)

Detailed research on systems beyond journalism that inform
Loom's architecture. Each document includes methodology,
mapping to Loom, and concrete design recommendations.

- **`prior-art-fact-checking.md`** — IFCN Code of Principles,
  ClaimReview schema, Snopes, PolitiFact, Full Fact AI
- **`prior-art-intelligence.md`** — Admiralty Code / NATO
  source grading (dual-axis), ICD 203 analytic standards,
  structured analytic techniques (ACH), Sherman Kent
  estimative language
- **`prior-art-legal-provenance.md`** — Federal Rules of
  Evidence (hearsay hierarchy, chain of custody, Daubert),
  Wikidata sourcing model, C2PA content provenance, FAIR
  data principles, Schema.org
- **`prior-art-scientific.md`** — Cochrane systematic reviews,
  GRADE framework, IPCC confidence language, evidence-based
  medicine hierarchy, PRISMA
- **`prior-art-epistemic.md`** — Bayesian epistemology, Dung
  argumentation frameworks, truth maintenance systems,
  Toulmin model, epistemic logic
- **`architectural-recommendations.md`** — Unified synthesis:
  10 concrete architectural upgrades with phased implementation
