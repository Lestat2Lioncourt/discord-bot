#!/usr/bin/env python3
"""
Script pour forcer la regeneration de la carte des membres.

Usage:
    python scripts/regenerate_map.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Ajouter le dossier parent au path pour les imports
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Charger .env manuellement avant les imports
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

# Mettre des valeurs par defaut pour eviter les erreurs de config
if not os.getenv("DISCORD_TOKEN"):
    os.environ["DISCORD_TOKEN"] = "SCRIPT_MODE"
if not os.getenv("DB_PASSWORD"):
    os.environ["DB_PASSWORD"] = "PLACEHOLDER_CONFIGURE_ENV"

import asyncpg
from config import DB_CONFIG
from utils.map_generator import generate_map
from utils.logger import get_logger

logger = get_logger("scripts.regenerate_map")


async def main():
    """Force la regeneration de la carte."""
    print("Connexion a la base de donnees...")

    try:
        pool = await asyncpg.create_pool(**DB_CONFIG)
        print("Connecte.")

        print("Regeneration de la carte...")
        result = await generate_map(pool)

        if result:
            print(f"Carte generee: {result}")
        else:
            print("Aucun membre avec localisation ou erreur.")

        await pool.close()
        print("Termine.")

    except Exception as e:
        logger.error(f"Erreur: {e}")
        print(f"Erreur: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
