import asyncpg
from typing import Optional, List, Dict, Any

from utils.logger import get_logger

logger = get_logger("utils.database")


class Database:
    """Classe utilitaire pour les opérations base de données courantes.

    Fournit des méthodes simplifiées pour les opérations CRUD sur user_profile.
    Pour les opérations complexes, utiliser directement les modèles (UserProfile, Player).

    Attributs:
        db_pool: Pool de connexions asyncpg
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    # =========================================================================
    # Méthodes utilitaires
    # =========================================================================

    async def execute_migration(self, sql_file_path: str) -> bool:
        """Exécute un fichier de migration SQL.

        Args:
            sql_file_path: Chemin vers le fichier .sql

        Returns:
            True si succès, False en cas d'erreur
        """
        try:
            with open(sql_file_path, "r", encoding="utf-8") as f:
                sql = f.read()

            async with self.db_pool.acquire() as conn:
                await conn.execute(sql)
            logger.info(f"Migration exécutée: {sql_file_path}")
            return True
        except FileNotFoundError as e:
            logger.error(f"Fichier migration introuvable {sql_file_path}: {e}")
            return False
        except asyncpg.PostgresError as e:
            logger.error(f"Erreur SQL migration {sql_file_path}: {e}")
            return False

    # =========================================================================
    # Gestion des membres (user_profile)
    # =========================================================================

    async def get_member(self, username: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations complètes d'un membre.

        Args:
            username: Nom d'utilisateur Discord

        Returns:
            Dict avec tous les champs du profil ou None
        """
        query = """
        SELECT username, discord_name, language, localisation,
               latitude, longitude, creation_date, last_connection,
               charte_validated, approval_status
        FROM user_profile
        WHERE username = $1
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, username)
            return dict(row) if row else None

    async def update_member_charte_status(self, username: str, validated: bool) -> None:
        """Met à jour le statut de validation de la charte.

        Args:
            username: Nom d'utilisateur Discord
            validated: True si la charte est acceptée
        """
        query = """
        UPDATE user_profile
        SET charte_validated = $1
        WHERE username = $2
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, validated, username)
        logger.info(f"Charte {'validée' if validated else 'invalidée'} pour {username}")

    async def update_member_approval_status(self, username: str, status: str) -> None:
        """Met à jour le statut d'approbation.

        Args:
            username: Nom d'utilisateur Discord
            status: Nouveau statut (pending, approved, refused)
        """
        query = """
        UPDATE user_profile
        SET approval_status = $1
        WHERE username = $2
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, status, username)
        logger.info(f"Statut approbation '{status}' pour {username}")

    async def update_member_location(self, username: str, localisation: str,
                                     latitude: float, longitude: float) -> None:
        """Met à jour la localisation d'un membre.

        Args:
            username: Nom d'utilisateur Discord
            localisation: Adresse textuelle saisie
            latitude: Coordonnée GPS latitude
            longitude: Coordonnée GPS longitude
        """
        query = """
        UPDATE user_profile
        SET localisation = $1, latitude = $2, longitude = $3
        WHERE username = $4
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, localisation, latitude, longitude, username)
        logger.info(f"Localisation mise à jour pour {username}: {localisation}")

    async def clear_member_location(self, username: str) -> None:
        """Supprime la localisation d'un membre (met les champs à NULL).

        Args:
            username: Nom d'utilisateur Discord
        """
        query = """
        UPDATE user_profile
        SET localisation = NULL, latitude = NULL, longitude = NULL
        WHERE username = $1
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, username)
        logger.info(f"Localisation supprimée pour {username}")

    async def get_pending_members(self) -> List[Dict[str, Any]]:
        """Récupère les membres en attente de validation par un sage.

        Returns:
            Liste de dicts {username, discord_name, creation_date, charte_validated}
        """
        query = """
        SELECT username, discord_name, creation_date, charte_validated
        FROM user_profile
        WHERE approval_status = 'pending'
          AND charte_validated = TRUE
        ORDER BY creation_date ASC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def get_members_with_location(self, team_id: int = None) -> List[Dict[str, Any]]:
        """Récupère les membres ayant une localisation définie.

        Args:
            team_id: Filtre par équipe (optionnel)

        Returns:
            Liste de dicts {username, discord_name, localisation, latitude, longitude}
        """
        if team_id:
            query = """
            SELECT DISTINCT up.username, up.discord_name, up.localisation,
                   up.latitude, up.longitude
            FROM user_profile up
            INNER JOIN players p ON up.username = p.member_username
            WHERE up.latitude IS NOT NULL
              AND up.longitude IS NOT NULL
              AND p.team_id = $1
            """
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, team_id)
        else:
            query = """
            SELECT username, discord_name, localisation, latitude, longitude
            FROM user_profile
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query)

        return [dict(row) for row in rows]

    # =========================================================================
    # Statistiques
    # =========================================================================

    async def get_stats(self) -> Dict[str, int]:
        """Récupère les statistiques globales du bot.

        Returns:
            Dict avec total_members, approved_members, pending_members,
            total_players, total_teams, members_with_location
        """
        stats = {}

        queries = {
            'total_members': "SELECT COUNT(*) FROM user_profile",
            'approved_members': "SELECT COUNT(*) FROM user_profile WHERE approval_status = 'approved'",
            'pending_members': "SELECT COUNT(*) FROM user_profile WHERE approval_status = 'pending' AND charte_validated = TRUE",
            'total_players': "SELECT COUNT(*) FROM players",
            'total_teams': "SELECT COUNT(*) FROM teams",
            'members_with_location': "SELECT COUNT(*) FROM user_profile WHERE latitude IS NOT NULL",
        }

        async with self.db_pool.acquire() as conn:
            for key, query in queries.items():
                stats[key] = await conn.fetchval(query) or 0

        return stats
