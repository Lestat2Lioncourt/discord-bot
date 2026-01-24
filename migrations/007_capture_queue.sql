-- Migration 007: Table capture_queue pour le traitement asynchrone des images
-- Les images sont stockées en attente, traitées par Claude Vision sur machine locale,
-- puis validées/refusées par l'utilisateur via le bot.

CREATE TABLE IF NOT EXISTS capture_queue (
    id SERIAL PRIMARY KEY,

    -- Qui a soumis
    discord_user_id BIGINT NOT NULL,
    discord_username VARCHAR(100) NOT NULL,
    discord_display_name VARCHAR(100),

    -- Pour quel joueur (peut être NULL si sélectionné après)
    player_name VARCHAR(100),

    -- L'image (stockée en base pour simplicité)
    image_data BYTEA NOT NULL,
    image_filename VARCHAR(255),

    -- Statut du traitement
    -- pending: en attente de traitement
    -- processing: en cours de traitement par Claude
    -- completed: traité avec succès, en attente de validation utilisateur
    -- validated: validé par l'utilisateur, sauvegardé en base
    -- rejected: refusé par l'utilisateur
    -- failed: erreur lors du traitement
    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    -- Dates
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    validated_at TIMESTAMP WITH TIME ZONE,

    -- Résultat de l'analyse Claude (JSON)
    result_json JSONB,

    -- Message d'erreur si failed
    error_message TEXT,

    -- Index pour les requêtes fréquentes
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'validated', 'rejected', 'failed'))
);

-- Index pour trouver rapidement les captures en attente
CREATE INDEX IF NOT EXISTS idx_capture_queue_status ON capture_queue(status);

-- Index pour trouver les captures d'un utilisateur
CREATE INDEX IF NOT EXISTS idx_capture_queue_user ON capture_queue(discord_user_id);

-- Index pour trouver les captures pending (pour le script de traitement)
CREATE INDEX IF NOT EXISTS idx_capture_queue_pending ON capture_queue(status) WHERE status = 'pending';

-- Index pour trouver les captures completed (pour notification utilisateur)
CREATE INDEX IF NOT EXISTS idx_capture_queue_completed ON capture_queue(status, discord_user_id) WHERE status = 'completed';

COMMENT ON TABLE capture_queue IS 'File d''attente des captures Tennis Clash à analyser via Claude Vision';
COMMENT ON COLUMN capture_queue.status IS 'pending → processing → completed → validated/rejected (ou failed)';
COMMENT ON COLUMN capture_queue.result_json IS 'JSON retourné par Claude Vision avec stats et équipements';
