"""
Cog pour gerer l'inscription des nouveaux membres.

Flow:
1. Nouveau membre rejoint -> demarre automatiquement en DM
2. Validation de la charte (OBLIGATOIRE)
3. "As-tu des joueurs dans This Is PSG ?" -> saisie jusqu'a vide
4. "As-tu des joueurs dans This Is PSG 2 ?" -> saisie jusqu'a vide
5. Localisation (optionnel, pour la carte des membres)
6. En attente de validation par un Sage
"""

import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from typing import Optional, List
import asyncio

from models.user_profile import UserProfile
from models.player import Player, Team
from utils.database import Database
from utils.logger import get_logger
from utils.roles import is_newbie, is_membre, is_sage
from config import CHARTE_TEXTS, DATA_DIR, CHANNEL_ACCUEIL_ID

logger = get_logger("cogs.registration")


class RegistrationCog(commands.Cog):
    """Cog pour gerer l'inscription des nouveaux membres."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)
        self.active_registrations = {}  # username -> step

    async def start_registration(self, member: discord.Member):
        """Demarre le processus d'inscription pour un membre."""
        username = member.name
        logger.info(f"Demarrage inscription pour {username}")

        try:
            dm_channel = await member.create_dm()
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM a {username}")
            return

        # Verifier le profil
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)

        # Si deja valide, ne pas relancer
        if profile.charte_validated and profile.approval_status == "approved":
            await dm_channel.send("Tu es deja inscrit et valide !")
            return

        # Marquer comme en cours d'inscription
        self.active_registrations[username] = "charte"

        # Message de bienvenue
        await dm_channel.send(
            f"Bienvenue **{member.display_name}** !\n\n"
            f"Je vais te guider dans ton inscription pour rejoindre la team.\n"
            f"Reponds aux questions suivantes."
        )

        await asyncio.sleep(1)

        # Etape 1: Charte
        await self.send_charte(member, dm_channel)

    async def send_charte(self, member: discord.Member, dm_channel: discord.DMChannel):
        """Envoie la charte clause par clause."""
        username = member.name

        # Charger les textes de la charte
        charte_files = [
            ("0a_intro", False),  # (key, needs_validation)
            ("0b_intro", False),
            ("1_regles_generales", True),
            ("2_structure_roles", True),
            ("3_regles_fonctionnement", True),
            ("4_sanctions", True),
            ("5_engagement", True),
        ]

        for key, needs_validation in charte_files:
            if key not in CHARTE_TEXTS:
                continue

            file_path = CHARTE_TEXTS[key]
            if not file_path.exists():
                logger.warning(f"Fichier charte introuvable: {file_path}")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            # Decouper si trop long (limite Discord: 2000 chars)
            chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]

            for chunk in chunks:
                await dm_channel.send(chunk)
                await asyncio.sleep(0.5)

            if needs_validation:
                # Creer les boutons de validation
                view = CharteValidationView(self, member, key)
                msg = await dm_channel.send(
                    "**Acceptes-tu cette clause ?**",
                    view=view
                )
                view.message = msg

                # Attendre la reponse
                try:
                    await asyncio.wait_for(view.wait(), timeout=300)  # 5 min
                except asyncio.TimeoutError:
                    await dm_channel.send(
                        "Temps ecoule. L'inscription est annulee.\n"
                        "Tape `!inscription` pour recommencer."
                    )
                    self.active_registrations.pop(username, None)
                    return

                if not view.accepted:
                    await dm_channel.send(
                        "L'acceptation de la charte est **obligatoire** pour rejoindre la team.\n"
                        "Ton inscription est annulee.\n\n"
                        "Si tu changes d'avis, tape `!inscription` pour recommencer."
                    )
                    self.active_registrations.pop(username, None)
                    return

        # Toutes les clauses acceptees
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.validate_charte()

        await dm_channel.send(
            "Parfait ! Tu as accepte toute la charte.\n\n"
            "Passons a l'enregistrement de tes joueurs..."
        )
        await asyncio.sleep(1)

        # Etape 2: Joueurs Team 1
        self.active_registrations[username] = "team1"
        await self.ask_players_for_team(member, dm_channel, 1, "This Is PSG")

    async def ask_players_for_team(self, member: discord.Member, dm_channel: discord.DMChannel,
                                    team_id: int, team_name: str):
        """Demande les joueurs pour une equipe."""
        username = member.name

        view = YesNoView(member)
        await dm_channel.send(
            f"**As-tu des joueurs dans {team_name} ?**",
            view=view
        )

        try:
            await asyncio.wait_for(view.wait(), timeout=300)
        except asyncio.TimeoutError:
            await dm_channel.send("Temps ecoule. Tape `!inscription` pour recommencer.")
            self.active_registrations.pop(username, None)
            return

        if view.answer:
            # Saisie des joueurs
            await dm_channel.send(
                f"Saisis les noms de tes joueurs dans **{team_name}** (un par message).\n"
                f"Envoie un message **vide** ou tape **stop** quand tu as termine."
            )

            players_added = []
            while True:
                def check(m):
                    return m.author == member and isinstance(m.channel, discord.DMChannel)

                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=120)
                    player_name = msg.content.strip()

                    # Fin de saisie
                    if not player_name or player_name.lower() == "stop":
                        break

                    # Validation basique
                    if len(player_name) < 2:
                        await dm_channel.send("Nom trop court, reessaie.")
                        continue
                    if len(player_name) > 50:
                        await dm_channel.send("Nom trop long, reessaie.")
                        continue

                    # Enregistrer le joueur
                    try:
                        await Player.create(self.bot.db_pool, username, player_name, team_id)
                        players_added.append(player_name)
                        await dm_channel.send(f"Joueur **{player_name}** ajoute !")
                    except Exception as e:
                        logger.error(f"Erreur creation joueur: {e}")
                        await dm_channel.send(f"Erreur lors de l'ajout de {player_name}.")

                except asyncio.TimeoutError:
                    await dm_channel.send("Temps ecoule, on continue...")
                    break

            if players_added:
                await dm_channel.send(
                    f"Tu as ajoute {len(players_added)} joueur(s) dans {team_name}."
                )
            else:
                await dm_channel.send(f"Aucun joueur ajoute dans {team_name}.")

        await asyncio.sleep(1)

        # Passer a l'equipe suivante ou a la localisation
        if team_id == 1:
            self.active_registrations[username] = "team2"
            await self.ask_players_for_team(member, dm_channel, 2, "This Is PSG 2")
        else:
            self.active_registrations[username] = "localisation"
            await self.ask_location(member, dm_channel)

    async def ask_location(self, member: discord.Member, dm_channel: discord.DMChannel):
        """Demande la localisation (optionnel)."""
        view = YesNoView(member)
        await dm_channel.send(
            "**Souhaites-tu partager ta localisation ?**\n\n"
            "Cela permet d'afficher ta position sur la **carte des membres**.\n"
            "Tu peux etre aussi precis que tu veux :\n"
            "- General : pays, region (ex: *France*, *Ile-de-France*)\n"
            "- Precis : ville ou adresse (ex: *Paris*, *75001 Paris*)\n\n"
            "*Cette information est optionnelle et modifiable a tout moment.*",
            view=view
        )

        try:
            await asyncio.wait_for(view.wait(), timeout=300)
        except asyncio.TimeoutError:
            await self.finish_registration(member, dm_channel)
            return

        if view.answer:
            await dm_channel.send("Indique ta localisation :")

            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=120)
                location = msg.content.strip()

                if location:
                    await self.save_location(member, dm_channel, location)
                else:
                    await dm_channel.send("Localisation ignoree.")
                    await self.finish_registration(member, dm_channel)

            except asyncio.TimeoutError:
                await dm_channel.send("Temps ecoule.")
                await self.finish_registration(member, dm_channel)
        else:
            await self.finish_registration(member, dm_channel)

    async def save_location(self, member: discord.Member, dm_channel: discord.DMChannel, location: str):
        """Geocode et sauvegarde la localisation."""
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut

        username = member.name

        await dm_channel.send("Recherche de la localisation...")

        try:
            geolocator = Nominatim(user_agent="discord-bot-this-is-psg")
            loc = geolocator.geocode(location, timeout=10)

            if loc:
                async with self.bot.db_pool.acquire() as conn:
                    profile = await UserProfile.get_or_create_user(username, conn, member)
                    await profile.set_location(location, loc.latitude, loc.longitude)

                await dm_channel.send(f"Localisation enregistree : **{loc.address}**")
            else:
                await dm_channel.send(
                    "Localisation non trouvee. Tu pourras la modifier plus tard avec `!profil`."
                )

        except GeocoderTimedOut:
            await dm_channel.send("Service de localisation indisponible. Tu pourras reessayer plus tard.")
        except Exception as e:
            logger.error(f"Erreur geocoding: {e}")
            await dm_channel.send("Erreur lors de la localisation. Tu pourras reessayer plus tard.")

        await asyncio.sleep(1)
        await self.finish_registration(member, dm_channel)

    async def finish_registration(self, member: discord.Member, dm_channel: discord.DMChannel):
        """Termine l'inscription."""
        username = member.name
        self.active_registrations.pop(username, None)

        # Compter les joueurs enregistres
        players = await Player.get_by_member(self.bot.db_pool, username)

        summary = f"**Inscription terminee !**\n\n"

        if players:
            summary += "**Tes joueurs :**\n"
            for p in players:
                summary += f"- {p.player_name} ({p.team_name or 'Sans equipe'})\n"
            summary += "\n"

        summary += (
            "Ton inscription est maintenant **en attente de validation** par un Sage.\n"
            "Tu seras notifie des que ta candidature sera examinee.\n\n"
            "Utilise `!profil` pour voir tes informations."
        )

        await dm_channel.send(summary)

        # Notifier les sages (sera ameliore en Phase 6)
        logger.info(f"Inscription terminee pour {username}, en attente de validation")

    @commands.command(name="inscription")
    async def cmd_inscription(self, ctx):
        """Demarre ou reprend le processus d'inscription."""
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("Je t'envoie les instructions en message prive...")

        await self.start_registration(ctx.author)

    @commands.command(name="profil")
    async def cmd_profil(self, ctx, member: discord.Member = None):
        """Affiche le profil d'un membre."""
        target = member or ctx.author
        username = target.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, target)
            await profile.load_from_db()

        # Recuperer les joueurs
        players = await Player.get_by_member(self.bot.db_pool, username)

        embed = discord.Embed(
            title=f"Profil de {target.display_name}",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Statut",
            value=profile.get_status_display(),
            inline=False
        )

        if players:
            # Grouper par equipe
            team1_players = [p for p in players if p.team_name == "This Is PSG"]
            team2_players = [p for p in players if p.team_name == "This Is PSG 2"]
            other_players = [p for p in players if p.team_name not in ("This Is PSG", "This Is PSG 2")]

            if team1_players:
                names = ", ".join([p.player_name for p in team1_players])
                embed.add_field(name="This Is PSG", value=names, inline=False)

            if team2_players:
                names = ", ".join([p.player_name for p in team2_players])
                embed.add_field(name="This Is PSG 2", value=names, inline=False)

            if other_players:
                names = ", ".join([p.player_name for p in other_players])
                embed.add_field(name="Autres", value=names, inline=False)
        else:
            embed.add_field(name="Joueurs", value="Aucun joueur enregistre", inline=False)

        if profile.localisation:
            embed.add_field(name="Localisation", value=profile.localisation, inline=False)

        # Si c'est son propre profil, proposer l'edition
        if target == ctx.author:
            embed.set_footer(text="Utilise !joueur, !localisation pour modifier")

        await ctx.send(embed=embed)

    @commands.command(name="joueur")
    async def cmd_joueur(self, ctx, *, player_info: str = None):
        """Ajoute un joueur. Usage: !joueur NomJoueur [equipe]"""
        if not player_info:
            await ctx.send(
                "**Usage:** `!joueur NomJoueur [equipe]`\n"
                "**Exemples:**\n"
                "- `!joueur MonPseudo` (equipe par defaut: This Is PSG)\n"
                "- `!joueur MonPseudo 2` (pour This Is PSG 2)"
            )
            return

        # Parser l'argument
        parts = player_info.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in ("1", "2"):
            player_name = parts[0]
            team_id = int(parts[1])
        else:
            player_name = player_info
            team_id = 1  # Par defaut

        username = ctx.author.name

        try:
            await Player.create(self.bot.db_pool, username, player_name, team_id)
            team_name = "This Is PSG" if team_id == 1 else "This Is PSG 2"
            await ctx.send(f"Joueur **{player_name}** ajoute dans **{team_name}** !")
        except Exception as e:
            logger.error(f"Erreur ajout joueur: {e}")
            await ctx.send("Erreur lors de l'ajout du joueur.")

    @commands.command(name="localisation")
    async def cmd_localisation(self, ctx, *, location: str = None):
        """Definit ta localisation. Usage: !localisation MaVille"""
        if not location:
            await ctx.send(
                "**Usage:** `!localisation MaVille`\n"
                "**Exemples:**\n"
                "- `!localisation France`\n"
                "- `!localisation Paris`\n"
                "- `!localisation 75001 Paris`"
            )
            return

        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut

        username = ctx.author.name

        try:
            geolocator = Nominatim(user_agent="discord-bot-this-is-psg")
            loc = geolocator.geocode(location, timeout=10)

            if loc:
                async with self.bot.db_pool.acquire() as conn:
                    profile = await UserProfile.get_or_create_user(username, conn, ctx.author)
                    await profile.set_location(location, loc.latitude, loc.longitude)

                await ctx.send(f"Localisation enregistree : **{loc.address}**")
            else:
                await ctx.send("Localisation non trouvee. Essaie avec un autre format.")

        except GeocoderTimedOut:
            await ctx.send("Service de localisation indisponible. Reessaie plus tard.")
        except Exception as e:
            logger.error(f"Erreur geocoding: {e}")
            await ctx.send("Erreur lors de la localisation.")


class CharteValidationView(View):
    """Vue pour valider une clause de la charte."""

    def __init__(self, cog: RegistrationCog, member: discord.Member, clause_key: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.member = member
        self.clause_key = clause_key
        self.accepted = False
        self.message = None

    @discord.ui.button(label="J'accepte", style=ButtonStyle.green)
    async def accept(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            return
        self.accepted = True
        await interaction.response.edit_message(content="Clause acceptee !", view=None)
        self.stop()

    @discord.ui.button(label="Je refuse", style=ButtonStyle.red)
    async def refuse(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            return
        self.accepted = False
        await interaction.response.edit_message(content="Clause refusee.", view=None)
        self.stop()


class YesNoView(View):
    """Vue simple Oui/Non."""

    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)
        self.member = member
        self.answer = None

    @discord.ui.button(label="Oui", style=ButtonStyle.green)
    async def yes(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            return
        self.answer = True
        await interaction.response.edit_message(view=None)
        self.stop()

    @discord.ui.button(label="Non", style=ButtonStyle.secondary)
    async def no(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            return
        self.answer = False
        await interaction.response.edit_message(view=None)
        self.stop()


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(RegistrationCog(bot))
