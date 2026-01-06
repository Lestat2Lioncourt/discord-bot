"""
Utilitaires pour le mode debug.
"""

from functools import wraps
from discord.ext import commands

from config import DEBUG_MODE, DEBUG_USER
from utils.logger import get_logger

logger = get_logger("debug")

# Utilisateurs avec droits sudo temporaires (debug uniquement)
_sudo_users: set[int] = set()


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


# =============================================================================
# Fonctions sudo (debug uniquement)
# =============================================================================

def is_sudo(user_id: int) -> bool:
    """Vérifie si un utilisateur a les droits sudo (debug uniquement)."""
    if not DEBUG_MODE:
        return False
    return user_id in _sudo_users


def toggle_sudo(user_id: int) -> bool:
    """
    Active/désactive le mode sudo pour un utilisateur.

    Returns:
        True si sudo activé, False si désactivé.
    """
    if not DEBUG_MODE:
        return False

    if user_id in _sudo_users:
        _sudo_users.discard(user_id)
        logger.info(f"Sudo désactivé pour {user_id}")
        return False
    else:
        _sudo_users.add(user_id)
        logger.info(f"Sudo activé pour {user_id}")
        return True


def clear_sudo() -> None:
    """Retire tous les droits sudo."""
    _sudo_users.clear()
    logger.info("Tous les droits sudo ont été retirés")
