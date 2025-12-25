import discord
from discord.ext import commands
from utils.image_processing import process_image
from utils.logger import get_logger
from utils.database import Database
from utils.validators import validate_pseudo, validate_image_attachment
import json
import asyncio
from datetime import datetime

from config import CHARTE_JSON_PATH, DATA_DIR, TEMP_DIR

logger = get_logger("cogs.user_commands")


class UserCommandsCog(commands.Cog):
    """Commandes accessibles à tous les utilisateurs."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)

        # Charger la structure de la charte (pour les chemins des fichiers)
        with open(CHARTE_JSON_PATH, "r", encoding="utf-8") as f:
            self.charte = json.load(f)

    @commands.command()
    async def hello(self, ctx):
        """Commande pour dire bonjour."""
        await ctx.send("Bonjour ! Je suis en ligne.")

    @commands.command()
    async def charte(self, ctx):
        """Affiche la charte de la team."""
        await ctx.send("""
        **This is PSG** est une team cool mais ambitieuse.
        """)

    @commands.command(name="profile")
    async def list_profile(self, ctx):
        """Affiche le profil de l'utilisateur qui exécute la commande (version debug)."""
        async with self.bot.db_pool.acquire() as connection:
            query = """
            SELECT username, discord_name, language, localisation, latitude, longitude,
                   creation_date, last_connection, charte_validated, approval_status
            FROM user_profile
            WHERE username = $1
            """
            user = await connection.fetchrow(query, ctx.author.name)

        if user is None:
            await ctx.send("❌ Aucun profil trouvé pour vous dans la base de données.")
            return

        # Construction du message
        message = ("\n"
            f"`Username....... : {user['username'] or 'Non renseigné'}`\n"
            f"`Discord Name... : {user['discord_name'] or 'Non renseigné'}`\n"
            f"`Language....... : {user['language'] or 'Non renseigné'}`\n"
            f"`Localisation... : {user['localisation'] or 'Non renseigné'}`\n"
            f"`Latitude....... : {user['latitude'] or 'Non renseigné'}`\n"
            f"`Longitude...... : {user['longitude'] or 'Non renseigné'}`\n"
            f"`Creation Date.. : {user['creation_date'] or 'Non renseigné'}`\n"
            f"`Last Connection : {user['last_connection'] or 'Non renseigné'}`\n"
            f"`Charte......... : {'Validée' if user['charte_validated'] else 'Non validée'}`\n"
            f"`Statut......... : {user['approval_status'] or 'pending'}`\n"
        )
        await ctx.send(message)

    @commands.command(name="users", aliases=["utilisateurs"])
    async def list_users(self, ctx):
        """Affiche la liste des utilisateurs enregistrés dans la base de données."""
        async with self.bot.db_pool.acquire() as connection:
            users = await connection.fetch("""SELECT creation_date, 
                                                     last_connection, 
                                                     username, 
                                                     discord_name 
                                              FROM   user_profile
                                            ORDER BY last_connection DESC """)

        if users:
            user_list = "```"
            for user in users:
                user_list += f"{user['last_connection'].strftime('%Y-%m-%d %H:%M')} - {user['username']} ({user['discord_name']})\n"
            user_list += "```"
            
            embed = discord.Embed(
                title="📜 Liste des utilisateurs enregistrés",
                description=user_list,
                color=discord.Color.blue()
            )
            logger.debug(f"Liste utilisateurs: {len(users)} résultats")
        else:
            embed = discord.Embed(
                title="📜 Liste des utilisateurs enregistrés",
                description="Aucun utilisateur trouvé en base.",
                color=discord.Color.red()
            )
        await ctx.send(embed=embed)

    @commands.command(name="db_status")
    async def db_status(self, ctx):
        """Vérifie si la connexion à la base de données est active."""
        try:
            async with self.bot.db_pool.acquire() as connection:
                await connection.fetchval("SELECT 1")  # Exécute une requête test
            embed = discord.Embed(
                title="🟢 Connexion réussie",
                description="La connexion à la base de données est active.",
                color=discord.Color.green()
            )
        except Exception as e:
            embed = discord.Embed(
                title="🔴 Erreur de connexion",
                description=f"Impossible de se connecter à la base de données.\nErreur : {e}",
                color=discord.Color.red()
            )
        await ctx.send(embed=embed)

    @commands.command(name="pseudo")
    async def update_pseudo(self, ctx, new_pseudo: str):
        """Permet à un utilisateur de modifier son display_name."""
        # Validation du pseudo
        is_valid, error = validate_pseudo(new_pseudo)
        if not is_valid:
            await ctx.send(f"Erreur: {error}")
            return

        try:
            async with self.bot.db_pool.acquire() as connection:
                query = """
                UPDATE user_profile
                SET discord_name = $1
                WHERE username = $2
                """
                await connection.execute(query, new_pseudo, ctx.author.name)

            await ctx.send(f"Votre pseudo a été mis à jour en `{new_pseudo}`.")
            logger.info(f"{ctx.author.name} a changé son pseudo en '{new_pseudo}'")
        except Exception as e:
            logger.error(f"Erreur mise à jour pseudo: {e}")
            await ctx.send("Erreur lors de la mise à jour du pseudo.")

    @commands.command(name="template")
    async def process_template(self, ctx):
        """Traite l'image jointe à la commande et génère un fichier JSON."""
        if len(ctx.message.attachments) == 0:
            await ctx.send("Aucune image jointe à la commande.")
            return

        attachment = ctx.message.attachments[0]

        # Validation de l'image
        is_valid, error = validate_image_attachment(attachment.filename, attachment.size)
        if not is_valid:
            await ctx.send(f"Erreur: {error}")
            return

        try:
            # Télécharger l'image jointe
            image_path = TEMP_DIR / f"temp_{attachment.filename}"
            await attachment.save(str(image_path))

            # Traiter l'image avec le script de traitement
            json_path = process_image(str(image_path))

            # Lire le contenu du fichier JSON
            with open(json_path, "r", encoding="utf-8") as json_file:
                json_content = json_file.read()

            await ctx.send(f"Contenu du fichier JSON généré :\n```json\n{json_content}\n```")
            logger.info(f"Template traité pour {ctx.author.name}: {attachment.filename}")
        except Exception as e:
            logger.error(f"Erreur traitement template: {e}")
            await ctx.send("Erreur lors du traitement de l'image.")

    @commands.command(name="validate_charte")
    async def validate_charte(self, ctx):
        """Gère le processus de validation manuelle de la charte."""
        username = str(ctx.author.name)

        # Récupérer le nombre total de clauses et les validations de l'utilisateur
        total_clauses = await self.db.get_total_clauses()
        user_validations = await self.db.get_user_validations(username)
        validated_clause_ids = [clause_idx for clause_idx, validation in user_validations if validation == 1]

        # Vérifier si l'utilisateur a déjà validé toutes les clauses
        if await self.db.is_fully_validated(username, total_clauses):
            await ctx.send("Vous avez déjà validé toutes les clauses de la charte. Vous êtes membre !")
            return

        await ctx.send(f"**Il vous reste {total_clauses - len(validated_clause_ids)} clause(s) à valider.**")

        # Afficher les clauses non validées une par une
        for clause in self.charte["charte"]:
            if clause["idx"] not in validated_clause_ids and clause["validation"] == 1:
                clause_path = DATA_DIR / clause["path"].replace("data/", "")
                with open(clause_path, "r", encoding="utf-8") as f:
                    content = f.read()

                await ctx.send(f"**Clause {clause['idx']} - {clause['name']}:**\n{content}")
                await ctx.send("Tapez **OK** pour accepter ou **KO** pour refuser.")

                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["ok", "ko"]

                try:
                    response = await self.bot.wait_for("message", check=check, timeout=120.0)
                except asyncio.TimeoutError:
                    await ctx.send("Temps écoulé (2 min). Utilisez `!validate_charte` pour reprendre.")
                    return

                if response.content.lower() == "ok":
                    await self.db.add_validation(username, clause["idx"], 1)
                    await ctx.send("Clause acceptée !")
                    logger.info(f"{username} a accepté la clause {clause['idx']}")
                else:
                    await self.db.add_validation(username, clause["idx"], 0)
                    await ctx.send("Clause refusée.")
                    logger.info(f"{username} a refusé la clause {clause['idx']}")

        # Vérification finale
        if await self.db.is_fully_validated(username, total_clauses):
            await ctx.send("Bravo ! Vous avez validé toutes les clauses. Bienvenue dans la team !")

async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(UserCommandsCog(bot))
