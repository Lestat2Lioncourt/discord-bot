import discord
from discord.ext import commands
from utils.image_processing import process_image
import json
import os
import asyncio
from datetime import datetime

class UserCommandsCog(commands.Cog):
    """Commandes accessibles à tous les utilisateurs."""

    def __init__(self, bot):
        self.bot = bot
        self.charte_path = "data/charte.json"
        self.validation_path = "data/validation_charte.json"

        # Charger la charte
        with open(self.charte_path, "r", encoding="utf-8") as f:
            self.charte = json.load(f)

        # Charger les validations
        if os.path.exists(self.validation_path):
            with open(self.validation_path, "r", encoding="utf-8") as f:
                self.validations = json.load(f)
        else:
            self.validations = {}

    def save_validations(self):
        with open(self.validation_path, "w", encoding="utf-8") as f:
            json.dump(self.validations, f, indent=4, ensure_ascii=False)

    def get_user_validations(self, username):
        return self.validations.get(username, [])

    def add_validation(self, username, clause_idx):
        if username not in self.validations:
            self.validations[username] = []
        if clause_idx not in self.validations[username]:
            self.validations[username].append(clause_idx)
        self.save_validations()

    def remove_validation(self, username, clause_idx):
        if username in self.validations and clause_idx in self.validations[username]:
            self.validations[username].remove(clause_idx)
            if not self.validations[username]:
                del self.validations[username]
            self.save_validations()

    def is_fully_validated(self, username):
        user_validations = self.get_user_validations(username)
        return all(clause_idx in user_validations for clause_idx in range(len(self.charte["charte"])))

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
        """Affiche le profil de l'utilisateur qui exécute la commande."""
        async with self.bot.db_pool.acquire() as connection:
            query = """
            SELECT username, discord_name, game_name, language, localisation, latitude, longitude, creation_date, last_connection
            FROM user_profile
            WHERE username = $1
            """
            user = await connection.fetchrow(query, ctx.author.name)

        if user is None:  # Vérifie si `fetchrow()` a retourné `None`
            await ctx.send("❌ Aucun profil trouvé pour vous dans la base de données.")
            return  # On arrête ici pour éviter un affichage inutile

        # Construction du message avec des valeurs par défaut si `NULL`
        message = ("\n"
            f"`Username....... : {user['username'] or 'Non renseigné'}`\n"
            f"`Discord Name... : {user['discord_name'] or 'Non renseigné'}`\n"
            f"`Game Name...... : {user['game_name'] or 'Non renseigné'}`\n"
            f"`Language....... : {user['language'] or 'Non renseigné'}`\n"
            f"`Localisation... : {user['localisation'] or 'Non renseigné'}`\n"
            f"`Latitude....... : {user['latitude'] or 'Non renseigné'}`\n"
            f"`Longitude...... : {user['longitude'] or 'Non renseigné'}`\n"
            f"`Creation Date.. : {user['creation_date'] or 'Non renseigné'}`\n"
            f"`Last Connection : {user['last_connection'] or 'Non renseigné'}`\n"
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
            print(user_list)
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
        async with self.bot.db_pool.acquire() as connection:
            query = """
            UPDATE user_profile
            SET discord_name = $1
            WHERE username = $2
            """
            await connection.execute(query, new_pseudo, ctx.author.name)

        await ctx.send(f"✅ Votre pseudo a été mis à jour avec succès en `{new_pseudo}`.")

    @commands.command(name="template")
    async def process_template(self, ctx):
        """Traite l'image jointe à la commande et génère un fichier JSON."""
        if len(ctx.message.attachments) == 0:
            await ctx.send("❌ Aucune image jointe à la commande.")
            return

        # Télécharger l'image jointe
        attachment = ctx.message.attachments[0]
        image_path = f"temp_{attachment.filename}"
        await attachment.save(image_path)

        # Traiter l'image avec le script de traitement
        json_path = process_image(image_path)

        # Lire le contenu du fichier JSON
        with open(json_path, "r", encoding="utf-8") as json_file:
            json_content = json_file.read()

        # Envoyer un message de confirmation avec le contenu du fichier JSON
        await ctx.send(f"✅ Contenu du fichier JSON généré :\n```json\n{json_content}\n```")

    @commands.command(name="validate_charte")
    async def validate_charte(self, ctx):
        """Gère le processus de validation de la charte."""
        username = str(ctx.author)

        # Vérifier si l'utilisateur a déjà validé toutes les clauses
        if self.is_fully_validated(username):
            await ctx.send("Vous avez déjà validé toutes les clauses de la charte. Vous êtes désormais membre !")
            return

        # Afficher les clauses non validées
        user_validations = self.get_user_validations(username)
        for clause in self.charte["charte"]:
            if clause["idx"] not in user_validations:
                with open(clause["path"], "r", encoding="utf-8") as f:
                    content = f.read()
                await ctx.send(f"**Clause {clause['idx']}:**\n{content}")
                await ctx.send("**Accepte cette clause en entrant 'OK'** ou autre chose pour refuser.")

                # Attendre la réponse de l'utilisateur
                def check(m):
                    return m.author == ctx.author and m.content.lower() in ["ok", "ko"]

                try:
                    response = await self.bot.wait_for("message", check=check, timeout=60.0)
                except asyncio.TimeoutError:
                    await ctx.send("Temps écoulé. Veuillez réessayer.")
                    return

                if response.content.lower() == "ok":
                    self.add_validation(username, clause["idx"])
                    await ctx.send("Clause validée avec succès !")
                else:
                    self.remove_validation(username, clause["idx"])
                    await ctx.send("Clause dévalidée.")

        # Vérifier si l'utilisateur a validé toutes les clauses
        if self.is_fully_validated(username):
            await ctx.send("Félicitations ! Vous avez validé toutes les clauses de la charte. Vous êtes désormais membre !")

# La fonction setup doit utiliser le nom exact de la classe
async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(UserCommandsCog(bot))
    print("✅ Cog UserCommandsCog correctement ajouté au bot")
