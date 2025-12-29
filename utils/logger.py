"""
Configuration centralisée du logging pour le bot Discord.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOGS_DIR


def setup_logger(name: str = "discord_bot", level: int = logging.INFO) -> logging.Logger:
    """
    Configure et retourne un logger avec sortie console et fichier.

    Args:
        name: Nom du logger
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Logger configuré
    """
    logger = logging.getLogger(name)

    # Éviter les duplications si le logger est déjà configuré
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Format pour la console (simplifié)
    console_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # Format pour le fichier (détaillé)
    file_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # Handler fichier avec rotation
    log_file = LOGS_DIR / "bot.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Ne pas propager au logger racine
    logger.propagate = False

    return logger


# Logger principal du bot
bot_logger = setup_logger("discord_bot")


def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger enfant du logger principal.

    Args:
        name: Nom du module (ex: "cogs.events")

    Returns:
        Logger configuré
    """
    return logging.getLogger(f"discord_bot.{name}")
