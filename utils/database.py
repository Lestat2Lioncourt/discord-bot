import asyncpg
import json
import sys
from pathlib import Path

# Ajouter le dossier parent au path pour importer config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CHARTE_JSON_PATH
from utils.logger import get_logger

logger = get_logger("utils.database")


class Database:
    def __init__(self, db_pool):
        self.db_pool = db_pool

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
