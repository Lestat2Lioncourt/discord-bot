-- Migration 008: Table player_equipment pour les cartes equipees
-- Chaque capture de stats peut avoir jusqu'a 6 equipements

CREATE TABLE IF NOT EXISTS player_equipment (
    id SERIAL PRIMARY KEY,
    stats_id INTEGER NOT NULL REFERENCES player_stats(id) ON DELETE CASCADE,
    slot INTEGER NOT NULL,          -- 1=Raquette, 2=Grip, 3=Chaussures, 4=Poignet, 5=Nutrition, 6=Entrainement
    card_name VARCHAR(50),          -- Le marteau, Le koi, L'enclume...
    card_level INTEGER,             -- 12, 13...
    UNIQUE(stats_id, slot)          -- Un seul equipement par slot par capture
);

-- Index pour les requetes
CREATE INDEX IF NOT EXISTS idx_player_equipment_stats_id ON player_equipment(stats_id);
CREATE INDEX IF NOT EXISTS idx_player_equipment_card_name ON player_equipment(card_name);
