# Loom — Next Plan

## Iteration 5: Live integration test + AGENTS.md skill map update

The foundation is built. Four iterations of momentum have
produced a working pipeline with 69 tests. Time to prove it
works end-to-end with live HTTP, then clean up the docs.

1. **Live integration test** — Fetch a real .gov URL, extract
   claims, classify, corroborate, store. Verify the full chain
   works against a live server (not just fixtures).

2. **Update AGENTS.md** — Skill map is outdated (doesn't list
   new skills: classify.claim_type, loom.kb.find_similar,
   loom.kb.record_contradiction, loom.kb.update_claim).

3. **Pipeline CLI** — Make `pipeline.py` runnable from command
   line: `python3 pipeline.py <url>` prints stored claims.

4. **Reflection** — Update next-plan with Phase 2 roadmap
   (dual-axis schema, warrant tracking, ClaimReview export).
   Assess whether to continue or pause here.

## Success criteria
- Live test fetches real URL and stores claims
- AGENTS.md accurately reflects current capabilities
- Pipeline is usable from command line
- has_next evaluated honestly
