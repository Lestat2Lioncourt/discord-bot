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
# Timeouts (en secondes)
# =============================================================================
class Timeouts:
    """Timeouts pour les differentes interactions."""
    LANGUAGE_SELECT = 300      # 5 minutes pour choisir la langue
    CHARTE_READ = 600          # 10 minutes pour lire la charte
    PLAYER_INPUT = 120         # 2 minutes pour saisir les joueurs
    LOCATION_INPUT = 120       # 2 minutes pour saisir la localisation
    KEEP_OR_RESET = 300        # 5 minutes pour choisir conserver/effacer
    LANGUAGE_CHANGE = 60       # 1 minute pour le changement de langue (!langue)
    GEOCODING = 10             # 10 secondes pour l'API de geocoding
