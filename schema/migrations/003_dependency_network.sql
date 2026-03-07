-- Migration 003: Dependency network (ATMS-inspired)
-- Adds source retraction tracking, dependency labels, and sensitivity analysis

-- Track retracted/discredited sources
CREATE TABLE IF NOT EXISTS source_retractions (
    retraction_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    reason TEXT NOT NULL,              -- retracted|corrected|expired|discredited
    detail TEXT,                       -- explanation
    retracted_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retractions_url ON source_retractions(source_url);

-- ATMS-style labels: minimal supporting sets per claim
-- Each label is a set of evidence_ids that independently support the claim
CREATE TABLE IF NOT EXISTS dependency_labels (
    label_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_ids TEXT NOT NULL,        -- JSON array of evidence_ids in this support set
    is_minimal INTEGER DEFAULT 1,      -- 1 if no subset also supports the claim
    is_valid INTEGER DEFAULT 1,        -- 0 if any evidence in set is retracted
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_labels_claim ON dependency_labels(claim_id);

-- Add retraction status to evidence
ALTER TABLE evidence ADD COLUMN retracted INTEGER DEFAULT 0;
ALTER TABLE evidence ADD COLUMN retracted_reason TEXT;
ALTER TABLE evidence ADD COLUMN retracted_at TEXT;
