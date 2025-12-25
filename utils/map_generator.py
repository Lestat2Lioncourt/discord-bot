"""
Generateur de carte des membres.

Genere un fichier HTML statique avec la carte Leaflet des membres.
Appele automatiquement quand une localisation est modifiee.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DATA_DIR, TEMP_DIR
from utils.logger import get_logger

logger = get_logger("utils.map_generator")

# Chemins des fichiers
MAP_TEMPLATE_PATH = DATA_DIR / "map_template.html"
MAP_OUTPUT_PATH = TEMP_DIR / "carte_membres.html"

# Chemin pour le serveur web (configurable)
WEB_OUTPUT_PATH: Optional[Path] = None


def set_web_output_path(path: str):
    """Configure le chemin de sortie pour le serveur web."""
    global WEB_OUTPUT_PATH
    WEB_OUTPUT_PATH = Path(path)
    WEB_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Chemin web configure: {WEB_OUTPUT_PATH}")


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

        # Recuperer les membres avec localisation
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT username, discord_name, localisation, latitude, longitude
                FROM user_profile
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                AND approval_status = 'approved'
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

        # Sauvegarder dans temp (pour la commande !carte)
        with open(MAP_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Sauvegarder aussi pour le serveur web si configure
        if WEB_OUTPUT_PATH:
            with open(WEB_OUTPUT_PATH, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"Carte web mise a jour: {WEB_OUTPUT_PATH} ({len(members_data)} membres)")

        logger.info(f"Carte generee: {len(members_data)} membres")
        return MAP_OUTPUT_PATH

    except Exception as e:
        logger.error(f"Erreur generation carte: {e}", exc_info=True)
        return None


async def regenerate_map_if_needed(db_pool):
    """
    Regenere la carte si le serveur web est configure.
    Appeler cette fonction apres chaque modification de localisation.
    """
    if WEB_OUTPUT_PATH:
        await generate_map(db_pool)
    else:
        logger.debug("Serveur web non configure, carte non regeneree")
