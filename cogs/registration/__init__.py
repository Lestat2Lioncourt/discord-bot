"""
Cog pour gerer l'inscription des nouveaux membres.

Flow:
1. Choix de la langue (FR/EN)
2. Validation de la charte (fichier HTML + bouton unique)
3. "As-tu des joueurs dans This Is PSG ?" -> saisie jusqu'a vide
4. "As-tu des joueurs dans This Is PSG 2 ?" -> saisie jusqu'a vide
5. Localisation (optionnel, pour la carte des membres)
6. En attente de validation par un Sage

Structure du module:
- views.py: Classes View pour les interactions (boutons)
- steps.py: Fonctions du flow d'inscription
- handlers.py: Commandes Discord (!inscription, !profil, etc.)
"""

import discord
from discord.ext import commands

from models.user_profile import UserProfile
from utils.database import Database
from utils.logger import get_logger

from .handlers import RegistrationCommands
from . import steps

logger = get_logger("cogs.registration")


class RegistrationCog(RegistrationCommands, commands.Cog):
    """Cog pour gerer l'inscription des nouveaux membres."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)
        self.active_registrations = {}  # username -> step

    async def start_registration(self, member: discord.Member):
        """Demarre le processus d'inscription pour un membre.

        Args:
            member: Membre Discord a inscrire
        """
        username = member.name
        logger.info(f"Demarrage inscription pour {username}")

        try:
            dm_channel = await member.create_dm()
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM a {username}")
            return

        # Verifier si c'est un revenant AVANT get_or_create (qui reinitialise le profil)
        returning_info = await UserProfile.check_returning_member(
            self.bot.db_pool, member.id, username
        )
        if returning_info:
            # Stocker pour notification a la fin de l'inscription
            self.active_registrations[f"{username}_returning"] = returning_info

        # Verifier le profil (reinitialise si 'deleted')
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)

        # Si deja valide, ne pas relancer
        if profile.charte_validated and profile.approval_status == "approved":
            lang = profile.language
            from utils.i18n import t
            await dm_channel.send(t("welcome.already_registered", lang))
            return

        # Marquer comme en cours d'inscription
        self.active_registrations[username] = "language"

        # Message d'intro avec info sur !inscription
        await dm_channel.send(
            "═" * 35 + "\n"
            "🎾 **INSCRIPTION - THIS IS PSG** 🎾\n"
            "═" * 35 + "\n\n"
            "*Tu peux relancer ce processus a tout moment avec la commande `!inscription`*"
        )

        # Etape 1: Choix de la langue
        await steps.ask_language(self, member, dm_channel)


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(RegistrationCog(bot))
