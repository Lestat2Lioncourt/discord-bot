"""
Views pour le processus d'inscription.

Contient les vues interactives Discord (boutons) pour:
- Selection de langue
- Acceptation de la charte
- Conservation ou reinitialisation des joueurs
"""

import discord
from discord.ui import View, Button
from discord import ButtonStyle, Interaction

from constants import Timeouts
from utils.i18n import t
from utils.logger import get_logger

logger = get_logger("registration.views")


class LanguageSelectView(View):
    """Vue pour choisir la langue."""

    def __init__(self, member: discord.Member):
        super().__init__(timeout=Timeouts.LANGUAGE_SELECT)
        self.member = member
        self.language = None

    @discord.ui.button(label="🇫🇷", style=ButtonStyle.primary)
    async def french(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user != self.member:
            return
        self.language = "FR"
        try:
            await interaction.message.edit(content="🇫🇷 Francais selectionne", view=None)
        except Exception as e:
            logger.debug(f"Impossible de modifier le message de selection de langue: {e}")
        self.stop()

    @discord.ui.button(label="🇬🇧", style=ButtonStyle.primary)
    async def english(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user != self.member:
            return
        self.language = "EN"
        try:
            await interaction.message.edit(content="🇬🇧 English selected", view=None)
        except Exception as e:
            logger.debug(f"Impossible de modifier le message de selection de langue: {e}")
        self.stop()


class CharteAcceptView(View):
    """Vue pour accepter/refuser la charte."""

    def __init__(self, member: discord.Member, lang: str = "FR"):
        super().__init__(timeout=Timeouts.CHARTE_READ)
        self.member = member
        self.lang = lang
        self.accepted = False

        # Modifier les labels des boutons selon la langue
        self.accept_btn.label = t("charte.accept_button", lang)
        self.refuse_btn.label = t("charte.refuse_button", lang)

    @discord.ui.button(label="J'accepte", style=ButtonStyle.green, custom_id="accept")
    async def accept_btn(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user != self.member:
            return
        self.accepted = True
        try:
            await interaction.message.edit(content="✅", view=None)
        except Exception as e:
            logger.debug(f"Impossible de modifier le message d'acceptation de charte: {e}")
        self.stop()

    @discord.ui.button(label="Je refuse", style=ButtonStyle.red, custom_id="refuse")
    async def refuse_btn(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user != self.member:
            return
        self.accepted = False
        try:
            await interaction.message.edit(content="❌", view=None)
        except Exception as e:
            logger.debug(f"Impossible de modifier le message de refus de charte: {e}")
        self.stop()


class KeepOrResetView(View):
    """Vue pour choisir de conserver ou effacer les joueurs existants."""

    def __init__(self, member: discord.Member, lang: str = "FR"):
        super().__init__(timeout=Timeouts.KEEP_OR_RESET)
        self.member = member
        self.lang = lang
        self.keep = None

        self.keep_btn.label = t("profile.keep_button", lang)
        self.reset_btn.label = t("profile.reset_button", lang)

    @discord.ui.button(label="Conserver", style=ButtonStyle.green, custom_id="keep")
    async def keep_btn(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user != self.member:
            return
        self.keep = True
        try:
            await interaction.message.edit(content=t("profile.players_kept", self.lang), view=None)
        except Exception as e:
            logger.debug(f"Impossible de modifier le message de conservation des joueurs: {e}")
        self.stop()

    @discord.ui.button(label="Tout effacer", style=ButtonStyle.red, custom_id="reset")
    async def reset_btn(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user != self.member:
            return
        self.keep = False
        try:
            await interaction.message.edit(content=t("profile.players_deleted", self.lang), view=None)
        except Exception as e:
            logger.debug(f"Impossible de modifier le message de suppression des joueurs: {e}")
        self.stop()
