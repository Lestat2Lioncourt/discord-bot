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
}

if not DB_CONFIG["password"]:
    raise ValueError(
        "DB_PASSWORD non défini. "
        "Créez un fichier .env à partir de .env.example"
    )

# =============================================================================
# Fichiers de données
# =============================================================================
CHARTE_JSON_PATH = DATA_DIR / "charte.json"

# Fichiers texte de la charte
CHARTE_TEXTS = {
    "0a_intro": TEXTS_DIR / "charte_0a_intro.txt",
    "0b_intro": TEXTS_DIR / "charte_0b_intro.txt",
    "1_regles_generales": TEXTS_DIR / "charte_1_regles_generales.txt",
    "2_structure_roles": TEXTS_DIR / "charte_2_structure_roles.txt",
    "3_regles_fonctionnement": TEXTS_DIR / "charte_3_regles_fonctionnement.txt",
    "4_sanctions": TEXTS_DIR / "charte_4_sanctions.txt",
    "5_engagement": TEXTS_DIR / "charte_5_engagement.txt",
}

# =============================================================================
# Configuration du Bot
# =============================================================================
BOT_PREFIX = "!"
