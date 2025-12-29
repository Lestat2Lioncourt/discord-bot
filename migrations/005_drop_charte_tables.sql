-- Migration 005: Suppression des tables Charte et Validation_charte (obsoletes)
-- Le nouveau systeme utilise uniquement user_profile.charte_validated

-- Supprimer les contraintes de cle etrangere d'abord
ALTER TABLE IF EXISTS validation_charte
    DROP CONSTRAINT IF EXISTS validation_charte_id_clause_fkey;

ALTER TABLE IF EXISTS validation_charte
    DROP CONSTRAINT IF EXISTS validation_charte_username_fkey;

-- Supprimer les index
DROP INDEX IF EXISTS idx_validation_charte_username;
DROP INDEX IF EXISTS idx_validation_charte_clause;

-- Supprimer les tables
DROP TABLE IF EXISTS validation_charte CASCADE;
DROP TABLE IF EXISTS charte CASCADE;

-- Nettoyage des vues eventuelles
DROP VIEW IF EXISTS vvalidation_charte;
