# Loom — Next Plan

## Phase 1: Foundation

1. Evidence graph schema — SQLite DB with sources, claims, evidence, contradictions tables
2. Harvester worker — web fetching with content hashing and robots.txt respect
3. Classifier worker — T1-T7 tier assignment with domain verification
4. Corroborator worker — deterministic confidence computation
5. KB worker — storage and query over the evidence graph
6. E2E test — full acquisition pipeline (harvest → classify → extract → corroborate → store)

## Success criteria
- All workers register and respond to skill invocations
- Evidence graph stores claims with full provenance
- Confidence computation matches spec rules deterministically
- E2E test passes with a golden fixture (known source → expected claims → expected confidence)
