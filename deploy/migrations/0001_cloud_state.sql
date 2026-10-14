-- Compact private projections and durable single-writer job authority.
-- Raw articles, enriched inputs, estimators and native checkpoints live in S3.
CREATE SCHEMA IF NOT EXISTS marketpulse AUTHORIZATION marketpulse_owner;
REVOKE ALL ON SCHEMA marketpulse FROM PUBLIC;
GRANT USAGE ON SCHEMA marketpulse TO marketpulse_worker, marketpulse_reader;

CREATE TABLE marketpulse.schema_migrations (
    name text PRIMARY KEY,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE marketpulse.objects (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    object_key text NOT NULL UNIQUE,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    kind text NOT NULL CHECK (kind IN ('projection', 'checkpoint', 'model', 'input', 'archive')),
    verified_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE marketpulse.jobs (
    job_key text PRIMARY KEY CHECK (length(job_key) BETWEEN 1 AND 160),
    kind text NOT NULL CHECK (kind IN ('bootstrap', 'prediction', 'outcomes', 'training', 'retention')),
    status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETE', 'UNKNOWN', 'FAILED')),
    owner uuid NOT NULL,
    lease_until timestamptz NOT NULL,
    checkpoint_hash text REFERENCES marketpulse.objects(sha256),
    result_hash text REFERENCES marketpulse.objects(sha256),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'COMPLETE' OR (checkpoint_hash IS NOT NULL AND result_hash IS NOT NULL))
);
CREATE INDEX jobs_incomplete ON marketpulse.jobs(lease_until) WHERE status='RUNNING';
CREATE TABLE marketpulse.projections (
    projection_id text PRIMARY KEY CHECK (length(projection_id) BETWEEN 1 AND 160),
    kind text NOT NULL CHECK (kind IN ('research', 'forward')),
    object_hash text NOT NULL REFERENCES marketpulse.objects(sha256),
    job_key text NOT NULL REFERENCES marketpulse.jobs(job_key),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (octet_length(payload::text) <= 4000000),
    CHECK (payload->>'schema' = 'marketpulse-cloud-projection/1'),
    CHECK (payload->>'paper_action_authorized' = 'false'),
    CHECK (payload->>'deployment_promoted' = 'false'),
    CHECK ((kind='research' AND payload->>'availability_tier'='HISTORICAL_APPROXIMATE')
        OR (kind='forward' AND payload->>'availability_tier'='FORWARD_CAPTURED'))
);
CREATE INDEX projections_latest ON marketpulse.projections(kind, created_at DESC);

-- Views deliberately exclude artifact keys, leases and provider payloads.
CREATE VIEW marketpulse.dashboard_research AS
    SELECT projection_id, payload, created_at FROM marketpulse.projections
    WHERE kind='research';
CREATE VIEW marketpulse.dashboard_forward AS
    SELECT projection_id, payload, created_at FROM marketpulse.projections
    WHERE kind='forward';
CREATE VIEW marketpulse.dashboard_jobs AS
    SELECT job_key, kind, status, updated_at FROM marketpulse.jobs;
GRANT SELECT ON marketpulse.dashboard_research, marketpulse.dashboard_forward,
    marketpulse.dashboard_jobs TO marketpulse_reader;
GRANT SELECT ON marketpulse.schema_migrations, marketpulse.objects,
    marketpulse.jobs, marketpulse.projections TO marketpulse_worker;
GRANT INSERT ON marketpulse.objects, marketpulse.jobs, marketpulse.projections
    TO marketpulse_worker;
GRANT UPDATE (status, lease_until, checkpoint_hash, result_hash, updated_at)
    ON marketpulse.jobs TO marketpulse_worker;
-- Neither application role can change schema, overwrite projections or delete history.
