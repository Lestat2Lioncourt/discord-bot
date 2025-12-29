"""
Configuration centralisée du bot Discord.
Charge les variables d'environnement et définit les chemins.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# =============================================================================
# Chemins de base
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEXTS_DIR = DATA_DIR / "texts"
TEMP_DIR = BASE_DIR / "temp"
LOGS_DIR = BASE_DIR / "logs"

# Créer les dossiers nécessaires s'ils n'existent pas
TEMP_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# =============================================================================
# Chargement des variables d'environnement
# =============================================================================
# Cherche .env dans le dossier du projet
load_dotenv(BASE_DIR / ".env")

# =============================================================================
# Configuration Discord
# =============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError(
        "DISCORD_TOKEN non défini. "
        "Créez un fichier .env à partir de .env.example"
    )

# =============================================================================
# Configuration Base de données
# =============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "this_is_psg"),
    "user": os.getenv("DB_USER", "bot_user"),
    "password": os.getenv("DB_PASSWORD"),
    "min_size": int(os.getenv("DB_POOL_MIN_SIZE", "2")),
    "max_size": int(os.getenv("DB_POOL_MAX_SIZE", "10")),
}

if not DB_CONFIG["password"]:
    raise ValueError(
        "DB_PASSWORD non défini. "
        "Créez un fichier .env à partir de .env.example"
    )

# =============================================================================
# Fichiers de données - Charte HTML
# =============================================================================
CHARTE_DIR = DATA_DIR / "charte"
CHARTE_FILES = {
    "fr": CHARTE_DIR / "charte_fr.html",
    "en": CHARTE_DIR / "charte_en.html",
}
# URL de la charte en ligne (prioritaire sur les fichiers locaux)
URL_CHARTE = os.getenv("URL_CHARTE", "")

# =============================================================================
# Configuration du Bot
# =============================================================================
BOT_PREFIX = "!"

# =============================================================================
# Mode Debug
# =============================================================================
# En mode debug, seul DEBUG_USER peut utiliser les commandes
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEBUG_USER = os.getenv("DEBUG_USER", "detrax75")

# =============================================================================
# Discord Server ID
# =============================================================================
SERVER_ID = int(os.getenv("SERVER_ID", "0"))

# =============================================================================
# Discord Role IDs
# =============================================================================
ROLE_NEWBIE_ID = int(os.getenv("ROLE_NEWBIE_ID", "0"))
ROLE_MEMBRE_ID = int(os.getenv("ROLE_MEMBRE_ID", "0"))
ROLE_SAGE_ID = int(os.getenv("ROLE_SAGE_ID", "0"))

# =============================================================================
# Discord Channel IDs
# =============================================================================
CHANNEL_ACCUEIL_ID = int(os.getenv("CHANNEL_ACCUEIL_ID", "0"))
CHANNEL_GENERAL_ID = int(os.getenv("CHANNEL_GENERAL_ID", "0"))
CHANNEL_SAGE_ID = int(os.getenv("CHANNEL_SAGE_ID", "0"))

# =============================================================================
# Serveur Web / GitHub Pages
# =============================================================================
# URL de la carte des membres
WEB_URL = os.getenv("WEB_URL", "")
# URL du site (page index)
SITE_URL = os.getenv("SITE_URL", "")

# =============================================================================
# GitHub API (pour publication carte sans git local)
# =============================================================================
# Token GitHub avec permission "contents: write" sur le repo
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# Repo au format "owner/repo"
GITHUB_REPO = os.getenv("GITHUB_REPO", "Lestat2Lioncourt/discord-bot")

# =============================================================================
# Timeouts (en secondes) - configurables via .env
# =============================================================================
TIMEOUT_LANGUAGE_SELECT = int(os.getenv("TIMEOUT_LANGUAGE_SELECT", "300"))
TIMEOUT_CHARTE_READ = int(os.getenv("TIMEOUT_CHARTE_READ", "600"))
TIMEOUT_PLAYER_INPUT = int(os.getenv("TIMEOUT_PLAYER_INPUT", "120"))
TIMEOUT_LOCATION_INPUT = int(os.getenv("TIMEOUT_LOCATION_INPUT", "120"))
TIMEOUT_KEEP_OR_RESET = int(os.getenv("TIMEOUT_KEEP_OR_RESET", "300"))
TIMEOUT_LANGUAGE_CHANGE = int(os.getenv("TIMEOUT_LANGUAGE_CHANGE", "60"))
TIMEOUT_GEOCODING = int(os.getenv("TIMEOUT_GEOCODING", "10"))
