import asyncio
import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from datetime import datetime

from models.user_profile import UserProfile
from utils.database import Database
from utils.logger import get_logger
from utils.roles import assign_newbie_role, is_newbie, is_membre
from config import CHARTE_TEXTS, DATA_DIR, CHANNEL_ACCUEIL_ID

logger = get_logger("cogs.events")

class EventsCog(commands.Cog):
    """Cog pour gerer les evenements du bot."""

    def __init__(self, bot):
        self.bot = bot
        self.active_profiles = {}  # Dictionnaire pour stocker les profils actifs
        self.db = Database(bot.db_pool)  # Initialiser le module de base de donnees
        self.welcome_sent = False  # Flag pour verifier si le message de bienvenue a ete envoye

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

        # Envoyer un message dans le canal d'accueil
        accueil_channel = member.guild.get_channel(CHANNEL_ACCUEIL_ID)
        if accueil_channel:
            await accueil_channel.send(
                f"Bienvenue {member.mention} sur **{member.guild.name}** !\n\n"
                f"Pour commencer ton inscription, tape `!inscription` ici."
            )
        else:
            logger.warning(f"Canal accueil (ID: {CHANNEL_ACCUEIL_ID}) introuvable")

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

            # Verifier si l'utilisateur a valide la charte (ancien systeme)
            # TODO: Migrer vers le nouveau systeme avec !inscription
            total_clauses = await self.db.get_total_clauses()
            user_validations = await self.db.get_user_validations(after.name)
            logger.debug(f"Validations de {after.name}: {len(user_validations)}/{total_clauses}")

        # Mettre a jour le champ last_connection lors de la deconnexion
        elif before.status in (discord.Status.online, discord.Status.idle) and after.status == discord.Status.offline:
            logger.info(f"Utilisateur deconnecte: {after.name} ({after.display_name})")

            # Verifier et mettre a jour last_connection si necessaire
            async with self.bot.db_pool.acquire() as db_connection:
                user_profile = await UserProfile.get_or_create_user(after.name, db_connection, after)
                user_profile.last_connection = datetime.now()
                await user_profile.save()
                logger.debug(f"Profil mis a jour pour {after.display_name}")

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
