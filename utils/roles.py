"""
Utilitaires pour la gestion des rôles Discord.
"""

import discord
from typing import Optional

from config import ROLE_NEWBIE_ID, ROLE_MEMBRE_ID, ROLE_SAGE_ID
from utils.logger import get_logger

logger = get_logger("roles")


def get_role(guild: discord.Guild, role_id: int) -> Optional[discord.Role]:
    """Récupère un rôle par son ID."""
    return guild.get_role(role_id)


def is_sage(member: discord.Member) -> bool:
    """Vérifie si le membre a le rôle Sage."""
    return any(role.id == ROLE_SAGE_ID for role in member.roles)


def is_membre(member: discord.Member) -> bool:
    """Vérifie si le membre a le rôle Membre."""
    return any(role.id == ROLE_MEMBRE_ID for role in member.roles)


def is_newbie(member: discord.Member) -> bool:
    """Vérifie si le membre a le rôle Newbie."""
    return any(role.id == ROLE_NEWBIE_ID for role in member.roles)


async def assign_newbie_role(member: discord.Member) -> bool:
    """
    Attribue le rôle Newbie à un nouveau membre.
    Retourne True si succès, False sinon.
    """
    role = get_role(member.guild, ROLE_NEWBIE_ID)
    if not role:
        logger.error(f"Rôle Newbie (ID: {ROLE_NEWBIE_ID}) introuvable")
        return False

    try:
        await member.add_roles(role, reason="Nouveau membre")
        logger.info(f"Rôle Newbie attribué à {member.name}")
        return True
    except discord.Forbidden:
        logger.error(f"Permission refusée pour attribuer Newbie à {member.name}")
        return False
    except discord.HTTPException as e:
        logger.error(f"Erreur attribution Newbie à {member.name}: {e}")
        return False


async def promote_to_membre(member: discord.Member) -> bool:
    """
    Promeut un Newbie en Membre (remplace Newbie par Membre).
    Retourne True si succès, False sinon.
    """
    newbie_role = get_role(member.guild, ROLE_NEWBIE_ID)
    membre_role = get_role(member.guild, ROLE_MEMBRE_ID)

    if not membre_role:
        logger.error(f"Rôle Membre (ID: {ROLE_MEMBRE_ID}) introuvable")
        return False

    try:
        # Ajouter le rôle Membre
        await member.add_roles(membre_role, reason="Approuvé par un Sage")
        logger.info(f"Rôle Membre attribué à {member.name}")

        # Retirer le rôle Newbie si présent
        if newbie_role and is_newbie(member):
            await member.remove_roles(newbie_role, reason="Promu en Membre")
            logger.info(f"Rôle Newbie retiré de {member.name}")

        return True
    except discord.Forbidden:
        logger.error(f"Permission refusée pour promouvoir {member.name}")
        return False
    except discord.HTTPException as e:
        logger.error(f"Erreur promotion de {member.name}: {e}")
        return False


async def demote_to_newbie(member: discord.Member) -> bool:
    """
    Rétrograde un Membre en Newbie (en cas de refus d'inscription).
    Retourne True si succès, False sinon.
    """
    newbie_role = get_role(member.guild, ROLE_NEWBIE_ID)
    membre_role = get_role(member.guild, ROLE_MEMBRE_ID)

    if not newbie_role:
        logger.error(f"Rôle Newbie (ID: {ROLE_NEWBIE_ID}) introuvable")
        return False

    try:
        # Ajouter le rôle Newbie
        await member.add_roles(newbie_role, reason="Inscription refusée")

        # Retirer le rôle Membre si présent
        if membre_role and is_membre(member):
            await member.remove_roles(membre_role, reason="Inscription refusée")

        logger.info(f"{member.name} rétrogradé en Newbie")
        return True
    except discord.Forbidden:
        logger.error(f"Permission refusée pour rétrograder {member.name}")
        return False
    except discord.HTTPException as e:
        logger.error(f"Erreur rétrogradation de {member.name}: {e}")
        return False
