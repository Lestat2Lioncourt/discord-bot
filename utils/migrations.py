"""
Systeme de migrations automatiques pour la base de donnees.

Execute les migrations SQL non encore appliquees au demarrage du bot.
"""

import asyncpg
from pathlib import Path
from typing import Optional

from config import BASE_DIR
from utils.logger import get_logger

logger = get_logger("migrations")

MIGRATIONS_DIR = BASE_DIR / "migrations"

# Table de suivi des migrations
SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    """Cree la table de suivi si elle n'existe pas."""
    await conn.execute(SCHEMA_MIGRATIONS_TABLE)


async def get_applied_migrations(conn: asyncpg.Connection) -> set[str]:
    """Retourne les migrations deja appliquees."""
    rows = await conn.fetch("SELECT filename FROM schema_migrations")
    return {row["filename"] for row in rows}


async def mark_as_applied(conn: asyncpg.Connection, filename: str) -> None:
    """Marque une migration comme appliquee."""
    await conn.execute(
        "INSERT INTO schema_migrations (filename) VALUES ($1)",
        filename
    )


async def run_migrations(pool: asyncpg.Pool) -> tuple[int, int]:
    """
    Execute les migrations non encore appliquees.

    Args:
        pool: Pool de connexions asyncpg

    Returns:
        (nombre de migrations executees, nombre total de migrations)
    """
    if not MIGRATIONS_DIR.exists():
        logger.warning(f"Dossier migrations introuvable: {MIGRATIONS_DIR}")
        return 0, 0

    # Lister les fichiers de migration tries par nom
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not migration_files:
        logger.info("Aucune migration trouvee")
        return 0, 0

    async with pool.acquire() as conn:
        # Creer la table de suivi
        await ensure_migrations_table(conn)

        # Recuperer les migrations deja appliquees
        applied = await get_applied_migrations(conn)

        # Filtrer les nouvelles migrations
        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            logger.info(f"Base a jour ({len(applied)} migrations appliquees)")
            return 0, len(migration_files)

        logger.info(f"{len(pending)} migration(s) a executer")

        # Executer chaque migration dans une transaction
        executed = 0
        for migration_file in pending:
            try:
                async with conn.transaction():
                    sql = migration_file.read_text(encoding="utf-8")
                    await conn.execute(sql)
                    await mark_as_applied(conn, migration_file.name)

                logger.info(f"Migration appliquee: {migration_file.name}")
                executed += 1

            except Exception as e:
                logger.error(f"Erreur migration {migration_file.name}: {e}")
                raise

        logger.info(f"{executed} migration(s) executee(s) avec succes")
        return executed, len(migration_files)


async def check_migrations_status(pool: asyncpg.Pool) -> dict:
    """
    Retourne le statut des migrations.

    Returns:
        {"applied": [...], "pending": [...], "total": int}
    """
    if not MIGRATIONS_DIR.exists():
        return {"applied": [], "pending": [], "total": 0}

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    all_names = [f.name for f in migration_files]

    async with pool.acquire() as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_migrations(conn)

    pending = [name for name in all_names if name not in applied]

    return {
        "applied": sorted(applied),
        "pending": pending,
        "total": len(all_names)
    }
