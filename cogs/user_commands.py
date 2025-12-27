import discord
from discord.ext import commands
from utils.image_processing import process_image
from utils.logger import get_logger
from utils.database import Database
from utils.validators import validate_pseudo, validate_image_attachment
import json
import asyncio

from config import CHARTE_JSON_PATH, TEMP_DIR, WEB_URL, SITE_URL

logger = get_logger("cogs.user_commands")

class UserCommandsCog(commands.Cog):
    """Commandes accessibles à tous les utilisateurs."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)

        # Charger la structure de la charte (pour les chemins des fichiers)
        with open(CHARTE_JSON_PATH, "r", encoding="utf-8") as f:
            self.charte = json.load(f)


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

    @commands.command(name="users", aliases=["utilisateurs", "membres"])
    async def list_users(self, ctx):
        """Affiche la liste des utilisateurs enregistrés."""
        async with self.bot.db_pool.acquire() as connection:
            users = await connection.fetch("""
                SELECT last_connection, username, discord_name, approval_status
                FROM user_profile
                ORDER BY last_connection DESC
            """)

        if not users:
            embed = discord.Embed(
                title="📜 Liste des membres",
                description="Aucun membre trouvé.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Indicateurs de statut
        status_icons = {"approved": "✓", "pending": "⏳", "refused": "✗"}

        # Calculer la largeur max des noms
        max_name_len = max(len(u['discord_name'] or u['username']) for u in users)

        user_list = "```"
        for user in users:
            last_conn = user['last_connection']
            if last_conn:
                date_str = last_conn.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = "----/--/-- --:--"
            display = user['discord_name'] or user['username']
            status = status_icons.get(user['approval_status'], "?")
            user_list += f"{date_str} {display:<{max_name_len}} {status}\n"
        user_list += "```"

        # Si le message dépasse 4000 caractères, on envoie en plusieurs messages
        if len(user_list) > 4000:
            # Découper en morceaux
            chunks = []
            current = "```"
            for user in users:
                last_conn = user['last_connection']
                date_str = last_conn.strftime('%Y-%m-%d %H:%M') if last_conn else "----/--/-- --:--"
                display = user['discord_name'] or user['username']
                status = status_icons.get(user['approval_status'], "?")
                line = f"{date_str} {display:<{max_name_len}} {status}\n"

                if len(current) + len(line) + 3 > 4000:  # +3 pour ```
                    current += "```"
                    chunks.append(current)
                    current = "```" + line
                else:
                    current += line
            current += "```"
            chunks.append(current)

            await ctx.send(f"📜 **Membres ({len(users)})**")
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            embed = discord.Embed(
                title=f"📜 Membres ({len(users)})",
                description=user_list,
                color=discord.Color.blue()
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

    @commands.command(name="pseudo", aliases=["nickname", "nick"])
    async def update_pseudo(self, ctx, *, new_pseudo: str):
        """Permet à un utilisateur de modifier son pseudo Discord."""
        # Validation du pseudo
        is_valid, error = validate_pseudo(new_pseudo)
        if not is_valid:
            await ctx.send(f"Erreur: {error}")
            return

        try:
            # Mettre à jour le pseudo Discord sur le serveur
            if ctx.guild:
                member = ctx.guild.get_member(ctx.author.id)
                if member:
                    try:
                        await member.edit(nick=new_pseudo)
                    except discord.Forbidden:
                        await ctx.send("Je n'ai pas la permission de changer ton pseudo sur ce serveur.")
                        return

            # Mettre à jour en base de données
            async with self.bot.db_pool.acquire() as connection:
                query = """
                UPDATE user_profile
                SET discord_name = $1
                WHERE username = $2
                """
                await connection.execute(query, new_pseudo, ctx.author.name)

            await ctx.send(f"Pseudo mis à jour : `{new_pseudo}`")
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

    @commands.command(name="carte", aliases=["map", "members-map"])
    async def show_map(self, ctx):
        """Affiche le lien vers la carte interactive des membres."""
        if WEB_URL:
            embed = discord.Embed(
                title="🗺️ Carte des membres",
                description="Carte interactive des membres de la team",
                url=WEB_URL,
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Ouvrir la carte",
                value=f"[Cliquez ici pour voir la carte interactive]({WEB_URL})",
                inline=False
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("La carte n'est pas configuree. Contactez un administrateur.")

    @commands.command(name="site", aliases=["website", "web"])
    async def show_site(self, ctx):
        """Affiche le lien vers le site de la team."""
        if SITE_URL:
            embed = discord.Embed(
                title="🌐 Site This Is PSG",
                description="Page officielle de la team",
                url=SITE_URL,
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Ouvrir le site",
                value=f"[Cliquez ici pour acceder au site]({SITE_URL})",
                inline=False
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("Le site n'est pas configure. Contactez un administrateur.")


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(UserCommandsCog(bot))
