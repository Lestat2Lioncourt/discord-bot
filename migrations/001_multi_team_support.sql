-- =============================================================================
-- Migration 001: Support multi-teams et multi-joueurs
-- Date: 2024-12
-- Description:
--   - Ajoute la table teams (PSG, PSG2)
--   - Ajoute la table players (joueurs in-game liés aux membres)
--   - Ajoute la table member_approval (validation par les sages)
--   - Modifie user_profile (charte_validated, approval_status)
--   - Migre les données existantes
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. Ajouter contrainte unique sur user_profile.username (requis pour FK)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'user_profile_username_unique'
    ) THEN
        ALTER TABLE user_profile ADD CONSTRAINT user_profile_username_unique UNIQUE (username);
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 1. Créer la table teams
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Insérer les teams initiales
INSERT INTO teams (name) VALUES ('This Is PSG'), ('This Is PSG 2')
ON CONFLICT (name) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 2. Créer la table players
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    id SERIAL PRIMARY KEY,
    member_username VARCHAR(100) NOT NULL,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    player_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_member FOREIGN KEY (member_username)
        REFERENCES user_profile(username) ON DELETE CASCADE,
    CONSTRAINT unique_player_per_team UNIQUE (team_id, player_name)
);

-- Index pour les recherches fréquentes
CREATE INDEX IF NOT EXISTS idx_players_member ON players(member_username);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);

-- -----------------------------------------------------------------------------
-- 3. Créer la table member_approval
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member_approval (
    id SERIAL PRIMARY KEY,
    member_username VARCHAR(100) NOT NULL,
    sage_username VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    CONSTRAINT fk_member_approval FOREIGN KEY (member_username)
        REFERENCES user_profile(username) ON DELETE CASCADE,
    CONSTRAINT chk_status CHECK (status IN ('pending', 'approved', 'refused'))
);

CREATE INDEX IF NOT EXISTS idx_approval_member ON member_approval(member_username);
CREATE INDEX IF NOT EXISTS idx_approval_status ON member_approval(status);

-- -----------------------------------------------------------------------------
-- 4. Modifier user_profile
-- -----------------------------------------------------------------------------
-- Ajouter les nouvelles colonnes si elles n'existent pas
DO $$
BEGIN
    -- Ajouter charte_validated
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_profile' AND column_name = 'charte_validated'
    ) THEN
        ALTER TABLE user_profile ADD COLUMN charte_validated BOOLEAN DEFAULT FALSE;
    END IF;

    -- Ajouter approval_status
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_profile' AND column_name = 'approval_status'
    ) THEN
        ALTER TABLE user_profile ADD COLUMN approval_status VARCHAR(20) DEFAULT 'pending';
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 5. Migrer les données existantes
-- -----------------------------------------------------------------------------

-- 5.1 Migrer game_name vers players (si la colonne existe)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_profile' AND column_name = 'game_name'
    ) THEN
        INSERT INTO players (member_username, team_id, player_name)
        SELECT username, 1, game_name
        FROM user_profile
        WHERE game_name IS NOT NULL
          AND game_name != ''
          AND NOT EXISTS (
              SELECT 1 FROM players p
              WHERE p.member_username = user_profile.username
                AND p.player_name = user_profile.game_name
          );
    END IF;
END $$;

-- 5.2 Migrer validation_charte vers charte_validated (si les tables existent)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'validation_charte')
       AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'charte')
    THEN
        UPDATE user_profile up
        SET charte_validated = TRUE
        WHERE EXISTS (
            SELECT 1 FROM validation_charte vc
            WHERE vc.username = up.username
            GROUP BY vc.username
            HAVING COUNT(*) = (SELECT COUNT(*) FROM charte)
               AND SUM(CASE WHEN vc.validation = 1 THEN 1 ELSE 0 END) = COUNT(*)
        );
    END IF;
END $$;

-- 5.3 Marquer les anciens membres comme approuvés (si charte validée)
UPDATE user_profile
SET approval_status = 'approved'
WHERE charte_validated = TRUE;

-- -----------------------------------------------------------------------------
-- 6. Nettoyage (à exécuter manuellement après vérification)
-- -----------------------------------------------------------------------------
-- DROP VIEW IF EXISTS vvalidation_charte;
-- DROP TABLE IF EXISTS validation_charte;
-- ALTER TABLE user_profile DROP COLUMN IF EXISTS game_name;

-- =============================================================================
-- Vérification post-migration
-- =============================================================================
-- SELECT 'teams' as table_name, COUNT(*) as count FROM teams
-- UNION ALL
-- SELECT 'players', COUNT(*) FROM players
-- UNION ALL
-- SELECT 'member_approval', COUNT(*) FROM member_approval
-- UNION ALL
-- SELECT 'charte_validated=true', COUNT(*) FROM user_profile WHERE charte_validated = TRUE;
