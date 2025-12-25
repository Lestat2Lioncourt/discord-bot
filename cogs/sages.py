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
from utils.i18n import t
from config import CHANNEL_ACCUEIL_ID

logger = get_logger("cogs.sages")


def sage_only():
    """Decorateur pour limiter une commande aux Sages."""
    async def predicate(ctx):
        if not is_sage(ctx.author):
            await ctx.send(t("errors.sage_only", "FR"))  # Default FR, user may not have a profile
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
        # Recuperer la langue du sage
        async with self.bot.db_pool.acquire() as conn:
            sage_profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        lang = sage_profile.language or "FR"

        pending = await UserProfile.get_pending_members(self.bot.db_pool)

        if not pending:
            await ctx.send(t("sages_cmd.pending_none", lang))
            return

        embed = discord.Embed(
            title=t("sages_cmd.pending_title", lang),
            color=discord.Color.orange(),
            description=t("sages_cmd.pending_count", lang, count=len(pending))
        )

        for member_data in pending[:25]:  # Limite Discord : 25 fields
            username = member_data['username']
            discord_name = member_data.get('discord_name', username)

            # Recuperer les joueurs
            players = await Player.get_by_member(self.bot.db_pool, username)
            no_players = t("sages_cmd.pending_no_players", lang)
            players_str = ", ".join([p.player_name for p in players]) if players else no_players

            embed.add_field(
                name=f"{discord_name} (@{username})",
                value=f"{t('sages_cmd.pending_players', lang)}: {players_str}",
                inline=False
            )

        embed.set_footer(text=t("sages_cmd.pending_footer", lang))
        await ctx.send(embed=embed)

    @commands.command(name="valider", aliases=["approve", "accepter"])
    @sage_only()
    async def cmd_valider(self, ctx, member: discord.Member):
        """Valide un membre en attente. Usage: !valider @user"""
        username = member.name

        # Langue du sage pour les messages de confirmation
        async with self.bot.db_pool.acquire() as conn:
            sage_profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        sage_lang = sage_profile.language or "FR"

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            member_lang = profile.language or "FR"

            # Verifier que le membre est bien en attente
            if profile.approval_status == "approved":
                await ctx.send(t("sages_cmd.already_approved", sage_lang, member=member.mention))
                return

            if not profile.charte_validated:
                await ctx.send(t("sages_cmd.charte_not_validated", sage_lang, member=member.mention))
                return

            # Approuver
            await profile.approve()

        # Promouvoir (Newbie -> Membre)
        success = await promote_to_membre(member)

        if success:
            await ctx.send(t("sages_cmd.validated_success", sage_lang, member=member.mention))

            # Message de bienvenue public dans le canal d'accueil (langue du membre)
            accueil_channel = ctx.guild.get_channel(CHANNEL_ACCUEIL_ID)
            if accueil_channel:
                await accueil_channel.send(
                    t("sages_cmd.welcome_public", member_lang, member=member.mention, guild=ctx.guild.name)
                )

            # Notifier le membre en DM (langue du membre)
            try:
                await member.send(t("finish.approved", member_lang, sage_name=ctx.author.display_name))
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer DM a {username}")

            logger.info(f"{username} valide par {ctx.author.name}")
        else:
            await ctx.send(t("sages_cmd.validated_error", sage_lang, member=member.mention))

    @commands.command(name="refuser", aliases=["refuse", "reject"])
    @sage_only()
    async def cmd_refuser(self, ctx, member: discord.Member, *, raison: str = None):
        """Refuse un membre. Usage: !refuser @user [raison]"""
        username = member.name

        # Langue du sage pour les messages de confirmation
        async with self.bot.db_pool.acquire() as conn:
            sage_profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        sage_lang = sage_profile.language or "FR"

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            member_lang = profile.language or "FR"

            if profile.approval_status == "refused":
                await ctx.send(t("sages_cmd.already_refused", sage_lang, member=member.mention))
                return

            # Refuser
            await profile.refuse()

        # Retrograder si necessaire
        await demote_to_newbie(member)

        # Message de confirmation
        msg = t("sages_cmd.refused_success", sage_lang, member=member.mention)
        if raison:
            msg += "\n" + t("sages_cmd.refused_reason", sage_lang, reason=raison)
        await ctx.send(msg)

        # Notifier le membre en DM (langue du membre)
        try:
            dm_msg = t("finish.refused", member_lang)
            if raison:
                dm_msg += "\n\n" + t("finish.refused_reason", member_lang, reason=raison)
            dm_msg += "\n\n" + t("finish.refused_contact", member_lang)

            await member.send(dm_msg)
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer DM a {username}")

        logger.info(f"{username} refuse par {ctx.author.name}" + (f" - Raison: {raison}" if raison else ""))

    @commands.command(name="profil-admin", aliases=["profile-admin"])
    async def cmd_profil_admin(self, ctx, *, search: str = None):
        """Affiche le profil complet d'un membre (vue admin). Usage: !profil-admin detrax"""
        # Verification Sage (manuelle car peut etre en DM)
        is_sage_user = False
        for guild in self.bot.guilds:
            member_in_guild = guild.get_member(ctx.author.id)
            if member_in_guild and is_sage(member_in_guild):
                is_sage_user = True
                break

        if not is_sage_user:
            await ctx.send(t("errors.sage_only", "FR"))
            return

        if not search:
            if ctx.author.guild:
                await ctx.send("**Usage:** `!profil-admin <nom>` (ex: `!profil-admin detrax`)")
            else:
                await ctx.author.send("**Usage:** `!profil-admin <nom>` (ex: `!profil-admin detrax`)")
            return

        # Langue du sage
        async with self.bot.db_pool.acquire() as conn:
            sage_profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        lang = sage_profile.language or "FR"

        # Nettoyer la recherche (enlever @ si present)
        search = search.strip().lstrip('@').lower()

        # Chercher dans la base de donnees (insensible a la casse)
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT username, discord_name FROM user_profile
                   WHERE LOWER(username) LIKE $1 OR LOWER(discord_name) LIKE $1
                   LIMIT 10""",
                f"%{search}%"
            )

        if not rows:
            no_result = "Aucun membre trouve." if lang.upper() == "FR" else "No member found."
            await ctx.author.send(f"{no_result} (`{search}`)")
            return

        # Afficher tous les profils trouves
        if len(rows) > 1:
            count_msg = f"**{len(rows)} membres trouves pour `{search}` :**" if lang.upper() == "FR" else f"**{len(rows)} members found for `{search}`:**"
            await ctx.author.send(count_msg)

        for row in rows:
            username = row['username']
            await self._send_profile_embed(ctx, username, lang)

        # Si la commande a ete lancee dans un salon public, confirmer
        if ctx.guild:
            if len(rows) > 1:
                confirm = f"{len(rows)} profils envoyes en DM." if lang.upper() == "FR" else f"{len(rows)} profiles sent via DM."
            else:
                confirm = "Profil envoye en DM." if lang.upper() == "FR" else "Profile sent via DM."
            await ctx.send(confirm)

    async def _send_profile_embed(self, ctx, username: str, lang: str):
        """Envoie l'embed de profil pour un utilisateur."""
        # Charger le profil
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_by_username(conn, username)
            if profile:
                await profile.load_from_db()

        if not profile:
            return

        # Chercher le membre Discord dans les guilds
        discord_member = None
        for guild in self.bot.guilds:
            discord_member = discord.utils.find(
                lambda m: m.name.lower() == username.lower(),
                guild.members
            )
            if discord_member:
                break

        players = await Player.get_by_member(self.bot.db_pool, username)

        display_name = discord_member.display_name if discord_member else (profile.discord_name or username)

        embed = discord.Embed(
            title=t("sages_cmd.profil_admin_title", lang, name=display_name),
            color=discord.Color.blue()
        )

        # Username
        embed.add_field(name="Username", value=f"`{username}`", inline=True)

        # Statut
        embed.add_field(
            name=t("sages_cmd.profil_admin_status", lang),
            value=profile.get_status_display(),
            inline=True
        )

        # Roles (seulement si on a trouve le membre Discord)
        if discord_member:
            roles = [r.name for r in discord_member.roles if r.name != "@everyone"]
            embed.add_field(
                name=t("sages_cmd.profil_admin_roles", lang),
                value=", ".join(roles) if roles else t("sages_cmd.profil_admin_no_roles", lang),
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
            embed.add_field(
                name=t("sages_cmd.profil_admin_players", lang),
                value=t("sages_cmd.profil_admin_no_players", lang),
                inline=False
            )

        # Localisation
        if profile.localisation:
            loc_str = profile.localisation
            if profile.latitude and profile.longitude:
                loc_str += f" ({profile.latitude:.2f}, {profile.longitude:.2f})"
            embed.add_field(name=t("sages_cmd.profil_admin_location", lang), value=loc_str, inline=False)

        # Dates
        if profile.creation_date:
            embed.add_field(
                name=t("sages_cmd.profil_admin_registered", lang),
                value=profile.creation_date.strftime("%d/%m/%Y"),
                inline=True
            )
        if profile.last_connection:
            embed.add_field(
                name=t("sages_cmd.profil_admin_last_seen", lang),
                value=profile.last_connection.strftime("%d/%m/%Y %H:%M"),
                inline=True
            )

        # Envoyer en DM
        await ctx.author.send(embed=embed)


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(SagesCog(bot))
