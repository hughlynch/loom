# Loom — Next Plan

## Iteration 2: Claim-type classification + temporal model

From architectural-recommendations.md Phase 1 (no arch change needed):

1. **Claim-type classification** — Add `classify.claim_type` skill to
   classifier that categorizes claims as empirical_fact, statistical,
   causal, prediction, opinion, attribution, or temporal. Different
   claim types get different assessment methods and TTL defaults.

2. **Temporal validity model** — Enhance `classify.temporal_validity`
   to compute real validity windows based on claim type and source date.
   Add `valid_from`, `valid_until`, `temporal_status` (current/outdated/
   superseded) to KB schema.

3. **KB update_claim skill** — Add ability to update an existing claim's
   confidence/status when new evidence arrives (with version tracking).

4. **Multi-source corroboration test** — Golden fixture with same claim
   from 2+ sources at different tiers, verifying corroboration boost
   and independence check.

## Success criteria
- Claim-type classifier assigns correct types to test claims
- Temporal validity windows match expected TTL for each claim type
- KB supports claim updates with version history
- Multi-source corroboration test demonstrates confidence boost
- All tests pass (target: 30+ Python tests)
