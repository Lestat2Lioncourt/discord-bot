"""
Cog pour les commandes reservees aux Sages.

Commandes:
- !pending : Liste les inscriptions en attente
- !valider @user : Valide un membre (Newbie -> Membre)
- !refuser @user [raison] : Refuse un membre
"""

import discord
from discord.ext import commands
from typing import Optional

from models.user_profile import UserProfile
from models.player import Player
from utils.logger import get_logger
from utils.roles import is_sage, promote_to_membre, demote_to_newbie

logger = get_logger("cogs.sages")


def sage_only():
    """Decorateur pour limiter une commande aux Sages."""
    async def predicate(ctx):
        if not is_sage(ctx.author):
            await ctx.send("Cette commande est reservee aux Sages.")
            return False
        return True
    return commands.check(predicate)


class SagesCog(commands.Cog):
    """Cog pour les commandes des Sages."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="pending", aliases=["attente", "inscriptions"])
    @sage_only()
    async def cmd_pending(self, ctx):
        """Liste les inscriptions en attente de validation."""
        pending = await UserProfile.get_pending_members(self.bot.db_pool)

        if not pending:
            await ctx.send("Aucune inscription en attente.")
            return

        embed = discord.Embed(
            title="Inscriptions en attente",
            color=discord.Color.orange(),
            description=f"{len(pending)} membre(s) en attente"
        )

        for member_data in pending[:25]:  # Limite Discord : 25 fields
            username = member_data['username']
            discord_name = member_data.get('discord_name', username)

            # Recuperer les joueurs
            players = await Player.get_by_member(self.bot.db_pool, username)
            players_str = ", ".join([p.player_name for p in players]) if players else "Aucun"

            embed.add_field(
                name=f"{discord_name} (@{username})",
                value=f"Joueurs: {players_str}",
                inline=False
            )

        embed.set_footer(text="Utilise !valider @user ou !refuser @user [raison]")
        await ctx.send(embed=embed)

    @commands.command(name="valider", aliases=["approve", "accepter"])
    @sage_only()
    async def cmd_valider(self, ctx, member: discord.Member):
        """Valide un membre en attente. Usage: !valider @user"""
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)

            # Verifier que le membre est bien en attente
            if profile.approval_status == "approved":
                await ctx.send(f"{member.mention} est deja approuve.")
                return

            if not profile.charte_validated:
                await ctx.send(f"{member.mention} n'a pas encore valide la charte.")
                return

            # Approuver
            await profile.approve()

        # Promouvoir (Newbie -> Membre)
        success = await promote_to_membre(member)

        if success:
            await ctx.send(f"{member.mention} a ete valide et promu Membre !")

            # Notifier le membre en DM
            try:
                await member.send(
                    f"Felicitations ! Ta candidature a ete **validee** par {ctx.author.display_name}.\n"
                    f"Tu as maintenant acces a tous les salons du serveur.\n\n"
                    f"Bienvenue dans la team !"
                )
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer DM a {username}")

            logger.info(f"{username} valide par {ctx.author.name}")
        else:
            await ctx.send(f"Erreur lors de la promotion de {member.mention}. Verifie les permissions.")

    @commands.command(name="refuser", aliases=["refuse", "reject"])
    @sage_only()
    async def cmd_refuser(self, ctx, member: discord.Member, *, raison: str = None):
        """Refuse un membre. Usage: !refuser @user [raison]"""
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)

            if profile.approval_status == "refused":
                await ctx.send(f"{member.mention} est deja refuse.")
                return

            # Refuser
            await profile.refuse()

        # Retrograder si necessaire
        await demote_to_newbie(member)

        # Message de confirmation
        raison_txt = f"\nRaison: {raison}" if raison else ""
        await ctx.send(f"{member.mention} a ete refuse.{raison_txt}")

        # Notifier le membre en DM
        try:
            msg = f"Ta candidature a ete **refusee** par un Sage."
            if raison:
                msg += f"\n\n**Raison:** {raison}"
            msg += "\n\nSi tu penses que c'est une erreur, contacte un Sage."

            await member.send(msg)
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer DM a {username}")

        logger.info(f"{username} refuse par {ctx.author.name}" + (f" - Raison: {raison}" if raison else ""))

    @commands.command(name="profil-admin", aliases=["profile-admin"])
    @sage_only()
    async def cmd_profil_admin(self, ctx, member: discord.Member):
        """Affiche le profil complet d'un membre (vue admin)."""
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.load_from_db()

        players = await Player.get_by_member(self.bot.db_pool, username)

        embed = discord.Embed(
            title=f"Profil de {member.display_name}",
            color=discord.Color.blue()
        )

        # Statut
        embed.add_field(
            name="Statut",
            value=profile.get_status_display(),
            inline=False
        )

        # Roles
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        embed.add_field(
            name="Roles",
            value=", ".join(roles) if roles else "Aucun",
            inline=False
        )

        # Joueurs
        if players:
            team1 = [p.player_name for p in players if p.team_name == "This Is PSG"]
            team2 = [p.player_name for p in players if p.team_name == "This Is PSG 2"]

            if team1:
                embed.add_field(name="This Is PSG", value=", ".join(team1), inline=True)
            if team2:
                embed.add_field(name="This Is PSG 2", value=", ".join(team2), inline=True)
        else:
            embed.add_field(name="Joueurs", value="Aucun", inline=False)

        # Localisation
        if profile.localisation:
            loc_str = profile.localisation
            if profile.latitude and profile.longitude:
                loc_str += f" ({profile.latitude:.2f}, {profile.longitude:.2f})"
            embed.add_field(name="Localisation", value=loc_str, inline=False)

        # Dates
        if profile.creation_date:
            embed.add_field(
                name="Inscription",
                value=profile.creation_date.strftime("%d/%m/%Y"),
                inline=True
            )
        if profile.last_connection:
            embed.add_field(
                name="Derniere connexion",
                value=profile.last_connection.strftime("%d/%m/%Y %H:%M"),
                inline=True
            )

        await ctx.send(embed=embed)


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(SagesCog(bot))
