"""
Generateur de carte des membres.

Genere un fichier HTML statique avec la carte Leaflet des membres.
Appele automatiquement quand une localisation est modifiee.
Peut publier sur GitHub Pages automatiquement.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DATA_DIR, TEMP_DIR, BASE_DIR
from utils.logger import get_logger

logger = get_logger("utils.map_generator")

# Chemins des fichiers
MAP_TEMPLATE_PATH = DATA_DIR / "map_template.html"
MAP_OUTPUT_PATH = TEMP_DIR / "carte_membres.html"
GITHUB_PAGES_PATH = BASE_DIR / "docs" / "index.html"

# Configuration GitHub Pages (activee par defaut si le dossier docs/ existe)
GITHUB_PAGES_ENABLED = GITHUB_PAGES_PATH.parent.exists()


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

        # Sauvegarder dans temp (pour la commande !carte avec fichier)
        with open(MAP_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Publier sur GitHub Pages si active
        if GITHUB_PAGES_ENABLED:
            await publish_to_github_pages(html_content, len(members_data))

        logger.info(f"Carte generee: {len(members_data)} membres")
        return MAP_OUTPUT_PATH

    except Exception as e:
        logger.error(f"Erreur generation carte: {e}", exc_info=True)
        return None


async def publish_to_github_pages(html_content: str, member_count: int):
    """
    Publie la carte sur GitHub Pages.
    Sauvegarde dans docs/index.html et fait un commit/push.
    """
    try:
        # Sauvegarder le fichier
        GITHUB_PAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(GITHUB_PAGES_PATH, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Commit et push
        commit_msg = f"Update carte: {member_count} membres - {datetime.now().strftime('%d/%m/%Y %H:%M')}"

        # Executer les commandes git
        subprocess.run(
            ["git", "add", "docs/index.html"],
            cwd=BASE_DIR,
            capture_output=True,
            check=True
        )

        # Verifier s'il y a des changements a commiter
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=BASE_DIR,
            capture_output=True
        )

        if result.returncode != 0:  # Il y a des changements
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=BASE_DIR,
                capture_output=True,
                check=True
            )

            subprocess.run(
                ["git", "push"],
                cwd=BASE_DIR,
                capture_output=True,
                check=True
            )

            logger.info(f"Carte publiee sur GitHub Pages: {member_count} membres")
        else:
            logger.debug("Pas de changement a publier sur GitHub Pages")

    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur git lors de la publication: {e.stderr.decode() if e.stderr else e}")
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
