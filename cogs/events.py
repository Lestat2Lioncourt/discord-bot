"""
Cog pour gerer les evenements du bot.

Evenements geres:
- on_ready: Bot connecte et pret
- on_member_join: Nouveau membre (role Newbie + inscription auto)
- on_presence_update: Mise a jour last_connection + rappel charte
- on_member_update: Changements de profil membre
"""

import asyncio
import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from datetime import datetime, timedelta

from models.user_profile import UserProfile
from models.player import Player
from utils.database import Database
from utils.logger import get_logger
from utils.roles import assign_newbie_role, is_newbie, is_membre, is_sage
from utils.i18n import t
from utils.cache import TTLCache
from config import DATA_DIR, CHANNEL_ACCUEIL_ID

logger = get_logger("cogs.events")

# Delai minimum entre deux rappels de charte (24h)
CHARTE_REMINDER_COOLDOWN = timedelta(hours=24)


class EventsCog(commands.Cog):
    """Cog pour gerer les evenements du bot."""

    def __init__(self, bot):
        self.bot = bot
        # TTLCache pour profils actifs (5 min TTL, max 200 entrees)
        self.active_profiles: TTLCache = TTLCache(ttl_seconds=300, max_size=200)
        self.db = Database(bot.db_pool)  # Initialiser le module de base de donnees
        self.welcome_sent = False  # Flag pour verifier si le message de bienvenue a ete envoye
        # TTLCache pour rappels charte (25h TTL pour couvrir le cooldown de 24h)
        self.charte_reminders: TTLCache = TTLCache(ttl_seconds=90000, max_size=500)

    @commands.Cog.listener()
    async def on_ready(self):
        """Evenement declenche lorsque le bot est pret."""
        logger.info(f"{self.bot.user} est connecte et pret")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Evenement declenche lorsqu'un utilisateur rejoint le serveur."""
        logger.info(f"Nouveau membre: {member.name}")

        # Attribuer le role Newbie
        await assign_newbie_role(member)

        # Creer le profil en base de donnees
        async with self.bot.db_pool.acquire() as db_connection:
            await UserProfile.get_or_create_user(member.name, db_connection, member)

        # Demarrer automatiquement l'inscription en DM (pas de message public)
        registration_cog = self.bot.get_cog("RegistrationCog")
        if registration_cog:
            await registration_cog.start_registration(member)
        else:
            logger.warning("RegistrationCog non trouve")

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Evenement declenche lorsqu'un utilisateur change de statut."""
        logger.debug(f"Presence update: {after.name} ({before.status} -> {after.status})")

        # Mettre a jour le champ last_connection lors de la connexion
        if before.status != after.status and after.status in (discord.Status.online, discord.Status.idle):
            logger.info(f"Utilisateur connecte: {after.name} ({after.display_name})")

            # Verifier et mettre a jour discord_name et last_connection si necessaire
            async with self.bot.db_pool.acquire() as db_connection:
                user_profile = await UserProfile.get_or_create_user(after.name, db_connection, after)
                user_profile.last_connection = datetime.now()
                await user_profile.save()
                self.active_profiles.set(after.name, user_profile)
                logger.debug(f"Profil charge pour {after.display_name} [{after.name}]")

                # Inscription auto pour les Membres/Sages incomplets
                await self._check_incomplete_registration(after, user_profile)

        # Mettre a jour le champ last_connection lors de la deconnexion
        elif before.status in (discord.Status.online, discord.Status.idle) and after.status == discord.Status.offline:
            logger.info(f"Utilisateur deconnecte: {after.name} ({after.display_name})")

            # Verifier et mettre a jour last_connection si necessaire
            async with self.bot.db_pool.acquire() as db_connection:
                user_profile = await UserProfile.get_or_create_user(after.name, db_connection, after)
                user_profile.last_connection = datetime.now()
                await user_profile.save()
                logger.debug(f"Profil mis a jour pour {after.display_name}")

    async def _check_incomplete_registration(self, member: discord.Member, profile: UserProfile):
        """Lance l'inscription auto si charte non validee ou aucun joueur (1x / 24h max)."""
        # Ne concerne que les Membres ou Sages
        if not (is_membre(member) or is_sage(member)):
            return

        # Verifier si inscription incomplete
        charte_ok = profile.charte_validated
        players = await Player.get_by_member(self.bot.db_pool, member.name)
        has_players = len(players) > 0

        # Si tout est OK, rien a faire
        if charte_ok and has_players:
            return

        # Verifier le cooldown (1 rappel par 24h)
        now = datetime.now()
        last_reminder = self.charte_reminders.get(str(member.id))
        if last_reminder and (now - last_reminder) < CHARTE_REMINDER_COOLDOWN:
            logger.debug(f"Inscription auto ignoree pour {member.name} (cooldown)")
            return

        # Lancer l'inscription automatiquement
        lang = profile.language or "FR"
        try:
            if lang.upper() == "FR":
                msg = (
                    f"Bonjour {member.display_name} !\n\n"
                    "**Ton inscription n'est pas encore completement finalisee.**\n"
                    "Je relance le processus..."
                )
            else:
                msg = (
                    f"Hello {member.display_name}!\n\n"
                    "**Your registration is not yet complete.**\n"
                    "Restarting the process..."
                )

            await member.send(msg)
            self.charte_reminders.set(str(member.id), now)

            # Lancer le flow d'inscription
            registration_cog = self.bot.get_cog("RegistrationCog")
            if registration_cog:
                await registration_cog.start_registration(member)
                logger.info(f"Inscription auto lancee pour {member.name}")

        except discord.Forbidden:
            logger.debug(f"Impossible d'envoyer rappel charte a {member.name} (DMs fermes)")
        except discord.HTTPException as e:
            logger.error(f"Erreur envoi rappel charte a {member.name}: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Evenement declenche lorsqu'un utilisateur est mis a jour."""
        logger.debug(f"Member update: {before.status} -> {after.status}")


# ===============================================================================
# setup : Ajoute le cog des evenements au bot
# ===============================================================================
async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(EventsCog(bot))
