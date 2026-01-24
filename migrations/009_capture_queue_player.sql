-- Migration 009: Ajout player_id et build_type a capture_queue
-- Le joueur et le build sont maintenant selectionnes AVANT l'analyse

-- Ajout des colonnes
ALTER TABLE capture_queue
ADD COLUMN IF NOT EXISTS player_id INTEGER REFERENCES players(id),
ADD COLUMN IF NOT EXISTS build_type VARCHAR(50);

-- Index pour les requetes par joueur
CREATE INDEX IF NOT EXISTS idx_capture_queue_player_id ON capture_queue(player_id);

-- Commentaires
COMMENT ON COLUMN capture_queue.player_id IS 'ID du joueur associe (selectionne a la soumission)';
COMMENT ON COLUMN capture_queue.build_type IS 'Type de build (main, tour1, tour2, etc.)';
