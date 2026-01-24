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
    """Types de build/gameplay pour les joueurs Tennis Clash.

    Le build est maintenant calcule automatiquement a partir des stats.
    """
    # Noms des stats en francais pour l'affichage
    STAT_NAMES = {
        "agility": "Agilite",
        "endurance": "Endurance",
        "serve": "Service",
        "volley": "Volee",
        "forehand": "Coup droit",
        "backhand": "Revers",
    }

    # Profils predefinis (combinaisons connues -> nom du profil)
    # Cle: tuple de stats triees alphabetiquement
    # A completer manuellement apres analyse des builds calcules
    PROFILES = {
        # ("backhand", "forehand", "serve"): "Puissance",
        # ("agility", "endurance"): "Defense",
        # ("serve", "volley"): "Serve-Volee",
    }

    # Seuils pour le calcul automatique
    THRESHOLD_DOMINANT = 0.20   # +20% au-dessus de la moyenne = stat dominante
    THRESHOLD_BALANCED = 0.15  # Si toutes les stats sont a +/-15% = equilibre

    @classmethod
    def calculate(cls, stats: dict) -> str:
        """Calcule automatiquement le type de build a partir des stats.

        Args:
            stats: Dict avec agility, endurance, serve, volley, forehand, backhand

        Returns:
            Nom du build (ex: "Agilite-Volee" ou "Equilibre")
        """
        if not stats:
            return "Inconnu"

        # Recuperer les valeurs des 6 stats
        stat_values = {
            key: stats.get(key, 0) or 0
            for key in cls.STAT_NAMES.keys()
        }

        values = list(stat_values.values())
        if not values or sum(values) == 0:
            return "Inconnu"

        # Calculer la moyenne
        mean = sum(values) / len(values)

        # Calculer l'ecart relatif pour chaque stat
        deviations = {
            key: (value - mean) / mean if mean > 0 else 0
            for key, value in stat_values.items()
        }

        # Verifier si le build est equilibre (toutes les stats a +/-15%)
        if all(abs(dev) <= cls.THRESHOLD_BALANCED for dev in deviations.values()):
            return "Equilibre"

        # Trouver les stats dominantes (+20% au-dessus de la moyenne)
        dominant_stats = [
            key for key, dev in deviations.items()
            if dev >= cls.THRESHOLD_DOMINANT
        ]

        # Trier par valeur decroissante et garder 2-3 max
        dominant_stats.sort(key=lambda k: stat_values[k], reverse=True)
        dominant_stats = dominant_stats[:3]

        if not dominant_stats:
            # Pas de stat vraiment dominante, prendre les 2 plus hautes
            sorted_stats = sorted(stat_values.items(), key=lambda x: x[1], reverse=True)
            dominant_stats = [s[0] for s in sorted_stats[:2]]

        # Verifier si ca correspond a un profil predefini
        profile_key = tuple(sorted(dominant_stats))
        if profile_key in cls.PROFILES:
            return cls.PROFILES[profile_key]

        # Sinon, concatener les noms de stats
        stat_names = [cls.STAT_NAMES[s] for s in dominant_stats]
        return "-".join(stat_names)

    @classmethod
    def is_valid(cls, build_type: str) -> bool:
        """Verifie si un type de build est valide (toujours True maintenant)."""
        return True  # Les builds sont calcules dynamiquement


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
