# Loom: Adversarial Resilience

**Author:** Hugh Lynch, with Claude
**Date:** 2026-03-06
**Part of:** Loom — the ABWP Knowledge System
**Depends on:** Knowledge Acquisition (`spec/knowledge-acquisition.md`), Knowledge CI/CD (`spec/knowledge-ci.md`), Pedagogy (`spec/pedagogy.md`), Grove Coaching Flywheel (GROVE-RECONSTRUCTION-GUIDE.md Section 13)
**Applies to:** All Loom consumers — Cubby, Weft, Sil, Shep, Yohumps, Geeni, and any system that presents Loom knowledge to users

---

## Why "Loom"

The ABWP ecosystem uses textile metaphors throughout: **Weft**
(the horizontal threads — community data woven across civic
life), **Warp** (the vertical threads — economic foundation),
**Weave** (the social fabric those threads produce).

**Loom** is the machine that holds warp and weft in tension and
produces the fabric. That is precisely what the knowledge system
does. It holds evidence in structured tension — contradictions
as features, confidence levels computed from competing sources,
provenance chains under scrutiny — and produces something
coherent and trustworthy from it.

Loom is three specs:

- **Knowledge Acquisition** (`knowledge-acquisition.md`) — how
  Loom acquires evidence from unreliable digital sources
- **Knowledge CI/CD** (`knowledge-ci.md`) — how Loom compiles,
  tests, and deploys knowledge snapshots
- **Pedagogy** (`pedagogy.md`) — how Loom teaches what it knows
  to humans and agents

This document is the fourth: how Loom defends itself against
actors who would corrupt, discredit, overwhelm, capture, or
destroy it.

---

## 1. Why This Document Exists

A widely respected, uncontrollable source of evidence-based
knowledge is a threat to powerful interests. Anyone who profits
from confusion, manufactures false consensus, promotes
epistemological nihilism ("nothing is true, everything is
biased"), or depends on controlling the narrative has a rational
incentive to undermine Loom.

The architecture already contains defensive primitives — the
evidence hierarchy, provenance chains, content hashing,
deterministic confidence computation, the community challenge
process. This document codifies the threat model, identifies
attack vectors, and specifies how Loom's existing architecture
defends against each. Where the existing architecture has gaps,
it specifies new defenses.

The goal is not to make Loom invulnerable. It is to make
attacking Loom more expensive than the information it provides
is worth, and to ensure that successful attacks are detectable,
reversible, and public.

---

## 2. Threat Model

### 2.1 Adversary categories

Six categories of adversary, each with different capabilities
and motivations:

**Those who profit from confusion.** If the public can easily
see what their city council actually voted for, what the budget
actually says, what the evidence actually shows, the
fog-of-complexity strategy stops working. These adversaries
want Loom to be unreliable enough to dismiss.

**Those who profit from false consensus.** If the system
surfaces genuine disagreement instead of letting one side
dominate the narrative, manufactured consensus becomes visible.
These adversaries want Loom to validate their position or be
discredited.

**Those who profit from epistemological nihilism.** "Nothing is
true, everything is biased" is the most effective attack on
evidence-based systems. If you convince people that *all*
knowledge systems are equally biased, they stop trusting any of
them, and power flows to whoever shouts loudest. These
adversaries want Loom to be seen as "just another biased
source."

**Those who see an uncontrolled information source as a
competitive threat.** This includes platforms, media
organizations, and political operations whose influence depends
on controlling the narrative. These adversaries want Loom
marginalized or co-opted.

**Those with specific claims to protect.** Individuals or
organizations whose interests are damaged by specific true
claims in the evidence graph. These adversaries want specific
claims removed or contested, not the whole system destroyed.

**Those who attack systems for sport or ideology.** Bad-faith
actors who flood, troll, or grief any open system. These
adversaries want to waste curator time and degrade system
quality for its own sake.

### 2.2 Attack vectors

| Attack | Goal | Mechanism | Adversary type |
|--------|------|-----------|----------------|
| **Poisoning** | Corrupt the evidence graph | Submit false sources, flood with low-quality claims, forge provenance | Confusion, specific claims |
| **Delegitimization** | Destroy trust in the system | "It's biased," "It's an AI," "Who elected this system?" | Nihilism, competitive threat |
| **Legal/regulatory** | Force the system offline or under control | Copyright claims, defamation threats, regulatory capture | Specific claims, competitive threat |
| **Flooding** | Overwhelm the curation process | Mass bad-faith challenges, source submission overload, coordinated noise | Sport/ideology, confusion |
| **Co-option** | Capture the governance structure | Get partisans into curator roles, influence concept map design, game reputation | False consensus, competitive threat |
| **Targeted discrediting** | Find any error and amplify it | Cherry-pick wrong claims, demonstrate "the system can't be trusted" | Any adversary type |

---

## 3. Defense: The Evidence Graph as Armor

**Defends against:** Poisoning

The evidence graph is its own primary defense. Loom does not
ask anyone to trust it. It shows its work. Every claim links
to evidence, every evidence link traces to a source, every
source has a tier and a reliability score. An attacker who says
"Loom is wrong about X" faces a system that responds not with
"trust us" but with "here is the T1 government filing, here is
the content hash proving it hasn't been altered, here is the
date it was retrieved."

The adversarial design principle: **make the system's response
to "you're wrong" be "here's the evidence" — automatically,
structurally, without human intervention.**

### 3.1 The evidence hierarchy is a firewall

Poisoning works by injecting false claims. Loom's evidence
hierarchy (T1–T7, defined in `knowledge-acquisition.md` §2)
makes this structurally difficult:

- **T1/T2 sources are hard to forge.** Government filings come
  from .gov domains. Census data comes from census.gov. Court
  records come from PACER or state court systems. An attacker
  cannot submit a fake budget document and have it treated as
  T1 evidence.
- **T6/T7 sources carry minimal weight.** These are where
  poisoning is easy — anyone can write a blog post. But T6/T7
  sources can never override higher-tier evidence. They can
  only corroborate or contextualize.
- **The cardinal rule holds under attack:** no amount of T6
  sources can override a single T1 source. An attacker would
  need to compromise the primary source itself, not just flood
  the system with contradicting claims.

### 3.2 Content hashing detects tampering

Every harvested source is SHA-256 hashed at retrieval
(`content_hash` in the sources table, `knowledge-acquisition.md`
§4.2). If the source content changes on re-harvest, the system
detects the difference and re-evaluates all claims derived from
that source. An attacker cannot retroactively alter what the
system already captured.

### 3.3 Source provenance verification

For T1/T2 sources, the Harvester verifies that the URL resolves
to the institution's official domain. Budget documents from
`budget.cityname.gov` are T1. The same document rehosted on
`totally-real-budget.com` is not. The system follows links to
primary sources but does not accept mirrors as authoritative.

Rules:
- T1 sources must come from recognized government domains or
  verified institutional endpoints
- T2 sources must come from the institution's official data
  portal or API
- Sources that *claim* to mirror T1/T2 content are treated at
  the tier of the mirror, not the original
- The Classifier worker (`classify.source_tier`) enforces this
  during acquisition

### 3.4 Rate limiting on source introduction

New sources below a reliability threshold can only enter the
system at a controlled rate. A flood of new blog posts all
making the same claim in one day triggers the
`consensus_manufacturing` anti-pattern detector
(`knowledge-acquisition.md` §8).

Specific controls:
- New sources from previously unseen origins enter at
  reliability 0.3 (below the default 0.5)
- Sources with reliability below 0.4 are rate-limited to 10
  new claims per day per origin
- Origins that produce more than 50 claims in 24 hours that
  all share the same topic are flagged for review
- The `coordinated_inauthenticity` detection
  (`knowledge-acquisition.md` §5.2) runs on every batch of
  claims sharing a novel assertion

### 3.5 Quarantine for novel claims

Claims from new, unestablished sources enter at "unverified"
regardless of content. They can only be promoted through
corroboration with independent, higher-tier sources.

A novel claim — one with no existing entry in the evidence
graph — from a source with reliability below 0.5 enters a
quarantine queue. Quarantined claims are:
- Visible in the evidence graph (transparency, not suppression)
- Marked as "unverified — pending corroboration"
- Not included in knowledge snapshots until promoted
- Automatically promoted if corroborated by a T3+ source within
  the review window
- Automatically expired if no corroboration arrives within 30
  days

---

## 4. Defense: Radical Transparency

**Defends against:** Delegitimization

The "it's biased" attack is the most dangerous because it is
irrefutable in the abstract — every system has perspectives
baked in. The defense is not to claim neutrality (which is
dishonest) but to make every choice visible and contestable.

### 4.1 The concept map is public

Anyone can see how knowledge is organized, what prerequisites
are assumed, what is marked as frontier. If the organization
reflects a bias, it is visible and challengeable. The concept
map (`pedagogy.md` §3) is a published artifact, not a hidden
implementation detail.

### 4.2 The evidence hierarchy is explicit and published

"We weight government filings above blog posts" is a stated
policy, not a hidden algorithm. The full hierarchy
(`knowledge-acquisition.md` §2) is published. If someone
disagrees with the hierarchy, the disagreement is about an
explicit rule, not a black box.

This transforms the attack surface from "the system is biased"
(vague, irrefutable) to "tier T4 should be ranked above T3 for
academic sources" (specific, debatable on evidence).

### 4.3 Confidence computation is deterministic

The confidence computation rules (`knowledge-acquisition.md`
§4.3) are not LLM judgments. They are published, deterministic
algorithms. Anyone can verify that the same evidence produces
the same confidence level. An accusation of bias must contend
with a verifiable computation, not an opaque model.

### 4.4 The challenge process is open

The community challenge process (`knowledge-acquisition.md`
§7.4) allows anyone to contest a claim. The resolution is
public. The reasoning is recorded. This is the pull-request
model — disagreement is a feature of the system, not an attack
on it.

### 4.5 Acknowledge what the system cannot do

Loom does not determine truth. It evaluates evidence. When the
evidence is ambiguous, it says so. When important sources are
behind paywalls or offline, it notes the gap
(`survivorship_sourcing` anti-pattern, `knowledge-acquisition.md`
§8). This honesty is the best defense against accusations of
overreach.

**The meta-principle:** transparency is not a vulnerability.
Every mechanism an attacker could point to and say "see, this
is biased" is already documented, explained, and contestable.
The system that shows its work is harder to delegitimize than
the system that claims objectivity.

---

## 5. Defense: Legal Posture

**Defends against:** Legal/regulatory attack

### 5.1 Report, don't editorialize

Loom reports what sources say, with attribution. It does not
offer editorial opinions. Claims are linked to their sources.
If a source is wrong, the system points to the source, not its
own judgment. The distinction between "the budget document says
X" (a fact about a document) and "X is true" (an assertion of
truth) is legally significant. Loom does the former.

### 5.2 Represent both sides of contested claims

For contested claims, the system presents both positions with
their evidence. This is the strongest libel defense available:
a system that accurately reports what multiple sources say,
including contradictory sources, is not making a defamatory
claim — it is reporting a documented disagreement.

### 5.3 Fair use posture

The system stores excerpts with attribution, not full
reproductions. Fair use analysis favors:
- **Transformative use** — claims are extracted, structured,
  cross-referenced, and confidence-scored; the output is
  fundamentally different from the input
- **Attribution** — every excerpt links to its source
- **Limited portion** — excerpts, not full documents
- **Public interest** — civic knowledge serves democratic
  participation
- **Non-commercial** — community infrastructure, not a content
  business

### 5.4 Respond to takedown requests transparently

If a legal challenge demands removal of specific claims:
1. Evaluate whether the claim is factual reporting with
   attribution (protected) or assertion without evidence
   (defensible but riskier)
2. If the claim is sourced to public records (T1/T2), note
   that the information is a matter of public record
3. If the claim must be removed, document the removal publicly
   — "Claim C-3201 was removed on [date] pursuant to [legal
   basis]. The underlying source was [source]." Censorship
   should be visible, not silent
4. Never remove the *source record* — only the claim. The
   provenance chain remains for audit

---

## 6. Defense: Structural Rate Limits

**Defends against:** Flooding, challenge abuse

### 6.1 Challenge reputation

Challengers build reputation through successful, evidence-based
challenges. New challengers have rate limits. Challengers whose
challenges are consistently rejected (no supporting evidence)
face increasing friction.

| Challenger tier | Max open challenges | Required evidence |
|----------------|--------------------|--------------------|
| New (0 successful) | 3 per week | Must cite specific source |
| Established (3+ successful) | 10 per week | Must cite specific source |
| Trusted (10+ successful, <20% rejection rate) | Unlimited | Must cite specific source |

Reputation degrades on bad-faith patterns:
- 5+ rejected challenges with no cited evidence: 30-day
  cooldown
- Challenges targeting the same claim repeatedly after
  resolution: escalation to curator review of the challenger,
  not the claim

### 6.2 Challenge cost is effort, not money

A challenge must include:
1. A specific claim ID (not "everything is wrong")
2. A specific counter-source (not "I disagree")
3. A specific argument for why the counter-source should
   override the existing evidence (not "you're biased")

This is the same design as requiring bug reports to include
reproduction steps. It does not prevent anyone from
challenging — it ensures that challenges are actionable.

### 6.3 Triage automation

The Adjudicator worker (`knowledge-acquisition.md` §3.1)
handles the first pass on challenges:

1. Does the counter-source exist and is it retrievable?
2. What tier is the counter-source?
3. Could the counter-source's tier potentially override the
   existing evidence?
4. Is this a duplicate of a recently resolved challenge?

If the counter-source is lower-tier than the existing evidence
and no new information is presented, the challenge is
auto-closed with an explanation: "The cited source is T6; the
existing claim is supported by T1 evidence. Per the evidence
hierarchy, T6 sources cannot override T1 sources. If you have
T1/T2/T3 evidence, please resubmit."

Only challenges with potentially overriding evidence reach
human curators.

---

## 7. Defense: Governance Separation

**Defends against:** Co-option

### 7.1 Curators don't control the evidence hierarchy

The evidence hierarchy (T1–T7) is a system constant, not a
policy that curators set. A captured curator can resolve
individual contradictions but cannot change the rule that T1
sources override T6 sources. The hierarchy is defined in
`knowledge-acquisition.md` §2 and is immutable short of a
spec revision (which is versioned, public, and requires
ecosystem-wide review).

### 7.2 Concept maps are versioned

Changes to how knowledge is organized are tracked, diffable,
and reversible — like code. A partisan restructuring of the
concept map is visible in the changelog. Every concept map
change records:
- Who made it (curator ID)
- When (timestamp)
- What changed (diff of edges and nodes)
- Why (required justification text)

### 7.3 Multi-curator consensus for high-impact changes

Changes that affect many claims require multiple curators, not
a single individual:

| Change type | Required curators | Escalation |
|-------------|------------------|------------|
| Resolve a single contradiction | 1 curator | Standard |
| Reclassify a source's tier | 2 curators | Source affects >10 claims |
| Restructure a concept map branch | 2 curators | Branch has >20 concepts |
| Modify a confidence computation rule | Spec revision | Not a curation decision |
| Override T1 evidence | 2 curators + documented justification | Always |

### 7.4 Curator accountability

Every curation decision is attributed and permanent. Curators
build a public track record. Patterns of biased curation are
detectable the same way the coaching flywheel detects
anti-patterns in workers:

- Curators who consistently resolve contradictions in favor of
  one political position trigger the `partisan_resolution`
  pattern detector
- Curators who override higher-tier evidence without documented
  justification trigger the `authority_override` pattern
  detector
- Curators whose resolutions are frequently reversed by other
  curators trigger review

The coaching flywheel applies to curators exactly as it applies
to workers: observed behavior, pattern detection, coaching
intervention, improvement measurement.

---

## 8. Defense: Own Your Errors

**Defends against:** Targeted discrediting

The system *will* make mistakes. The defense is not to prevent
all errors (impossible) but to make error correction a visible,
celebrated feature.

### 8.1 Public changelog

Every correction is visible. The knowledge snapshot's
`changelog.json` (`knowledge-ci.md` §3) records every claim
change between versions. "In v47, claim C-3201 was reported as
verified. In v48, new evidence from [source] revealed this was
incorrect. The claim has been corrected."

This is the Wikipedia model — errors are part of the public
record, and the correction is part of the public record too.

### 8.2 Error post-mortems

When a significant error is discovered — a claim that was
"verified" turns out to be wrong, a source that was T3 turns
out to have fabricated content — the system publishes a
post-mortem:

1. **What was wrong:** The specific claim and how long it was
   wrong
2. **Why the system didn't catch it:** Which step in the
   acquisition pipeline failed, or what gap in the evidence
   hierarchy permitted the error
3. **What evidence corrected it:** The source and evidence that
   revealed the error
4. **What structural change prevents recurrence:** A specific
   improvement to the pipeline, not just "we'll be more
   careful"

This transforms errors from ammunition ("the system is broken")
into evidence of rigor ("the system catches and fixes its
mistakes transparently").

### 8.3 "We were wrong" is not a bug

It is the system working. A system that is never wrong is
either lying or not doing anything interesting. A system that
acknowledges and corrects errors in public is demonstrating
exactly the epistemic honesty it claims to value.

The presentation principle: corrections are never buried.
They are announced with the same prominence as the original
claim. If a Cubby report cited a claim that was later
corrected, the correction appears in Cubby's feed with a link
to the original report. Users who saw the original see the
correction.

---

## 9. Anti-patterns for Adversarial Defense

Named anti-patterns following Grove's coaching convention.
These are patterns in *Loom's own behavior* that weaken its
defenses — they are things the system must not do, monitored
by the coaching flywheel.

**1. Trust by assertion** (`trust_by_assertion`)
Demanding trust without showing evidence. "This claim is
verified" without a visible provenance chain. Any claim
presented without accessible evidence links has failed the
most basic defense.
*Detection:* Audit snapshot chunks for claims without embedded
evidence references.
*Remediation:* Block snapshot deployment if any chunk contains
a "verified" or "corroborated" claim without at least one
evidence link.

**2. Neutrality theater** (`neutrality_theater`)
Claiming the system is objective or unbiased rather than
transparent. Objectivity is an assertion that invites attack.
Transparency is a practice that resists it.
*Detection:* Review system-generated descriptions and
documentation for claims of neutrality or objectivity.
*Remediation:* Replace claims of neutrality with descriptions
of process: "Loom evaluates evidence using a published
hierarchy" not "Loom provides unbiased information."

**3. Error burial** (`error_burial`)
Quietly fixing errors instead of publishing corrections. Silent
fixes undermine the public changelog and make "you quietly
changed it" a valid attack.
*Detection:* Diff snapshots for claim changes that lack
corresponding changelog entries.
*Remediation:* Block snapshot deployment if claims changed
between versions without changelog entries.

**4. Challenge suppression** (`challenge_suppression`)
Making the challenge process difficult to discourage dissent.
High barriers to challenge protect the system from flooding
but also protect it from legitimate correction.
*Detection:* Monitor challenge submission rates, auto-close
rates, and time-to-resolution. A sudden drop in challenges
may indicate suppression, not satisfaction.
*Remediation:* Publish challenge statistics. If auto-close
rates exceed 80% for 30 days, review the triage criteria for
excessive strictness.

**5. Authority capture** (`authority_capture`)
Allowing individual curators unchecked power over claims. A
single curator who can resolve contradictions, reclassify
sources, and restructure concept maps without review has too
much power.
*Detection:* Monitor curator activity concentration. Flag when
a single curator accounts for >30% of resolutions in a
30-day window.
*Remediation:* Require second-curator review when concentration
thresholds are exceeded. The multi-curator consensus rules
(§7.3) should prevent this, but monitoring catches edge cases.

---

## 10. How This Maps to Grove

Every defense maps to existing Grove primitives. No new
protocol methods or orchestrator changes are required.

| Defense | Grove implementation |
|---------|---------------------|
| Evidence hierarchy as firewall | Classifier worker skill (`classify.source_tier`) with hardened domain verification |
| Content hashing | Harvester worker stores `content_hash` in sources table; Corroborator verifies on re-harvest |
| Source provenance verification | Classifier worker rules for T1/T2 domain validation |
| Rate limiting on source introduction | Duty-based monitoring (`duty.loom.source_rate_check`) |
| Novel claim quarantine | Adjudicator worker routing rule: new source + novel claim → quarantine queue |
| Radical transparency | Snapshot artifacts are public; concept maps in versioned storage |
| Challenge reputation | Challenger table in community KB, scored like worker health |
| Challenge triage | Adjudicator worker skill (`adjudicate.triage_challenge`) |
| Multi-curator consensus | Curator worker with `requires_approval` grant and quorum rules |
| Curator accountability | Coaching flywheel applied to curator decisions, same as worker coaching |
| Public changelog | `changelog.json` in every snapshot artifact (`knowledge-ci.md` §3) |
| Error post-mortems | Ritual: `ritual.loom.post_mortem` triggered on significant claim reversals |
| Anti-pattern detection | Coaching catalog extensions, same pattern as `knowledge-acquisition.md` §8 |

### New rituals

```yaml
id: ritual.loom.post_mortem
version: 1.0.0
description: >
  Investigate and publish a post-mortem for a significant
  knowledge error — a claim that was verified or corroborated
  and later found to be incorrect.

params:
  - name: claim_id
    type: string
    required: true
  - name: correcting_evidence_id
    type: string
    required: true
  - name: community_id
    type: string
    required: true

steps:
  - id: gather_history
    skill: kb.query.claim_history
    context_map:
      claim_id: "{{ params.claim_id }}"
      community_id: "{{ params.community_id }}"

  - id: trace_pipeline
    skill: loom.trace.acquisition_path
    depends_on: [gather_history]
    context_map:
      claim_id: "{{ params.claim_id }}"
      evidence_chain: "{{ steps.gather_history.result.evidence_chain }}"

  - id: identify_failure
    skill: loom.analyze.pipeline_failure
    depends_on: [trace_pipeline]
    context_map:
      acquisition_path: "{{ steps.trace_pipeline.result }}"
      correcting_evidence_id: "{{ params.correcting_evidence_id }}"

  - id: draft_post_mortem
    skill: loom.write.post_mortem
    depends_on: [identify_failure]
    context_map:
      claim_history: "{{ steps.gather_history.result }}"
      pipeline_failure: "{{ steps.identify_failure.result }}"
      correcting_evidence_id: "{{ params.correcting_evidence_id }}"

  - id: curator_review
    skill: curate.review
    depends_on: [draft_post_mortem]
    context_map:
      post_mortem: "{{ steps.draft_post_mortem.result }}"
      community_id: "{{ params.community_id }}"

output_map:
  post_mortem: "{{ steps.curator_review.result.approved_post_mortem }}"
  structural_fix: "{{ steps.identify_failure.result.recommended_fix }}"
  affected_claims: "{{ steps.gather_history.result.downstream_claims }}"
```

### New duties

```yaml
id: duty.loom.source_rate_check
interval: 1h
description: >
  Monitor source introduction rates and flag anomalies
  that may indicate coordinated poisoning attempts.

skill: loom.monitor.source_rates
context_map:
  window: "24h"
  threshold_new_origins: 50
  threshold_claims_per_origin: 10
  threshold_topic_concentration: 0.8
```

```yaml
id: duty.loom.challenge_health
interval: 24h
description: >
  Monitor challenge process health — submission rates,
  auto-close rates, resolution times — and flag potential
  challenge suppression.

skill: loom.monitor.challenge_health
context_map:
  window: "30d"
  max_auto_close_rate: 0.8
  min_submission_rate_percentile: 10
```

---

## 11. Open Questions

**How do you handle government source compromise?** If a .gov
domain is hacked or a government official publishes deliberately
misleading data through official channels, the T1 designation
provides false security. The content hash detects *changes* but
not *original falsity*. This is a genuine limitation — the
evidence hierarchy assumes institutional sources are
non-adversarial, which is usually but not always true. The
mitigation is cross-verification: even T1 claims should be
cross-checked against T2/T3 sources when feasible. A T1 budget
document that contradicts the T2 financial audit warrants
investigation, not automatic deference.

**Where is the line between rate limiting and suppression?**
Every anti-flooding measure is also a potential
anti-participation measure. Rate limits that stop coordinated
attacks also slow down legitimate community members who are
passionate about multiple issues. The `challenge_suppression`
anti-pattern monitor (§9) helps, but the threshold calibration
requires real-world experience.

**Should Loom defend itself or let others defend it?** A system
that argues for its own credibility has an obvious conflict of
interest. The strongest defense may be to let Loom's users —
journalists, community members, researchers — make the case
based on their experience. Loom should show its work and let
the work speak.

**How transparent is too transparent for adversarial
resilience?** Publishing the full defense playbook (this
document) tells adversaries exactly what defenses they face.
The alternative — security through obscurity — is worse.
Every defense here relies on structural properties (the
evidence hierarchy, deterministic computation, content hashing),
not secrecy. Knowing the defenses doesn't help an attacker
bypass them any more than knowing a lock exists helps you pick
it without the key.

---

*The best defense for a knowledge system is not to be
impregnable but to be transparent. An attacker who succeeds
against an opaque system has won permanently — no one knows
what was changed. An attacker who succeeds against a
transparent system has won temporarily — the provenance chain,
the changelog, and the community challenge process will
eventually surface the corruption. The goal is not to prevent
all attacks but to ensure that every attack is detectable,
reversible, and public. That is what makes the attack not
worth attempting.*
