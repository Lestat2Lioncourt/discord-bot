-- ============================================================================
-- Migration 002: Utiliser discord_id comme identifiant principal
-- ============================================================================
--
-- Objectif: Remplacer username par discord_id pour identifier les membres
-- Raison: Le username Discord peut changer, pas le discord_id
--
-- IMPORTANT: Executer ce script APRES avoir lance le bot une fois pour
-- remplir les discord_id existants via la commande !migration-id
-- ============================================================================

-- 1. Ajouter la colonne discord_id a user_profile
ALTER TABLE user_profile
ADD COLUMN IF NOT EXISTS discord_id BIGINT;

-- 2. Creer un index unique sur discord_id (une fois rempli)
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profile_discord_id ON user_profile(discord_id);

-- 3. Ajouter discord_id a la table players
ALTER TABLE players
ADD COLUMN IF NOT EXISTS member_discord_id BIGINT;

-- ============================================================================
-- ETAPE MANUELLE: Lancer le bot et executer !migration-id pour remplir les IDs
-- ============================================================================

-- 4. Une fois les IDs remplis, executer ces commandes:
--
-- -- Rendre discord_id NOT NULL
-- ALTER TABLE user_profile ALTER COLUMN discord_id SET NOT NULL;
--
-- -- Ajouter la contrainte unique
-- ALTER TABLE user_profile ADD CONSTRAINT user_profile_discord_id_unique UNIQUE (discord_id);
--
-- -- Mettre a jour la reference dans players
-- UPDATE players p
-- SET member_discord_id = u.discord_id
-- FROM user_profile u
-- WHERE p.member_username = u.username;
--
-- -- Ajouter la foreign key
-- ALTER TABLE players
-- ADD CONSTRAINT fk_players_discord_id
-- FOREIGN KEY (member_discord_id) REFERENCES user_profile(discord_id);

-- ============================================================================
-- NOTE: On garde username comme colonne secondaire (mise a jour auto)
-- ============================================================================
