-- ── DPDP-compliant IAM schema extension ─────────────────────────────────────
-- Applied after foundation/schema.sql. All tables are idempotent (IF NOT EXISTS).

-- ── Extend foundation tables ─────────────────────────────────────────────────
-- Add contact columns to guardian_links for OTP delivery
ALTER TABLE foundation.guardian_links ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE foundation.guardian_links ADD COLUMN IF NOT EXISTS phone TEXT;

-- Add confirmed status to delegated_access
ALTER TABLE foundation.delegated_access ADD COLUMN IF NOT EXISTS confirmed BOOLEAN DEFAULT false;

-- Unique DID per challenge slot (upsert uses this)
CREATE UNIQUE INDEX IF NOT EXISTS auth_challenges_did_idx
    ON foundation.auth_challenges (did) WHERE used = false;

-- ── DID Documents ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.did_documents (
    did                   TEXT PRIMARY KEY,
    identity_id           UUID REFERENCES foundation.identities(id) ON DELETE CASCADE,
    did_document          JSONB NOT NULL DEFAULT '{}',
    public_key_jwk        JSONB NOT NULL DEFAULT '{}',
    encrypted_private_key TEXT,   -- Fernet-encrypted Ed25519 private bytes; NULL for client-held
    created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS did_documents_identity_idx
    ON foundation.did_documents (identity_id);

-- ── Verifiable Credentials ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.credentials (
    id                UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    vc_type           TEXT[]  NOT NULL,
    issuer_did        TEXT    NOT NULL,
    subject_did       TEXT    NOT NULL,
    credential_json   JSONB   NOT NULL,
    proof_jws         TEXT    NOT NULL,
    issued_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ,
    revoked_at        TIMESTAMPTZ,
    revocation_reason TEXT
);

CREATE INDEX IF NOT EXISTS credentials_subject_idx
    ON foundation.credentials (subject_did, issued_at DESC);

CREATE INDEX IF NOT EXISTS credentials_vc_type_gin_idx
    ON foundation.credentials USING GIN (vc_type);

-- ── DPDP Consent Records ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.consent_records (
    id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    credential_id    UUID    REFERENCES foundation.credentials(id),
    guardian_did     TEXT    NOT NULL,
    child_id         UUID    REFERENCES foundation.identities(id) ON DELETE CASCADE,
    purpose          TEXT    NOT NULL,
    lawful_basis     TEXT    NOT NULL DEFAULT 'consent',
    data_categories  TEXT[]  NOT NULL DEFAULT '{}',
    scope            TEXT[]  NOT NULL DEFAULT '{}',
    consent_version  TEXT    NOT NULL DEFAULT '1.0',
    channel          TEXT    NOT NULL,
    retention_days   INT     DEFAULT 365,
    otp_verified     BOOLEAN DEFAULT false,
    guardian_ip      INET,
    granted_at       TIMESTAMPTZ DEFAULT now(),
    expires_at       TIMESTAMPTZ,
    withdrawn_at     TIMESTAMPTZ,
    withdrawal_reason TEXT
);

CREATE INDEX IF NOT EXISTS consent_records_child_idx
    ON foundation.consent_records (child_id, granted_at DESC);

CREATE INDEX IF NOT EXISTS consent_records_guardian_idx
    ON foundation.consent_records (guardian_did);

-- ── Auth Tokens (JWT JTI registry for revocation) ───────────────────────────

CREATE TABLE IF NOT EXISTS foundation.auth_tokens (
    jti          UUID    PRIMARY KEY,
    subject_did  TEXT    NOT NULL,
    role         TEXT    NOT NULL,
    scopes       TEXT[]  NOT NULL DEFAULT '{}',
    child_ids    TEXT[]  DEFAULT '{}',
    issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS auth_tokens_subject_active_idx
    ON foundation.auth_tokens (subject_did)
    WHERE revoked_at IS NULL;

-- ── Roles ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.roles (
    name        TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ── Role Assignments ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.role_assignments (
    identity_id UUID REFERENCES foundation.identities(id) ON DELETE CASCADE,
    role        TEXT REFERENCES foundation.roles(name),
    granted_by  UUID,
    granted_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ,
    PRIMARY KEY (identity_id, role)
);

-- ── Permissions (RBAC matrix + ABAC policy) ──────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.permissions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role        TEXT NOT NULL REFERENCES foundation.roles(name),
    resource    TEXT NOT NULL,
    action      TEXT NOT NULL,
    abac_policy JSONB DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS permissions_role_resource_action_idx
    ON foundation.permissions (role, resource, action);

-- ── Delegated Access (guardian → teacher) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.delegated_access (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    credential_id      UUID REFERENCES foundation.credentials(id),
    delegator_did      TEXT NOT NULL,
    delegate_did       TEXT NOT NULL,
    child_id           UUID REFERENCES foundation.identities(id) ON DELETE CASCADE,
    scopes             TEXT[] NOT NULL DEFAULT '{}',
    valid_from         TIMESTAMPTZ DEFAULT now(),
    valid_until        TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    revocation_reason  TEXT
);

CREATE INDEX IF NOT EXISTS delegated_access_delegate_active_idx
    ON foundation.delegated_access (delegate_did)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS delegated_access_child_idx
    ON foundation.delegated_access (child_id);

-- ── Audit Log (append-only, hash-chained) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.audit_log (
    id             BIGSERIAL PRIMARY KEY,
    event_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
    caller_did     TEXT,
    caller_role    TEXT,
    action         TEXT NOT NULL,
    resource_type  TEXT NOT NULL,
    resource_id    TEXT,
    endpoint       TEXT,
    http_method    TEXT,
    success        BOOLEAN NOT NULL,
    denial_reason  TEXT,
    request_id     UUID,
    caller_ip      INET,
    row_hash       TEXT,
    prev_hash      TEXT
);

CREATE INDEX IF NOT EXISTS audit_log_caller_idx
    ON foundation.audit_log (caller_did, event_time DESC);

CREATE INDEX IF NOT EXISTS audit_log_resource_idx
    ON foundation.audit_log (resource_id, event_time DESC);

CREATE INDEX IF NOT EXISTS audit_log_time_idx
    ON foundation.audit_log (event_time DESC);

-- Tamper-prevention: block UPDATE and DELETE on audit_log
DO $$ BEGIN
    CREATE RULE audit_log_no_update AS ON UPDATE TO foundation.audit_log DO INSTEAD NOTHING;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE RULE audit_log_no_delete AS ON DELETE TO foundation.audit_log DO INSTEAD NOTHING;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── OTP Tokens ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.otp_tokens (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guardian_did TEXT NOT NULL,
    purpose      TEXT NOT NULL CHECK (purpose IN (
                     'consent_grant', 'erasure_request',
                     'role_elevation', 'delegation_grant')),
    otp_hash     TEXT NOT NULL,
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS otp_tokens_active_idx
    ON foundation.otp_tokens (guardian_did, purpose, expires_at)
    WHERE used_at IS NULL;

-- ── Auth Challenges (DID-auth nonce) ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.auth_challenges (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nonce      TEXT NOT NULL,
    did        TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    used       BOOLEAN DEFAULT false
);

-- ── Seed: Roles ───────────────────────────────────────────────────────────────

INSERT INTO foundation.roles (name, description) VALUES
    ('child',    'Learner — access limited to own chat and learning state'),
    ('guardian', 'Parent or legal guardian — manages consent and views child reports'),
    ('teacher',  'Educator — read access to assigned students via delegated consent'),
    ('admin',    'Platform administrator — destructive operations require SoD approval'),
    ('observer', 'Read-only access to demo and monitor interfaces')
ON CONFLICT DO NOTHING;

-- ── Seed: Permission matrix ───────────────────────────────────────────────────

-- child
INSERT INTO foundation.permissions (role, resource, action, abac_policy) VALUES
    ('child', 'chat',          'write', '{"owner_only": true, "require_scope": "ai_interaction"}'),
    ('child', 'learner_state', 'read',  '{"owner_only": true, "require_scope": "learner_data"}')
ON CONFLICT DO NOTHING;

-- guardian
INSERT INTO foundation.permissions (role, resource, action, abac_policy) VALUES
    ('guardian', 'consent',       'manage', '{"owner_only": true}'),
    ('guardian', 'learner_state', 'read',   '{"guardian_of": true, "require_scope": "learner_data"}'),
    ('guardian', 'report',        'read',   '{"guardian_of": true, "require_scope": "progress_report"}'),
    ('guardian', 'psyche',        'read',   '{"guardian_of": true, "require_scope": "learner_data", "sensitivity": "HIGH"}'),
    ('guardian', 'delegation',    'manage', '{"guardian_of": true}'),
    ('guardian', 'erasure',       'request','{"guardian_of": true, "sod_required": true}')
ON CONFLICT DO NOTHING;

-- teacher
INSERT INTO foundation.permissions (role, resource, action, abac_policy) VALUES
    ('teacher', 'learner_state', 'read', '{"require_delegation": true, "delegation_scope": "learner_data"}'),
    ('teacher', 'report',        'read', '{"require_delegation": true, "delegation_scope": "progress_report"}')
ON CONFLICT DO NOTHING;

-- admin
INSERT INTO foundation.permissions (role, resource, action, abac_policy) VALUES
    ('admin', 'erasure',         'confirm', '{"sod_required": true}'),
    ('admin', 'role_assignment', 'manage',  '{"sod_required": true}')
ON CONFLICT DO NOTHING;

-- observer
INSERT INTO foundation.permissions (role, resource, action, abac_policy) VALUES
    ('observer', 'demo',    'read', '{}'),
    ('observer', 'monitor', 'read', '{}')
ON CONFLICT DO NOTHING;
