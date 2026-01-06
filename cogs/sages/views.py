"""
Classes View pour les commandes Sage.

Fournit les interfaces utilisateur pour:
- Confirmation de suppression (auto et par Sage)
- Boutons Valider/Refuser sur les notifications
"""

from typing import Optional

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, View

from utils.roles import is_sage
from utils.logger import get_logger

logger = get_logger("cogs.sages.views")


class DeleteConfirmView(View):
    """Vue de confirmation pour l'auto-suppression d'un utilisateur."""

    def __init__(self, target: discord.Member, author: discord.Member):
        super().__init__(timeout=30)
        self.target = target
        self.author = author
        self.confirmed = False

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce n'est pas ta demande.", ephemeral=True)
            return
        await interaction.response.defer()
        self.confirmed = False
        self.stop()

    @discord.ui.button(label="SUPPRIMER DEFINITIVEMENT", style=discord.ButtonStyle.danger)
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

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
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

    @discord.ui.button(label="Confirmer (autre Sage)", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: Interaction, button: discord.ui.Button):
        # Verifier que c'est un Sage different
        if interaction.user.id == self.requesting_sage.id:
            await interaction.response.send_message(
                "Tu ne peux pas valider ta propre demande de suppression.\n"
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
