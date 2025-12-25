"""
Serveur web pour afficher la carte des membres.

Usage:
    python -m web.server

Configuration via variables d'environnement:
    WEB_HOST: Adresse d'ecoute (default: 0.0.0.0)
    WEB_PORT: Port d'ecoute (default: 8080)
"""

import os
import sys
from pathlib import Path

# Ajouter le repertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from config import TEMP_DIR, BASE_DIR
from utils.logger import get_logger

logger = get_logger("web.server")

# Configuration
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

# Chemin du fichier carte
MAP_FILE = TEMP_DIR / "carte_membres.html"

app = FastAPI(
    title="This Is PSG - Carte des membres",
    description="Serveur web pour la carte interactive des membres",
    version="1.0.0"
)


@app.get("/", response_class=HTMLResponse)
async def home():
    """Page d'accueil avec redirection vers la carte."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=/carte">
        <title>This Is PSG</title>
    </head>
    <body>
        <p>Redirection vers <a href="/carte">la carte des membres</a>...</p>
    </body>
    </html>
    """


@app.get("/carte", response_class=HTMLResponse)
async def carte():
    """Affiche la carte des membres."""
    if not MAP_FILE.exists():
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head><title>Carte non disponible</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Carte non disponible</h1>
                <p>La carte n'a pas encore ete generee.</p>
                <p>Utilisez la commande <code>!carte</code> dans Discord pour la generer.</p>
            </body>
            </html>
            """,
            status_code=404
        )

    with open(MAP_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    return HTMLResponse(content=content)


@app.get("/health")
async def health():
    """Endpoint de sante pour monitoring."""
    return {
        "status": "ok",
        "map_exists": MAP_FILE.exists(),
        "map_path": str(MAP_FILE)
    }


@app.get("/api/stats")
async def stats():
    """Statistiques basiques."""
    import json
    from datetime import datetime

    if not MAP_FILE.exists():
        return {"error": "Carte non generee"}

    # Lire le fichier pour extraire les stats
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Extraire le nombre de membres du contenu
    try:
        # Le JSON est entre {{MEMBERS_JSON}} qui a ete remplace
        import re
        match = re.search(r'const members = (\[.*?\]);', content, re.DOTALL)
        if match:
            members = json.loads(match.group(1))
            return {
                "member_count": len(members),
                "last_modified": datetime.fromtimestamp(MAP_FILE.stat().st_mtime).isoformat()
            }
    except Exception as e:
        logger.error(f"Erreur extraction stats: {e}")

    return {"error": "Impossible d'extraire les statistiques"}


def run():
    """Lance le serveur web."""
    logger.info(f"Demarrage du serveur web sur {WEB_HOST}:{WEB_PORT}")
    uvicorn.run(
        "web.server:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    run()
