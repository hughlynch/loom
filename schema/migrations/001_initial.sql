-- Migration 001: Initial evidence graph schema
-- Version: 1.0.0
-- Applied: creates the core Loom evidence graph tables

-- Source registry
CREATE TABLE IF NOT EXISTS sources (
    source_id       TEXT PRIMARY KEY,
    url             TEXT,
    origin          TEXT NOT NULL,     -- publisher/institution
    source_type     TEXT NOT NULL,     -- primary_record, news, opinion, academic, community, social_media, anonymous
    tier            INTEGER NOT NULL,  -- 1-7 per evidence hierarchy
    first_seen      TEXT NOT NULL,
    last_verified   TEXT NOT NULL,
    content_hash    TEXT,              -- SHA-256 of retrieved content
    reliability     REAL DEFAULT 0.5,  -- 0-1, updated over time
    metadata        TEXT               -- JSON: author, publication date, etc.
);

-- Claims: atomic knowledge assertions
CREATE TABLE IF NOT EXISTS claims (
    claim_id        TEXT PRIMARY KEY,
    statement       TEXT NOT NULL,     -- natural language assertion
    normalized      TEXT,              -- canonical form for dedup
    category        TEXT NOT NULL,
    confidence      TEXT NOT NULL,     -- verified/corroborated/reported/contested/unverified
    valid_from      TEXT,              -- temporal validity start
    valid_until     TEXT,              -- temporal validity end
    community_id    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    superseded_by   TEXT,              -- claim_id that replaced this
    chunk_ids       TEXT               -- JSON: linked KB chunks
);

-- Evidence links: connects claims to sources
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id     TEXT PRIMARY KEY,
    claim_id        TEXT NOT NULL REFERENCES claims(claim_id),
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    relationship    TEXT NOT NULL,     -- supports, contradicts, partially_supports, contextualizes
    excerpt         TEXT,              -- relevant passage from source
    retrieved_at    TEXT NOT NULL,
    transformation  TEXT,              -- how claim was derived: verbatim, summarized, inferred, extracted
    UNIQUE(claim_id, source_id, relationship)
);

-- Contradictions: explicit disagreement records
CREATE TABLE IF NOT EXISTS contradictions (
    contradiction_id TEXT PRIMARY KEY,
    claim_a_id       TEXT NOT NULL REFERENCES claims(claim_id),
    claim_b_id       TEXT NOT NULL REFERENCES claims(claim_id),
    nature           TEXT NOT NULL,    -- factual, interpretive, temporal, definitional
    resolution       TEXT,             -- null until resolved
    resolved_by      TEXT,             -- source_id or curator_id
    resolved_at      TEXT,
    notes            TEXT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_sources_origin ON sources(origin);
CREATE INDEX IF NOT EXISTS idx_sources_tier ON sources(tier);
CREATE INDEX IF NOT EXISTS idx_sources_reliability ON sources(reliability);
CREATE INDEX IF NOT EXISTS idx_sources_last_verified ON sources(last_verified);

CREATE INDEX IF NOT EXISTS idx_claims_community ON claims(community_id);
CREATE INDEX IF NOT EXISTS idx_claims_confidence ON claims(confidence);
CREATE INDEX IF NOT EXISTS idx_claims_category ON claims(category);
CREATE INDEX IF NOT EXISTS idx_claims_valid_until ON claims(valid_until);
CREATE INDEX IF NOT EXISTS idx_claims_superseded_by ON claims(superseded_by);
CREATE INDEX IF NOT EXISTS idx_claims_updated_at ON claims(updated_at);

CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_relationship ON evidence(relationship);

CREATE INDEX IF NOT EXISTS idx_contradictions_claim_a ON contradictions(claim_a_id);
CREATE INDEX IF NOT EXISTS idx_contradictions_claim_b ON contradictions(claim_b_id);
CREATE INDEX IF NOT EXISTS idx_contradictions_resolution ON contradictions(resolution);
