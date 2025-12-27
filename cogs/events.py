import asyncio
import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from datetime import datetime, timedelta

from models.user_profile import UserProfile
from utils.database import Database
from utils.logger import get_logger
from utils.roles import assign_newbie_role, is_newbie, is_membre, is_sage
from utils.i18n import t
from config import CHARTE_TEXTS, DATA_DIR, CHANNEL_ACCUEIL_ID

logger = get_logger("cogs.events")

# Delai minimum entre deux rappels de charte (24h)
CHARTE_REMINDER_COOLDOWN = timedelta(hours=24)


class EventsCog(commands.Cog):
    """Cog pour gerer les evenements du bot."""

    def __init__(self, bot):
        self.bot = bot
        self.active_profiles = {}  # Dictionnaire pour stocker les profils actifs
        self.db = Database(bot.db_pool)  # Initialiser le module de base de donnees
        self.welcome_sent = False  # Flag pour verifier si le message de bienvenue a ete envoye
        self.charte_reminders = {}  # {discord_id: datetime} pour limiter les rappels

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
                self.active_profiles[after.name] = user_profile
                logger.debug(f"Profil charge pour {after.display_name} [{after.name}]")

                # Rappel de charte pour les Membres/Sages qui n'ont pas valide
                await self._check_charte_reminder(after, user_profile)

        # Mettre a jour le champ last_connection lors de la deconnexion
        elif before.status in (discord.Status.online, discord.Status.idle) and after.status == discord.Status.offline:
            logger.info(f"Utilisateur deconnecte: {after.name} ({after.display_name})")

            # Verifier et mettre a jour last_connection si necessaire
            async with self.bot.db_pool.acquire() as db_connection:
                user_profile = await UserProfile.get_or_create_user(after.name, db_connection, after)
                user_profile.last_connection = datetime.now()
                await user_profile.save()
                logger.debug(f"Profil mis a jour pour {after.display_name}")

    async def _check_charte_reminder(self, member: discord.Member, profile: UserProfile):
        """Envoie un rappel si le membre n'a pas valide la charte (1 rappel / 24h max)."""
        # Ne concerne que les Membres ou Sages
        if not (is_membre(member) or is_sage(member)):
            return

        # Deja valide ?
        if profile.charte_validated:
            return

        # Verifier le cooldown (1 rappel par 24h)
        now = datetime.now()
        last_reminder = self.charte_reminders.get(member.id)
        if last_reminder and (now - last_reminder) < CHARTE_REMINDER_COOLDOWN:
            logger.debug(f"Rappel charte ignore pour {member.name} (cooldown)")
            return

        # Envoyer le rappel
        lang = profile.language or "FR"
        try:
            if lang.upper() == "FR":
                msg = (
                    f"Bonjour {member.display_name} !\n\n"
                    "Tu n'as pas encore valide la charte du serveur. "
                    "Merci de taper `!inscription` pour completer ton inscription."
                )
            else:
                msg = (
                    f"Hello {member.display_name}!\n\n"
                    "You haven't validated the server charter yet. "
                    "Please type `!inscription` to complete your registration."
                )

            await member.send(msg)
            self.charte_reminders[member.id] = now
            logger.info(f"Rappel charte envoye a {member.name}")

        except discord.Forbidden:
            logger.debug(f"Impossible d'envoyer rappel charte a {member.name} (DMs fermes)")
        except Exception as e:
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
