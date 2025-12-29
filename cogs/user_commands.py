"""
Cog pour les commandes accessibles a tous les utilisateurs.

Toutes les reponses sont envoyees en DM pour eviter de polluer les salons.

Commandes:
- !users: Liste des membres enregistres
- !db_status: Verifie la connexion BDD
- !pseudo: Modifie le pseudo Discord
- !template: Traite une image OCR
- !carte: Lien vers la carte des membres
- !site: Lien vers le site de la team
- !stats: Statistiques de la communaute
"""

import asyncpg
import discord
from discord.ext import commands
from utils.image_processing import process_image
from utils.logger import get_logger
from utils.database import Database
from utils.validators import validate_pseudo, validate_image_attachment
from utils.discord_helpers import reply_dm

from config import TEMP_DIR, WEB_URL, SITE_URL

logger = get_logger("cogs.user_commands")


class UserCommandsCog(commands.Cog):
    """Commandes accessibles à tous les utilisateurs."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)


    @commands.command(name="users", aliases=["utilisateurs", "membres"])
    async def list_users(self, ctx):
        """Affiche la liste des utilisateurs enregistrés (en DM)."""
        async with self.bot.db_pool.acquire() as connection:
            users = await connection.fetch("""
                SELECT last_connection, username, discord_name, approval_status
                FROM user_profile
                WHERE approval_status != 'deleted'
                ORDER BY last_connection DESC
            """)

        if not users:
            embed = discord.Embed(
                title="📜 Liste des membres",
                description="Aucun membre trouvé.",
                color=discord.Color.red()
            )
            await reply_dm(ctx, embed=embed)
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

            # Envoyer en DM (notifier une seule fois)
            try:
                await ctx.author.send(f"📜 **Membres ({len(users)})**")
                for chunk in chunks:
                    await ctx.author.send(chunk)
                if ctx.guild:
                    await ctx.send("📬 Reponse envoyee en DM.")
            except discord.Forbidden:
                await ctx.send(f"📜 **Membres ({len(users)})**")
                for chunk in chunks:
                    await ctx.send(chunk)
        else:
            embed = discord.Embed(
                title=f"📜 Membres ({len(users)})",
                description=user_list,
                color=discord.Color.blue()
            )
            await reply_dm(ctx, embed=embed)

    @commands.command(name="db_status")
    async def db_status(self, ctx):
        """Vérifie si la connexion à la base de données est active (en DM)."""
        try:
            async with self.bot.db_pool.acquire() as connection:
                await connection.fetchval("SELECT 1")  # Exécute une requête test
            embed = discord.Embed(
                title="🟢 Connexion réussie",
                description="La connexion à la base de données est active.",
                color=discord.Color.green()
            )
        except asyncpg.PostgresError as e:
            embed = discord.Embed(
                title="🔴 Erreur de connexion",
                description=f"Impossible de se connecter à la base de données.\nErreur : {e}",
                color=discord.Color.red()
            )
        await reply_dm(ctx, embed=embed)

    @commands.command(name="pseudo", aliases=["nickname", "nick"])
    async def update_pseudo(self, ctx, *, new_pseudo: str):
        """Permet à un utilisateur de modifier son pseudo Discord (en DM)."""
        # Validation du pseudo
        is_valid, error = validate_pseudo(new_pseudo)
        if not is_valid:
            await reply_dm(ctx, f"Erreur: {error}")
            return

        try:
            # Mettre à jour le pseudo Discord sur le serveur
            if ctx.guild:
                member = ctx.guild.get_member(ctx.author.id)
                if member:
                    try:
                        await member.edit(nick=new_pseudo)
                    except discord.Forbidden:
                        await reply_dm(ctx, "Je n'ai pas la permission de changer ton pseudo sur ce serveur.")
                        return

            # Mettre à jour en base de données
            async with self.bot.db_pool.acquire() as connection:
                query = """
                UPDATE user_profile
                SET discord_name = $1
                WHERE username = $2
                """
                await connection.execute(query, new_pseudo, ctx.author.name)

            await reply_dm(ctx, f"Pseudo mis à jour : `{new_pseudo}`")
            logger.info(f"{ctx.author.name} a changé son pseudo en '{new_pseudo}'")
        except asyncpg.PostgresError as e:
            logger.error(f"Erreur mise à jour pseudo: {e}")
            await reply_dm(ctx, "Erreur lors de la mise à jour du pseudo.")

    @commands.command(name="template")
    async def process_template(self, ctx):
        """Traite l'image jointe à la commande et génère un fichier JSON (en DM)."""
        if len(ctx.message.attachments) == 0:
            await reply_dm(ctx, "Aucune image jointe à la commande.")
            return

        attachment = ctx.message.attachments[0]

        # Validation de l'image
        is_valid, error = validate_image_attachment(attachment.filename, attachment.size)
        if not is_valid:
            await reply_dm(ctx, f"Erreur: {error}")
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

            await reply_dm(ctx, f"Contenu du fichier JSON généré :\n```json\n{json_content}\n```")
            logger.info(f"Template traité pour {ctx.author.name}: {attachment.filename}")
        except OSError as e:
            logger.error(f"Erreur traitement template (fichier): {e}")
            await reply_dm(ctx, "Erreur lors du traitement de l'image.")

    @commands.command(name="carte", aliases=["map", "members-map"])
    async def show_map(self, ctx):
        """Affiche le lien vers la carte interactive des membres (en DM)."""
        if WEB_URL:
            await reply_dm(ctx, f"🗺️ **Carte des membres** : {WEB_URL}")
        else:
            await reply_dm(ctx, "La carte n'est pas configuree. Contactez un administrateur.")

    @commands.command(name="site", aliases=["website", "web"])
    async def show_site(self, ctx):
        """Affiche le lien vers le site de la team (en DM)."""
        if SITE_URL:
            await reply_dm(ctx, f"🌐 **Site This Is PSG** : {SITE_URL}")
        else:
            await reply_dm(ctx, "Le site n'est pas configure. Contactez un administrateur.")

    @commands.command(name="stats", aliases=["statistiques", "dashboard"])
    async def show_stats(self, ctx):
        """Affiche les statistiques de la communaute (en DM)."""
        async with self.bot.db_pool.acquire() as conn:
            # Stats membres par statut
            members_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE approval_status != 'deleted') as total,
                    COUNT(*) FILTER (WHERE approval_status = 'approved') as approved,
                    COUNT(*) FILTER (WHERE approval_status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE approval_status = 'refused') as refused
                FROM user_profile
            """)

            # Stats joueurs par equipe
            players_stats = await conn.fetch("""
                SELECT t.name as team_name, COUNT(p.id) as count
                FROM teams t
                LEFT JOIN players p ON t.id = p.team_id
                GROUP BY t.id, t.name
                ORDER BY t.id
            """)

            # Stats carte (membres avec localisation)
            map_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE latitude IS NOT NULL) as on_map,
                    COUNT(*) FILTER (WHERE approval_status != 'deleted') as total
                FROM user_profile
            """)

            # Top localisations (depuis location_display)
            locations = await conn.fetch("""
                SELECT location_display, COUNT(*) as count
                FROM user_profile
                WHERE location_display IS NOT NULL
                  AND location_display != ''
                  AND approval_status != 'deleted'
                GROUP BY location_display
                ORDER BY count DESC
                LIMIT 5
            """)

            # Derniere inscription
            last_reg = await conn.fetchval("""
                SELECT MAX(creation_date) FROM user_profile
                WHERE approval_status != 'deleted'
            """)

        # Construire l'embed
        embed = discord.Embed(
            title="📊 Statistiques This Is PSG",
            color=discord.Color.blue()
        )

        # Membres
        total = members_stats['total'] or 0
        approved = members_stats['approved'] or 0
        pending = members_stats['pending'] or 0
        embed.add_field(
            name="👥 Membres",
            value=f"Total : **{total}**\nValides : {approved}\nEn attente : {pending}",
            inline=True
        )

        # Joueurs par equipe
        players_text = ""
        for team in players_stats:
            players_text += f"{team['team_name']} : {team['count']}\n"
        if not players_text:
            players_text = "Aucun joueur"
        embed.add_field(
            name="🎾 Joueurs",
            value=players_text.strip(),
            inline=True
        )

        # Carte
        on_map = map_stats['on_map'] or 0
        map_total = map_stats['total'] or 1
        pct = int(on_map / map_total * 100) if map_total > 0 else 0
        embed.add_field(
            name="🗺️ Carte",
            value=f"Sur la carte : **{on_map}** ({pct}%)",
            inline=True
        )

        # Localisations
        if locations:
            loc_text = "\n".join([f"{loc['location_display']} ({loc['count']})" for loc in locations])
            embed.add_field(
                name="📍 Localisations",
                value=loc_text,
                inline=False
            )

        # Footer avec derniere inscription
        if last_reg:
            from datetime import datetime
            delta = datetime.now() - last_reg.replace(tzinfo=None)
            if delta.days > 0:
                embed.set_footer(text=f"Derniere inscription : il y a {delta.days}j")
            else:
                hours = delta.seconds // 3600
                embed.set_footer(text=f"Derniere inscription : il y a {hours}h")

        await reply_dm(ctx, embed=embed)


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(UserCommandsCog(bot))
