# Loom — Next Plan

## Iteration 3: Extractor worker (heuristic claim extraction)

The extractor is the missing link in the pipeline. Without it,
claims must be manually specified. Build a heuristic extractor
that works without LLM calls (pattern-based), then wire the
full automated pipeline: URL → harvest → classify → extract →
corroborate → store.

1. **Heuristic claim extraction** — `extract.claims` skill that
   finds factual assertions in text using sentence segmentation
   and heuristic filters (discard questions, commands, fragments).

2. **Entity extraction** — `extract.entities` skill that finds
   named entities (people, orgs, places, numbers) using regex
   patterns. Not NER-quality, but sufficient for pipeline wiring.

3. **Automated pipeline function** — Python module that chains
   all workers: given a URL, produce stored claims with provenance.

4. **Second golden fixture** — AP News article fixture exercising
   the full automated pipeline (T3 source, multiple claims).

## Success criteria
- Extractor produces sensible claims from real text
- Entity extraction finds named entities
- Automated pipeline runs URL → stored claims without manual steps
- Two golden fixtures pass (gov T1 + news T3)
- All tests pass (target: 50+ Python tests)
