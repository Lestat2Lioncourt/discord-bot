"""
Generateur de carte des membres.

Genere un fichier HTML statique avec la carte Leaflet des membres.
Appele automatiquement quand une localisation est modifiee.
Publie sur GitHub Pages via l'API GitHub (sans git local).
"""

import asyncpg
import aiohttp
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DATA_DIR, TEMP_DIR, BASE_DIR, GITHUB_TOKEN, GITHUB_REPO
from utils.logger import get_logger

logger = get_logger("utils.map_generator")

# Chemins des fichiers
MAP_TEMPLATE_PATH = DATA_DIR / "map_template.html"
MAP_OUTPUT_PATH = TEMP_DIR / "carte_membres.html"
GITHUB_PAGES_PATH = BASE_DIR / "docs" / "carte.html"
CARTE_META_PATH = BASE_DIR / "docs" / "carte_meta.json"

# Configuration GitHub Pages (activee si token configure)
GITHUB_PAGES_ENABLED = bool(GITHUB_TOKEN)

# URL de base de l'API GitHub
GITHUB_API_URL = "https://api.github.com"


async def generate_map(db_pool) -> Optional[Path]:
    """
    Genere la carte des membres et retourne le chemin du fichier.

    Args:
        db_pool: Pool de connexions a la base de donnees

    Returns:
        Path du fichier genere, ou None en cas d'erreur
    """
    try:
        # Import ici pour eviter les imports circulaires
        from models.player import Player

        # Recuperer tous les membres avec localisation (peu importe le statut)
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT username, discord_name, localisation, latitude, longitude
                FROM user_profile
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """)

        if not rows:
            logger.warning("Aucun membre avec localisation pour la carte")
            return None

        # Construire les donnees des membres
        members_data = []
        for row in rows:
            username = row['username']
            display_name = row['discord_name'] or username

            # Recuperer les joueurs de ce membre, separes par equipe
            players = await Player.get_by_member(db_pool, username)
            team1 = [p.player_name for p in players if p.team_name == "This Is PSG"] if players else []
            team2 = [p.player_name for p in players if p.team_name == "This Is PSG 2"] if players else []

            members_data.append({
                "name": display_name,
                "lat": float(row['latitude']),
                "lng": float(row['longitude']),
                "team1": team1,
                "team2": team2
            })

        # Lire le template
        with open(MAP_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            template = f.read()

        # Remplacer les placeholders
        html_content = template.replace("{{MEMBERS_JSON}}", json.dumps(members_data, ensure_ascii=False))
        html_content = html_content.replace("{{MEMBER_COUNT}}", str(len(members_data)))
        html_content = html_content.replace("{{DATE}}", datetime.now().strftime("%d/%m/%Y %H:%M"))

        # Sauvegarder dans temp (pour la commande !carte avec fichier)
        with open(MAP_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Publier sur GitHub Pages si active
        if GITHUB_PAGES_ENABLED:
            await publish_to_github_pages(html_content, len(members_data))

        logger.info(f"Carte generee: {len(members_data)} membres")
        return MAP_OUTPUT_PATH

    except asyncpg.PostgresError as e:
        logger.error(f"Erreur DB generation carte: {e}", exc_info=True)
        return None
    except OSError as e:
        logger.error(f"Erreur fichier generation carte: {e}", exc_info=True)
        return None


async def _get_file_sha(session: aiohttp.ClientSession, path: str) -> Optional[str]:
    """Recupere le SHA d'un fichier sur GitHub (necessaire pour update).

    Args:
        session: Session aiohttp
        path: Chemin du fichier dans le repo (ex: "docs/carte.html")

    Returns:
        SHA du fichier ou None si le fichier n'existe pas
    """
    url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("sha")
            elif resp.status == 404:
                return None  # Fichier n'existe pas encore
            else:
                logger.warning(f"GitHub API get SHA: {resp.status}")
                return None
    except aiohttp.ClientError as e:
        logger.error(f"Erreur GitHub API get SHA: {e}")
        return None


async def _update_github_file(
    session: aiohttp.ClientSession,
    path: str,
    content: str,
    commit_message: str
) -> bool:
    """Met a jour un fichier sur GitHub via l'API.

    Args:
        session: Session aiohttp
        path: Chemin du fichier dans le repo
        content: Contenu du fichier (texte)
        commit_message: Message de commit

    Returns:
        True si succes, False sinon
    """
    url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # Encoder le contenu en base64
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # Recuperer le SHA actuel (necessaire pour update)
    sha = await _get_file_sha(session, path)

    payload = {
        "message": commit_message,
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    try:
        async with session.put(url, headers=headers, json=payload) as resp:
            if resp.status in (200, 201):
                return True
            else:
                error = await resp.text()
                logger.error(f"GitHub API update {path}: {resp.status} - {error}")
                return False
    except aiohttp.ClientError as e:
        logger.error(f"Erreur GitHub API update {path}: {e}")
        return False


async def publish_to_github_pages(html_content: str, member_count: int):
    """
    Publie la carte sur GitHub Pages via l'API GitHub.
    Met a jour docs/carte.html et docs/carte_meta.json directement.
    """
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN non configure, publication impossible")
        return

    now = datetime.now()
    commit_msg = f"Update carte: {member_count} membres - {now.strftime('%d/%m/%Y %H:%M')}"

    # Preparer les metadonnees
    meta_data = json.dumps({
        "last_update": now.strftime("%d/%m/%Y %H:%M"),
        "member_count": member_count
    })

    try:
        async with aiohttp.ClientSession() as session:
            # Mettre a jour carte.html
            success_html = await _update_github_file(
                session, "docs/carte.html", html_content, commit_msg
            )

            # Mettre a jour carte_meta.json
            success_meta = await _update_github_file(
                session, "docs/carte_meta.json", meta_data, commit_msg
            )

            if success_html and success_meta:
                logger.info(f"Carte publiee sur GitHub Pages: {member_count} membres")
            elif success_html or success_meta:
                logger.warning("Publication partielle sur GitHub Pages")
            else:
                logger.error("Echec publication GitHub Pages")

    except Exception as e:
        logger.error(f"Erreur publication GitHub Pages: {e}", exc_info=True)


async def regenerate_map_if_needed(db_pool):
    """
    Regenere la carte si GitHub Pages est active.
    Appeler cette fonction apres chaque modification de localisation.
    """
    if GITHUB_PAGES_ENABLED:
        await generate_map(db_pool)
    else:
        logger.debug("GitHub Pages non configure, carte non regeneree")
