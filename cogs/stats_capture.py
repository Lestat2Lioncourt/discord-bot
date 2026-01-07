"""
Cog pour la capture et le suivi des statistiques Tennis Clash.

Commandes:
- !capture: Analyse une capture d'ecran et enregistre les stats
- !evolution: Affiche l'evolution d'un personnage
- !compare: Compare un personnage entre joueurs

Flow de !capture:
1. User envoie une image
2. OCR extrait les stats
3. Bot affiche preview et demande confirmation
4. User selectionne son joueur (team 1 ou 2)
5. User selectionne le type de build
6. Stats enregistrees en base
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
from utils.image_processing import extract_stats_v2, format_stats_preview, ExtractedStats
from utils.discord_helpers import reply_dm
from utils.logger import get_logger
from utils.i18n import get_text
from config import TEMP_DIR

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
        """Analyse une capture d'ecran Tennis Clash et enregistre les stats.

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

        # Telecharger l'image
        image_path = TEMP_DIR / f"capture_{ctx.author.id}_{attachment.filename}"
        try:
            await attachment.save(str(image_path))
        except discord.HTTPException as e:
            logger.error(f"Erreur telechargement image: {e}")
            await reply_dm(ctx, get_text("stats.download_error", lang))
            return

        # Extraire les stats
        await ctx.author.send(get_text("stats.analyzing", lang))
        stats = extract_stats_v2(str(image_path))

        # Nettoyer l'image temporaire
        if os.path.exists(image_path):
            os.remove(image_path)

        # Afficher le preview
        preview = format_stats_preview(stats, lang)
        embed = discord.Embed(
            title=get_text("stats.preview_title", lang),
            description=preview,
            color=discord.Color.blue() if stats.confidence >= 0.5 else discord.Color.orange()
        )

        if stats.warnings:
            warnings_text = "\n".join(f"- {w}" for w in stats.warnings[:5])
            embed.add_field(name=get_text("stats.warnings", lang), value=warnings_text, inline=False)

        # Vue de confirmation
        confirm_view = ConfirmStatsView()
        msg = await ctx.author.send(embed=embed, view=confirm_view)

        await confirm_view.wait()

        if confirm_view.cancelled or not confirm_view.confirmed:
            await msg.edit(content=get_text("stats.cancelled", lang), embed=None, view=None)
            return

        # Recuperer les joueurs du membre
        players = await Player.get_by_member(self.bot.db_pool, ctx.author.name)

        if not players:
            await msg.edit(
                content=get_text("stats.no_players", lang),
                embed=None, view=None
            )
            return

        # Selectionner le joueur
        player_view = PlayerSelectView(players)
        await msg.edit(
            content=get_text("stats.select_player", lang),
            embed=None, view=player_view
        )

        await player_view.wait()

        if player_view.cancelled or player_view.selected_player is None:
            await msg.edit(content=get_text("stats.cancelled", lang), view=None)
            return

        selected_player_id = player_view.selected_player
        selected_player = next((p for p in players if p.id == selected_player_id), None)

        # Selectionner le build
        build_view = BuildSelectView()
        await msg.edit(
            content=get_text("stats.select_build", lang),
            view=build_view
        )

        await build_view.wait()

        if build_view.cancelled or build_view.selected_build is None:
            await msg.edit(content=get_text("stats.cancelled", lang), view=None)
            return

        # Enregistrer en base
        try:
            # Sauvegarder les stats
            saved_stats = await PlayerStats.create(
                db_pool=self.bot.db_pool,
                discord_id=ctx.author.id,
                player_id=selected_player_id,
                character_name=stats.character_name or "Inconnu",
                points=stats.points,
                global_power=stats.global_power,
                agility=stats.agility,
                endurance=stats.endurance,
                serve=stats.serve,
                volley=stats.volley,
                forehand=stats.forehand,
                backhand=stats.backhand,
                build_type=build_view.selected_build
            )

            # Sauvegarder les equipements
            if stats.equipment:
                equipment_data = [
                    {
                        'slot': eq.slot,
                        'card_name': eq.card_name,
                        'card_level': eq.card_level
                    }
                    for eq in stats.equipment
                    if eq.card_name or eq.card_level  # Seulement si au moins une donnee
                ]
                if equipment_data:
                    await PlayerEquipment.create_many(
                        self.bot.db_pool,
                        saved_stats.id,
                        equipment_data
                    )

            success_embed = discord.Embed(
                title=get_text("stats.saved_title", lang),
                description=get_text("stats.saved_desc", lang).format(
                    character=stats.character_name,
                    player=selected_player.player_name if selected_player else "?"
                ),
                color=discord.Color.green()
            )
            await msg.edit(embed=success_embed, view=None)
            logger.info(f"Stats enregistrees: {stats.character_name} pour {ctx.author.name}")

        except Exception as e:
            logger.error(f"Erreur enregistrement stats: {e}")
            await msg.edit(content=get_text("stats.save_error", lang), view=None)

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
