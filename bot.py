import discord
from discord.ext import commands
import asyncio
import asyncpg
import logging

from config import (
    DISCORD_TOKEN,
    DB_CONFIG,
    BOT_PREFIX,
    BASE_DIR,
    validate_config,
)
from utils.logger import get_logger
from utils.validators import validate_user_id, validate_username
from utils.debug import debug_only, is_debug_mode
from utils.i18n import t
from utils.migrations import run_migrations, fix_missing_location_display
from models.user_profile import UserProfile

# ===============================================================================
# Initialisations
# ===============================================================================
TOKEN = DISCORD_TOKEN
logger = get_logger("main")

# -------------------------------------------------------------------------------
# Intents - Sélection des fonctionnalités du bot actives
# -------------------------------------------------------------------------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True    # Permet d'accéder aux informations des serveurs
intents.members = True   # Ajout des intents pour détecter les nouveaux membres
intents.presences = True

# -------------------------------------------------------------------------------
# Configure le niveau de log de discord.py pour ignorer les messages
# d'information
# -------------------------------------------------------------------------------
logging.getLogger("discord").setLevel(logging.WARNING)

# -------------------------------------------------------------------------------
# Configure le caractère préfixe et désactiver la commande `help` native
# strip_after_prefix=True permet d'ignorer les espaces après "!" (utile sur mobile)
# -------------------------------------------------------------------------------
bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    help_command=None,
    strip_after_prefix=True,
    case_insensitive=True  # Ignore la casse (utile sur mobile)
)

# -------------------------------------------------------------------------------
# Note: La connexion DB est stockée dans bot.db_pool (pas de variable globale)
# -------------------------------------------------------------------------------

# ===============================================================================
# Charge les cogs (modules d'interaction avec le bot)
# ===============================================================================
async def load_cogs():
    """Charge dynamiquement les cogs dans le dossier cogs."""
    cogs_dir = BASE_DIR / "cogs"
    if not cogs_dir.exists():
        logger.error(f"Le dossier {cogs_dir} n'existe pas. Aucun cog n'a été chargé.")
        return

    cog_names = []

    # Fichiers .py (sauf __init__.py)
    for filepath in cogs_dir.glob("*.py"):
        if filepath.name != "__init__.py":
            cog_names.append(filepath.stem)

    # Packages (dossiers avec __init__.py)
    for dirpath in cogs_dir.iterdir():
        if dirpath.is_dir() and (dirpath / "__init__.py").exists():
            cog_names.append(dirpath.name)

    for cog_name in cog_names:
        try:
            await bot.load_extension(f"cogs.{cog_name}")
            logger.info(f"Cog '{cog_name}' chargé avec succès")
        except commands.ExtensionAlreadyLoaded:
            logger.warning(f"Cog '{cog_name}' était déjà chargé")
        except commands.ExtensionNotFound:
            logger.error(f"Cog '{cog_name}' introuvable")
        except commands.NoEntryPointError:
            logger.error(f"Cog '{cog_name}' ne contient pas de fonction setup()")
        except commands.ExtensionFailed as e:
            logger.error(f"Échec du chargement de '{cog_name}': {e}")

# ===============================================================================
# Fonction de connexion à PostgreSQL
# ===============================================================================
async def connect_to_db() -> asyncpg.Pool:
    """Crée et retourne un pool de connexions PostgreSQL."""
    pool = await asyncpg.create_pool(**DB_CONFIG)
    logger.info("Base de données PostgreSQL connectée")
    return pool


async def close_db_pool():
    """Ferme proprement le pool de connexions."""
    if hasattr(bot, 'db_pool') and bot.db_pool:
        await bot.db_pool.close()
        bot.db_pool = None
        logger.info("Pool PostgreSQL fermé")

# ===============================================================================
# Commande test pour interagir avec la base de données
# ===============================================================================
@bot.command()
@debug_only()
async def add_user(ctx, user_id: int, user_name: str):
    """Ajoute un utilisateur dans la base de données."""
    # Validation des inputs
    is_valid, error = validate_user_id(user_id)
    if not is_valid:
        await ctx.send(f"Erreur: {error}")
        return

    is_valid, error = validate_username(user_name)
    if not is_valid:
        await ctx.send(f"Erreur: {error}")
        return

    try:
        async with bot.db_pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO users (id, name) VALUES ($1, $2)",
                user_id, user_name
            )
        await ctx.send(f"Utilisateur {user_name} ajouté avec succès !")
        logger.info(f"Utilisateur ajouté: {user_name} (ID: {user_id})")
    except asyncpg.PostgresError as e:
        logger.error(f"Erreur ajout utilisateur: {e}")
        await ctx.send("Erreur lors de l'ajout de l'utilisateur.")

# ===============================================================================
# Commande `help` personnalisée
# ===============================================================================
@bot.command(name="help", aliases=["aide", "commands", "commandes"])
async def custom_help(ctx, command_name: str = None):
    """Commande personnalisee pour afficher une aide contextuelle."""

    # Recuperer la langue de l'utilisateur
    lang = "FR"
    try:
        async with bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
            lang = profile.language or "FR"
    except asyncpg.PostgresError as e:
        logger.debug(f"Impossible de recuperer la langue pour {ctx.author.name}, utilisation FR par defaut: {e}")

    # Details de toutes les commandes (FR/EN)
    commands_details = {
        # General
        "help": {
            "desc_fr": "Affiche cette aide.",
            "desc_en": "Shows this help.",
            "usage": "!help [command]",
            "aliases": "!aide, !commands"
        },
        "langue": {
            "desc_fr": "Change ta langue preferee (FR/EN).",
            "desc_en": "Change your preferred language (FR/EN).",
            "usage": "!langue",
            "aliases": "!language, !lang"
        },
        # Inscription
        "inscription": {
            "desc_fr": "Demarre ou reprend le processus d'inscription.",
            "desc_en": "Start or resume the registration process.",
            "usage": "!inscription",
            "aliases": "-"
        },
        "profil": {
            "desc_fr": "Affiche ton profil ou celui d'un membre.",
            "desc_en": "Show your profile or another member's.",
            "usage": "!profil [@member]",
            "aliases": "-"
        },
        "joueur": {
            "desc_fr": "Affiche tes joueurs et permet d'en ajouter.",
            "desc_en": "Show your players and add new ones.",
            "usage": "!joueur",
            "aliases": "!player, !joueurs, !players"
        },
        "localisation": {
            "desc_fr": "Definit ta localisation pour la carte des membres.",
            "desc_en": "Set your location for the members map.",
            "usage": "!localisation <city or address>",
            "aliases": "-"
        },
        "users": {
            "desc_fr": "Liste tous les membres enregistres.",
            "desc_en": "List all registered members.",
            "usage": "!users",
            "aliases": "!utilisateurs"
        },
        # Sages
        "pending": {
            "desc_fr": "Liste les inscriptions en attente de validation.",
            "desc_en": "List pending registrations.",
            "usage": "!pending",
            "aliases": "!attente, !inscriptions",
            "sage": True
        },
        "valider": {
            "desc_fr": "Valide un membre et le promeut en Membre.",
            "desc_en": "Approve a member and promote to Member.",
            "usage": "!valider @member",
            "aliases": "!approve, !accepter",
            "sage": True
        },
        "refuser": {
            "desc_fr": "Refuse un membre avec une raison optionnelle.",
            "desc_en": "Reject a member with an optional reason.",
            "usage": "!refuser @member [reason]",
            "aliases": "!refuse, !reject",
            "sage": True
        },
        "profil-admin": {
            "desc_fr": "Affiche le profil complet d'un membre (vue admin).",
            "desc_en": "Show full member profile (admin view).",
            "usage": "!profil-admin @member",
            "aliases": "!profile-admin",
            "sage": True
        },
        "audit-permissions": {
            "desc_fr": "Exporte les permissions par salon et par role.",
            "desc_en": "Export permissions by channel and role.",
            "usage": "!audit-permissions",
            "aliases": "!audit-perms, !perms",
            "sage": True
        },
        "reset": {
            "desc_fr": "Reinitialise un membre pour tests (debug uniquement).",
            "desc_en": "Reset a member for testing (debug only).",
            "usage": "!reset @member",
            "aliases": "-",
            "sage": True
        },
        "stats": {
            "desc_fr": "Affiche les statistiques de la communaute (membres, joueurs, carte).",
            "desc_en": "Show community statistics (members, players, map).",
            "usage": "!stats",
            "aliases": "!statistiques, !dashboard"
        },
        "capture": {
            "desc_fr": "Soumet une capture d'ecran Tennis Clash pour analyse IA.",
            "desc_en": "Submit a Tennis Clash screenshot for AI analysis.",
            "usage": "!capture + image jointe",
            "aliases": "!cap"
        },
        "captures": {
            "desc_fr": "Liste tes captures enregistrees par personnage.",
            "desc_en": "List your recorded captures by character.",
            "usage": "!captures [personnage]",
            "aliases": "!stats-list"
        },
        "evolution": {
            "desc_fr": "Affiche l'evolution d'un personnage dans le temps.",
            "desc_en": "Show character evolution over time.",
            "usage": "!evolution <personnage>",
            "aliases": "!evo, !history"
        },
        "compare": {
            "desc_fr": "Compare un personnage entre tous les joueurs.",
            "desc_en": "Compare a character across all players.",
            "usage": "!compare <personnage>",
            "aliases": "!cmp"
        },
        "builds": {
            "desc_fr": "Liste les joueurs groupes par type de build.",
            "desc_en": "List players grouped by build type.",
            "usage": "!builds",
            "aliases": "!profils"
        },
    }

    if command_name is None:
        # Liste complete des commandes
        embed = discord.Embed(
            title=t("help_cmd.title", lang),
            description=t("help_cmd.subtitle", lang),
            color=discord.Color.blue()
        )

        # Commandes generales
        embed.add_field(
            name=t("help_cmd.general", lang),
            value=t("help_cmd.general_list", lang),
            inline=True
        )

        # Commandes inscription/profil
        embed.add_field(
            name=t("help_cmd.profile", lang),
            value=t("help_cmd.profile_list", lang),
            inline=True
        )

        # Stats joueurs
        embed.add_field(
            name=t("help_cmd.stats", lang),
            value=t("help_cmd.stats_list", lang),
            inline=True
        )

        # Communaute
        embed.add_field(
            name=t("help_cmd.community", lang),
            value=t("help_cmd.community_list", lang),
            inline=True
        )

        # Commandes Sages
        embed.add_field(
            name=t("help_cmd.sages", lang),
            value=t("help_cmd.sages_list", lang),
            inline=True
        )

        embed.set_footer(text=t("help_cmd.footer", lang))
        await ctx.send(embed=embed)

    else:
        # Details d'une commande specifique
        cmd = commands_details.get(command_name.lower())
        if cmd:
            embed = discord.Embed(
                title=t("help_cmd.cmd_title", lang, cmd=command_name.lower()),
                color=discord.Color.green()
            )
            desc = cmd["desc_fr"] if lang.upper() == "FR" else cmd["desc_en"]
            embed.add_field(name=t("help_cmd.description", lang), value=desc, inline=False)
            embed.add_field(name=t("help_cmd.usage", lang), value=f"`{cmd['usage']}`", inline=True)
            embed.add_field(name=t("help_cmd.aliases", lang), value=cmd["aliases"], inline=True)
            if cmd.get("sage"):
                embed.add_field(name=t("help_cmd.permission", lang), value=t("help_cmd.sage_only", lang), inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(t("help_cmd.unknown_cmd", lang, cmd=command_name))

# ===============================================================================
# Gestion des erreurs de commande
# ===============================================================================
@bot.event
async def on_command_error(ctx, error):
    """Gere les erreurs de commande."""
    if isinstance(error, commands.CommandNotFound):
        cmd = ctx.message.content.split()[0]
        await ctx.send(f"Commande `{cmd}` inconnue. Tape `!help` pour voir les commandes disponibles.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Argument manquant. Tape `!help {ctx.command}` pour voir l'usage.")
    elif isinstance(error, commands.CheckFailure):
        # Permission refusee (ex: sage_only, debug_only)
        pass  # Silencieux, le decorateur gere deja le message
    else:
        logger.error(f"Erreur commande {ctx.command}: {error}")

@bot.event
async def on_close():
    """Ferme proprement la connexion PostgreSQL à l'arrêt du bot."""
    await close_db_pool()

# ===============================================================================
# Démarrage du bot
# ===============================================================================
if __name__ == "__main__":
    async def main():
        # Validation de la configuration au démarrage
        config_warnings = validate_config()
        for warning in config_warnings:
            logger.warning(f"CONFIG: {warning}")

        async with bot:
            try:
                # Connexion DB et stockage dans bot.db_pool
                bot.db_pool = await connect_to_db()

                # Executer les migrations automatiquement
                try:
                    executed, total = await run_migrations(bot.db_pool)
                    if executed > 0:
                        logger.info(f"Migrations: {executed}/{total} appliquee(s)")
                except (asyncpg.PostgresError, OSError) as e:
                    logger.error(f"Erreur migrations: {e}")
                    raise

                # Corriger les location_display manquants
                try:
                    fixed = await fix_missing_location_display(bot.db_pool)
                    if fixed > 0:
                        logger.info(f"Location display: {fixed} profil(s) corrige(s)")
                except Exception as e:
                    logger.warning(f"Erreur correction location_display: {e}")

                await load_cogs()
                if is_debug_mode():
                    logger.warning("=== MODE DEBUG ACTIVÉ ===")
                logger.info("Démarrage du bot...")
                await bot.start(TOKEN)
            except KeyboardInterrupt:
                logger.info("Bot arrêté par l'utilisateur")
            finally:
                logger.info("Fermeture propre du bot...")
                await bot.close()
                await close_db_pool()
                logger.info("Connexions fermées")

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except Exception as e:
        logger.critical(f"Erreur critique: {e}")
    finally:
        loop.run_until_complete(asyncio.sleep(1))
        loop.close()
