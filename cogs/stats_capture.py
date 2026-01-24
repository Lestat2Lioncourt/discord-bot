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

import asyncio

import discord
from discord.ext import commands, tasks
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


class ValidateCaptureView(View):
    """Vue pour valider ou refuser une capture analysee."""

    def __init__(self, capture_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.capture_id = capture_id
        self.validated = None  # None = pas de reponse, True = valide, False = refuse

    @discord.ui.button(label="Valider", style=ButtonStyle.success, emoji="✅")
    async def validate_btn(self, interaction: discord.Interaction, button: Button):
        self.validated = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Refuser", style=ButtonStyle.danger, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: Button):
        self.validated = False
        await interaction.response.defer()
        self.stop()


class StatsCog(commands.Cog):
    """Commandes de capture et suivi des statistiques Tennis Clash."""

    def __init__(self, bot):
        self.bot = bot
        self._notified_captures = set()  # IDs des captures deja notifiees

    async def cog_load(self):
        """Demarre la tache de check des analyses."""
        self.check_completed_captures.start()
        # Lancer un check immediat au demarrage (apres que le bot soit pret)
        asyncio.create_task(self._initial_capture_check())

    async def cog_unload(self):
        """Arrete la tache de check des analyses."""
        self.check_completed_captures.cancel()

    @tasks.loop(minutes=5)
    async def check_completed_captures(self):
        """Verifie toutes les 5 minutes s'il y a des analyses terminees."""
        try:
            # Recuperer toutes les captures completees
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM capture_queue
                    WHERE status = 'completed'
                    ORDER BY processed_at ASC
                """)

            if not rows:
                return

            logger.info(f"Check periodique: {len(rows)} capture(s) completee(s) a notifier")

            for row in rows:
                capture_id = row['id']

                # Eviter de notifier plusieurs fois la meme capture
                if capture_id in self._notified_captures:
                    continue

                # Trouver l'utilisateur
                user = self.bot.get_user(row['discord_user_id'])
                if not user:
                    try:
                        user = await self.bot.fetch_user(row['discord_user_id'])
                    except discord.NotFound:
                        logger.warning(f"Utilisateur {row['discord_user_id']} introuvable")
                        continue

                # Creer l'objet CaptureQueue
                capture = CaptureQueue._from_row(row)

                # Notifier
                self._notified_captures.add(capture_id)
                await self._notify_capture_ready(user, capture)

        except Exception as e:
            logger.error(f"Erreur check periodique captures: {e}")

    @check_completed_captures.before_loop
    async def before_check_completed(self):
        """Attend que le bot soit pret avant de demarrer la tache."""
        await self.bot.wait_until_ready()

    async def _initial_capture_check(self):
        """Check immediat au demarrage du bot."""
        await self.bot.wait_until_ready()
        # Petit delai pour laisser le temps aux autres cogs de se charger
        await asyncio.sleep(2)
        logger.info("Check initial des captures en attente...")
        await self.check_completed_captures()

    async def _notify_capture_ready(self, user: discord.User, capture: CaptureQueue):
        """Notifie l'utilisateur qu'une capture a ete analysee et lui permet de valider.

        Args:
            user: Utilisateur a notifier
            capture: Capture analysee
        """
        result = capture.result_json
        if not result:
            logger.warning(f"Capture {capture.id} completee mais sans result_json")
            return

        # Construire le preview des stats
        stats = result.get("stats", {})
        equipment = result.get("equipment", [])

        # Afficher joueur et build selectionnes a la soumission
        player_info = capture.player_name or "?"
        build_info = capture.build_type or "?"

        preview_lines = [
            f"**Joueur:** {player_info} | **Build:** {build_info}",
            "",
            f"**Personnage:** {result.get('character_name', '?')} (niv.{result.get('character_level', '?')})",
            f"**Points:** {result.get('points', '?')}",
            f"**Puissance:** {result.get('global_power', '?')}",
            "",
            f"**Stats:**",
            f"  AGI: {stats.get('agility', '?')} | END: {stats.get('endurance', '?')}",
            f"  SER: {stats.get('serve', '?')} | VOL: {stats.get('volley', '?')}",
            f"  CD: {stats.get('forehand', '?')} | REV: {stats.get('backhand', '?')}",
            "",
            f"**Equipement:**",
        ]

        slot_names = {
            1: "Raquette", 2: "Grip", 3: "Chaussures",
            4: "Poignet", 5: "Nutrition", 6: "Entrainement"
        }
        for eq in equipment:
            slot = eq.get("slot", 0)
            slot_name = slot_names.get(slot, f"Slot {slot}")
            preview_lines.append(
                f"  {slot_name}: {eq.get('name', '?')} (niv.{eq.get('level', '?')})"
            )

        embed = discord.Embed(
            title="Analyse terminee !",
            description="\n".join(preview_lines),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Capture #{capture.id} - Soumise le {capture.submitted_at.strftime('%d/%m %H:%M') if capture.submitted_at else '?'}")

        # Envoyer avec boutons
        view = ValidateCaptureView(capture.id)

        try:
            msg = await user.send(embed=embed, view=view)
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer DM a {user.name}")
            return

        # Attendre la reponse
        await view.wait()

        if view.validated is True:
            await self._validate_capture(user, capture, msg)
        elif view.validated is False:
            await self._reject_capture(capture, msg)
        else:
            # Timeout
            await msg.edit(content="Temps ecoule. Tu peux refaire une commande pour revoir cette capture.", embed=embed, view=None)

    async def _validate_capture(self, user: discord.User, capture: CaptureQueue, msg: discord.Message):
        """Valide une capture et sauvegarde les stats.

        Le joueur et build ont ete selectionnes a la soumission.

        Args:
            user: Utilisateur qui valide
            capture: Capture a valider
            msg: Message a mettre a jour
        """
        result = capture.result_json

        # Verifier que player_id et build_type sont definis
        if not capture.player_id or not capture.build_type:
            # Fallback pour les anciennes captures sans player_id/build_type
            await self._validate_capture_legacy(user, capture, msg)
            return

        # Sauvegarder en base directement avec le joueur/build selectionnes a la soumission
        try:
            stats = result.get("stats", {})
            character_name = result.get("character_name") or "Inconnu"

            # Verifier si les stats sont identiques a la derniere capture
            last_stats = await PlayerStats.get_latest_for_build(
                self.bot.db_pool,
                capture.player_id,
                character_name,
                capture.build_type
            )

            # Creer un objet temporaire pour comparer
            new_stats = PlayerStats(
                id=None,
                discord_id=user.id,
                player_id=capture.player_id,
                character_name=character_name,
                points=result.get("points"),
                global_power=result.get("global_power"),
                agility=stats.get("agility"),
                endurance=stats.get("endurance"),
                serve=stats.get("serve"),
                volley=stats.get("volley"),
                forehand=stats.get("forehand"),
                backhand=stats.get("backhand"),
                build_type=capture.build_type
            )

            if last_stats and new_stats.is_same_as(last_stats):
                # Stats identiques - ne pas inserer
                await capture.update_status(self.bot.db_pool, CaptureStatus.VALIDATED)
                self._notified_captures.discard(capture.id)

                last_date = last_stats.captured_at.strftime("%d/%m/%Y") if last_stats.captured_at else "?"
                await msg.edit(
                    content=f"Pas de changement pour **{character_name}** ({capture.player_name or '?'}, {capture.build_type}) depuis le {last_date}.\nCapture ignoree.",
                    view=None
                )
                logger.info(f"Capture {capture.id} ignoree (identique) par {user.name}")
                return

            # Stats differentes - inserer
            saved_stats = await PlayerStats.create(
                db_pool=self.bot.db_pool,
                discord_id=user.id,
                player_id=capture.player_id,
                character_name=character_name,
                points=result.get("points"),
                global_power=result.get("global_power"),
                agility=stats.get("agility"),
                endurance=stats.get("endurance"),
                serve=stats.get("serve"),
                volley=stats.get("volley"),
                forehand=stats.get("forehand"),
                backhand=stats.get("backhand"),
                build_type=capture.build_type
            )

            # Sauvegarder les equipements
            equipment = result.get("equipment", [])
            if equipment:
                equipment_data = [
                    {
                        'slot': eq.get('slot'),
                        'card_name': eq.get('name'),
                        'card_level': eq.get('level')
                    }
                    for eq in equipment
                    if eq.get('name') or eq.get('level')
                ]
                if equipment_data:
                    await PlayerEquipment.create_many(
                        self.bot.db_pool,
                        saved_stats.id,
                        equipment_data
                    )

            # Marquer comme valide
            await capture.update_status(self.bot.db_pool, CaptureStatus.VALIDATED)

            # Retirer de la liste des captures notifiees
            self._notified_captures.discard(capture.id)

            await msg.edit(
                content=f"Stats enregistrees pour **{character_name}** ({capture.player_name or '?'}, {capture.build_type}) !",
                view=None
            )
            logger.info(f"Capture {capture.id} validee par {user.name}")

        except Exception as e:
            logger.error(f"Erreur sauvegarde stats capture {capture.id}: {e}")
            await msg.edit(content=f"Erreur lors de l'enregistrement: {e}", view=None)

    async def _validate_capture_legacy(self, user: discord.User, capture: CaptureQueue, msg: discord.Message):
        """Valide une capture sans player_id/build_type (anciennes captures).

        Demande le joueur et build a l'utilisateur.

        Args:
            user: Utilisateur qui valide
            capture: Capture a valider
            msg: Message a mettre a jour
        """
        result = capture.result_json

        # Recuperer les joueurs du membre pour selection
        players = await Player.get_by_member(self.bot.db_pool, user.name)

        if not players:
            await msg.edit(
                content="Tu n'as pas de joueur enregistre. Contacte un Sage pour t'inscrire.",
                embed=None, view=None
            )
            await capture.update_status(self.bot.db_pool, CaptureStatus.REJECTED)
            return

        # Selectionner le joueur
        player_view = PlayerSelectView(players)
        await msg.edit(content="Selectionne le joueur pour ces stats:", embed=None, view=player_view)

        await player_view.wait()

        if player_view.cancelled or player_view.selected_player is None:
            await msg.edit(content="Validation annulee.", view=None)
            return

        selected_player_id = player_view.selected_player
        selected_player = next((p for p in players if p.id == selected_player_id), None)

        # Selectionner le build
        build_view = BuildSelectView()
        await msg.edit(content="Selectionne le type de build:", view=build_view)

        await build_view.wait()

        if build_view.cancelled or build_view.selected_build is None:
            await msg.edit(content="Validation annulee.", view=None)
            return

        # Sauvegarder en base
        try:
            stats = result.get("stats", {})
            character_name = result.get("character_name") or "Inconnu"
            selected_build = build_view.selected_build

            # Verifier si les stats sont identiques a la derniere capture
            last_stats = await PlayerStats.get_latest_for_build(
                self.bot.db_pool,
                selected_player_id,
                character_name,
                selected_build
            )

            # Creer un objet temporaire pour comparer
            new_stats = PlayerStats(
                id=None,
                discord_id=user.id,
                player_id=selected_player_id,
                character_name=character_name,
                points=result.get("points"),
                global_power=result.get("global_power"),
                agility=stats.get("agility"),
                endurance=stats.get("endurance"),
                serve=stats.get("serve"),
                volley=stats.get("volley"),
                forehand=stats.get("forehand"),
                backhand=stats.get("backhand"),
                build_type=selected_build
            )

            if last_stats and new_stats.is_same_as(last_stats):
                # Stats identiques - ne pas inserer
                await capture.update_status(self.bot.db_pool, CaptureStatus.VALIDATED)
                self._notified_captures.discard(capture.id)

                last_date = last_stats.captured_at.strftime("%d/%m/%Y") if last_stats.captured_at else "?"
                await msg.edit(
                    content=f"Pas de changement pour **{character_name}** ({selected_player.player_name if selected_player else '?'}, {selected_build}) depuis le {last_date}.\nCapture ignoree.",
                    view=None
                )
                logger.info(f"Capture {capture.id} ignoree (identique, legacy) par {user.name}")
                return

            # Stats differentes - inserer
            saved_stats = await PlayerStats.create(
                db_pool=self.bot.db_pool,
                discord_id=user.id,
                player_id=selected_player_id,
                character_name=character_name,
                points=result.get("points"),
                global_power=result.get("global_power"),
                agility=stats.get("agility"),
                endurance=stats.get("endurance"),
                serve=stats.get("serve"),
                volley=stats.get("volley"),
                forehand=stats.get("forehand"),
                backhand=stats.get("backhand"),
                build_type=selected_build
            )

            # Sauvegarder les equipements
            equipment = result.get("equipment", [])
            if equipment:
                equipment_data = [
                    {
                        'slot': eq.get('slot'),
                        'card_name': eq.get('name'),
                        'card_level': eq.get('level')
                    }
                    for eq in equipment
                    if eq.get('name') or eq.get('level')
                ]
                if equipment_data:
                    await PlayerEquipment.create_many(
                        self.bot.db_pool,
                        saved_stats.id,
                        equipment_data
                    )

            # Marquer comme valide
            await capture.update_status(self.bot.db_pool, CaptureStatus.VALIDATED)
            self._notified_captures.discard(capture.id)

            await msg.edit(
                content=f"Stats enregistrees pour **{character_name}** ({selected_player.player_name if selected_player else '?'}, {selected_build}) !",
                view=None
            )
            logger.info(f"Capture {capture.id} validee (legacy) par {user.name}")

        except Exception as e:
            logger.error(f"Erreur sauvegarde stats capture {capture.id}: {e}")
            await msg.edit(content=f"Erreur lors de l'enregistrement: {e}", view=None)

    async def _reject_capture(self, capture: CaptureQueue, msg: discord.Message):
        """Refuse une capture.

        Args:
            capture: Capture a refuser
            msg: Message a mettre a jour
        """
        await capture.update_status(self.bot.db_pool, CaptureStatus.REJECTED)
        self._notified_captures.discard(capture.id)
        await msg.edit(content="Capture refusee et supprimee.", embed=None, view=None)
        logger.info(f"Capture {capture.id} refusee")

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

        # Recuperer les joueurs du membre
        players = await Player.get_by_member(self.bot.db_pool, ctx.author.name)

        if not players:
            await reply_dm(
                ctx,
                "Tu n'as pas de joueur enregistre. Contacte un Sage pour t'inscrire."
            )
            return

        # Selection du joueur
        selected_player = None
        if len(players) == 1:
            # Auto-selection si un seul joueur
            selected_player = players[0]
            await reply_dm(ctx, f"Joueur: **{selected_player.player_name}** (auto)")
        else:
            # Afficher le menu de selection
            player_view = PlayerSelectView(players)
            msg = await reply_dm(ctx, "Selectionne le joueur pour cette capture:", view=player_view)

            await player_view.wait()

            if player_view.cancelled or player_view.selected_player is None:
                await reply_dm(ctx, "Capture annulee.")
                return

            selected_player = next((p for p in players if p.id == player_view.selected_player), None)

        # Selection du build
        build_view = BuildSelectView()
        await reply_dm(ctx, f"Joueur: **{selected_player.player_name}**\nSelectionne le type de build:", view=build_view)

        await build_view.wait()

        if build_view.cancelled or build_view.selected_build is None:
            await reply_dm(ctx, "Capture annulee.")
            return

        selected_build = build_view.selected_build

        # Message de confirmation
        await reply_dm(
            ctx,
            f"Joueur: **{selected_player.player_name}** | Build: **{selected_build}**\n"
            f"Transmission au moteur IA en cours..."
        )

        # Telecharger l'image en memoire (bytes)
        try:
            image_data = await attachment.read()
        except discord.HTTPException as e:
            logger.error(f"Erreur telechargement image: {e}")
            await reply_dm(ctx, get_text("stats.download_error", lang))
            return

        # Stocker en file d'attente avec joueur et build
        try:
            capture = await CaptureQueue.create(
                db_pool=self.bot.db_pool,
                discord_user_id=ctx.author.id,
                discord_username=ctx.author.name,
                discord_display_name=ctx.author.display_name,
                player_id=selected_player.id,
                build_type=selected_build,
                player_name=selected_player.player_name,
                image_data=image_data,
                image_filename=attachment.filename
            )

            # Compter les captures en attente
            pending_count = await CaptureQueue.count_pending(self.bot.db_pool)

            # Repondre a l'utilisateur
            await reply_dm(
                ctx,
                f"Image enregistree pour **{selected_player.player_name}** ({selected_build}).\n"
                f"Tu seras notifie quand elle aura ete traitee.\n"
                f"(Position dans la file: {pending_count})"
            )

            logger.info(f"Capture {capture.id} enregistree pour {ctx.author.name} (player={selected_player.player_name}, build={selected_build})")

            # Notifier l'admin
            await self._notify_admin_new_capture(ctx.author, capture.id, pending_count, selected_player.player_name, selected_build)

        except Exception as e:
            logger.error(f"Erreur enregistrement capture: {e}")
            await reply_dm(ctx, get_text("stats.save_error", lang))

    async def _notify_admin_new_capture(self, user: discord.User, capture_id: int, pending_count: int,
                                         player_name: str = None, build_type: str = None):
        """Notifie l'admin qu'une nouvelle capture est en attente.

        Args:
            user: Utilisateur qui a soumis la capture
            capture_id: ID de la capture
            pending_count: Nombre total de captures en attente
            player_name: Nom du joueur selectionne
            build_type: Type de build selectionne
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
            desc_lines = [
                f"**De:** {user.display_name} (@{user.name})",
                f"**Capture ID:** {capture_id}",
            ]
            if player_name:
                desc_lines.append(f"**Joueur:** {player_name}")
            if build_type:
                desc_lines.append(f"**Build:** {build_type}")
            desc_lines.append(f"**En attente:** {pending_count} image(s)")

            embed = discord.Embed(
                title="Nouvelle capture en attente",
                description="\n".join(desc_lines),
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

    @commands.command(name="captures", aliases=["stats-list"])
    async def list_captures(self, ctx, *, character_name: str = None):
        """Affiche un resume des captures enregistrees.

        Usage:
            !captures           - Resume par personnage
            !captures Mei-Li    - Detail pour un personnage
        """
        if character_name:
            await self._show_character_detail(ctx, character_name)
        else:
            await self._show_captures_summary(ctx)

    async def _show_captures_summary(self, ctx):
        """Affiche le resume des captures par personnage."""
        summary = await PlayerStats.get_summary_by_character(self.bot.db_pool)
        total = await PlayerStats.get_total_count(self.bot.db_pool)

        if not summary:
            await reply_dm(ctx, "Aucune capture enregistree.")
            return

        # Construire l'embed
        embed = discord.Embed(
            title="Captures enregistrees",
            description=f"**{total}** captures au total",
            color=discord.Color.blue()
        )

        # Formater la liste
        lines = []
        for item in summary[:15]:  # Max 15 personnages
            char = item['character_name']
            count = item['capture_count']
            players = item['player_count']
            lines.append(f"**{char}**: {count} capture(s) ({players} joueur(s))")

        if len(summary) > 15:
            lines.append(f"... et {len(summary) - 15} autre(s)")

        embed.add_field(
            name="Par personnage",
            value="\n".join(lines),
            inline=False
        )

        embed.set_footer(text="Utilise !captures <personnage> pour le detail")

        await reply_dm(ctx, embed=embed)

    async def _show_character_detail(self, ctx, character_name: str):
        """Affiche le detail des captures pour un personnage."""
        all_stats = await PlayerStats.get_all_for_character(self.bot.db_pool, character_name)

        if not all_stats:
            await reply_dm(ctx, f"Aucune capture pour **{character_name}**.")
            return

        # Grouper par player_id
        by_player = {}
        for stat in all_stats:
            if stat.player_id not in by_player:
                by_player[stat.player_id] = []
            by_player[stat.player_id].append(stat)

        embed = discord.Embed(
            title=f"Captures - {character_name}",
            description=f"**{len(all_stats)}** capture(s) par **{len(by_player)}** joueur(s)",
            color=discord.Color.blue()
        )

        # Afficher par joueur (derniere capture)
        for player_id, stats in list(by_player.items())[:10]:
            latest = stats[0]  # Deja trie par date desc

            # Recuperer le nom du joueur
            player = await Player.get_by_id(self.bot.db_pool, player_id)
            player_name = player.player_name if player else f"ID:{player_id}"

            # Infos
            date_str = latest.captured_at.strftime("%d/%m/%Y") if latest.captured_at else "?"
            value = (
                f"Puissance: **{latest.global_power or '?'}** | Points: {latest.points or '?'}\n"
                f"Build: {latest.build_type or '?'} | {len(stats)} capture(s)\n"
                f"Derniere: {date_str}"
            )

            embed.add_field(
                name=player_name,
                value=value,
                inline=True
            )

        if len(by_player) > 10:
            embed.set_footer(text=f"... et {len(by_player) - 10} autre(s) joueur(s)")

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
