"""
Cog pour les commandes reservees aux Sages.

Commandes:
- !pending : Liste les inscriptions en attente
- !valider <nom> : Valide un membre (Newbie -> Membre)
- !refuser <nom> [raison] : Refuse un membre
"""

import asyncpg
import asyncio
import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from typing import Optional

from models.user_profile import UserProfile
from models.player import Player
from utils.logger import get_logger
from utils.roles import is_sage, promote_to_membre, demote_to_newbie
from utils.i18n import t
from utils.map_generator import regenerate_map_if_needed
from config import CHANNEL_GENERAL_ID, CHANNEL_SAGE_ID, DEBUG_MODE, DEBUG_USER, ROLE_SAGE_ID, SERVER_ID
from constants import Teams, ApprovalStatus
from utils.discord_helpers import find_member, find_member_strict
from utils.debug import debug_only
from utils.audit import log_action, AuditAction
from utils.metrics import metrics

logger = get_logger("cogs.sages")


def check_is_sage(user, bot) -> bool:
    """
    Verifie si un utilisateur est Sage.

    Fonctionne en contexte serveur (Member avec roles) et en DM (User sans roles).
    En DM, utilise SERVER_ID pour trouver le membre directement.

    Args:
        user: L'utilisateur (Member ou User)
        bot: Instance du bot

    Returns:
        True si l'utilisateur est Sage, False sinon
    """
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

        # Recuperer tous les joueurs en une seule requete (evite N+1)
        usernames = [m['username'] for m in pending[:25]]
        players_by_member = await Player.get_by_members(self.bot.db_pool, usernames)

        embed = discord.Embed(
            title=t("sages_cmd.pending_title", lang),
            color=discord.Color.orange(),
            description=t("sages_cmd.pending_count", lang, count=len(pending))
        )

        for member_data in pending[:25]:  # Limite Discord : 25 fields
            username = member_data['username']
            discord_name = member_data.get('discord_name', username)

            # Utiliser le dictionnaire pre-charge
            players = players_by_member.get(username, [])
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

        # Rechercher le membre (unique requis pour action d'ecriture)
        member, error = await find_member_strict(self.bot, search, ctx.guild)
        if error:
            await ctx.send(error)
            return

        await self._validate_member(ctx, member, sage_lang)

    async def _do_validate(self, interaction: Interaction, member: discord.Member):
        """Validation depuis un bouton (interaction deja repondue)."""
        try:
            await self._validate_member(interaction, member, "FR", sage=interaction.user)
        except (discord.HTTPException, asyncpg.PostgresError) as e:
            logger.error(f"_do_validate erreur: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"Erreur: {e}", ephemeral=True)
            except discord.HTTPException as followup_error:
                logger.debug(f"Impossible d'envoyer le message d'erreur: {followup_error}")

    async def _do_refuse(self, interaction: Interaction, member: discord.Member):
        """Refus depuis un bouton (interaction deja repondue)."""
        try:
            await self._refuse_member(interaction, member, "FR", sage=interaction.user)
        except (discord.HTTPException, asyncpg.PostgresError) as e:
            logger.error(f"_do_refuse erreur: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"Erreur: {e}", ephemeral=True)
            except discord.HTTPException as followup_error:
                logger.debug(f"Impossible d'envoyer le message d'erreur: {followup_error}")

    async def _validate_member(self, ctx_or_interaction, member: discord.Member, sage_lang: str, sage: discord.Member = None):
        """Logique de validation d'un membre (utilisable par commande ou bouton)."""
        is_interaction = isinstance(ctx_or_interaction, Interaction)
        sage = sage or (ctx_or_interaction.user if is_interaction else ctx_or_interaction.author)
        username = member.name

        # Helper pour envoyer un message
        async def send_msg(msg, ephemeral=False):
            if is_interaction:
                await ctx_or_interaction.followup.send(msg, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(msg)

        async with self.bot.db_pool.acquire() as conn:
            # Transaction pour éviter les race conditions
            async with conn.transaction():
                profile = await UserProfile.get_or_create_user(username, conn, member)
                member_lang = profile.language or "FR"

                if profile.approval_status == "approved":
                    await send_msg(t("sages_cmd.already_approved", sage_lang, member=member.mention), ephemeral=True)
                    return False

                if not profile.charte_validated:
                    await send_msg(t("sages_cmd.charte_not_validated", sage_lang, member=member.mention), ephemeral=True)
                    return False

                await profile.approve(conn=conn)

        success = await promote_to_membre(member)

        if success:
            await send_msg(t("sages_cmd.validated_success", sage_lang, member=member.mention, sage_name=sage.display_name))

            guild = member.guild if hasattr(member, 'guild') else None
            if not guild:
                for g in self.bot.guilds:
                    if g.get_member(member.id):
                        guild = g
                        break

            if guild:
                general_channel = guild.get_channel(CHANNEL_GENERAL_ID)
                if general_channel:
                    await general_channel.send(
                        t("sages_cmd.welcome_public", member_lang, member=member.mention, guild=guild.name)
                    )

            try:
                await member.send(t("finish.approved", member_lang, sage_name=sage.display_name))
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer DM a {username}")

            # Regenerer la carte (le nouveau membre peut avoir une localisation)
            await regenerate_map_if_needed(self.bot.db_pool)

            # Audit logging
            await log_action(
                self.bot.db_pool,
                AuditAction.VALIDATE,
                target_username=username,
                sage_username=sage.name,
                sage_discord_id=sage.id,
                target_discord_id=member.id
            )

            logger.info(f"{username} valide par {sage.name}")
            return True
        else:
            await send_msg(t("sages_cmd.validated_error", sage_lang, member=member.mention), ephemeral=True)
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

        # Rechercher le membre (unique requis pour action d'ecriture)
        member, error = await find_member_strict(self.bot, search, ctx.guild)
        if error:
            await ctx.send(error)
            return

        await self._refuse_member(ctx, member, sage_lang, raison)

    async def _refuse_member(self, ctx_or_interaction, member: discord.Member, sage_lang: str, raison: str = None, sage: discord.Member = None):
        """Logique de refus d'un membre (utilisable par commande ou bouton)."""
        is_interaction = isinstance(ctx_or_interaction, Interaction)
        sage = sage or (ctx_or_interaction.user if is_interaction else ctx_or_interaction.author)
        username = member.name

        # Helper pour envoyer un message
        async def send_msg(msg, ephemeral=False):
            if is_interaction:
                await ctx_or_interaction.followup.send(msg, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(msg)

        async with self.bot.db_pool.acquire() as conn:
            # Transaction pour éviter les race conditions
            async with conn.transaction():
                profile = await UserProfile.get_or_create_user(username, conn, member)
                member_lang = profile.language or "FR"

                if profile.approval_status == "refused":
                    await send_msg(t("sages_cmd.already_refused", sage_lang, member=member.mention), ephemeral=True)
                    return False

                # Refuser
                await profile.refuse(conn=conn)

        # Retrograder si necessaire
        await demote_to_newbie(member)

        # Message de confirmation
        msg = t("sages_cmd.refused_success", sage_lang, member=member.mention, sage_name=sage.display_name)
        if raison:
            msg += "\n" + t("sages_cmd.refused_reason", sage_lang, reason=raison)

        await send_msg(msg)

        # Notifier le membre en DM
        try:
            dm_msg = t("finish.refused", member_lang)
            if raison:
                dm_msg += "\n\n" + t("finish.refused_reason", member_lang, reason=raison)
            dm_msg += "\n\n" + t("finish.refused_contact", member_lang)
            await member.send(dm_msg)
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer DM a {username}")

        # Audit logging
        await log_action(
            self.bot.db_pool,
            AuditAction.REFUSE,
            target_username=username,
            sage_username=sage.name,
            sage_discord_id=sage.id,
            target_discord_id=member.id,
            details=raison
        )

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

        # Pre-fetch tous les joueurs en une seule requete (evite N+1)
        all_usernames = [m['username'] for m in pending]
        all_players = await Player.get_by_members(self.bot.db_pool, all_usernames)

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

                # Charger le profil
                async with self.bot.db_pool.acquire() as conn:
                    profile = await UserProfile.get_or_create_user(username, conn, member)
                    await profile.load_from_db()

                # Utiliser les joueurs pre-fetches
                players = all_players.get(username, [])

                # Envoyer la notification
                await notify_sages_new_registration(self.bot, member, profile, players)
                count += 1
                logger.debug(f"check_users: notification envoyee pour {username}")

                # Petit delai pour eviter le rate limiting
                await asyncio.sleep(0.5)

            except (discord.HTTPException, asyncpg.PostgresError) as e:
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
        # Verification Sage
        if not check_is_sage(ctx.author, self.bot):
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
                embed.add_field(name=Teams.TEAM1_NAME, value=", ".join(team1), inline=True)
            if team2:
                embed.add_field(name=Teams.TEAM2_NAME, value=", ".join(team2), inline=True)
        else:
            embed.add_field(
                name=t("sages_cmd.profil_admin_players", lang),
                value=t("sages_cmd.profil_admin_no_players", lang),
                inline=False
            )

        # Localisation (affichage anonymise: pays/region + coordonnees GPS)
        if profile.latitude and profile.longitude:
            # Utiliser location_display (anonymise) ou fallback sur "Localisation definie"
            loc_display = profile.location_display or "Localisation definie"
            loc_str = f"{loc_display} ({profile.latitude:.4f}, {profile.longitude:.4f})"
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
        try:
            await ctx.author.send(embed=embed)
            # Confirmer si la commande n'etait pas deja en DM
            if not isinstance(ctx.channel, discord.DMChannel):
                await ctx.send(t("commands.sent_dm", lang))
        except discord.Forbidden:
            await ctx.send(t("errors.dm_failed", lang))

    # =========================================================================
    # Commande !reset (debug uniquement)
    # =========================================================================
    @commands.command(name="reset")
    @debug_only()
    async def cmd_reset(self, ctx, *, search: str = None):
        """Reinitialise un membre pour permettre une nouvelle inscription (debug)."""
        if not search:
            await ctx.send("**Usage:** `!reset <nom>` (ex: `!reset detrax`)")
            return

        # Rechercher le membre (unique requis)
        member, error = await find_member_strict(self.bot, search, ctx.guild)
        if error:
            await ctx.send(error)
            return

        username = member.name

        # Charger le profil
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)

            if not profile:
                await ctx.send(f"Profil de `{username}` introuvable.")
                return

            # Reinitialiser le profil
            await profile.reset()

            # Supprimer tous les joueurs
            deleted_count = await Player.delete_all_for_member(self.bot.db_pool, username)

            # Retrograder en Newbie si necessaire
            await demote_to_newbie(member)

        msg = f"✅ **{member.display_name}** reinitialise :\n"
        msg += f"• Statut : pending\n"
        msg += f"• Charte : non validee\n"
        msg += f"• Joueurs supprimes : {deleted_count}\n"
        msg += f"• Role : Newbie\n"
        msg += f"\nLe membre peut relancer `!inscription`."

        await ctx.send(msg)

        # Audit logging
        await log_action(
            self.bot.db_pool,
            AuditAction.RESET,
            target_username=username,
            sage_username=ctx.author.name,
            sage_discord_id=ctx.author.id,
            target_discord_id=member.id,
            details=f"joueurs supprimes: {deleted_count}"
        )

        logger.info(f"Reset de {username} par {ctx.author.name}")

    # =========================================================================
    # Commande !delete (suppression complete RGPD)
    # =========================================================================
    @commands.command(name="delete", aliases=["supprimer", "purge"])
    async def cmd_delete(self, ctx, *, search: str = None):
        """Supprime completement un utilisateur et toutes ses donnees (RGPD)."""
        if not search:
            await ctx.send("**Usage:** `!delete <nom>` (ex: `!delete detrax`)")
            return

        # Rechercher le membre
        member, error = await find_member_strict(self.bot, search, ctx.guild)
        if error:
            await ctx.send(error)
            return

        username = member.name
        is_self = (member.id == ctx.author.id)
        is_sage_user = check_is_sage(ctx.author, self.bot)

        # Verifier les permissions
        if not is_self and not is_sage_user:
            await ctx.send("❌ Tu ne peux supprimer que ton propre profil.")
            return

        # Charger le profil pour verifier qu'il existe
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            if not profile:
                await ctx.send(f"Profil de `{username}` introuvable.")
                return

        # Compter les donnees
        players = await Player.get_by_member(self.bot.db_pool, username)

        # Message de confirmation (adapte selon auto-suppression ou suppression par Sage)
        if is_self:
            # Auto-suppression: confirmation simple
            warning = (
                f"⚠️ **ATTENTION - SUPPRESSION DEFINITIVE** ⚠️\n\n"
                f"Tu es sur le point de supprimer **TOUTES** tes donnees:\n"
                f"• Profil utilisateur\n"
                f"• {len(players)} joueur(s)\n"
                f"• Historique des pseudos\n"
                f"• Logs d'audit\n\n"
                f"**Cette action est IRREVERSIBLE !**\n"
                f"**Tu seras deconnecte du serveur a l'issue de la suppression.**\n"
                f"Tu pourras revenir a tout moment via le lien d'invitation."
            )
            view = DeleteConfirmView(member, ctx.author)
            timeout = 30
        else:
            # Suppression par un Sage: double validation requise
            warning = (
                f"⚠️ **ATTENTION - SUPPRESSION DEFINITIVE** ⚠️\n\n"
                f"**{ctx.author.display_name}** demande la suppression de **{member.display_name}** (@{username}).\n\n"
                f"Donnees a supprimer:\n"
                f"• Profil utilisateur\n"
                f"• {len(players)} joueur(s)\n"
                f"• Historique des pseudos\n"
                f"• Logs d'audit\n\n"
                f"**Cette action est IRREVERSIBLE !**\n"
                f"Le membre sera deconnecte du serveur.\n\n"
                f"🛡️ **Un autre Sage doit confirmer cette suppression.**"
            )
            view = DeleteSageConfirmView(member, ctx.author)
            timeout = 300  # 5 minutes

        confirm_msg = await ctx.send(warning, view=view)

        try:
            await asyncio.wait_for(view.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Temps ecoule. Suppression annulee.", view=None)
            return

        if not view.confirmed:
            await confirm_msg.edit(content="❌ Suppression annulee.", view=None)
            return

        # Recuperer le nom du Sage confirmant (si double validation)
        confirming_sage_name = None
        if hasattr(view, 'confirming_sage') and view.confirming_sage:
            confirming_sage_name = view.confirming_sage.display_name

        # Effectuer la suppression
        results = await UserProfile.delete_all_data(self.bot.db_pool, member.id, username)

        # Envoyer un DM avant le kick (sauf auto-suppression, il voit deja le message)
        if not is_self:
            try:
                dm_msg = (
                    f"👋 **Tes donnees ont ete supprimees du serveur {ctx.guild.name}.**\n\n"
                    f"Tu vas etre deconnecte du serveur.\n"
                    f"Si tu le souhaites, tu peux revenir a tout moment en utilisant le lien d'invitation."
                )
                await member.send(dm_msg)
            except (discord.Forbidden, discord.HTTPException):
                pass  # DMs fermes, on continue quand meme

        # Kicker le membre
        kick_msg = ""
        if is_self:
            reason = "Suppression RGPD (auto)"
        elif confirming_sage_name:
            reason = f"Suppression RGPD par {ctx.author.name} (confirme par {confirming_sage_name})"
        else:
            reason = f"Suppression RGPD par {ctx.author.name}"

        try:
            await member.kick(reason=reason)
            kick_msg = "\n\n*Deconnecte du serveur.*"
        except (discord.Forbidden, discord.HTTPException) as e:
            kick_msg = f"\n\n⚠️ *Impossible de deconnecter: {e}*"

        # Message de confirmation
        if confirming_sage_name:
            validation_info = f"\n\n*Demande par {ctx.author.display_name}, confirmee par {confirming_sage_name}.*"
        else:
            validation_info = ""

        msg = (
            f"✅ **Donnees supprimees pour {member.display_name}** :\n"
            f"• Profil : {results['user_profile']}\n"
            f"• Joueurs : {results['players']}\n"
            f"• Historique pseudos : {results['username_history']}\n"
            f"• Logs audit : {results['audit_log']}"
            f"{kick_msg}"
            f"{validation_info}"
        )
        await confirm_msg.edit(content=msg, view=None)

        if confirming_sage_name:
            logger.info(f"Suppression complete de {username} par {ctx.author.name} (confirme par {confirming_sage_name})")
        else:
            logger.info(f"Suppression complete de {username} par {ctx.author.name}")

    # =========================================================================
    # Commande !audit-permissions
    # =========================================================================
    @commands.command(name="audit-permissions", aliases=["audit-perms", "perms"])
    @sage_only()
    async def cmd_audit_permissions(self, ctx):
        """Exporte les permissions par role (salons autorises/interdits)."""
        # Recuperer la guilde (ctx.guild peut etre None dans certains contextes)
        guild = ctx.guild
        if not guild and hasattr(ctx.channel, 'guild'):
            guild = ctx.channel.guild
        if not guild:
            # Chercher la guilde via le membre
            for g in self.bot.guilds:
                if g.get_member(ctx.author.id):
                    guild = g
                    break

        if not guild:
            await ctx.send("Cette commande doit etre utilisee sur un serveur.")
            return

        await ctx.send("Generation de l'audit des permissions en cours...")

        # Recuperer les salons textuels et vocaux (pas les categories)
        channels = [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)]
        channels.sort(key=lambda c: (c.category.position if c.category else -1, c.position))

        # Roles a auditer (exclure bots, du plus haut au plus bas, @everyone en dernier)
        roles_to_audit = [r for r in guild.roles if not r.is_bot_managed() and r.name != "@everyone"]
        roles_to_audit.reverse()
        # Ajouter @everyone a la fin
        everyone_role = guild.default_role
        if everyone_role:
            roles_to_audit.append(everyone_role)

        # Construire le rapport par role
        messages = []

        for role in roles_to_audit:
            allowed = []  # Salons autorises (lecture)
            denied = []   # Salons explicitement interdits

            for channel in channels:
                overwrites = channel.overwrites_for(role)
                prefix = "#" if isinstance(channel, discord.TextChannel) else "V:"

                # Verifier si le role a acces en lecture
                if overwrites.read_messages is True:
                    allowed.append(f"{prefix}{channel.name}")
                elif overwrites.read_messages is False:
                    denied.append(f"{prefix}{channel.name}")
                # Si None, herite des permissions par defaut (on ne l'affiche pas)

            # Ne pas afficher les roles sans permissions specifiques
            if not allowed and not denied:
                continue

            # Construire le message pour ce role
            role_msg = f"**[ {role.name} ]**\n"

            if allowed:
                role_msg += "[+] " + ", ".join(allowed[:30])
                if len(allowed) > 30:
                    role_msg += f" (+{len(allowed) - 30})"
                role_msg += "\n"

            if denied:
                role_msg += "[-] " + ", ".join(denied[:30])
                if len(denied) > 30:
                    role_msg += f" (+{len(denied) - 30})"
                role_msg += "\n"

            messages.append(role_msg)

        # Envoyer en DM
        try:
            header = f"**Audit des permissions - {guild.name}**\n"
            header += f"{discord.utils.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            header += f"{len(roles_to_audit)} roles | {len(channels)} salons\n"
            header += "[+] = acces autorise | [-] = acces interdit"
            await ctx.author.send(header)

            # Envoyer chaque role separement pour eviter la limite de 2000 caracteres
            for msg in messages:
                if len(msg) > 1900:
                    # Decouper si trop long
                    chunks = [msg[i:i+1900] for i in range(0, len(msg), 1900)]
                    for chunk in chunks:
                        await ctx.author.send(chunk)
                else:
                    await ctx.author.send(msg)

            await ctx.send(f"Audit envoye en DM ({len(messages)} roles avec permissions specifiques).")
            logger.info(f"Audit permissions genere par {ctx.author.name}")

        except discord.Forbidden:
            await ctx.send("Impossible d'envoyer le rapport en DM. Verifie que tes DMs sont ouverts.")

    # =========================================================================
    # Commande !metrics
    # =========================================================================
    @commands.command(name="metrics", aliases=["stats", "status"])
    @sage_only()
    async def cmd_metrics(self, ctx):
        """Affiche les metriques du bot."""
        summary = metrics.get_summary()

        embed = discord.Embed(
            title="📊 Metriques du Bot",
            color=discord.Color.blue()
        )

        # Uptime
        uptime_s = summary["uptime_seconds"]
        hours = int(uptime_s // 3600)
        minutes = int((uptime_s % 3600) // 60)
        embed.add_field(
            name="⏱️ Uptime",
            value=f"{hours}h {minutes}m",
            inline=True
        )

        # Commandes
        cmd = summary["commands"]
        embed.add_field(
            name="📝 Commandes",
            value=f"Total: {cmd['total']}\nSucces: {cmd['success']}\nErreurs: {cmd['error']}",
            inline=True
        )

        # Temps de reponse
        embed.add_field(
            name="⚡ Temps moyen",
            value=f"{summary['response_time_avg_ms']:.0f} ms",
            inline=True
        )

        # Cache
        cache = summary["cache"]
        embed.add_field(
            name="💾 Cache",
            value=f"Hits: {cache['hits']}\nMisses: {cache['misses']}\nTaux: {cache['hit_rate_percent']:.0f}%",
            inline=True
        )

        # DB
        db = summary["db"]
        embed.add_field(
            name="🗄️ Base de donnees",
            value=f"Requetes: {db['queries']}\nErreurs: {db['errors']}",
            inline=True
        )

        # Top commandes
        if cmd["by_name"]:
            top_cmds = sorted(cmd["by_name"].items(), key=lambda x: x[1], reverse=True)[:5]
            top_str = "\n".join([f"!{name}: {count}" for name, count in top_cmds])
            embed.add_field(
                name="🏆 Top commandes",
                value=top_str or "Aucune",
                inline=False
            )

        await ctx.send(embed=embed)


class DeleteConfirmView(View):
    """Vue de confirmation pour l'auto-suppression d'un utilisateur."""

    def __init__(self, target: discord.Member, author: discord.Member):
        super().__init__(timeout=30)
        self.target = target
        self.author = author
        self.confirmed = False

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce n'est pas ta demande.", ephemeral=True)
            return
        await interaction.response.defer()
        self.confirmed = False
        self.stop()

    @discord.ui.button(label="🗑️ SUPPRIMER DEFINITIVEMENT", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce n'est pas ta demande.", ephemeral=True)
            return
        await interaction.response.defer()
        self.confirmed = True
        self.stop()


class DeleteSageConfirmView(View):
    """Vue de confirmation avec double validation Sage (anti-abus)."""

    def __init__(self, target: discord.Member, requesting_sage: discord.Member):
        super().__init__(timeout=300)  # 5 minutes pour laisser le temps a un autre Sage
        self.target = target
        self.requesting_sage = requesting_sage
        self.confirmed = False
        self.confirming_sage = None

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: Interaction, button: discord.ui.Button):
        # Seul le Sage demandeur peut annuler
        if interaction.user.id != self.requesting_sage.id:
            await interaction.response.send_message(
                "Seul le Sage ayant initie la demande peut annuler.", ephemeral=True
            )
            return
        await interaction.response.defer()
        self.confirmed = False
        self.stop()

    @discord.ui.button(label="✅ Confirmer (autre Sage)", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: Interaction, button: discord.ui.Button):
        # Verifier que c'est un Sage different
        if interaction.user.id == self.requesting_sage.id:
            await interaction.response.send_message(
                "⚠️ Tu ne peux pas valider ta propre demande de suppression.\n"
                "Un **autre Sage** doit confirmer.", ephemeral=True
            )
            return

        # Verifier que c'est bien un Sage
        if not is_sage(interaction.user):
            await interaction.response.send_message(
                "Seuls les Sages peuvent confirmer une suppression.", ephemeral=True
            )
            return

        await interaction.response.defer()
        self.confirmed = True
        self.confirming_sage = interaction.user
        self.stop()


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

    def _get_sage_member(self, user: discord.User) -> Optional[discord.Member]:
        """Retrouve le membre Sage dans une guilde."""
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if member and is_sage(member):
                return member
        return None

    @discord.ui.button(label="Valider", style=ButtonStyle.success, emoji="✅")
    async def validate_btn(self, interaction: Interaction, button: Button):
        try:
            logger.info(f"Bouton Valider clique par {interaction.user.name} pour {self.username}")

            # Repondre immediatement pour eviter le timeout de 3s
            await interaction.response.defer()

            # Verifier que c'est un Sage (en DM, interaction.user est un User, pas un Member)
            sage_member = self._get_sage_member(interaction.user)
            if not sage_member:
                await interaction.followup.send("Seuls les Sages peuvent valider.", ephemeral=True)
                return

            member = self._get_member()
            if not member:
                await interaction.followup.send(f"Membre {self.username} non trouve sur le serveur.", ephemeral=True)
                return

            logger.debug(f"Membre trouve: {member.name} dans {member.guild.name}")

            # Desactiver les boutons
            self.validate_btn.disabled = True
            self.refuse_btn.disabled = True
            await interaction.edit_original_response(view=self)

            # Recuperer le cog pour utiliser _validate_member
            cog = self.bot.get_cog("SagesCog")
            if cog:
                await cog._do_validate(interaction, member)
            else:
                logger.error("SagesCog non trouve!")
                await interaction.followup.send("Erreur interne: cog non trouve.", ephemeral=True)

        except discord.HTTPException as e:
            logger.error(f"Erreur bouton Valider: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"Erreur: {e}", ephemeral=True)
            except discord.HTTPException as followup_error:
                logger.debug(f"Impossible d'envoyer le message d'erreur: {followup_error}")

    @discord.ui.button(label="Refuser", style=ButtonStyle.danger, emoji="❌")
    async def refuse_btn(self, interaction: Interaction, button: Button):
        try:
            logger.info(f"Bouton Refuser clique par {interaction.user.name} pour {self.username}")

            # Repondre immediatement pour eviter le timeout de 3s
            await interaction.response.defer()

            # Verifier que c'est un Sage (en DM, interaction.user est un User, pas un Member)
            sage_member = self._get_sage_member(interaction.user)
            if not sage_member:
                await interaction.followup.send("Seuls les Sages peuvent refuser.", ephemeral=True)
                return

            member = self._get_member()
            if not member:
                await interaction.followup.send(f"Membre {self.username} non trouve sur le serveur.", ephemeral=True)
                return

            logger.debug(f"Membre trouve: {member.name} dans {member.guild.name}")

            # Desactiver les boutons
            self.validate_btn.disabled = True
            self.refuse_btn.disabled = True
            await interaction.edit_original_response(view=self)

            # Recuperer le cog pour utiliser _refuse_member
            cog = self.bot.get_cog("SagesCog")
            if cog:
                await cog._do_refuse(interaction, member)
            else:
                logger.error("SagesCog non trouve!")
                await interaction.followup.send("Erreur interne: cog non trouve.", ephemeral=True)

        except discord.HTTPException as e:
            logger.error(f"Erreur bouton Refuser: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"Erreur: {e}", ephemeral=True)
            except discord.HTTPException as followup_error:
                logger.debug(f"Impossible d'envoyer le message d'erreur: {followup_error}")


async def notify_sages_new_registration(bot, member: discord.Member, profile, players: list):
    """Envoie une notification aux Sages quand un membre termine son inscription."""
    logger.debug(f"notify_sages_new_registration appelé pour {member.name} (DEBUG_MODE={DEBUG_MODE})")

    # Construire l'embed
    embed = discord.Embed(
        title="📋 Nouvelle inscription",
        description=f"**{member.display_name}** (@{member.name}) a termine son inscription.",
        color=discord.Color.orange()
    )

    # Statut charte
    charte_status = "✅ Validée" if profile.charte_validated else "❌ Non validée"
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
                logger.info(f"Notification inscription envoyee dans le salon des Sages")
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
        status_emoji = "🚫"
        status_text = "REFUSE precedemment"
    elif previous_status == 'deleted':
        color = discord.Color.orange()
        status_emoji = "🔄"
        status_text = "Ancien membre SUPPRIME"
    elif previous_status == 'approved':
        color = discord.Color.green()
        status_emoji = "✅"
        status_text = "Ancien membre approuve"
    else:
        color = discord.Color.orange()
        status_emoji = "⚠️"
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


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(SagesCog(bot))
