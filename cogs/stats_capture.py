"""
Cog pour la capture et le suivi des statistiques Tennis Clash.

Commandes:
- !capture: Soumet une capture d'ecran pour analyse (traitement asynchrone)
- !evolution: Affiche l'evolution d'un personnage
- !compare: Compare un personnage entre joueurs

Flow de !capture (asynchrone):
1. User envoie une image
2. Bot stocke l'image en file d'attente (capture_queue)
3. User recoit confirmation "Image enregistree, tu seras notifie..."
4. Script local (machine admin) traite les images avec Claude Vision
5. User est notifie et peut valider/refuser les resultats
"""

import discord
from discord.ext import commands
from discord import ButtonStyle, SelectOption
from discord.ui import Button, View, Select
from typing import Optional
import os

from constants import BuildTypes, EquipmentSlots
from models.player import Player
from models.player_stats import PlayerStats
from models.player_equipment import PlayerEquipment
from models.user_profile import UserProfile
from models.capture_queue import CaptureQueue, CaptureStatus
from utils.image_processing import extract_stats_v2, format_stats_preview, ExtractedStats
from utils.discord_helpers import reply_dm
from utils.logger import get_logger
from utils.i18n import get_text
from config import TEMP_DIR, DEBUG_USER

logger = get_logger("cogs.stats_capture")


class PlayerSelectView(View):
    """Vue pour selectionner le joueur in-game."""

    def __init__(self, players: list, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.selected_player = None
        self.cancelled = False

        # Creer le menu de selection
        options = [
            SelectOption(
                label=f"{p.player_name} ({p.team_name})",
                value=str(p.id),
                description=f"Team: {p.team_name}"
            )
            for p in players
        ]

        select = Select(
            placeholder="Selectionne ton joueur...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

        # Bouton annuler
        cancel_btn = Button(label="Annuler", style=ButtonStyle.secondary)
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_player = int(interaction.data['values'][0])
        await interaction.response.defer()
        self.stop()

    async def cancel_callback(self, interaction: discord.Interaction):
        self.cancelled = True
        await interaction.response.defer()
        self.stop()


class BuildSelectView(View):
    """Vue pour selectionner le type de build."""

    def __init__(self, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.selected_build = None
        self.cancelled = False

        options = [
            SelectOption(label=build, value=build)
            for build in BuildTypes.ALL
        ]

        select = Select(
            placeholder="Type de build...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

        cancel_btn = Button(label="Annuler", style=ButtonStyle.secondary)
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_build = interaction.data['values'][0]
        await interaction.response.defer()
        self.stop()

    async def cancel_callback(self, interaction: discord.Interaction):
        self.cancelled = True
        await interaction.response.defer()
        self.stop()


class ConfirmStatsView(View):
    """Vue pour confirmer ou annuler l'enregistrement des stats."""

    def __init__(self, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.confirmed = False
        self.cancelled = False

    @discord.ui.button(label="Confirmer", style=ButtonStyle.success, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Annuler", style=ButtonStyle.danger, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        self.cancelled = True
        await interaction.response.defer()
        self.stop()


class StatsCog(commands.Cog):
    """Commandes de capture et suivi des statistiques Tennis Clash."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="capture", aliases=["cap", "stats-capture"])
    async def capture_stats(self, ctx):
        """Soumet une capture d'ecran Tennis Clash pour analyse.

        L'image est mise en file d'attente et sera traitee par Claude Vision.
        Tu seras notifie quand l'analyse sera terminee.

        Usage: Envoie une image avec la commande !capture
        """
        lang = await self._get_user_lang(ctx.author.id)

        # Verifier qu'une image est jointe
        if not ctx.message.attachments:
            await reply_dm(ctx, get_text("stats.no_image", lang))
            return

        attachment = ctx.message.attachments[0]

        # Verifier le type de fichier
        if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            await reply_dm(ctx, get_text("stats.invalid_image", lang))
            return

        # Telecharger l'image en memoire (bytes)
        try:
            image_data = await attachment.read()
        except discord.HTTPException as e:
            logger.error(f"Erreur telechargement image: {e}")
            await reply_dm(ctx, get_text("stats.download_error", lang))
            return

        # Stocker en file d'attente
        try:
            capture = await CaptureQueue.create(
                db_pool=self.bot.db_pool,
                discord_user_id=ctx.author.id,
                discord_username=ctx.author.name,
                discord_display_name=ctx.author.display_name,
                image_data=image_data,
                image_filename=attachment.filename
            )

            # Compter les captures en attente
            pending_count = await CaptureQueue.count_pending(self.bot.db_pool)

            # Repondre a l'utilisateur
            await reply_dm(
                ctx,
                f"Image enregistree, tu seras notifie quand elle aura ete traitee.\n"
                f"(Position dans la file: {pending_count})"
            )

            logger.info(f"Capture {capture.id} enregistree pour {ctx.author.name}")

            # Notifier l'admin
            await self._notify_admin_new_capture(ctx.author, capture.id, pending_count)

        except Exception as e:
            logger.error(f"Erreur enregistrement capture: {e}")
            await reply_dm(ctx, get_text("stats.save_error", lang))

    async def _notify_admin_new_capture(self, user: discord.User, capture_id: int, pending_count: int):
        """Notifie l'admin qu'une nouvelle capture est en attente.

        Args:
            user: Utilisateur qui a soumis la capture
            capture_id: ID de la capture
            pending_count: Nombre total de captures en attente
        """
        try:
            # Trouver l'admin par son nom (DEBUG_USER)
            admin = None
            for guild in self.bot.guilds:
                admin = discord.utils.find(
                    lambda m: m.name.lower() == DEBUG_USER.lower(),
                    guild.members
                )
                if admin:
                    break

            if not admin:
                logger.warning(f"Admin {DEBUG_USER} non trouve pour notification")
                return

            # Envoyer le DM
            embed = discord.Embed(
                title="Nouvelle capture en attente",
                description=(
                    f"**De:** {user.display_name} (@{user.name})\n"
                    f"**Capture ID:** {capture_id}\n"
                    f"**En attente:** {pending_count} image(s)"
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Lance process_queue.py pour traiter")

            await admin.send(embed=embed)
            logger.info(f"Notification envoyee a {DEBUG_USER} pour capture {capture_id}")

        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer DM a {DEBUG_USER}")
        except Exception as e:
            logger.error(f"Erreur notification admin: {e}")

    @commands.command(name="evolution", aliases=["evo", "history"])
    async def show_evolution(self, ctx, *, character_name: str = None):
        """Affiche l'evolution d'un personnage.

        Usage: !evolution Mei-Li
        """
        lang = await self._get_user_lang(ctx.author.id)

        if not character_name:
            await reply_dm(ctx, get_text("stats.evo_usage", lang))
            return

        # Recuperer l'historique
        history = await PlayerStats.get_by_character(
            self.bot.db_pool, ctx.author.id, character_name
        )

        if not history:
            await reply_dm(ctx, get_text("stats.evo_no_data", lang).format(character=character_name))
            return

        # Construire l'embed
        embed = discord.Embed(
            title=get_text("stats.evo_title", lang).format(character=character_name),
            color=discord.Color.blue()
        )

        # Afficher les 5 dernieres captures
        for i, stat in enumerate(history[:5]):
            date_str = stat.captured_at.strftime("%d/%m/%Y") if stat.captured_at else "?"
            value = (
                f"Points: {stat.points or '?'} | Puissance: {stat.global_power or '?'}\n"
                f"AGI:{stat.agility or '?'} END:{stat.endurance or '?'} "
                f"SER:{stat.serve or '?'} VOL:{stat.volley or '?'}\n"
                f"CD:{stat.forehand or '?'} REV:{stat.backhand or '?'}"
            )
            if stat.build_type:
                value += f"\nBuild: {stat.build_type}"

            embed.add_field(
                name=f"{date_str}",
                value=value,
                inline=False
            )

        # Evolution de la puissance
        if len(history) >= 2:
            latest = history[0].global_power or 0
            oldest = history[-1].global_power or 0
            diff = latest - oldest
            sign = "+" if diff >= 0 else ""
            embed.set_footer(text=f"Evolution puissance: {sign}{diff} ({len(history)} captures)")

        await reply_dm(ctx, embed=embed)

    @commands.command(name="compare", aliases=["cmp"])
    async def compare_character(self, ctx, *, character_name: str = None):
        """Compare les stats d'un personnage entre tous les joueurs.

        Usage: !compare Mei-Li
        """
        lang = await self._get_user_lang(ctx.author.id)

        if not character_name:
            await reply_dm(ctx, get_text("stats.compare_usage", lang))
            return

        # Recuperer toutes les stats pour ce personnage
        all_stats = await PlayerStats.get_all_for_character(self.bot.db_pool, character_name)

        if not all_stats:
            await reply_dm(ctx, get_text("stats.compare_no_data", lang).format(character=character_name))
            return

        # Grouper par discord_id et garder le plus recent
        latest_by_user = {}
        for stat in all_stats:
            if stat.discord_id not in latest_by_user:
                latest_by_user[stat.discord_id] = stat

        # Trier par puissance globale
        sorted_stats = sorted(
            latest_by_user.values(),
            key=lambda s: s.global_power or 0,
            reverse=True
        )

        embed = discord.Embed(
            title=get_text("stats.compare_title", lang).format(character=character_name),
            description=f"{len(sorted_stats)} joueurs",
            color=discord.Color.gold()
        )

        # Afficher le top 10
        for i, stat in enumerate(sorted_stats[:10], 1):
            # Essayer de recuperer le nom du joueur
            member = self.bot.get_user(stat.discord_id)
            name = member.display_name if member else f"ID:{stat.discord_id}"

            value = (
                f"Puissance: **{stat.global_power or '?'}** | Points: {stat.points or '?'}\n"
                f"Build: {stat.build_type or '?'}"
            )

            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"#{i}"
            embed.add_field(
                name=f"{medal} {name}",
                value=value,
                inline=False
            )

        await reply_dm(ctx, embed=embed)

    async def _get_user_lang(self, discord_id: int) -> str:
        """Recupere la langue preferee de l'utilisateur."""
        try:
            profile = await UserProfile.get_by_discord_id(self.bot.db_pool, discord_id)
            if profile and profile.language:
                return profile.language.upper()
        except Exception:
            pass
        return "FR"


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(StatsCog(bot))
