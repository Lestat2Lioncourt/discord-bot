-- Migration 004: Ajouter champ location_display pour affichage anonymise
-- Ce champ contient uniquement le pays/region, pas l'adresse complete

ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS location_display VARCHAR(100);

-- Mettre a jour les profils existants avec coordonnees (on mettra juste "Localisation definie")
-- Le champ sera mis a jour proprement lors du prochain geocodage
UPDATE user_profile
SET location_display = 'Localisation definie'
WHERE latitude IS NOT NULL AND location_display IS NULL;
