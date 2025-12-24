"""
Modèle UserProfile - Représente le profil d'un membre Discord.
"""

import asyncpg
from datetime import datetime
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger

logger = get_logger("models.user_profile")


class UserProfile:
    """Représente le profil d'un utilisateur Discord."""

    def __init__(self, username: str, db_connection, discord_name: str = None,
                 last_connection: datetime = None):
        self.username = username
        self.db_connection = db_connection
        self.discord_name = discord_name
        self.last_connection = last_connection

        # Champs existants
        self.game_name = None  # Deprecated - utiliser players
        self.language = None
        self.localisation = None
        self.latitude = None
        self.longitude = None
        self.creation_date = None

        # Nouveaux champs
        self.charte_validated = False
        self.approval_status = "pending"  # pending, approved, refused

    @classmethod
    async def get_or_create_user(cls, username: str, db_connection, member=None) -> 'UserProfile':
        """Récupère ou crée un profil utilisateur."""
        logger.debug(f"Vérification du profil pour {username}")

        query = """
        SELECT username, discord_name, last_connection, charte_validated, approval_status
        FROM user_profile WHERE username = $1
        """
        existing_user = await db_connection.fetchrow(query, username)

        if existing_user:
            logger.debug(f"Profil existant pour {username}")

            # Vérifier si le nom d'affichage a changé
            if member and existing_user['discord_name'] != member.display_name:
                update_query = """
                UPDATE user_profile SET discord_name = $1 WHERE username = $2
                """
                await db_connection.execute(update_query, member.display_name, username)
                logger.debug(f"Nom d'affichage mis à jour pour {username}")

            profile = cls(
                username,
                db_connection,
                member.display_name if member else existing_user['discord_name'],
                existing_user['last_connection']
            )
            profile.charte_validated = existing_user.get('charte_validated', False)
            profile.approval_status = existing_user.get('approval_status', 'pending')
            return profile

        # Créer un nouveau profil
        insert_query = """
        INSERT INTO user_profile (username, discord_name, last_connection, charte_validated, approval_status)
        VALUES ($1, $2, $3, FALSE, 'pending')
        """
        await db_connection.execute(
            insert_query,
            username,
            member.display_name if member else None,
            datetime.now()
        )
        logger.info(f"Nouveau profil créé: {username}")

        # Envoyer un message de bienvenue
        if member:
            try:
                await member.send(
                    f"Bienvenue {username} ! Ton profil a été créé.\n"
                    f"Utilise `!inscription` pour compléter ton inscription."
                )
                logger.debug(f"Message de bienvenue envoyé à {username}")
            except Exception as e:
                logger.warning(f"Impossible d'envoyer le DM à {username}: {e}")

        profile = cls(
            username,
            db_connection,
            member.display_name if member else None,
            datetime.now()
        )
        profile.charte_validated = False
        profile.approval_status = "pending"
        return profile

    async def load_from_db(self) -> None:
        """Charge les informations complètes depuis la base de données."""
        query = """
        SELECT game_name, language, localisation, latitude, longitude,
               discord_name, last_connection, creation_date,
               charte_validated, approval_status
        FROM user_profile WHERE username = $1
        """
        try:
            result = await self.db_connection.fetchrow(query, self.username)
            if result:
                self.game_name = result["game_name"]
                self.language = result["language"]
                self.localisation = result["localisation"]
                self.latitude = result["latitude"]
                self.longitude = result["longitude"]
                self.discord_name = result["discord_name"]
                self.last_connection = result["last_connection"]
                self.creation_date = result["creation_date"]
                self.charte_validated = result.get("charte_validated", False)
                self.approval_status = result.get("approval_status", "pending")
        except Exception as e:
            logger.error(f"Erreur chargement profil {self.username}: {e}")

    async def save(self) -> None:
        """Enregistre les modifications dans la base de données."""
        query = """
        UPDATE user_profile
        SET discord_name = $1, last_connection = $2
        WHERE username = $3
        """
        try:
            await self.db_connection.execute(
                query, self.discord_name, self.last_connection, self.username
            )
            logger.debug(f"Profil mis à jour pour {self.username}")
        except Exception as e:
            logger.error(f"Erreur mise à jour profil {self.username}: {e}")

    async def validate_charte(self) -> None:
        """Marque la charte comme validée."""
        query = """
        UPDATE user_profile SET charte_validated = TRUE WHERE username = $1
        """
        await self.db_connection.execute(query, self.username)
        self.charte_validated = True
        logger.info(f"Charte validée pour {self.username}")

    async def set_location(self, localisation: str, latitude: float, longitude: float) -> None:
        """Définit la localisation du membre."""
        query = """
        UPDATE user_profile
        SET localisation = $1, latitude = $2, longitude = $3
        WHERE username = $4
        """
        await self.db_connection.execute(query, localisation, latitude, longitude, self.username)
        self.localisation = localisation
        self.latitude = latitude
        self.longitude = longitude
        logger.info(f"Localisation définie pour {self.username}: {localisation}")

    async def clear_location(self) -> None:
        """Supprime la localisation du membre."""
        query = """
        UPDATE user_profile
        SET localisation = NULL, latitude = NULL, longitude = NULL
        WHERE username = $1
        """
        await self.db_connection.execute(query, self.username)
        self.localisation = None
        self.latitude = None
        self.longitude = None
        logger.info(f"Localisation supprimée pour {self.username}")

    def is_registration_complete(self) -> bool:
        """Vérifie si l'inscription est complète (charte validée)."""
        return self.charte_validated

    def is_approved(self) -> bool:
        """Vérifie si le membre est approuvé par un sage."""
        return self.approval_status == "approved"

    def is_pending(self) -> bool:
        """Vérifie si le membre est en attente d'approbation."""
        return self.approval_status == "pending"

    def get_status_display(self) -> str:
        """Retourne un affichage du statut pour les commandes."""
        charte_status = "Validée" if self.charte_validated else "Non validée"
        approval_map = {
            "pending": "En attente",
            "approved": "Approuvé",
            "refused": "Refusé"
        }
        approval_display = approval_map.get(self.approval_status, self.approval_status)

        return f"Charte: {charte_status} | Statut: {approval_display}"

    def __str__(self) -> str:
        return (
            f"UserProfile(username={self.username}, discord_name={self.discord_name}, "
            f"charte_validated={self.charte_validated}, approval_status={self.approval_status})"
        )
