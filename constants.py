"""
Constantes globales du bot Discord This Is PSG.

Ce fichier centralise toutes les valeurs constantes utilisees dans le projet
pour eviter les valeurs hardcodees et faciliter la maintenance.
"""


# =============================================================================
# Statuts d'approbation
# =============================================================================
class ApprovalStatus:
    """Statuts possibles pour l'approbation d'un membre."""
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"
    DELETED = "deleted"  # Soft delete (RGPD) - profil vide mais ID conserve


# =============================================================================
# Equipes
# =============================================================================
class Teams:
    """Configuration des equipes."""
    TEAM1_ID = 1
    TEAM1_NAME = "This Is PSG"
    TEAM2_ID = 2
    TEAM2_NAME = "This Is PSG 2"

    @classmethod
    def get_name(cls, team_id: int) -> str:
        """Retourne le nom d'une equipe par son ID."""
        return {
            cls.TEAM1_ID: cls.TEAM1_NAME,
            cls.TEAM2_ID: cls.TEAM2_NAME,
        }.get(team_id, "Unknown")


# =============================================================================
# Types de build (gameplay) Tennis Clash
# =============================================================================
class BuildTypes:
    """Types de build/gameplay pour les joueurs Tennis Clash."""
    SERVICE_VOLEE = "Service-Volee"
    PUISSANCE_EQUILIBREE = "Puissance equilibree"
    PUISSANCE_DESEQUILIBREE = "Puissance desequilibree"

    ALL = [SERVICE_VOLEE, PUISSANCE_EQUILIBREE, PUISSANCE_DESEQUILIBREE]

    @classmethod
    def is_valid(cls, build_type: str) -> bool:
        """Verifie si un type de build est valide."""
        return build_type in cls.ALL


# =============================================================================
# Slots d'equipement Tennis Clash
# =============================================================================
class EquipmentSlots:
    """Les 6 slots d'equipement dans Tennis Clash."""
    RACKET = 1       # Raquette
    GRIP = 2         # Grip
    SHOES = 3        # Chaussures
    WRIST = 4        # Poignet
    NUTRITION = 5    # Nutrition
    TRAINING = 6     # Entrainement

    NAMES = {
        1: "Raquette",
        2: "Grip",
        3: "Chaussures",
        4: "Poignet",
        5: "Nutrition",
        6: "Entrainement",
    }

    @classmethod
    def get_name(cls, slot: int) -> str:
        """Retourne le nom d'un slot."""
        return cls.NAMES.get(slot, f"Slot {slot}")


# =============================================================================
# Timeouts (en secondes) - valeurs depuis config.py
# =============================================================================
from config import (
    TIMEOUT_LANGUAGE_SELECT,
    TIMEOUT_CHARTE_READ,
    TIMEOUT_PLAYER_INPUT,
    TIMEOUT_LOCATION_INPUT,
    TIMEOUT_KEEP_OR_RESET,
    TIMEOUT_LANGUAGE_CHANGE,
    TIMEOUT_GEOCODING,
)


class Timeouts:
    """Timeouts pour les differentes interactions (configurables via .env)."""
    LANGUAGE_SELECT = TIMEOUT_LANGUAGE_SELECT
    CHARTE_READ = TIMEOUT_CHARTE_READ
    PLAYER_INPUT = TIMEOUT_PLAYER_INPUT
    LOCATION_INPUT = TIMEOUT_LOCATION_INPUT
    KEEP_OR_RESET = TIMEOUT_KEEP_OR_RESET
    LANGUAGE_CHANGE = TIMEOUT_LANGUAGE_CHANGE
    GEOCODING = TIMEOUT_GEOCODING
