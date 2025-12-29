#!/usr/bin/env python3
"""
Script d'exécution des migrations de base de données.

Usage:
    python scripts/run_migration.py [--dry-run]

Options:
    --dry-run   Affiche le SQL sans l'exécuter
"""

import asyncio
import asyncpg
import sys
from pathlib import Path

# Ajouter le dossier parent au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DB_CONFIG, BASE_DIR
from utils.logger import setup_logger

logger = setup_logger("migration", level=20)  # INFO level


async def run_migration(dry_run: bool = False):
    """Exécute les migrations SQL."""
    migrations_dir = BASE_DIR / "migrations"

    if not migrations_dir.exists():
        logger.error(f"Dossier migrations introuvable: {migrations_dir}")
        return False

    # Lister les fichiers de migration
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.info("Aucune migration à exécuter")
        return True

    logger.info(f"Migrations trouvées: {len(migration_files)}")

    if dry_run:
        logger.info("=== MODE DRY-RUN ===")
        for migration_file in migration_files:
            logger.info(f"Migration: {migration_file.name}")
            with open(migration_file, "r", encoding="utf-8") as f:
                print(f.read())
        return True

    # Connexion à la base de données
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        logger.info("Connexion à la base de données établie")
    except Exception as e:
        logger.error(f"Erreur de connexion: {e}")
        return False

    try:
        for migration_file in migration_files:
            logger.info(f"Exécution de: {migration_file.name}")

            with open(migration_file, "r", encoding="utf-8") as f:
                sql = f.read()

            try:
                await conn.execute(sql)
                logger.info(f"Migration {migration_file.name} exécutée avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de {migration_file.name}: {e}")
                raise

        logger.info("=== Toutes les migrations ont été exécutées ===")

        # Vérification post-migration
        await verify_migration(conn)

        return True

    except Exception as e:
        logger.error(f"Erreur migration: {e}")
        return False

    finally:
        await conn.close()
        logger.info("Connexion fermée")


async def verify_migration(conn):
    """Vérifie que la migration s'est bien passée."""
    logger.info("=== Vérification post-migration ===")

    checks = [
        ("Teams", "SELECT COUNT(*) FROM teams"),
        ("Players", "SELECT COUNT(*) FROM players"),
        ("Member Approval", "SELECT COUNT(*) FROM member_approval"),
        ("Charte validée", "SELECT COUNT(*) FROM user_profile WHERE charte_validated = TRUE"),
        ("Membres approuvés", "SELECT COUNT(*) FROM user_profile WHERE approval_status = 'approved'"),
    ]

    for name, query in checks:
        try:
            count = await conn.fetchval(query)
            logger.info(f"  {name}: {count}")
        except Exception as e:
            logger.warning(f"  {name}: Erreur - {e}")


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("Mode dry-run activé - aucune modification ne sera effectuée")

    success = asyncio.run(run_migration(dry_run))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
