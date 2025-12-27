"""
Modèle UserProfile - Représente le profil d'un membre Discord.

Utilise discord_id (permanent) comme identifiant principal.
Le username est stocké mais mis à jour automatiquement s'il change.
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

    def __init__(self, discord_id: int, db_connection, username: str = None,
                 discord_name: str = None, last_connection: datetime = None):
        self.discord_id = discord_id
        self.username = username
        self.db_connection = db_connection
        self.discord_name = discord_name
        self.last_connection = last_connection

        # Champs existants
        self.language = "FR"  # Langue par defaut
        self.localisation = None
        self.latitude = None
        self.longitude = None
        self.creation_date = None

        # Nouveaux champs
        self.charte_validated = False
        self.approval_status = "pending"  # pending, approved, refused

    @classmethod
    async def get_or_create(cls, member, db_connection) -> 'UserProfile':
        """Récupère ou crée un profil utilisateur par discord_id."""
        discord_id = member.id
        username = member.name
        display_name = member.display_name

        logger.debug(f"Vérification du profil pour discord_id={discord_id}")

        # Chercher par discord_id d'abord
        query = """
        SELECT discord_id, username, discord_name, last_connection,
               charte_validated, approval_status, language
        FROM user_profile WHERE discord_id = $1
        """
        existing_user = await db_connection.fetchrow(query, discord_id)

        if existing_user:
            logger.debug(f"Profil existant pour discord_id={discord_id}")

            # Mettre à jour username et display_name si changés
            updates = []
            params = []
            param_idx = 1

            if existing_user['username'] != username:
                updates.append(f"username = ${param_idx}")
                params.append(username)
                param_idx += 1
                logger.info(f"Username mis à jour: {existing_user['username']} -> {username}")

                # Mettre à jour aussi dans la table players
                await db_connection.execute(
                    "UPDATE players SET member_username = $1 WHERE member_username = $2",
                    username, existing_user['username']
                )
                logger.info(f"Players mis à jour pour le nouveau username")

            if existing_user['discord_name'] != display_name:
                updates.append(f"discord_name = ${param_idx}")
                params.append(display_name)
                param_idx += 1

            if updates:
                params.append(discord_id)
                update_query = f"UPDATE user_profile SET {', '.join(updates)} WHERE discord_id = ${param_idx}"
                await db_connection.execute(update_query, *params)

            profile = cls(
                discord_id,
                db_connection,
                username,
                display_name,
                existing_user['last_connection']
            )
            profile.charte_validated = existing_user.get('charte_validated', False)
            profile.approval_status = existing_user.get('approval_status', 'pending')
            profile.language = existing_user.get('language', 'FR')
            return profile

        # Vérifier si un profil existe avec cet username (migration)
        query_by_username = """
        SELECT discord_id, username, discord_name, last_connection,
               charte_validated, approval_status, language
        FROM user_profile WHERE username = $1 AND discord_id IS NULL
        """
        existing_by_username = await db_connection.fetchrow(query_by_username, username)

        if existing_by_username:
            # Migrer le profil existant vers discord_id
            logger.info(f"Migration du profil {username} vers discord_id={discord_id}")
            update_query = """
            UPDATE user_profile SET discord_id = $1, discord_name = $2 WHERE username = $3
            """
            await db_connection.execute(update_query, discord_id, display_name, username)

            profile = cls(
                discord_id,
                db_connection,
                username,
                display_name,
                existing_by_username['last_connection']
            )
            profile.charte_validated = existing_by_username.get('charte_validated', False)
            profile.approval_status = existing_by_username.get('approval_status', 'pending')
            profile.language = existing_by_username.get('language', 'FR')
            return profile

        # Créer un nouveau profil
        insert_query = """
        INSERT INTO user_profile (discord_id, username, discord_name, last_connection,
                                  charte_validated, approval_status)
        VALUES ($1, $2, $3, $4, FALSE, 'pending')
        """
        await db_connection.execute(
            insert_query,
            discord_id,
            username,
            display_name,
            datetime.now()
        )
        logger.info(f"Nouveau profil créé: {username} (discord_id={discord_id})")

        profile = cls(
            discord_id,
            db_connection,
            username,
            display_name,
            datetime.now()
        )
        profile.charte_validated = False
        profile.approval_status = "pending"
        return profile

    # Alias pour compatibilité avec l'ancien code
    @classmethod
    async def get_or_create_user(cls, username: str, db_connection, member=None) -> 'UserProfile':
        """Compatibilité: utilise get_or_create avec le membre."""
        if member:
            return await cls.get_or_create(member, db_connection)

        # Fallback: chercher par username si pas de membre
        query = """
        SELECT discord_id, username, discord_name, last_connection,
               charte_validated, approval_status, language
        FROM user_profile WHERE username = $1
        """
        row = await db_connection.fetchrow(query, username)
        if row:
            profile = cls(
                row['discord_id'],
                db_connection,
                row['username'],
                row['discord_name'],
                row['last_connection']
            )
            profile.charte_validated = row.get('charte_validated', False)
            profile.approval_status = row.get('approval_status', 'pending')
            profile.language = row.get('language', 'FR')
            return profile
        return None

    async def load_from_db(self) -> None:
        """Charge les informations complètes depuis la base de données."""
        query = """
        SELECT language, localisation, latitude, longitude,
               discord_name, last_connection, creation_date,
               charte_validated, approval_status, username
        FROM user_profile WHERE discord_id = $1
        """
        try:
            result = await self.db_connection.fetchrow(query, self.discord_id)
            if result:
                self.language = result.get("language") or "FR"
                self.localisation = result["localisation"]
                self.latitude = result["latitude"]
                self.longitude = result["longitude"]
                self.discord_name = result["discord_name"]
                self.last_connection = result["last_connection"]
                self.creation_date = result["creation_date"]
                self.charte_validated = result.get("charte_validated", False)
                self.approval_status = result.get("approval_status", "pending")
                self.username = result["username"]
        except Exception as e:
            logger.error(f"Erreur chargement profil discord_id={self.discord_id}: {e}")

    async def save(self) -> None:
        """Enregistre les modifications dans la base de données."""
        query = """
        UPDATE user_profile
        SET discord_name = $1, last_connection = $2, username = $3
        WHERE discord_id = $4
        """
        try:
            await self.db_connection.execute(
                query, self.discord_name, self.last_connection, self.username, self.discord_id
            )
            logger.debug(f"Profil mis à jour pour discord_id={self.discord_id}")
        except Exception as e:
            logger.error(f"Erreur mise à jour profil discord_id={self.discord_id}: {e}")

    async def validate_charte(self) -> None:
        """Marque la charte comme validée."""
        query = "UPDATE user_profile SET charte_validated = TRUE WHERE discord_id = $1"
        await self.db_connection.execute(query, self.discord_id)
        self.charte_validated = True
        logger.info(f"Charte validée pour {self.username}")

    async def set_location(self, localisation: str, latitude: float, longitude: float) -> None:
        """Définit la localisation du membre."""
        query = """
        UPDATE user_profile
        SET localisation = $1, latitude = $2, longitude = $3
        WHERE discord_id = $4
        """
        await self.db_connection.execute(query, localisation, latitude, longitude, self.discord_id)
        self.localisation = localisation
        self.latitude = latitude
        self.longitude = longitude
        logger.info(f"Localisation définie pour {self.username}: {localisation}")

    async def clear_location(self) -> None:
        """Supprime la localisation du membre."""
        query = """
        UPDATE user_profile
        SET localisation = NULL, latitude = NULL, longitude = NULL
        WHERE discord_id = $1
        """
        await self.db_connection.execute(query, self.discord_id)
        self.localisation = None
        self.latitude = None
        self.longitude = None
        logger.info(f"Localisation supprimée pour {self.username}")

    async def set_language(self, language: str) -> None:
        """Definit la langue du membre."""
        language = language.upper() if language else "FR"
        if language not in ("FR", "EN"):
            language = "FR"
        query = "UPDATE user_profile SET language = $1 WHERE discord_id = $2"
        await self.db_connection.execute(query, language, self.discord_id)
        self.language = language
        logger.debug(f"Langue definie pour {self.username}: {language}")

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

    async def approve(self) -> None:
        """Approuve le membre."""
        query = "UPDATE user_profile SET approval_status = 'approved' WHERE discord_id = $1"
        await self.db_connection.execute(query, self.discord_id)
        self.approval_status = "approved"
        logger.info(f"Membre {self.username} approuvé")

    async def refuse(self) -> None:
        """Refuse le membre."""
        query = "UPDATE user_profile SET approval_status = 'refused' WHERE discord_id = $1"
        await self.db_connection.execute(query, self.discord_id)
        self.approval_status = "refused"
        logger.info(f"Membre {self.username} refusé")

    async def reset(self) -> None:
        """Reinitialise le profil pour permettre une nouvelle inscription."""
        query = """
        UPDATE user_profile
        SET approval_status = 'pending', charte_validated = FALSE
        WHERE discord_id = $1
        """
        await self.db_connection.execute(query, self.discord_id)
        self.approval_status = "pending"
        self.charte_validated = False
        logger.info(f"Profil {self.username} reinitialise")

    @staticmethod
    async def get_pending_members(db_pool) -> list:
        """Récupère tous les membres en attente d'approbation."""
        query = """
        SELECT discord_id, username, discord_name, charte_validated, creation_date
        FROM user_profile
        WHERE approval_status = 'pending' AND charte_validated = TRUE
        ORDER BY creation_date DESC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    @classmethod
    async def get_by_discord_id(cls, db_connection, discord_id: int) -> Optional['UserProfile']:
        """Récupère un profil par son discord_id."""
        query = """
        SELECT discord_id, username, discord_name, last_connection,
               charte_validated, approval_status, language
        FROM user_profile WHERE discord_id = $1
        """
        row = await db_connection.fetchrow(query, discord_id)
        if not row:
            return None

        profile = cls(
            row['discord_id'],
            db_connection,
            row['username'],
            row['discord_name'],
            row['last_connection']
        )
        profile.charte_validated = row.get('charte_validated', False)
        profile.approval_status = row.get('approval_status', 'pending')
        profile.language = row.get('language', 'FR')
        return profile

    @classmethod
    async def get_by_username(cls, db_connection, username: str) -> Optional['UserProfile']:
        """Récupère un profil par son username."""
        query = """
        SELECT discord_id, username, discord_name, last_connection,
               charte_validated, approval_status, language
        FROM user_profile WHERE LOWER(username) = LOWER($1)
        """
        row = await db_connection.fetchrow(query, username)
        if not row:
            return None

        profile = cls(
            row['discord_id'],
            db_connection,
            row['username'],
            row['discord_name'],
            row['last_connection']
        )
        profile.charte_validated = row.get('charte_validated', False)
        profile.approval_status = row.get('approval_status', 'pending')
        profile.language = row.get('language', 'FR')
        return profile

    def __str__(self) -> str:
        return (
            f"UserProfile(discord_id={self.discord_id}, username={self.username}, "
            f"discord_name={self.discord_name}, charte_validated={self.charte_validated}, "
            f"approval_status={self.approval_status})"
        )

    @staticmethod
    async def get_username_history(db_pool, discord_id: int) -> list:
        """Recupere l'historique des usernames pour un discord_id."""
        query = """
        SELECT username, discord_name, changed_at
        FROM username_history
        WHERE discord_id = $1
        ORDER BY changed_at DESC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, discord_id)
            return [dict(row) for row in rows]

    @staticmethod
    async def check_returning_member(db_pool, discord_id: int, current_username: str) -> Optional[dict]:
        """
        Verifie si un membre est un 'revenant' (ancien membre avec nouveau username).

        Retourne un dict avec les infos si c'est un revenant, None sinon.
        """
        async with db_pool.acquire() as conn:
            # Verifier si ce discord_id a deja un historique
            query = """
            SELECT username, discord_name, changed_at
            FROM username_history
            WHERE discord_id = $1 AND LOWER(username) != LOWER($2)
            ORDER BY changed_at DESC
            LIMIT 1
            """
            row = await conn.fetchrow(query, discord_id, current_username)

            if row:
                # C'est un revenant - recuperer aussi le statut precedent
                status_query = """
                SELECT approval_status, charte_validated
                FROM user_profile
                WHERE discord_id = $1
                """
                status = await conn.fetchrow(status_query, discord_id)

                return {
                    "old_username": row['username'],
                    "old_discord_name": row['discord_name'],
                    "last_seen": row['changed_at'],
                    "previous_status": status['approval_status'] if status else None,
                    "had_validated_charte": status['charte_validated'] if status else False
                }

            return None
