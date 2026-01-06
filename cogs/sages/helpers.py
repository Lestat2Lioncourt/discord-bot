"""
Fonctions utilitaires pour les commandes Sage.

Fournit la verification des droits Sage et le decorateur @sage_only().
"""

from discord.ext import commands

from utils.roles import is_sage
from utils.i18n import t
from utils.debug import is_sudo
from config import SERVER_ID


def check_is_sage(user, bot) -> bool:
    """
    Verifie si un utilisateur est Sage.

    Fonctionne en contexte serveur (Member avec roles) et en DM (User sans roles).
    En DM, utilise SERVER_ID pour trouver le membre directement.
    En mode DEBUG, les utilisateurs avec sudo sont aussi consideres Sage.

    Args:
        user: L'utilisateur (Member ou User)
        bot: Instance du bot

    Returns:
        True si l'utilisateur est Sage, False sinon
    """
    # Mode sudo (debug uniquement)
    if is_sudo(user.id):
        return True

    if hasattr(user, 'roles') and user.roles:
        # Contexte serveur : user est un Member avec roles
        return is_sage(user)

    # Contexte DM ou cache vide : chercher dans le serveur principal
    if SERVER_ID:
        guild = bot.get_guild(SERVER_ID)
        if guild:
            member = guild.get_member(user.id)
            if member:
                return is_sage(member)
    return False


def sage_only():
    """Decorateur pour limiter une commande aux Sages."""
    async def predicate(ctx):
        if not check_is_sage(ctx.author, ctx.bot):
            await ctx.send(t("errors.sage_only", "FR"))
            return False
        return True
    return commands.check(predicate)
