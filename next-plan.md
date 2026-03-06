# Loom — Next Plan

## Iteration 4: KB deduplication + contradiction detection

The pipeline stores claims but doesn't check for duplicates or
detect contradictions between stored claims. These are critical
for the CI/CD model — without dedup, re-harvesting the same URL
creates duplicate claims; without contradiction detection, the
"contested" status never triggers.

1. **KB deduplication** — Before storing, check if a semantically
   similar claim already exists (exact match + fuzzy LIKE match).
   If found, add evidence to existing claim instead of creating new.

2. **Contradiction detection** — `corroborate.find_contradictions`
   skill that compares numeric claims for conflicts (e.g., "population
   is 50,000" vs "population is 60,000"). Store contradictions in
   the contradictions table.

3. **Contested status propagation** — When a contradiction is found,
   update both claims to "contested" status with reduced confidence.

4. **Re-harvest test** — Golden fixture: harvest same URL twice,
   verify no duplicates; harvest conflicting URL, verify contradiction
   detected and status updated.

## Success criteria
- Duplicate claims are merged (same claim from same URL → 1 record)
- Contradicting claims create contradiction records
- Contested status propagates to both contradicting claims
- Confidence drops when claim becomes contested
- All tests pass (target: 70+ Python tests)
