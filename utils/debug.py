"""
Utilitaires pour le mode debug.
"""

from functools import wraps
from discord.ext import commands

from config import DEBUG_MODE, DEBUG_USER
from utils.logger import get_logger

logger = get_logger("debug")


def debug_only():
    """
    Décorateur qui restreint une commande au DEBUG_USER quand DEBUG_MODE=true.

    Usage:
        @bot.command()
        @debug_only()
        async def ma_commande(ctx):
            ...
    """
    async def predicate(ctx):
        if not DEBUG_MODE:
            return True

        username = ctx.author.name
        if username == DEBUG_USER:
            return True

        logger.debug(f"Commande bloquée pour {username} (mode debug)")
        return False

    return commands.check(predicate)


def is_debug_user(ctx) -> bool:
    """Vérifie si l'utilisateur est le DEBUG_USER."""
    return ctx.author.name == DEBUG_USER


def is_debug_mode() -> bool:
    """Retourne True si le mode debug est activé."""
    return DEBUG_MODE
