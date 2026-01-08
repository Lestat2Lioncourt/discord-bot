"""
Fonctions de notification pour les Sages.

Envoie des notifications dans le salon des Sages ou en DM (mode debug).
"""

import discord

from config import CHANNEL_SAGE_ID, DEBUG_MODE, DEBUG_USER
from constants import Teams
from utils.logger import get_logger

from .views import ValidationView

logger = get_logger("cogs.sages.notifications")


async def notify_sages_new_registration(bot, member: discord.Member, profile, players: list):
    """Envoie une notification aux Sages quand un membre termine son inscription."""
    logger.debug(f"notify_sages_new_registration appele pour {member.name} (DEBUG_MODE={DEBUG_MODE})")

    # Construire l'embed
    embed = discord.Embed(
        title="Nouvelle inscription",
        description=f"**{member.display_name}** (@{member.name}) a termine son inscription.",
        color=discord.Color.orange()
    )

    # Statut charte
    charte_status = "Validee" if profile.charte_validated else "Non validee"
    embed.add_field(name="Charte", value=charte_status, inline=True)

    # Joueurs
    if players:
        team1 = [p.player_name for p in players if p.team_name == Teams.TEAM1_NAME]
        team2 = [p.player_name for p in players if p.team_name == Teams.TEAM2_NAME]
        if team1:
            embed.add_field(name=Teams.TEAM1_NAME, value=", ".join(team1), inline=True)
        if team2:
            embed.add_field(name=Teams.TEAM2_NAME, value=", ".join(team2), inline=True)
    else:
        embed.add_field(name="Joueurs", value="Aucun", inline=False)

    # Localisation (affiche pays/region uniquement, pas l'adresse complete)
    if profile.localisation:
        location_display = profile.location_display or profile.localisation
        embed.add_field(name="Localisation", value=location_display, inline=False)

    # Creer la vue avec boutons
    view = ValidationView(bot, member.id, member.name)

    # Determiner ou envoyer
    if DEBUG_MODE:
        # En mode debug, envoyer en DM a DEBUG_USER
        for guild in bot.guilds:
            debug_member = discord.utils.find(
                lambda m: m.name.lower() == DEBUG_USER.lower(),
                guild.members
            )
            if debug_member:
                try:
                    await debug_member.send(embed=embed, view=view)
                    logger.info(f"Notification inscription envoyee a {DEBUG_USER} (debug)")
                except discord.Forbidden:
                    logger.warning(f"Impossible d'envoyer DM a {DEBUG_USER}")
                return
    else:
        # En mode normal, envoyer dans le salon des Sages
        for guild in bot.guilds:
            sage_channel = guild.get_channel(CHANNEL_SAGE_ID)
            if sage_channel:
                await sage_channel.send(embed=embed, view=view)
                logger.info("Notification inscription envoyee dans le salon des Sages")
                return

        logger.warning("Salon des Sages non trouve")


async def notify_sages_returning_member(bot, member: discord.Member, returning_info: dict):
    """
    Alerte les Sages quand un 'revenant' est detecte.

    Un revenant est un membre qui revient avec un nouveau username Discord.
    Ne notifie que si le username a change.
    """
    old_username = returning_info['old_username']
    logger.info(f"Revenant detecte: {member.name} (ancien: {old_username})")

    # Couleur selon le statut precedent
    previous_status = returning_info['previous_status']
    if previous_status == 'refused':
        color = discord.Color.red()
        status_emoji = "!"
        status_text = "REFUSE precedemment"
    elif previous_status == 'deleted':
        color = discord.Color.orange()
        status_emoji = "~"
        status_text = "Ancien membre SUPPRIME"
    elif previous_status == 'approved':
        color = discord.Color.green()
        status_emoji = "+"
        status_text = "Ancien membre approuve"
    else:
        color = discord.Color.orange()
        status_emoji = "?"
        status_text = "Etait en attente"

    # Format demande: "inscription de NouveauNom, precedemment inscrit sous le nom AncienNom"
    embed = discord.Embed(
        title=f"{status_emoji} Revenant detecte!",
        description=f"Inscription de **{member.name}**, precedemment inscrit sous le nom **{old_username}**",
        color=color
    )

    embed.add_field(
        name="Nouveau username",
        value=f"`{member.name}`",
        inline=True
    )

    embed.add_field(
        name="Ancien username",
        value=f"`{old_username}`",
        inline=True
    )

    if returning_info['old_discord_name']:
        embed.add_field(
            name="Ancien pseudo",
            value=returning_info['old_discord_name'],
            inline=True
        )

    embed.add_field(
        name="Statut precedent",
        value=status_text,
        inline=True
    )

    if returning_info['last_seen']:
        embed.add_field(
            name="Derniere activite",
            value=returning_info['last_seen'].strftime("%d/%m/%Y"),
            inline=True
        )

    embed.set_footer(text="Verifiez l'historique avant de valider")

    # Envoyer la notification (meme logique que pour les inscriptions)
    if DEBUG_MODE:
        for guild in bot.guilds:
            debug_member = discord.utils.find(
                lambda m: m.name.lower() == DEBUG_USER.lower(),
                guild.members
            )
            if debug_member:
                try:
                    await debug_member.send(embed=embed)
                    logger.info(f"Alerte revenant envoyee a {DEBUG_USER} (debug)")
                except discord.Forbidden:
                    logger.warning(f"Impossible d'envoyer DM a {DEBUG_USER}")
                return
    else:
        for guild in bot.guilds:
            sage_channel = guild.get_channel(CHANNEL_SAGE_ID)
            if sage_channel:
                await sage_channel.send(embed=embed)
                logger.info("Alerte revenant envoyee dans le salon des Sages")
                return

        logger.warning("Salon des Sages non trouve pour alerte revenant")


async def notify_sages_deletion_pending(bot, member: discord.Member, requesting_sage: discord.Member, player_count: int):
    """
    Notifie les Sages qu'une suppression est en attente de double validation.

    Args:
        bot: Instance du bot
        member: Membre a supprimer
        requesting_sage: Sage qui demande la suppression
        player_count: Nombre de joueurs associes
    """
    logger.info(f"Suppression en attente: {member.name} demandee par {requesting_sage.name}")

    embed = discord.Embed(
        title="Suppression en attente de validation",
        description=(
            f"**{requesting_sage.display_name}** demande la suppression de **{member.display_name}** (@{member.name}).\n\n"
            f"**Un autre Sage doit confirmer cette action.**"
        ),
        color=discord.Color.red()
    )

    embed.add_field(name="Membre a supprimer", value=f"{member.display_name} (@{member.name})", inline=True)
    embed.add_field(name="Demande par", value=requesting_sage.display_name, inline=True)
    embed.add_field(name="Joueurs associes", value=str(player_count), inline=True)
    embed.set_footer(text="Rendez-vous dans le salon ou la commande a ete executee pour valider/annuler")

    # Envoyer la notification
    if DEBUG_MODE:
        for guild in bot.guilds:
            debug_member = discord.utils.find(
                lambda m: m.name.lower() == DEBUG_USER.lower(),
                guild.members
            )
            if debug_member:
                try:
                    await debug_member.send(embed=embed)
                    logger.info(f"Notification suppression envoyee a {DEBUG_USER} (debug)")
                except discord.Forbidden:
                    logger.warning(f"Impossible d'envoyer DM a {DEBUG_USER}")
                return
    else:
        for guild in bot.guilds:
            sage_channel = guild.get_channel(CHANNEL_SAGE_ID)
            if sage_channel:
                await sage_channel.send(embed=embed)
                logger.info("Notification suppression envoyee dans le salon des Sages")
                return

        logger.warning("Salon des Sages non trouve pour notification suppression")
