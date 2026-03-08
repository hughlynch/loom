-- Migration 004: Event log for event-sourced storage
-- See spec/storage-strategy.md for rationale.
--
-- Events are the machine-readable counterpart to
-- claim_versions (which remains for human audit trail).
-- Enables: event-driven build triggers, diff queries,
-- replay for testing.

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    domain_id TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_events_seq
    ON events(sequence);
CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_aggregate
    ON events(aggregate_id);
CREATE INDEX IF NOT EXISTS idx_events_domain
    ON events(domain_id);
CREATE INDEX IF NOT EXISTS idx_events_domain_seq
    ON events(domain_id, sequence);
