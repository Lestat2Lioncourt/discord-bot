#!/usr/bin/env python3
"""
Script de traitement des captures Tennis Clash en attente.

Récupère les images en attente dans PostgreSQL, les analyse avec Claude Vision,
et met à jour les résultats en base.

Usage:
    python process_queue.py [--dry-run]

Options:
    --dry-run   Affiche les captures en attente sans les traiter
"""

import asyncio
import asyncpg
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Commande Claude selon l'OS
CLAUDE_CMD = "claude.cmd" if platform.system() == "Windows" else "claude"

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

# Prompt pour Claude Vision
ANALYSIS_PROMPT = """Analyse cette capture d'écran du jeu Tennis Clash.

Extrais TOUTES les informations visibles et retourne UNIQUEMENT un JSON valide (sans markdown, sans explication, sans commentaire) avec cette structure exacte:

{
    "character_name": "nom du personnage",
    "character_level": 14,
    "points": 2122,
    "global_power": 413,
    "stats": {
        "agility": 98,
        "endurance": 70,
        "serve": 45,
        "volley": 38,
        "forehand": 71,
        "backhand": 91
    },
    "equipment": [
        {"slot": 1, "name": "Nom raquette", "level": 14},
        {"slot": 2, "name": "Nom grip", "level": 14},
        {"slot": 3, "name": "Nom chaussures", "level": 13},
        {"slot": 4, "name": "Nom poignet", "level": 14},
        {"slot": 5, "name": "Nom nutrition", "level": 14},
        {"slot": 6, "name": "Nom entrainement", "level": 14}
    ]
}

IMPORTANT:
- Les niveaux des cartes sont affichés en blanc sur fond coloré (violet/orange/bleu)
- Retourne UNIQUEMENT le JSON, rien d'autre
- Si une valeur n'est pas visible, mets null
- Les noms des cartes sont en français"""


def call_claude_code(image_path: str) -> str:
    """Appelle Claude Code CLI avec l'image.

    Args:
        image_path: Chemin vers l'image à analyser (relatif au script)

    Returns:
        Réponse brute de Claude
    """
    # Prompt qui demande directement le JSON
    prompt = """Analyse cette capture d'écran Tennis Clash et retourne UNIQUEMENT un JSON valide (sans markdown, sans explication, sans tableau, sans commentaire) avec cette structure exacte:

{
    "character_name": "nom du personnage",
    "character_level": 14,
    "points": 2122,
    "global_power": 413,
    "stats": {
        "agility": 98,
        "endurance": 70,
        "serve": 45,
        "volley": 38,
        "forehand": 71,
        "backhand": 91
    },
    "equipment": [
        {"slot": 1, "name": "Nom raquette", "level": 14},
        {"slot": 2, "name": "Nom grip", "level": 14},
        {"slot": 3, "name": "Nom chaussures", "level": 13},
        {"slot": 4, "name": "Nom poignet", "level": 14},
        {"slot": 5, "name": "Nom nutrition", "level": 14},
        {"slot": 6, "name": "Nom entrainement", "level": 14}
    ]
}

IMPORTANT: Retourne UNIQUEMENT le JSON brut. Pas de texte, pas de markdown, pas d'explication."""

    # Dossier du script
    script_dir = Path(__file__).parent

    cmd = [
        CLAUDE_CMD,
        prompt,
        image_path
    ]

    print(f"  Appel Claude Code...")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,  # 3 minutes max
        cwd=script_dir  # Travailler dans le dossier du script
    )

    if result.returncode != 0:
        raise Exception(f"Claude Code error: {result.stderr}")

    return result.stdout.strip()


def parse_json_response(response: str) -> dict:
    """Parse la réponse JSON de Claude.

    Args:
        response: Réponse brute de Claude

    Returns:
        Dictionnaire avec les données extraites
    """
    text = response.strip()

    # Retirer les décorations Claude Code (●, >, etc.)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Retirer les préfixes de décoration
        line = re.sub(r'^[●❯>\s]+', '', line)
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # Retirer les blocs de code markdown si présents
    if "```" in text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            text = match.group(1)

    # Parser le JSON directement
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Essayer de trouver le JSON dans la réponse (entre { et })
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Dernier essai: nettoyer les caractères problématiques
    text_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    json_match = re.search(r'\{[\s\S]*\}', text_clean)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    raise Exception(f"Invalid JSON response: {text[:200]}...")


async def get_pending_captures(conn) -> list:
    """Récupère les captures en attente."""
    query = """
        SELECT id, discord_user_id, discord_username, player_name,
               image_data, image_filename, submitted_at
        FROM capture_queue
        WHERE status = 'pending'
        ORDER BY submitted_at ASC
    """
    return await conn.fetch(query)


async def update_capture_completed(conn, capture_id: int, result_json: dict) -> None:
    """Met à jour une capture comme traitée avec succès."""
    query = """
        UPDATE capture_queue
        SET status = 'completed',
            processed_at = NOW(),
            result_json = $1
        WHERE id = $2
    """
    await conn.execute(query, json.dumps(result_json), capture_id)


async def update_capture_failed(conn, capture_id: int, error: str) -> None:
    """Met à jour une capture comme échouée."""
    query = """
        UPDATE capture_queue
        SET status = 'failed',
            processed_at = NOW(),
            error_message = $1
        WHERE id = $2
    """
    await conn.execute(query, error, capture_id)


async def process_capture(conn, capture: dict) -> bool:
    """Traite une capture.

    Args:
        conn: Connexion à la base
        capture: Données de la capture

    Returns:
        True si succès, False si échec
    """
    capture_id = capture["id"]
    username = capture["discord_username"]
    player = capture["player_name"] or "inconnu"

    print(f"\n[{capture_id}] Traitement capture de {username} (joueur: {player})")

    # Sauvegarder l'image dans le dossier courant (pour que Claude Code la trouve)
    script_dir = Path(__file__).parent
    temp_path = script_dir / f"capture_{capture_id}.png"

    with open(temp_path, "wb") as f:
        f.write(capture["image_data"])

    try:
        # Appeler Claude Vision avec chemin relatif
        raw_response = call_claude_code(f"./capture_{capture_id}.png")

        # Parser le JSON
        result = parse_json_response(raw_response)
        print(f"  Personnage: {result.get('character_name')} (niv.{result.get('character_level')})")
        print(f"  Points: {result.get('points')}")

        # Mettre à jour la base
        await update_capture_completed(conn, capture_id, result)
        print(f"  ✓ Traitement réussi")
        return True

    except subprocess.TimeoutExpired:
        error = "Timeout Claude Code (>180s)"
        print(f"  ✗ {error} (reste en pending pour retry)")
        # On laisse en pending pour réessayer plus tard
        return False

    except Exception as e:
        error = str(e)
        print(f"  ✗ Erreur: {error[:100]} (reste en pending pour retry)")
        # On laisse en pending pour réessayer plus tard
        return False

    finally:
        # Nettoyer le fichier temporaire
        temp_path.unlink(missing_ok=True)


async def main(dry_run: bool = False):
    """Point d'entrée principal."""
    print("=" * 60)
    print("Tennis Clash - Traitement des captures en attente")
    print("=" * 60)

    # Connexion à la base
    print(f"\nConnexion à {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}...")

    try:
        conn = await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Erreur de connexion: {e}")
        sys.exit(1)

    try:
        # Récupérer les captures en attente
        captures = await get_pending_captures(conn)

        if not captures:
            print("\nAucune capture en attente.")
            return

        print(f"\n{len(captures)} capture(s) en attente")

        if dry_run:
            print("\n=== MODE DRY-RUN ===")
            for c in captures:
                print(f"  [{c['id']}] {c['discord_username']} - {c['player_name'] or '?'} - {c['submitted_at']}")
            return

        # Traiter chaque capture
        success = 0
        failed = 0

        for capture in captures:
            if await process_capture(conn, capture):
                success += 1
            else:
                failed += 1

        # Résumé
        print("\n" + "=" * 60)
        print(f"Résumé: {success} réussi(s), {failed} échoué(s)")
        print("=" * 60)

    finally:
        await conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run))
