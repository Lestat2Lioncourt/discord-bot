"""
Modèle UserProfile - Représente le profil d'un membre Discord.

Utilise discord_id (permanent) comme identifiant principal.
Le username est stocké mais mis à jour automatiquement s'il change.
"""

import asyncpg
from datetime import datetime
from typing import Optional

from constants import ApprovalStatus
from utils.logger import get_logger
from utils.cache import profile_cache, invalidate_profile

# Import conditionnel pour eviter erreur si geopy non installe (tests)
try:
    from utils.geocoding import invalidate_cache as invalidate_geocache
except ImportError:
    def invalidate_geocache(location: str) -> bool:
        """Stub si geopy non disponible."""
        return False

logger = get_logger("models.user_profile")


class UserProfile:
    """Représente le profil d'un utilisateur Discord.

    Attributs principaux:
        discord_id: Identifiant Discord permanent
        username: Nom d'utilisateur Discord actuel
        discord_name: Nom d'affichage (display_name)
        language: Langue préférée (FR/EN)
        charte_validated: True si la charte a été acceptée
        approval_status: Statut d'approbation (pending/approved/refused)
        localisation: Adresse saisie par l'utilisateur
        latitude/longitude: Coordonnées GPS
    """

    def __init__(self, discord_id: int, db_connection, username: str = None,
                 discord_name: str = None, last_connection: datetime = None):
        self.discord_id = discord_id
        self.username = username
        self.db_connection = db_connection
        self.discord_name = discord_name
        self.last_connection = last_connection

        # Champs existants (types explicites pour mypy)
        self.language: str = "FR"  # Langue par defaut
        self.localisation: Optional[str] = None
        self.location_display: Optional[str] = None  # Pays/region pour affichage anonymise
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.creation_date: Optional[datetime] = None

        # Nouveaux champs
        self.charte_validated = False
        self.approval_status = ApprovalStatus.PENDING

    @classmethod
    async def get_or_create(cls, member, db_connection) -> 'UserProfile':
        """Récupère ou crée un profil utilisateur par discord_id.

        Si le profil existe, met à jour username/display_name si changés.
        Si un profil existe par username sans discord_id, le migre.

        Args:
            member: Membre Discord (discord.Member)
            db_connection: Connexion asyncpg active

        Returns:
            Instance UserProfile (existante ou nouvellement créée)
        """
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

            # Si le profil etait 'deleted', le reinitialiser pour nouvelle inscription
            was_deleted = existing_user.get('approval_status') == ApprovalStatus.DELETED
            if was_deleted:
                updates.append(f"approval_status = ${param_idx}")
                params.append(ApprovalStatus.PENDING)
                param_idx += 1
                updates.append(f"charte_validated = ${param_idx}")
                params.append(False)
                param_idx += 1
                logger.info(f"Profil 'deleted' reinitialise pour {username}")

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
            # Si etait deleted, utiliser les valeurs reinitialisees
            if was_deleted:
                profile.charte_validated = False
                profile.approval_status = ApprovalStatus.PENDING
            else:
                profile.charte_validated = existing_user.get('charte_validated', False)
                profile.approval_status = existing_user.get('approval_status', ApprovalStatus.PENDING)
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
            profile.approval_status = existing_by_username.get('approval_status', ApprovalStatus.PENDING)
            profile.language = existing_by_username.get('language', 'FR')
            return profile

        # Créer un nouveau profil
        insert_query = f"""
        INSERT INTO user_profile (discord_id, username, discord_name, last_connection,
                                  charte_validated, approval_status)
        VALUES ($1, $2, $3, $4, FALSE, '{ApprovalStatus.PENDING}')
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
        profile.approval_status = ApprovalStatus.PENDING
        return profile

    @classmethod
    async def get_or_create_user(cls, username: str, db_connection, member=None) -> Optional['UserProfile']:
        """Alias de compatibilité pour get_or_create.

        Args:
            username: Nom d'utilisateur (utilisé si member est None)
            db_connection: Connexion asyncpg active
            member: Membre Discord (optionnel, préféré si fourni)

        Returns:
            Instance UserProfile ou None si non trouvé (sans member)
        """
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
            profile.approval_status = row.get('approval_status', ApprovalStatus.PENDING)
            profile.language = row.get('language', 'FR')
            return profile
        return None

    async def load_from_db(self) -> None:
        """Charge tous les champs du profil depuis la base de données.

        Remplit les attributs: language, localisation, latitude, longitude,
        location_display, creation_date, charte_validated, approval_status.
        """
        query = """
        SELECT language, localisation, location_display, latitude, longitude,
               discord_name, last_connection, creation_date,
               charte_validated, approval_status, username
        FROM user_profile WHERE discord_id = $1
        """
        try:
            result = await self.db_connection.fetchrow(query, self.discord_id)
            if result:
                self.language = result.get("language") or "FR"
                self.localisation = result["localisation"]
                self.location_display = result.get("location_display")
                self.latitude = result["latitude"]
                self.longitude = result["longitude"]
                self.discord_name = result["discord_name"]
                self.last_connection = result["last_connection"]
                self.creation_date = result["creation_date"]
                self.charte_validated = result.get("charte_validated", False)
                self.approval_status = result.get("approval_status", ApprovalStatus.PENDING)
                self.username = result["username"]
        except asyncpg.PostgresError as e:
            logger.error(f"Erreur chargement profil discord_id={self.discord_id}: {e}")

    async def save(self) -> None:
        """Sauvegarde discord_name, last_connection et username en base."""
        query = """
        UPDATE user_profile
        SET discord_name = $1, last_connection = $2, username = $3
        WHERE discord_id = $4
        """
        try:
            await self.db_connection.execute(
                query, self.discord_name, self.last_connection, self.username, self.discord_id
            )
            invalidate_profile(self.discord_id)
            logger.debug(f"Profil mis à jour pour discord_id={self.discord_id}")
        except asyncpg.PostgresError as e:
            logger.error(f"Erreur mise à jour profil discord_id={self.discord_id}: {e}")

    async def validate_charte(self) -> None:
        """Marque la charte comme validée."""
        query = "UPDATE user_profile SET charte_validated = TRUE WHERE discord_id = $1"
        await self.db_connection.execute(query, self.discord_id)
        self.charte_validated = True
        invalidate_profile(self.discord_id)
        logger.info(f"Charte validée pour {self.username}")

    async def set_location(self, localisation: str, latitude: float, longitude: float,
                           location_display: str = None) -> None:
        """Définit la localisation du membre.

        Args:
            localisation: Adresse complete saisie par l'utilisateur
            latitude: Latitude GPS
            longitude: Longitude GPS
            location_display: Affichage anonymise (pays/region) pour profil-admin
        """
        # Invalider l'ancien cache geocoding si une ancienne localisation existait
        if self.localisation:
            invalidate_geocache(self.localisation)

        query = """
        UPDATE user_profile
        SET localisation = $1, latitude = $2, longitude = $3, location_display = $4
        WHERE discord_id = $5
        """
        await self.db_connection.execute(query, localisation, latitude, longitude,
                                          location_display, self.discord_id)
        self.localisation = localisation
        self.latitude = latitude
        self.longitude = longitude
        self.location_display = location_display
        invalidate_profile(self.discord_id)
        logger.info(f"Localisation définie pour {self.username}: {location_display or localisation}")

    async def clear_location(self, conn=None) -> None:
        """Supprime la localisation du membre.

        Args:
            conn: Connexion existante (pour transactions)
        """
        # Invalider le cache geocoding avant suppression
        if self.localisation:
            invalidate_geocache(self.localisation)

        query = """
        UPDATE user_profile
        SET localisation = NULL, latitude = NULL, longitude = NULL
        WHERE discord_id = $1
        """
        connection = conn or self.db_connection
        await connection.execute(query, self.discord_id)
        self.localisation = None
        self.latitude = None
        self.longitude = None
        invalidate_profile(self.discord_id)
        logger.info(f"Localisation supprimée pour {self.username}")

    async def set_language(self, language: str) -> None:
        """Définit la langue préférée du membre.

        Args:
            language: Code langue (FR ou EN, normalisé en majuscules)
        """
        language = language.upper() if language else "FR"
        if language not in ("FR", "EN"):
            language = "FR"
        query = "UPDATE user_profile SET language = $1 WHERE discord_id = $2"
        await self.db_connection.execute(query, language, self.discord_id)
        self.language = language
        invalidate_profile(self.discord_id)
        logger.debug(f"Langue definie pour {self.username}: {language}")

    def is_registration_complete(self) -> bool:
        """Vérifie si l'inscription est complète (charte validée)."""
        return self.charte_validated

    def is_approved(self) -> bool:
        """Vérifie si le membre est approuvé par un sage."""
        return self.approval_status == ApprovalStatus.APPROVED

    def is_pending(self) -> bool:
        """Vérifie si le membre est en attente d'approbation."""
        return self.approval_status == ApprovalStatus.PENDING

    def get_status_display(self) -> str:
        """Retourne un affichage du statut pour les commandes."""
        charte_status = "Validée" if self.charte_validated else "Non validée"
        approval_map = {
            ApprovalStatus.PENDING: "En attente",
            ApprovalStatus.APPROVED: "Approuvé",
            ApprovalStatus.REFUSED: "Refusé"
        }
        approval_display = approval_map.get(self.approval_status, self.approval_status)
        return f"Charte: {charte_status} | Statut: {approval_display}"

    async def approve(self, conn=None) -> None:
        """Approuve le membre.

        Args:
            conn: Connexion asyncpg optionnelle (pour transactions)
        """
        query = "UPDATE user_profile SET approval_status = $1 WHERE discord_id = $2"
        connection = conn or self.db_connection
        await connection.execute(query, ApprovalStatus.APPROVED, self.discord_id)
        self.approval_status = ApprovalStatus.APPROVED
        invalidate_profile(self.discord_id)
        logger.info(f"Membre {self.username} approuvé")

    async def refuse(self, conn=None) -> None:
        """Refuse le membre.

        Args:
            conn: Connexion asyncpg optionnelle (pour transactions)
        """
        query = "UPDATE user_profile SET approval_status = $1 WHERE discord_id = $2"
        connection = conn or self.db_connection
        await connection.execute(query, ApprovalStatus.REFUSED, self.discord_id)
        self.approval_status = ApprovalStatus.REFUSED
        invalidate_profile(self.discord_id)
        logger.info(f"Membre {self.username} refusé")

    async def reset(self, conn=None) -> None:
        """Reinitialise le profil pour permettre une nouvelle inscription.

        Args:
            conn: Connexion asyncpg optionnelle (pour transactions)
        """
        query = """
        UPDATE user_profile
        SET approval_status = $1, charte_validated = FALSE
        WHERE discord_id = $2
        """
        connection = conn or self.db_connection
        await connection.execute(query, ApprovalStatus.PENDING, self.discord_id)
        self.approval_status = ApprovalStatus.PENDING
        self.charte_validated = False
        invalidate_profile(self.discord_id)
        logger.info(f"Profil {self.username} reinitialise")

    @staticmethod
    async def delete_all_data(db_pool, discord_id: int, username: str) -> dict:
        """Soft delete: vide les donnees mais conserve discord_id pour tracabilite.

        Le profil est conserve avec approval_status='deleted' pour:
        - Detecter si l'utilisateur revient avec un autre username
        - Conserver une trace de la suppression

        Args:
            db_pool: Pool de connexions asyncpg
            discord_id: Identifiant Discord
            username: Nom d'utilisateur

        Returns:
            Dict avec le nombre d'elements supprimes par table
        """
        from constants import ApprovalStatus

        results = {
            "players": 0,
            "audit_log": 0,
            "username_history": 0,
            "user_profile": "soft_deleted"
        }

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Supprimer les joueurs
                result = await conn.execute(
                    "DELETE FROM players WHERE member_username = $1", username
                )
                results["players"] = int(result.split()[-1]) if result else 0

                # Supprimer les logs d'audit
                result = await conn.execute(
                    "DELETE FROM audit_log WHERE target_username = $1", username
                )
                results["audit_log"] = int(result.split()[-1]) if result else 0

                # Supprimer l'historique des pseudos
                result = await conn.execute(
                    "DELETE FROM username_history WHERE discord_id = $1", discord_id
                )
                results["username_history"] = int(result.split()[-1]) if result else 0

                # Soft delete: vider les donnees sensibles, garder discord_id
                await conn.execute("""
                    UPDATE user_profile SET
                        approval_status = $1,
                        localisation = NULL,
                        latitude = NULL,
                        longitude = NULL,
                        location_display = NULL,
                        charte_validated = FALSE,
                        language = 'FR'
                    WHERE discord_id = $2
                """, ApprovalStatus.DELETED, discord_id)

        # Invalider le cache
        invalidate_profile(discord_id)
        logger.info(f"Soft delete pour {username} (discord_id={discord_id}): {results}")

        return results

    @staticmethod
    async def get_pending_members(db_pool) -> list:
        """Récupère les membres en attente avec charte validée.

        Args:
            db_pool: Pool de connexions asyncpg

        Returns:
            Liste de dicts avec discord_id, username, discord_name, etc.
        """
        query = f"""
        SELECT discord_id, username, discord_name, charte_validated, creation_date
        FROM user_profile
        WHERE approval_status = '{ApprovalStatus.PENDING}' AND charte_validated = TRUE
        ORDER BY creation_date DESC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    @classmethod
    async def get_by_discord_id(cls, db_connection, discord_id: int) -> Optional['UserProfile']:
        """Récupère un profil par son identifiant Discord.

        Args:
            db_connection: Connexion asyncpg active
            discord_id: Identifiant Discord (snowflake)

        Returns:
            Instance UserProfile ou None si non trouvé
        """
        # Verifier le cache
        cache_key = f"profile:{discord_id}"
        cached = profile_cache.get(cache_key)
        if cached is not None:
            # Mettre a jour la connexion DB (peut avoir change)
            cached.db_connection = db_connection
            return cached

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
        profile.approval_status = row.get('approval_status', ApprovalStatus.PENDING)
        profile.language = row.get('language', 'FR')

        # Stocker en cache
        profile_cache.set(cache_key, profile)
        return profile

    @classmethod
    async def get_by_username(cls, db_connection, username: str) -> Optional['UserProfile']:
        """Récupère un profil par son nom d'utilisateur.

        Args:
            db_connection: Connexion asyncpg active
            username: Nom d'utilisateur (insensible à la casse)

        Returns:
            Instance UserProfile ou None si non trouvé
        """
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
        profile.approval_status = row.get('approval_status', ApprovalStatus.PENDING)
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
        """Récupère l'historique des changements de username.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_id: Identifiant Discord

        Returns:
            Liste de dicts {username, discord_name, changed_at} triée par date décroissante
        """
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
        """Vérifie si un membre revient avec un nouveau username.

        Notifie dès que le username a changé, peu importe le statut précédent.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_id: Identifiant Discord
            current_username: Username actuel du membre

        Returns:
            Dict avec old_username, old_discord_name, last_seen, previous_status
            ou None si même username ou nouveau membre
        """
        async with db_pool.acquire() as conn:
            # Chercher le profil existant avec un username different
            query = """
            SELECT username, discord_name, last_connection, approval_status, charte_validated
            FROM user_profile
            WHERE discord_id = $1
              AND LOWER(username) != LOWER($2)
            """
            row = await conn.fetchrow(query, discord_id, current_username)

            if row:
                return {
                    "old_username": row['username'],
                    "old_discord_name": row['discord_name'],
                    "last_seen": row['last_connection'],
                    "previous_status": row['approval_status'],
                    "had_validated_charte": row['charte_validated'] or False
                }

            return None
