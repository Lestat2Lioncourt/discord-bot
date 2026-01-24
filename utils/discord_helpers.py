"""
Helpers pour les operations Discord communes.

Ce module centralise les fonctions utilitaires partagees entre les cogs.
"""

import discord
from discord.ext import commands
from typing import Optional, List, Tuple, Union
from utils.logger import get_logger

logger = get_logger("utils.discord_helpers")


async def reply_dm(
    ctx: commands.Context,
    content: str = None,
    *,
    embed: discord.Embed = None,
    file: discord.File = None,
    view: discord.ui.View = None,
    silent: bool = False
) -> Union[discord.Message, bool]:
    """
    Repond en DM a l'utilisateur. Si appele depuis un salon, notifie.

    Args:
        ctx: Contexte de la commande
        content: Message texte (optionnel)
        embed: Embed Discord (optionnel)
        file: Fichier a envoyer (optionnel)
        view: View Discord avec boutons/selects (optionnel)
        silent: Si True, ne pas notifier dans le salon d'origine

    Returns:
        Message envoye si succes, False si echec
    """
    try:
        # Preparer les kwargs
        kwargs = {}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if file:
            kwargs["file"] = file
        if view:
            kwargs["view"] = view

        # Envoyer en DM
        msg = await ctx.author.send(**kwargs)

        # Si on etait dans un salon public, notifier (sauf si silent)
        if ctx.guild and not silent:
            await ctx.send("Reponse envoyee en DM.")

        return msg

    except discord.Forbidden:
        # DMs fermes - envoyer dans le salon
        logger.warning(f"Impossible d'envoyer DM a {ctx.author.name}, fallback salon")
        kwargs = {}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if file:
            kwargs["file"] = file
        if view:
            kwargs["view"] = view
        await ctx.send(**kwargs)
        return False


async def find_member(
    bot,
    search: str,
    guild: discord.Guild = None,
    require_unique: bool = False
) -> Tuple[Optional[discord.Member], List[discord.Member], Optional[str]]:
    """
    Recherche un membre par username OU display_name.

    Args:
        bot: Instance du bot Discord
        search: Terme de recherche (partiel, insensible a la casse)
        guild: Guild specifique ou None pour chercher partout
        require_unique: Si True, retourne erreur si plusieurs resultats

    Returns:
        Tuple (member, all_matches, message):
        - member: Le membre trouve (ou None si erreur/aucun)
        - all_matches: Liste de tous les membres correspondants
        - message: Message d'erreur ou warning (ou None si OK)

    Exemples:
        # Lecture (plusieurs OK)
        member, matches, msg = await find_member(bot, "jean")
        if member:
            # Afficher profil(s)

        # Ecriture (unique requis)
        member, matches, msg = await find_member(bot, "jean", require_unique=True)
        if msg:
            await ctx.send(msg)
            return
        # Proceder avec member
    """
    search = search.strip().lstrip('@').lower()
    matches = []
    seen_ids = set()  # Eviter les doublons si membre dans plusieurs guilds

    # Determiner les guilds a parcourir
    guilds_to_search = [guild] if guild else bot.guilds

    for g in guilds_to_search:
        for member in g.members:
            if member.id in seen_ids:
                continue

            # Chercher dans username ET display_name
            username_match = search in member.name.lower()
            display_match = search in (member.display_name or "").lower()

            if username_match or display_match:
                matches.append(member)
                seen_ids.add(member.id)

    # Aucun resultat
    if not matches:
        return None, [], f"Aucun membre trouve pour `{search}`"

    # Un seul resultat -> OK
    if len(matches) == 1:
        return matches[0], matches, None

    # Plusieurs resultats
    if require_unique:
        names = ", ".join([f"`{m.display_name}`" for m in matches[:5]])
        suffix = f" (+{len(matches) - 5})" if len(matches) > 5 else ""
        return None, matches, f"Plusieurs membres correspondent a `{search}`: {names}{suffix}. Precisez votre recherche."

    # Plusieurs mais pas require_unique -> retourne le premier avec warning
    return matches[0], matches, f"plusieurs membres correspondent ({len(matches)})"


async def find_member_strict(
    bot,
    search: str,
    guild: discord.Guild = None
) -> Tuple[Optional[discord.Member], Optional[str]]:
    """
    Recherche un membre avec exigence d'unicite (pour actions d'ecriture).

    Raccourci pour find_member(..., require_unique=True).

    Args:
        bot: Instance du bot Discord
        search: Terme de recherche
        guild: Guild specifique ou None

    Returns:
        Tuple (member, error_message)
    """
    member, _, error = await find_member(bot, search, guild, require_unique=True)
    return member, error
