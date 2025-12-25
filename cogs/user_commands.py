import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from utils.image_processing import process_image
from utils.logger import get_logger
from utils.database import Database
from utils.validators import validate_pseudo, validate_image_attachment
import json
import asyncio
from datetime import datetime

from config import CHARTE_JSON_PATH, DATA_DIR, TEMP_DIR, WEB_URL
from models.player import Player

logger = get_logger("cogs.user_commands")

# Chemin du template de carte
MAP_TEMPLATE_PATH = DATA_DIR / "map_template.html"

USERS_PER_PAGE = 20


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
        """Affiche la liste des utilisateurs enregistrés avec pagination."""
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

        # Convertir en liste de dicts
        users_list = [dict(u) for u in users]
        total = len(users_list)
        total_pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE

        # Créer l'embed pour la première page
        embed = self._create_users_embed(users_list, 0, total, total_pages)

        if total_pages <= 1:
            await ctx.send(embed=embed)
        else:
            view = UsersPaginationView(users_list, total, total_pages, ctx.author)
            view.message = await ctx.send(embed=embed, view=view)

    def _create_users_embed(self, users: list, page: int, total: int, total_pages: int) -> discord.Embed:
        """Crée l'embed pour une page de la liste des utilisateurs."""
        start = page * USERS_PER_PAGE
        end = min(start + USERS_PER_PAGE, total)
        page_users = users[start:end]

        # Indicateurs de statut
        status_icons = {"approved": "✓", "pending": "⏳", "refused": "✗"}

        # Calculer la largeur max des noms pour cette page
        max_name_len = max(len(u['discord_name'] or u['username']) for u in page_users)

        user_list = "```"
        for user in page_users:
            last_conn = user['last_connection']
            if last_conn:
                date_str = last_conn.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = "----/--/-- --:--"
            display = user['discord_name'] or user['username']
            status = status_icons.get(user['approval_status'], "?")
            user_list += f"{date_str} {display:<{max_name_len}} {status}\n"
        user_list += "```"

        embed = discord.Embed(
            title=f"📜 Membres ({total})",
            description=user_list,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page {page + 1}/{total_pages}")
        return embed

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
    async def generate_map(self, ctx):
        """Genere une carte interactive des membres avec leur localisation."""
        await ctx.send("Generation de la carte en cours...")

        try:
            # Recuperer les membres avec localisation
            async with self.bot.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT username, discord_name, localisation, latitude, longitude
                    FROM user_profile
                    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                    AND approval_status = 'approved'
                """)

            if not rows:
                await ctx.send("Aucun membre n'a renseigne sa localisation.")
                return

            # Construire les donnees des membres
            members_data = []
            for row in rows:
                username = row['username']
                display_name = row['discord_name'] or username

                # Recuperer les joueurs de ce membre, separes par equipe
                players = await Player.get_by_member(self.bot.db_pool, username)
                team1 = [p.player_name for p in players if p.team_name == "This Is PSG"] if players else []
                team2 = [p.player_name for p in players if p.team_name == "This Is PSG 2"] if players else []

                members_data.append({
                    "name": display_name,
                    "lat": float(row['latitude']),
                    "lng": float(row['longitude']),
                    "team1": team1,
                    "team2": team2
                })

            # Lire le template
            with open(MAP_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                template = f.read()

            # Remplacer les placeholders
            html_content = template.replace("{{MEMBERS_JSON}}", json.dumps(members_data, ensure_ascii=False))
            html_content = html_content.replace("{{MEMBER_COUNT}}", str(len(members_data)))
            html_content = html_content.replace("{{DATE}}", datetime.now().strftime("%d/%m/%Y %H:%M"))

            # Sauvegarder le fichier temporaire
            map_file = TEMP_DIR / "carte_membres.html"
            with open(map_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Envoyer le lien ou le fichier selon la config
            if WEB_URL:
                # Serveur web configure -> envoyer le lien
                carte_url = f"{WEB_URL.rstrip('/')}/carte"
                embed = discord.Embed(
                    title="🗺️ Carte des membres",
                    description=f"**{len(members_data)}** membres localisés",
                    url=carte_url,
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Ouvrir la carte",
                    value=f"[Cliquez ici pour voir la carte interactive]({carte_url})",
                    inline=False
                )
                embed.set_footer(text=f"Mise à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                await ctx.send(embed=embed)
            else:
                # Pas de serveur web -> envoyer le fichier
                await ctx.send(
                    f"Carte generee avec **{len(members_data)}** membres localises.\n"
                    "Ouvre le fichier dans ton navigateur pour voir la carte interactive.",
                    file=discord.File(str(map_file), filename="carte_membres.html")
                )

            logger.info(f"Carte generee par {ctx.author.name}: {len(members_data)} membres")

        except Exception as e:
            logger.error(f"Erreur generation carte: {e}")
            await ctx.send("Erreur lors de la generation de la carte.")


class UsersPaginationView(View):
    """Vue pour la pagination de la liste des utilisateurs."""

    def __init__(self, users: list, total: int, total_pages: int, author):
        super().__init__(timeout=120)
        self.users = users
        self.total = total
        self.total_pages = total_pages
        self.author = author
        self.current_page = 0
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        """Met à jour l'état des boutons selon la page actuelle."""
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= self.total_pages - 1

    def _create_embed(self) -> discord.Embed:
        """Crée l'embed pour la page actuelle."""
        start = self.current_page * USERS_PER_PAGE
        end = min(start + USERS_PER_PAGE, self.total)
        page_users = self.users[start:end]

        # Indicateurs de statut
        status_icons = {"approved": "✓", "pending": "⏳", "refused": "✗"}

        # Calculer la largeur max des noms pour cette page
        max_name_len = max(len(u['discord_name'] or u['username']) for u in page_users)

        user_list = "```"
        for user in page_users:
            last_conn = user['last_connection']
            if last_conn:
                date_str = last_conn.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = "----/--/-- --:--"
            display = user['discord_name'] or user['username']
            status = status_icons.get(user['approval_status'], "?")
            user_list += f"{date_str} {display:<{max_name_len}} {status}\n"
        user_list += "```"

        embed = discord.Embed(
            title=f"📜 Membres ({self.total})",
            description=user_list,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
        return embed

    @discord.ui.button(label="◀ Précédent", style=ButtonStyle.secondary, custom_id="prev")
    async def prev_btn(self, interaction: Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.defer()
            return
        self.current_page = max(0, self.current_page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._create_embed(), view=self)

    @discord.ui.button(label="Suivant ▶", style=ButtonStyle.primary, custom_id="next")
    async def next_btn(self, interaction: Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.defer()
            return
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._create_embed(), view=self)

    async def on_timeout(self):
        """Désactive les boutons après timeout."""
        if self.message:
            try:
                self.prev_btn.disabled = True
                self.next_btn.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(UserCommandsCog(bot))
