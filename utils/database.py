import asyncpg
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ajouter le dossier parent au path pour importer config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CHARTE_JSON_PATH
from utils.logger import get_logger

logger = get_logger("utils.database")


class Database:
    """Classe principale pour les interactions avec la base de données."""

    def __init__(self, db_pool):
        self.db_pool = db_pool

    # =========================================================================
    # Méthodes utilitaires
    # =========================================================================

    async def execute_migration(self, sql_file_path: str) -> bool:
        """Exécute un fichier de migration SQL."""
        try:
            with open(sql_file_path, "r", encoding="utf-8") as f:
                sql = f.read()

            async with self.db_pool.acquire() as conn:
                await conn.execute(sql)
            logger.info(f"Migration exécutée: {sql_file_path}")
            return True
        except Exception as e:
            logger.error(f"Erreur migration {sql_file_path}: {e}")
            return False

    # =========================================================================
    # Gestion des membres (user_profile)
    # =========================================================================

    async def get_member(self, username: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations complètes d'un membre."""
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
        """Met à jour le statut de validation de la charte."""
        query = """
        UPDATE user_profile
        SET charte_validated = $1
        WHERE username = $2
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, validated, username)
        logger.info(f"Charte {'validée' if validated else 'invalidée'} pour {username}")

    async def update_member_approval_status(self, username: str, status: str) -> None:
        """Met à jour le statut d'approbation (pending, approved, refused)."""
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
        """Met à jour la localisation d'un membre."""
        query = """
        UPDATE user_profile
        SET localisation = $1, latitude = $2, longitude = $3
        WHERE username = $4
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, localisation, latitude, longitude, username)
        logger.info(f"Localisation mise à jour pour {username}: {localisation}")

    async def clear_member_location(self, username: str) -> None:
        """Supprime la localisation d'un membre."""
        query = """
        UPDATE user_profile
        SET localisation = NULL, latitude = NULL, longitude = NULL
        WHERE username = $1
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, username)
        logger.info(f"Localisation supprimée pour {username}")

    async def get_pending_members(self) -> List[Dict[str, Any]]:
        """Récupère les membres en attente de validation par un sage."""
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
        """Récupère les membres ayant une localisation définie."""
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
        """Récupère les statistiques globales."""
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

    async def add_validation(self, username: str, clause_idx: int, validation: int):
        """Ajoute ou met à jour une validation pour un utilisateur."""
        query = """
        INSERT INTO Validation_charte (Username,
                                       ID_Clause,
                                       Validation)
        VALUES ($1, $2, $3)
        ON CONFLICT (Username, ID_Clause) DO UPDATE
        SET Validation = EXCLUDED.Validation;
        """
        async with self.db_pool.acquire() as connection:
            await connection.execute(query, username, clause_idx, validation)

    async def remove_validation(self, username: str, clause_idx: int):
        """Supprime une validation pour un utilisateur."""
        query = """
        DELETE  FROM    Validation_charte
                WHERE   Username = $1
                AND     ID_Clause = $2;
        """
        async with self.db_pool.acquire() as connection:
            await connection.execute(query, username, clause_idx)

    async def get_user_validations(self, username: str):
        """Récupère les validations d'un utilisateur."""
        query = """
        SELECT  ID_Clause,
                Validation
        FROM    Validation_charte
        WHERE   Username = $1;
        """
        async with self.db_pool.acquire() as connection:
            rows = await connection.fetch(query, username)
            logger.debug(f"Validations récupérées pour {username}: {len(rows)} lignes")
            return [(row["id_clause"], row["validation"]) for row in rows]

    async def is_fully_validated(self, username: str, total_clauses: int):
        """Vérifie si un utilisateur a validé toutes les clauses."""
        query = """
        SELECT  COUNT(*)
        FROM    Validation_charte
        WHERE   Username = $1
        AND     Validation = 1;
        """
        async with self.db_pool.acquire() as connection:
            count = await connection.fetchval(query, username)
            return count == total_clauses

    async def get_clause(self, clause_idx: int):
        """Récupère le libellé d'une clause."""
        query = """
        SELECT  Clause
        FROM    Charte
        WHERE   ID_Clause = $1;
        """
        async with self.db_pool.acquire() as connection:
            return await connection.fetchval(query, clause_idx)

    async def get_total_clauses(self):
        """Récupère le nombre total de clauses."""
        query = """
        SELECT  COUNT(*)
        FROM    Charte;
        """
        async with self.db_pool.acquire() as connection:
            return await connection.fetchval(query)

    async def set_charte(self, charte_data: dict):
        """Remplit la table Charte en fonction du fichier charte.json."""
        logger.debug("Lancement de set_charte")
        query = """
        INSERT INTO Charte (ID_Clause, Clause)
        VALUES ($1, $2)
        ON CONFLICT (ID_Clause) DO NOTHING;
        """
        async with self.db_pool.acquire() as connection:
            for clause in charte_data["charte"]:
                if clause["validation"] == 1:
                    await connection.execute(query, clause["idx"], clause["name"])
                    logger.debug(f"Clause {clause['idx']} insérée: {clause['name']}")

    async def get_clause_by_name(self, clause_name: str):
        """Récupère l'ID d'une clause par son nom."""
        query = """
        SELECT ID_Clause
        FROM Charte
        WHERE Clause = $1;
        """
        async with self.db_pool.acquire() as connection:
            clause_id = await connection.fetchval(query, clause_name)
            logger.debug(f"Clause ID récupéré pour '{clause_name}': {clause_id}")
            return clause_id

    async def get_charte_data(self):
        """Récupère les données de charte.json."""
        with open(CHARTE_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)["charte"]
