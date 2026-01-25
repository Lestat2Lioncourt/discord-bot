#!/usr/bin/env python3
"""
Script pour recalculer les builds de toutes les captures existantes.

Utilise la logique BuildTypes.calculate() pour mettre a jour
les enregistrements player_stats.

Usage:
    python recalculate_builds.py [--dry-run]

Options:
    --dry-run   Affiche les changements sans les appliquer
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ajouter le dossier parent au path pour importer constants
sys.path.insert(0, str(Path(__file__).parent.parent))
from constants import BuildTypes

# Charger la config locale
load_dotenv(".env.local")

# Configuration DB
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "discord_bot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


async def recalculate_builds(dry_run: bool = False):
    """Recalcule les builds pour toutes les captures."""
    print("=" * 60)
    print("Recalcul des builds pour les captures existantes")
    print("=" * 60)

    if dry_run:
        print("\n[MODE DRY-RUN - Aucune modification ne sera appliquee]\n")

    # Connexion a la base
    print(f"Connexion a {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}...")

    try:
        conn = await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Erreur de connexion: {e}")
        sys.exit(1)

    try:
        # Recuperer toutes les stats
        query = """
            SELECT id, character_name, build_type,
                   agility, endurance, serve, volley, forehand, backhand
            FROM player_stats
            ORDER BY id
        """
        rows = await conn.fetch(query)

        print(f"\n{len(rows)} capture(s) a traiter\n")

        updated = 0
        unchanged = 0
        errors = 0

        for row in rows:
            stats_id = row['id']
            old_build = row['build_type']

            # Construire le dict de stats
            stats = {
                'agility': row['agility'] or 0,
                'endurance': row['endurance'] or 0,
                'serve': row['serve'] or 0,
                'volley': row['volley'] or 0,
                'forehand': row['forehand'] or 0,
                'backhand': row['backhand'] or 0,
            }

            # Calculer le nouveau build
            new_build = BuildTypes.calculate(stats)

            if new_build == old_build:
                unchanged += 1
                continue

            # Afficher le changement
            char_name = row['character_name'] or "?"
            print(f"[{stats_id}] {char_name}: {old_build or '(vide)'} -> {new_build}")

            if not dry_run:
                try:
                    await conn.execute(
                        "UPDATE player_stats SET build_type = $1 WHERE id = $2",
                        new_build, stats_id
                    )
                    updated += 1
                except Exception as e:
                    print(f"  ERREUR: {e}")
                    errors += 1
            else:
                updated += 1

        # Resume
        print("\n" + "=" * 60)
        print(f"Resume:")
        print(f"  - Inchanges: {unchanged}")
        print(f"  - Modifies:  {updated}")
        if errors:
            print(f"  - Erreurs:   {errors}")
        print("=" * 60)

        if dry_run and updated > 0:
            print("\nRelancez sans --dry-run pour appliquer les modifications.")

    finally:
        await conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(recalculate_builds(dry_run))
