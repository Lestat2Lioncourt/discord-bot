"""
Cog pour les commandes reservees aux Sages.

Commandes:
- !pending : Liste les inscriptions en attente
- !valider <nom> : Valide un membre (Newbie -> Membre)
- !refuser <nom> [raison] : Refuse un membre
"""

import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from typing import Optional
import asyncio

from models.user_profile import UserProfile
from models.player import Player
from utils.logger import get_logger
from utils.roles import is_sage, promote_to_membre, demote_to_newbie
from utils.i18n import t
from config import CHANNEL_ACCUEIL_ID, CHANNEL_SAGE_ID, DEBUG_MODE, DEBUG_USER

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

    async def _find_member_by_name(self, ctx, search: str) -> Optional[discord.Member]:
        """Recherche un membre par nom (partiel, insensible a la casse)."""
        search = search.strip().lstrip('@').lower()

        # Chercher dans tous les membres du serveur
        if ctx.guild:
            for member in ctx.guild.members:
                if (search in member.name.lower() or
                    search in (member.display_name or "").lower()):
                    return member

        # Chercher dans tous les guilds du bot
        for guild in self.bot.guilds:
            for member in guild.members:
                if (search in member.name.lower() or
                    search in (member.display_name or "").lower()):
                    return member

        return None

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
    async def cmd_valider(self, ctx, *, search: str = None):
        """Valide un membre en attente. Usage: !valider <nom>"""
        if not search:
            await ctx.send("**Usage:** `!valider <nom>` (ex: `!valider detrax`)")
            return

        # Langue du sage
        async with self.bot.db_pool.acquire() as conn:
            sage_profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        sage_lang = sage_profile.language or "FR"

        # Rechercher le membre
        member = await self._find_member_by_name(ctx, search)
        if not member:
            msg = f"Membre `{search}` non trouve." if sage_lang == "FR" else f"Member `{search}` not found."
            await ctx.send(msg)
            return

        await self._validate_member(ctx, member, sage_lang)

    async def _do_validate(self, interaction: Interaction, member: discord.Member):
        """Validation depuis un bouton (interaction deja repondue)."""
        sage = interaction.user
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            member_lang = profile.language or "FR"

            if profile.approval_status == "approved":
                await interaction.followup.send(f"{member.mention} est deja approuve.", ephemeral=True)
                return

            if not profile.charte_validated:
                await interaction.followup.send(f"{member.mention} n'a pas valide la charte.", ephemeral=True)
                return

            await profile.approve()

        success = await promote_to_membre(member)

        if success:
            await interaction.followup.send(f"{member.mention} a ete valide!")

            guild = member.guild
            if guild:
                accueil_channel = guild.get_channel(CHANNEL_ACCUEIL_ID)
                if accueil_channel:
                    await accueil_channel.send(
                        t("sages_cmd.welcome_public", member_lang, member=member.mention, guild=guild.name)
                    )

            try:
                await member.send(t("finish.approved", member_lang, sage_name=sage.display_name))
            except discord.Forbidden:
                pass

            logger.info(f"{username} valide par {sage.name} (bouton)")
        else:
            await interaction.followup.send(f"Erreur lors de la promotion de {member.mention}.", ephemeral=True)

    async def _do_refuse(self, interaction: Interaction, member: discord.Member):
        """Refus depuis un bouton (interaction deja repondue)."""
        sage = interaction.user
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            member_lang = profile.language or "FR"

            if profile.approval_status == "refused":
                await interaction.followup.send(f"{member.mention} est deja refuse.", ephemeral=True)
                return

            await profile.refuse()

        await demote_to_newbie(member)
        await interaction.followup.send(f"{member.mention} a ete refuse.")

        try:
            dm_msg = t("finish.refused", member_lang)
            dm_msg += "\n\n" + t("finish.refused_contact", member_lang)
            await member.send(dm_msg)
        except discord.Forbidden:
            pass

        logger.info(f"{username} refuse par {sage.name} (bouton)")

    async def _validate_member(self, ctx, member: discord.Member, sage_lang: str, sage: discord.Member = None):
        """Logique de validation d'un membre (commande uniquement)."""
        sage = sage or ctx.author
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            member_lang = profile.language or "FR"

            if profile.approval_status == "approved":
                await ctx.send(t("sages_cmd.already_approved", sage_lang, member=member.mention))
                return False

            if not profile.charte_validated:
                await ctx.send(t("sages_cmd.charte_not_validated", sage_lang, member=member.mention))
                return False

            await profile.approve()

        success = await promote_to_membre(member)

        if success:
            await ctx.send(t("sages_cmd.validated_success", sage_lang, member=member.mention))

            guild = member.guild if hasattr(member, 'guild') else None
            if not guild:
                for g in self.bot.guilds:
                    if g.get_member(member.id):
                        guild = g
                        break

            if guild:
                accueil_channel = guild.get_channel(CHANNEL_ACCUEIL_ID)
                if accueil_channel:
                    await accueil_channel.send(
                        t("sages_cmd.welcome_public", member_lang, member=member.mention, guild=guild.name)
                    )

            try:
                await member.send(t("finish.approved", member_lang, sage_name=sage.display_name))
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer DM a {username}")

            logger.info(f"{username} valide par {sage.name}")
            return True
        else:
            await ctx.send(t("sages_cmd.validated_error", sage_lang, member=member.mention))
            return False

    @commands.command(name="refuser", aliases=["refuse", "reject"])
    @sage_only()
    async def cmd_refuser(self, ctx, *, args: str = None):
        """Refuse un membre. Usage: !refuser <nom> [raison]"""
        if not args:
            await ctx.send("**Usage:** `!refuser <nom> [raison]` (ex: `!refuser detrax Compte en double`)")
            return

        # Separer le nom de la raison (premier mot = nom)
        parts = args.split(maxsplit=1)
        search = parts[0]
        raison = parts[1] if len(parts) > 1 else None

        # Langue du sage
        async with self.bot.db_pool.acquire() as conn:
            sage_profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        sage_lang = sage_profile.language or "FR"

        # Rechercher le membre
        member = await self._find_member_by_name(ctx, search)
        if not member:
            msg = f"Membre `{search}` non trouve." if sage_lang == "FR" else f"Member `{search}` not found."
            await ctx.send(msg)
            return

        await self._refuse_member(ctx, member, sage_lang, raison)

    async def _refuse_member(self, ctx_or_interaction, member: discord.Member, sage_lang: str, raison: str = None, sage: discord.Member = None):
        """Logique de refus d'un membre (utilisable par commande ou bouton)."""
        is_interaction = isinstance(ctx_or_interaction, Interaction)
        sage = sage or (ctx_or_interaction.user if is_interaction else ctx_or_interaction.author)
        username = member.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            member_lang = profile.language or "FR"

            if profile.approval_status == "refused":
                msg = t("sages_cmd.already_refused", sage_lang, member=member.mention)
                if is_interaction:
                    await ctx_or_interaction.response.send_message(msg, ephemeral=True)
                else:
                    await ctx_or_interaction.send(msg)
                return False

            # Refuser
            await profile.refuse()

        # Retrograder si necessaire
        await demote_to_newbie(member)

        # Message de confirmation
        msg = t("sages_cmd.refused_success", sage_lang, member=member.mention)
        if raison:
            msg += "\n" + t("sages_cmd.refused_reason", sage_lang, reason=raison)

        if is_interaction:
            await ctx_or_interaction.response.send_message(msg)
        else:
            await ctx_or_interaction.send(msg)

        # Notifier le membre en DM
        try:
            dm_msg = t("finish.refused", member_lang)
            if raison:
                dm_msg += "\n\n" + t("finish.refused_reason", member_lang, reason=raison)
            dm_msg += "\n\n" + t("finish.refused_contact", member_lang)
            await member.send(dm_msg)
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer DM a {username}")

        logger.info(f"{username} refuse par {sage.name}" + (f" - Raison: {raison}" if raison else ""))
        return True

    @commands.command(name="check_users", aliases=["check-users", "check_pending"])
    @sage_only()
    async def cmd_check_users(self, ctx):
        """Envoie les notifications pour tous les utilisateurs en attente de validation."""
        logger.info(f"check_users lance par {ctx.author.name}")

        # Recuperer les membres en attente
        pending = await UserProfile.get_pending_members(self.bot.db_pool)
        logger.info(f"check_users: {len(pending)} membre(s) en attente trouve(s)")

        if not pending:
            await ctx.send("Aucun membre en attente de validation.")
            return

        await ctx.send(f"Envoi des notifications pour **{len(pending)}** membre(s) en attente...")

        count = 0
        errors = 0
        for member_data in pending:
            try:
                username = member_data['username']
                discord_id = member_data.get('discord_id')

                # Trouver le membre Discord
                member = None
                for guild in self.bot.guilds:
                    if discord_id:
                        member = guild.get_member(discord_id)
                    if not member:
                        member = discord.utils.find(
                            lambda m: m.name.lower() == username.lower(),
                            guild.members
                        )
                    if member:
                        break

                if not member:
                    logger.warning(f"check_users: Membre {username} non trouve sur le serveur")
                    errors += 1
                    continue

                # Charger le profil et les joueurs
                async with self.bot.db_pool.acquire() as conn:
                    profile = await UserProfile.get_or_create_user(username, conn, member)
                    await profile.load_from_db()

                players = await Player.get_by_member(self.bot.db_pool, username)

                # Envoyer la notification
                await notify_sages_new_registration(self.bot, member, profile, players)
                count += 1
                logger.debug(f"check_users: notification envoyee pour {username}")

                # Petit delai pour eviter le rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"check_users: erreur pour {member_data.get('username', '?')}: {e}")
                errors += 1

        result_msg = f"**{count}** notification(s) envoyee(s)."
        if errors:
            result_msg += f" ({errors} erreur(s))"
        await ctx.send(result_msg)
        logger.info(f"check_users: {count} notifications, {errors} erreurs - par {ctx.author.name}")

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


class ValidationView(View):
    """Vue avec boutons Valider/Refuser pour les notifications aux Sages."""

    def __init__(self, bot, member_id: int, username: str):
        super().__init__(timeout=None)  # Pas de timeout pour les boutons persistants
        self.bot = bot
        self.member_id = member_id
        self.username = username

    def _get_member(self) -> Optional[discord.Member]:
        """Retrouve le membre Discord par son ID."""
        for guild in self.bot.guilds:
            member = guild.get_member(self.member_id)
            if member:
                return member
        return None

    @discord.ui.button(label="Valider", style=ButtonStyle.success, emoji="✅")
    async def validate_btn(self, interaction: Interaction, button: Button):
        # Verifier que c'est un Sage
        if not is_sage(interaction.user):
            await interaction.response.send_message("Seuls les Sages peuvent valider.", ephemeral=True)
            return

        member = self._get_member()
        if not member:
            await interaction.response.send_message(f"Membre {self.username} non trouve sur le serveur.", ephemeral=True)
            return

        # Desactiver les boutons immediatement
        self.validate_btn.disabled = True
        self.refuse_btn.disabled = True
        await interaction.response.edit_message(view=self)

        # Recuperer le cog pour utiliser _validate_member
        cog = self.bot.get_cog("SagesCog")
        if cog:
            # Utiliser un contexte factice pour la validation
            await cog._do_validate(interaction, member)

    @discord.ui.button(label="Refuser", style=ButtonStyle.danger, emoji="❌")
    async def refuse_btn(self, interaction: Interaction, button: Button):
        # Verifier que c'est un Sage
        if not is_sage(interaction.user):
            await interaction.response.send_message("Seuls les Sages peuvent refuser.", ephemeral=True)
            return

        member = self._get_member()
        if not member:
            await interaction.response.send_message(f"Membre {self.username} non trouve sur le serveur.", ephemeral=True)
            return

        # Desactiver les boutons immediatement
        self.validate_btn.disabled = True
        self.refuse_btn.disabled = True
        await interaction.response.edit_message(view=self)

        # Recuperer le cog pour utiliser _refuse_member
        cog = self.bot.get_cog("SagesCog")
        if cog:
            await cog._do_refuse(interaction, member)


async def notify_sages_new_registration(bot, member: discord.Member, profile, players: list):
    """Envoie une notification aux Sages quand un membre termine son inscription."""
    logger.debug(f"notify_sages_new_registration appelé pour {member.name} (DEBUG_MODE={DEBUG_MODE})")

    # Construire l'embed
    embed = discord.Embed(
        title="📋 Nouvelle inscription",
        description=f"**{member.display_name}** (@{member.name}) a termine son inscription.",
        color=discord.Color.orange()
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
        embed.add_field(name="Localisation", value=profile.localisation, inline=False)

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
                logger.info(f"Notification inscription envoyee dans le salon des Sages")
                return

        logger.warning("Salon des Sages non trouve")


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(SagesCog(bot))
