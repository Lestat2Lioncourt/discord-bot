-- Migration 006: Ajouter table audit_log pour tracer les actions des Sages
-- Date: 2024-12-28

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL,
    target_username VARCHAR(100) NOT NULL,
    target_discord_id BIGINT,
    sage_username VARCHAR(100) NOT NULL,
    sage_discord_id BIGINT NOT NULL,
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index pour recherches par cible ou par sage
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_username);
CREATE INDEX IF NOT EXISTS idx_audit_log_sage ON audit_log(sage_username);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
