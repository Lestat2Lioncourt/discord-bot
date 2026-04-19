-- Migration 010: Suppression de la contrainte UNIQUE sur discord_name
--
-- Raison : Discord n'impose pas l'unicite des display_names. Deux utilisateurs
-- peuvent avoir le meme display_name. La contrainte UNIQUE sur user_profile.discord_name
-- empechait donc l'inscription d'un nouveau membre si un ancien membre (meme parti)
-- avait deja ce display_name.

ALTER TABLE user_profile DROP CONSTRAINT IF EXISTS unique_discord_name;
