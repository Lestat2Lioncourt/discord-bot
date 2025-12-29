-- Migration 003: Historique des usernames
-- Permet de detecter les membres qui reviennent avec un nouveau username

-- D'abord, ajouter une contrainte unique sur discord_id dans user_profile
-- (necessaire pour la foreign key)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_profile_discord_id_unique'
    ) THEN
        ALTER TABLE user_profile ADD CONSTRAINT user_profile_discord_id_unique UNIQUE (discord_id);
    END IF;
END $$;

-- Table pour stocker l'historique des usernames
CREATE TABLE IF NOT EXISTS username_history (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL,
    username VARCHAR(100) NOT NULL,
    discord_name VARCHAR(100),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key vers user_profile
    CONSTRAINT fk_username_history_discord_id FOREIGN KEY (discord_id)
        REFERENCES user_profile(discord_id) ON DELETE CASCADE
);

-- Index pour accelerer les recherches
CREATE INDEX IF NOT EXISTS idx_username_history_discord_id ON username_history(discord_id);
CREATE INDEX IF NOT EXISTS idx_username_history_username ON username_history(username);

-- Fonction pour enregistrer automatiquement les changements de username
CREATE OR REPLACE FUNCTION log_username_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Si c'est une nouvelle insertion ou si le username a change
    IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND OLD.username != NEW.username) THEN
        INSERT INTO username_history (discord_id, username, discord_name)
        VALUES (NEW.discord_id, NEW.username, NEW.discord_name);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger pour capturer les changements
DROP TRIGGER IF EXISTS trigger_username_change ON user_profile;
CREATE TRIGGER trigger_username_change
    AFTER INSERT OR UPDATE OF username ON user_profile
    FOR EACH ROW
    EXECUTE FUNCTION log_username_change();

-- Migrer les usernames existants dans l'historique
INSERT INTO username_history (discord_id, username, discord_name, changed_at)
SELECT discord_id, username, discord_name, COALESCE(creation_date, CURRENT_TIMESTAMP)
FROM user_profile
WHERE discord_id IS NOT NULL
ON CONFLICT DO NOTHING;

COMMENT ON TABLE username_history IS 'Historique des changements de username Discord';
