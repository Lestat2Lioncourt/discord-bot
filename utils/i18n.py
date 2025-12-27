"""
Systeme d'internationalisation (i18n) pour le bot.
Supporte FR et EN.
"""

import json
from pathlib import Path
from typing import Optional

from config import BASE_DIR
from utils.logger import get_logger

logger = get_logger("i18n")

# Charger les traductions au demarrage
LOCALES_DIR = BASE_DIR / "locales"
TRANSLATIONS = {}

SUPPORTED_LANGUAGES = ["FR", "EN"]
DEFAULT_LANGUAGE = "FR"


def load_translations():
    """Charge tous les fichiers de traduction."""
    global TRANSLATIONS

    for lang in SUPPORTED_LANGUAGES:
        # Fichiers en minuscules (fr.json, en.json), cles en majuscules
        file_path = LOCALES_DIR / f"{lang.lower()}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                TRANSLATIONS[lang] = json.load(f)
                logger.debug(f"Traductions {lang} chargees")
        else:
            logger.warning(f"Fichier de traduction manquant: {file_path}")


def get_text(key: str, lang: str = None, **kwargs) -> str:
    """
    Recupere un texte traduit.

    Args:
        key: Cle de traduction (ex: "welcome.title", "charte.accepted")
        lang: Code langue (fr, en, FR, EN). Par defaut: fr
        **kwargs: Variables a substituer dans le texte

    Returns:
        Le texte traduit avec les variables substituees
    """
    if not TRANSLATIONS:
        load_translations()

    # Normaliser en majuscules (convention: FR, EN)
    lang = (lang or DEFAULT_LANGUAGE).upper()
    if lang not in TRANSLATIONS:
        lang = DEFAULT_LANGUAGE

    # Naviguer dans les cles imbriquees
    keys = key.split(".")
    value = TRANSLATIONS.get(lang, {})

    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break

    if value is None:
        logger.warning(f"Cle de traduction manquante: {key} ({lang})")
        return key

    # Substituer les variables
    if kwargs:
        try:
            value = value.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Variable manquante dans traduction {key}: {e}")

    return value


def t(key: str, lang: str = None, **kwargs) -> str:
    """Alias court pour get_text."""
    return get_text(key, lang, **kwargs)


class Translator:
    """Classe helper pour traduire avec une langue fixe."""

    def __init__(self, lang: str = None):
        self.lang = (lang or DEFAULT_LANGUAGE).upper()

    def __call__(self, key: str, **kwargs) -> str:
        return get_text(key, self.lang, **kwargs)

    def set_lang(self, lang: str):
        """Change la langue du traducteur."""
        normalized = lang.upper() if lang else DEFAULT_LANGUAGE
        if normalized in SUPPORTED_LANGUAGES:
            self.lang = normalized


# Charger les traductions au import
load_translations()
