-- Migration 002: Dual-axis evaluation system
-- Adds information credibility (C1-C6) alongside source reliability (T1-T7)
-- Adds GRADE-like adjustment factors and warrant tracking (Toulmin)
-- Adds structured disagreement model (IPCC-inspired)
-- Adds temporal deprecation fields (Wikidata-inspired)

-- Phase 2a: Evidence link extensions
ALTER TABLE evidence ADD COLUMN info_credibility TEXT;        -- C1-C6
ALTER TABLE evidence ADD COLUMN relationship TEXT DEFAULT 'supports'; -- supports|contradicts|contextualizes
ALTER TABLE evidence ADD COLUMN warrant TEXT;                 -- WHY evidence supports claim (Toulmin)
ALTER TABLE evidence ADD COLUMN assumptions TEXT;             -- JSON: declared premises
ALTER TABLE evidence ADD COLUMN inference TEXT DEFAULT 'verbatim'; -- verbatim|summarized|inferred|calculated|analogical
ALTER TABLE evidence ADD COLUMN directness TEXT DEFAULT 'direct';  -- direct|indirect_population|indirect_intervention|analogical
ALTER TABLE evidence ADD COLUMN upstream_source TEXT;         -- source_url of upstream (independence tracking)

-- Phase 2b: Claim extensions for GRADE and IPCC
ALTER TABLE claims ADD COLUMN info_credibility TEXT;          -- C1-C6 (best across evidence)
ALTER TABLE claims ADD COLUMN evidence_strength TEXT DEFAULT 'limited';  -- limited|medium|robust (IPCC)
ALTER TABLE claims ADD COLUMN agreement_level TEXT DEFAULT 'low';        -- low|medium|high (IPCC)
ALTER TABLE claims ADD COLUMN analytic_confidence TEXT;       -- low|medium|high|very_high (ICD 203)
ALTER TABLE claims ADD COLUMN claim_type TEXT;                -- empirical_fact|statistical|causal|prediction|opinion|attribution|temporal
ALTER TABLE claims ADD COLUMN temporal_status TEXT DEFAULT 'current'; -- current|outdated|superseded
ALTER TABLE claims ADD COLUMN superseded_by TEXT;             -- claim_id of replacement
ALTER TABLE claims ADD COLUMN superseded_reason TEXT;
ALTER TABLE claims ADD COLUMN deprecation_date TEXT;

-- Phase 2c: GRADE adjustment factors per evidence link
CREATE TABLE IF NOT EXISTS grade_adjustments (
    adjustment_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    factor TEXT NOT NULL,          -- risk_of_bias|inconsistency|indirectness|imprecision|publication_bias|large_effect|dose_response|confounding
    direction TEXT NOT NULL,       -- down|up
    magnitude REAL NOT NULL,       -- 0.0 to 1.0
    justification TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grade_evidence ON grade_adjustments(evidence_id);

-- Phase 2d: Structured disagreement model
CREATE TABLE IF NOT EXISTS disagreements (
    disagreement_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_strength TEXT NOT NULL,  -- limited|medium|robust
    agreement_level TEXT NOT NULL,    -- low|medium|high
    nature TEXT,                      -- factual|interpretive|temporal|definitional|methodological
    axis TEXT,                        -- what they disagree about
    resolution_path TEXT,             -- what would resolve it
    resolved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disagreement_positions (
    position_id TEXT PRIMARY KEY,
    disagreement_id TEXT NOT NULL REFERENCES disagreements(disagreement_id),
    position TEXT NOT NULL,           -- the claim being made
    evidence_ids TEXT,                -- JSON array of supporting evidence_ids
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disagreements_claim ON disagreements(claim_id);
CREATE INDEX IF NOT EXISTS idx_positions_disagreement ON disagreement_positions(disagreement_id);
