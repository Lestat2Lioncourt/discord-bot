import discord
import json
from discord.ext import commands
import asyncio
import asyncpg
import logging
from pathlib import Path

from config import (
    DISCORD_TOKEN,
    DB_CONFIG,
    CHARTE_JSON_PATH,
    BOT_PREFIX,
    BASE_DIR,
)
from utils.database import Database
from utils.logger import get_logger
from utils.validators import validate_user_id, validate_username
from utils.debug import debug_only, is_debug_mode

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
# Connecteur à la base de données
# -------------------------------------------------------------------------------
db_pool = None

# ===============================================================================
# Charge les cogs (modules d'interaction avec le bot)
# ===============================================================================
async def load_cogs():
    """Charge dynamiquement les cogs dans le dossier cogs."""
    cogs_dir = BASE_DIR / "cogs"
    if not cogs_dir.exists():
        logger.error(f"Le dossier {cogs_dir} n'existe pas. Aucun cog n'a été chargé.")
        return

    for filepath in cogs_dir.glob("*.py"):
        cog_name = filepath.stem  # Nom du fichier sans extension
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
async def connect_to_db():
    global db_pool
    db_pool = await asyncpg.create_pool(**DB_CONFIG)
    logger.info("Base de données PostgreSQL connectée")

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
        async with db_pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO users (id, name) VALUES ($1, $2)",
                user_id, user_name
            )
        await ctx.send(f"Utilisateur {user_name} ajouté avec succès !")
        logger.info(f"Utilisateur ajouté: {user_name} (ID: {user_id})")
    except Exception as e:
        logger.error(f"Erreur ajout utilisateur: {e}")
        await ctx.send("Erreur lors de l'ajout de l'utilisateur.")

# ===============================================================================
# Commande `help` personnalisée
# ===============================================================================
@bot.command(name="help", aliases=["aide", "commands", "commandes"])
async def custom_help(ctx, command_name: str = None):
    """Commande personnalisee pour afficher une aide contextuelle."""

    # Details de toutes les commandes
    commands_details = {
        # General
        "help": {
            "desc": "Affiche cette aide.",
            "usage": "!help [commande]",
            "aliases": "!aide, !commands"
        },
        "langue": {
            "desc": "Change ta langue preferee (FR/EN).",
            "usage": "!langue",
            "aliases": "!language, !lang"
        },
        # Inscription
        "inscription": {
            "desc": "Demarre ou reprend le processus d'inscription.",
            "usage": "!inscription",
            "aliases": "-"
        },
        "profil": {
            "desc": "Affiche ton profil ou celui d'un membre.",
            "usage": "!profil [@membre]",
            "aliases": "-"
        },
        "joueur": {
            "desc": "Affiche tes joueurs et permet d'en ajouter.",
            "usage": "!joueur",
            "aliases": "!player, !joueurs, !players"
        },
        "localisation": {
            "desc": "Definit ta localisation pour la carte des membres.",
            "usage": "!localisation <ville ou adresse>",
            "aliases": "-"
        },
        # Sages
        "pending": {
            "desc": "Liste les inscriptions en attente de validation.",
            "usage": "!pending",
            "aliases": "!attente, !inscriptions",
            "sage": True
        },
        "valider": {
            "desc": "Valide un membre et le promeut en Membre.",
            "usage": "!valider @membre",
            "aliases": "!approve, !accepter",
            "sage": True
        },
        "refuser": {
            "desc": "Refuse un membre avec une raison optionnelle.",
            "usage": "!refuser @membre [raison]",
            "aliases": "!refuse, !reject",
            "sage": True
        },
        "profil-admin": {
            "desc": "Affiche le profil complet d'un membre (vue admin).",
            "usage": "!profil-admin @membre",
            "aliases": "!profile-admin",
            "sage": True
        },
    }

    if command_name is None:
        # Liste complete des commandes
        embed = discord.Embed(
            title="📚 Commandes disponibles",
            description="Utilise `!help <commande>` pour plus de details.",
            color=discord.Color.blue()
        )

        # Commandes generales
        embed.add_field(
            name="🌐 General",
            value=(
                "`!help` - Affiche cette aide\n"
                "`!langue` - Change ta langue (FR/EN)"
            ),
            inline=False
        )

        # Commandes inscription/profil
        embed.add_field(
            name="👤 Inscription & Profil",
            value=(
                "`!inscription` - Demarre l'inscription\n"
                "`!profil` - Affiche ton profil\n"
                "`!joueur` - Gere tes joueurs\n"
                "`!localisation` - Definit ta position"
            ),
            inline=False
        )

        # Commandes Sages
        embed.add_field(
            name="⚖️ Sages (moderateurs)",
            value=(
                "`!pending` - Inscriptions en attente\n"
                "`!valider @user` - Valide un membre\n"
                "`!refuser @user` - Refuse un membre\n"
                "`!profil-admin @user` - Profil complet"
            ),
            inline=False
        )

        embed.set_footer(text="This Is PSG - Tennis Clash Team")
        await ctx.send(embed=embed)

    else:
        # Details d'une commande specifique
        cmd = commands_details.get(command_name.lower())
        if cmd:
            embed = discord.Embed(
                title=f"📖 Commande `!{command_name.lower()}`",
                color=discord.Color.green()
            )
            embed.add_field(name="Description", value=cmd["desc"], inline=False)
            embed.add_field(name="Usage", value=f"`{cmd['usage']}`", inline=True)
            embed.add_field(name="Aliases", value=cmd["aliases"], inline=True)
            if cmd.get("sage"):
                embed.add_field(name="⚠️ Permission", value="Reservee aux Sages", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Commande `{command_name}` non reconnue. Utilise `!help` pour la liste.")

# ===============================================================================
# Fonction d'initialisation
# ===============================================================================
async def initialize_bot():
    """Initialise le bot en remplissant la table Charte."""
    from cogs.admin_commands import AdminCommandsCog
    admin_cog = AdminCommandsCog(bot)

    if not CHARTE_JSON_PATH.exists():
        logger.error(f"Le fichier {CHARTE_JSON_PATH} n'existe pas")
        return

    with open(CHARTE_JSON_PATH, "r", encoding="utf-8") as f:
        charte_data = json.load(f)

    await admin_cog.db.set_charte(charte_data)
    logger.info("Table Charte mise à jour avec succès")

# ===============================================================================
# Démarrage du bot avec reconnexion automatique en cas de plantage
# ===============================================================================
async def run_bot():
    while True:
        try:
            await connect_to_db()
            bot.db_pool = db_pool
            await load_cogs()
            await initialize_bot()
            await bot.start(TOKEN)
        except discord.ConnectionClosed:
            logger.warning("Connexion perdue. Reconnexion dans 5 secondes...")
            await asyncio.sleep(5)

@bot.event
async def on_close():
    """Ferme proprement la connexion PostgreSQL à l'arrêt du bot."""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Connexion PostgreSQL fermée proprement")

# ===============================================================================
# Démarrage du bot
# ===============================================================================
if __name__ == "__main__":
    async def main():
        global db_pool
        async with bot:
            try:
                await connect_to_db()
                bot.db_pool = db_pool
                await load_cogs()
                await initialize_bot()
                if is_debug_mode():
                    logger.warning("=== MODE DEBUG ACTIVÉ ===")
                logger.info("Démarrage du bot...")
                await bot.start(TOKEN)
            except KeyboardInterrupt:
                logger.info("Bot arrêté par l'utilisateur")
            finally:
                logger.info("Fermeture propre du bot...")
                await bot.close()
                if db_pool:
                    await db_pool.close()
                logger.info("Connexions fermées")

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except Exception as e:
        logger.critical(f"Erreur critique: {e}")
    finally:
        loop.run_until_complete(asyncio.sleep(1))
        loop.close()
