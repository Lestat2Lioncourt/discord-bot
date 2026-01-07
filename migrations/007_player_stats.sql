-- Migration 007: Table player_stats pour le suivi des statistiques Tennis Clash
-- Stocke les captures d'ecran analysees par OCR

CREATE TABLE IF NOT EXISTS player_stats (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL,                    -- Membre Discord
    player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,  -- Joueur in-game (nullable si supprime)
    character_name VARCHAR(50) NOT NULL,           -- Nom du personnage (Mei-Li, Ingrid, etc.)
    points INTEGER,                                 -- Trophees (1770, 1777...)
    global_power INTEGER,                           -- Puissance globale
    agility INTEGER,
    endurance INTEGER,
    serve INTEGER,
    volley INTEGER,
    forehand INTEGER,
    backhand INTEGER,
    build_type VARCHAR(50),                         -- Service-Volee, Puissance equilibree, etc.
    comment TEXT,                                   -- Commentaire libre
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index pour les requetes frequentes
CREATE INDEX IF NOT EXISTS idx_player_stats_discord_id ON player_stats(discord_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_player_id ON player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_character ON player_stats(character_name);
CREATE INDEX IF NOT EXISTS idx_player_stats_date ON player_stats(captured_at DESC);
