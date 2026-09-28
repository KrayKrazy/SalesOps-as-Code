-- =====================================================================
-- KELEVRA SALESOPS v3.0 — MIGRACAO RECONCILIADA (real PT + ideal EN)
-- Idempotente. NUNCA renomeia, NUNCA exclui. Apenas additive.
-- Rode no SQL Editor do Supabase cloud (omdieogddacchiihjqyl).
-- =====================================================================

-- 1) cold_leads: colunas adicionais (additive, coexistem com o PT existente)
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS email              TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS website            TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS endereco           TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS cidade             TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS rating             NUMERIC(3,1) DEFAULT 0;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS review_count       INT DEFAULT 0;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS socials            JSONB;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS seo_dossier        JSONB;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS icp_score          INT DEFAULT 0;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS icp_reason         TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS whatsapp_valid     BOOLEAN DEFAULT FALSE;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS assigned_agent     TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS fonte              TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS followup_count     INT DEFAULT 0;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS last_followup_at   TIMESTAMPTZ;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS opt_out_at         TIMESTAMPTZ;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS last_seen_at       TIMESTAMPTZ;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS whatsapp_instance  TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS crm_external_id    TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS opening_copy       TEXT;
ALTER TABLE cold_leads ADD COLUMN IF NOT EXISTS trace_id_last      TEXT;

-- 2) Pool de WhatsApp instances (anti-ban)
CREATE TABLE IF NOT EXISTS whatsapp_instances (
    id                  BIGSERIAL PRIMARY KEY,
    instance_name       TEXT NOT NULL UNIQUE,
    type                TEXT DEFAULT 'evolution',
    daily_quota         INT DEFAULT 48,
    sent_today          INT DEFAULT 0,
    total_sent_all_time BIGINT DEFAULT 0,
    status              TEXT DEFAULT 'active',
    quarantined_at      TIMESTAMPTZ,
    cooldown_until      TIMESTAMPTZ,
    last_health_check   TIMESTAMPTZ,
    last_delivered_rate NUMERIC(5,4),
    provider_meta       JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 3) Execucoes dos agentes (observabilidade)
CREATE TABLE IF NOT EXISTS agent_runs (
    id              BIGSERIAL PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    lead_id         BIGINT,
    model           TEXT,
    prompt_version  TEXT,
    status          TEXT,
    input_hash      TEXT,
    tokens_in       INT DEFAULT 0,
    tokens_out      INT DEFAULT 0,
    cost_est        NUMERIC(12,6) DEFAULT 0,
    latency_ms      INT DEFAULT 0,
    trace_id        TEXT,
    meta            JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 4) Log de erros
CREATE TABLE IF NOT EXISTS error_log (
    id            BIGSERIAL PRIMARY KEY,
    agent_id      TEXT,
    lead_id       BIGINT,
    error_type    TEXT,
    message       TEXT,
    context       JSONB,
    severity      TEXT DEFAULT 'medium',
    resolved      BOOLEAN DEFAULT FALSE,
    resolution    TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    resolved_at   TIMESTAMPTZ
);

-- 5) Trilha de auditoria imutavel
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    lead_id     BIGINT,
    actor       TEXT,
    action      TEXT,
    from_state  TEXT,
    to_state    TEXT,
    detail      JSONB,
    trace_id    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 6) trace_id no log de mensagens (observabilidade)
ALTER TABLE messages_log ADD COLUMN IF NOT EXISTS trace_id TEXT;

-- 7) Indices de performance
CREATE INDEX IF NOT EXISTS idx_cold_leads_icp_score   ON cold_leads(icp_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_cold_leads_whats_valid ON cold_leads(whatsapp_valid, status);
CREATE INDEX IF NOT EXISTS idx_cold_leads_telefone    ON cold_leads(telefone);
CREATE INDEX IF NOT EXISTS idx_cold_leads_crm_id      ON cold_leads(crm_external_id);
CREATE INDEX IF NOT EXISTS idx_messages_log_lead      ON messages_log(lead_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent       ON agent_runs(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_error_log_resolved     ON error_log(resolved);
