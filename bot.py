import discord
import json
from discord.ext import commands
import asyncio
import asyncpg
import logging
from security.credentials import DISCORD_TOKEN, DB_DISCORD
import os
from utils.database import Database  # Importer le module de base de données

# ===============================================================================
# Initialisations
# ===============================================================================
TOKEN = DISCORD_TOKEN

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
logging.basicConfig(level=logging.INFO)

# -------------------------------------------------------------------------------
# Configure le caractère préfixe et désactiver la commande `help` native
# -------------------------------------------------------------------------------
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# -------------------------------------------------------------------------------
# Connecteur à la base de données
# -------------------------------------------------------------------------------
db_pool = None

# ===============================================================================
# Charge les cogs (modules d'interaction avec le bot)
# ===============================================================================
async def load_cogs():
    """Charge dynamiquement les cogs dans le dossier cogs."""
    cogs_dir = "cogs"
    if not os.path.exists(cogs_dir):
        print(f"Le dossier {cogs_dir} n'existe pas. Aucun cog n'a été chargé.")
        return

    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py"):
            cog_name = filename[:-3]  # Retirer l'extension .py
            try:
                await bot.load_extension(f"cogs.{cog_name}")
                print(f"✅ {cog_name} chargé avec succès.")
            except commands.ExtensionAlreadyLoaded:
                print(f"⚠️ {cog_name} était déjà chargé.")
            except commands.ExtensionNotFound:
                print(f"❌ {cog_name} introuvable.")
            except commands.NoEntryPointError:
                print(f"❌ {cog_name} ne contient pas de fonction `setup()`.")
            except commands.ExtensionFailed as e:
                print(f"❌ Échec du chargement de {cog_name}: {e}")

# ===============================================================================
# Fonction de connexion à PostgreSQL
# ===============================================================================
async def connect_to_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=DB_DISCORD["DB_HOST"],
        database=DB_DISCORD["DB_NAME"],
        user=DB_DISCORD["DB_USER"],
        password=DB_DISCORD["DB_PASSWORD"],
        port=DB_DISCORD["DB_PORT"])
    print("✅ Base de données connectée.")

# ===============================================================================
# Commande test pour interagir avec la base de données
# ===============================================================================
@bot.command()
async def add_user(ctx, user_id: int, user_name: str):
    """Ajoute un utilisateur dans la base de données."""
    async with db_pool.acquire() as connection:
        await connection.execute(
            "INSERT INTO users (id, name) VALUES ($1, $2)",
            user_id, user_name
        )
    await ctx.send(f"Utilisateur {user_name} ajouté avec succès !")

# ===============================================================================
# Commande `help` personnalisée
# ===============================================================================
@bot.command(name="help")
async def custom_help(ctx, command_name: str = None):
    """Commande personnalisée pour afficher une aide contextuelle."""

    if command_name is None:
        # Création de l'embed pour la liste des commandes
        embed = discord.Embed(
            title="Liste des commandes disponibles",
            description="Utilisez `!help <commande>` pour plus de détails sur une commande spécifique.",
            color=discord.Color.blue()
        )
        embed.add_field(name="!help", value="Affiche cette aide.", inline=False)
        embed.add_field(name="!add_user", value="Ajoute un utilisateur dans la base de données. (Usage : `!add_user <id> <nom>`)", inline=False)

        await ctx.send(embed=embed)

    else:
        # Détails d'une commande spécifique
        commands_details = {
            "help": "Affiche la liste des commandes ou des informations sur une commande spécifique.",
            "add_user": "Ajoute un utilisateur dans la base de données. Usage : `!add_user <id> <nom>`"
        }
        detail = commands_details.get(command_name.lower(), "Commande non reconnue. Utilisez `!help` pour la liste complète.")
        embed = discord.Embed(
            title=f"Détails de la commande `{command_name}`",
            description=detail,
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

# ===============================================================================
# Fonction d'initialisation
# ===============================================================================
async def initialize_bot():
    """Initialise le bot en remplissant la table Charte."""
    from cogs.admin_commands import AdminCommandsCog  # Importer le cog des commandes d'administration
    admin_cog = AdminCommandsCog(bot)
    charte_path = "data/charte.json"

    if not os.path.exists(charte_path):
        print(f"❌ Le fichier `{charte_path}` n'existe pas.")
        return

    with open(charte_path, "r", encoding="utf-8") as f:
        charte_data = json.load(f)

    await admin_cog.db.set_charte(charte_data)
    print("✅ La table `Charte` a été mise à jour avec succès.")

# ===============================================================================
# Démarrage du bot avec reconnexion automatique en cas de plantage
# ===============================================================================
async def run_bot():
    while True:
        try:
            # Connexion à la base de données avant de démarrer le bot
            await connect_to_db()
            bot.db_pool = db_pool  # Attache db_pool à l'objet bot
            await load_cogs()
            await initialize_bot()  # Appeler la fonction d'initialisation
            await bot.start(TOKEN)
        except discord.ConnectionClosed:
            print("Connexion perdue. Reconnexion dans 5 secondes...")
            await asyncio.sleep(5)

@bot.event
async def on_close():
    """Ferme proprement la connexion PostgreSQL à l'arrêt du bot."""
    global db_pool
    if db_pool:
        await db_pool.close()
        print("✅ Connexion PostgreSQL fermée proprement.")

# ===============================================================================
# Démarrage du bot
# ===============================================================================
if __name__ == "__main__":
    async def main():
        global db_pool
        async with bot:
            try:
                # Connexion à la base de données
                await connect_to_db()
                bot.db_pool = db_pool  # Attache db_pool à l'objet bot

                # Chargement des cogs
                await load_cogs()

                # Initialisation du bot
                await initialize_bot()

                # Démarrer le bot
                await bot.start(TOKEN)
            except KeyboardInterrupt:
                print("🛑 Bot arrêté par l'utilisateur.")
            finally:
                # Fermeture propre des connexions
                print("🔄 Fermeture propre du bot...")
                await bot.close()
                if db_pool:
                    await db_pool.close()
                print("✅ Connexions fermées.")

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except Exception as e:
        print(f"❌ Erreur critique : {e}")
    finally:
        loop.run_until_complete(asyncio.sleep(1))  # Laisser le temps aux connexions de se fermer
        loop.close()
