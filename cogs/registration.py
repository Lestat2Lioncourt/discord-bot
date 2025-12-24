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
        """Envoie la charte par blocs avec bouton Suivant, validation a la fin."""
        username = member.name

        # Charger et concatener tous les textes
        charte_files = ["0_intro", "1_regles_generales", "2_structure_roles", "3_regles_fonctionnement"]
        full_text = ""

        for key in charte_files:
            if key not in CHARTE_TEXTS:
                continue
            file_path = CHARTE_TEXTS[key]
            if not file_path.exists():
                logger.warning(f"Fichier charte introuvable: {file_path}")
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                full_text += f.read() + "\n\n"

        # Decouper en blocs lisibles (~1500 chars pour eviter scroll)
        chunks = []
        current_chunk = ""
        for line in full_text.split("\n"):
            if len(current_chunk) + len(line) + 1 > 1500:
                chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Afficher chaque bloc avec bouton Suivant
        for i, chunk in enumerate(chunks):
            await dm_channel.send(chunk)

            # Bouton Suivant sauf pour le dernier bloc
            if i < len(chunks) - 1:
                view = NextButtonView(member)
                await dm_channel.send("─" * 30, view=view)

                try:
                    await asyncio.wait_for(view.wait(), timeout=300)
                except asyncio.TimeoutError:
                    await dm_channel.send("Temps ecoule. Tape `!inscription` pour recommencer.")
                    self.active_registrations.pop(username, None)
                    return

        # Validation finale
        await asyncio.sleep(0.5)
        view = CharteValidationView(self, member, "final")
        await dm_channel.send(
            "─" * 30 + "\n"
            "**Acceptes-tu cette charte dans son integralite ?**\n"
            "*En acceptant, tu t'engages a respecter ces regles.*",
            view=view
        )

        try:
            await asyncio.wait_for(view.wait(), timeout=300)
        except asyncio.TimeoutError:
            await dm_channel.send("Temps ecoule. Tape `!inscription` pour recommencer.")
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

        # Charte validee
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.validate_charte()

        await dm_channel.send("Charte acceptee !")
        await asyncio.sleep(1)

        # Etape 2: Joueurs Team 1
        self.active_registrations[username] = "team1"
        await self.ask_players_for_team(member, dm_channel, 1, "This Is PSG")

    async def ask_players_for_team(self, member: discord.Member, dm_channel: discord.DMChannel,
                                    team_id: int, team_name: str, is_main_team: bool = True):
        """Demande les joueurs pour une equipe."""
        username = member.name

        # Message bien visible
        await dm_channel.send("═" * 35)

        if is_main_team:
            await dm_channel.send(
                f"🎾 **ENREGISTREMENT DE TES JOUEURS** 🎾\n\n"
                f"📋 **Equipe : {team_name}** (equipe principale)\n\n"
                f"Saisis le **nom de ton joueur** tel qu'il apparait dans le jeu.\n"
                f"Tape `.` si tu n'as pas de joueur dans cette equipe."
            )
        else:
            await dm_channel.send(
                f"📋 **Equipe : {team_name}**\n\n"
                f"Saisis le **nom de ton joueur** dans cette equipe.\n"
                f"Tape `.` si tu n'as pas de joueur ici."
            )

        players_added = []
        while True:
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=120)
                player_name = msg.content.strip()

                # Fin de saisie
                if player_name == "." or player_name.lower() == "stop" or not player_name:
                    break

                # Validation basique
                if len(player_name) < 2:
                    await dm_channel.send("Nom trop court, reessaie :")
                    continue
                if len(player_name) > 50:
                    await dm_channel.send("Nom trop long, reessaie :")
                    continue

                # Enregistrer le joueur
                try:
                    await Player.create(self.bot.db_pool, username, player_name, team_id)
                    players_added.append(player_name)
                    await dm_channel.send(f"Joueur **{player_name}** ajoute ! (`.` pour terminer, ou autre nom) :")
                except Exception as e:
                    error_msg = str(e)
                    if "unique_player_per_team" in error_msg or "duplicate key" in error_msg.lower():
                        await dm_channel.send(f"Le joueur **{player_name}** existe deja dans cette equipe. Autre nom ou `.` :")
                    else:
                        logger.error(f"Erreur creation joueur: {e}")
                        await dm_channel.send(f"Erreur lors de l'ajout. Reessaie :")

            except asyncio.TimeoutError:
                await dm_channel.send("Temps ecoule, on continue...")
                break

        if players_added:
            await dm_channel.send(f"{len(players_added)} joueur(s) ajoute(s) dans {team_name}.")

        await asyncio.sleep(0.5)

        # Passer a l'equipe suivante ou a la localisation
        if team_id == 1:
            self.active_registrations[username] = "team2"
            await self.ask_players_for_team(member, dm_channel, 2, "This Is PSG 2", is_main_team=False)
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

    @commands.command(name="joueur", aliases=["player", "joueurs", "players"])
    async def cmd_joueur(self, ctx):
        """Affiche les joueurs et permet d'en ajouter."""
        username = ctx.author.name
        member = ctx.author

        # Afficher les joueurs existants
        players = await Player.get_by_member(self.bot.db_pool, username)

        if players:
            team1 = [p.player_name for p in players if p.team_name == "This Is PSG"]
            team2 = [p.player_name for p in players if p.team_name == "This Is PSG 2"]

            msg = "**Tes joueurs actuels :**\n"
            if team1:
                msg += f"This Is PSG : {', '.join(team1)}\n"
            if team2:
                msg += f"This Is PSG 2 : {', '.join(team2)}\n"
            await ctx.send(msg)
        else:
            await ctx.send("Tu n'as aucun joueur enregistre.")

        await ctx.send("Je t'envoie le formulaire d'ajout en message prive...")

        # Demarrer la saisie en DM
        try:
            dm_channel = await member.create_dm()
            await self.start_player_registration(member, dm_channel)
        except discord.Forbidden:
            await ctx.send("Je ne peux pas t'envoyer de message prive. Verifie tes parametres.")

    async def start_player_registration(self, member: discord.Member, dm_channel: discord.DMChannel):
        """Demarre uniquement la saisie des joueurs (sans charte)."""
        username = member.name

        await dm_channel.send("═" * 35)
        await dm_channel.send("🎾 **GESTION DE TES JOUEURS** 🎾")
        await asyncio.sleep(0.5)

        # Team 1
        await self.ask_players_for_team_only(member, dm_channel, 1, "This Is PSG", is_main_team=True)

        # Team 2
        await self.ask_players_for_team_only(member, dm_channel, 2, "This Is PSG 2", is_main_team=False)

        # Resume
        players = await Player.get_by_member(self.bot.db_pool, username)
        if players:
            msg = "**Tes joueurs :**\n"
            for p in players:
                msg += f"- {p.player_name} ({p.team_name})\n"
            await dm_channel.send(msg)
        else:
            await dm_channel.send("Aucun joueur enregistre.")

    async def ask_players_for_team_only(self, member: discord.Member, dm_channel: discord.DMChannel,
                                         team_id: int, team_name: str, is_main_team: bool = True):
        """Saisie des joueurs pour une equipe (version standalone)."""
        username = member.name

        if is_main_team:
            await dm_channel.send(
                f"📋 **{team_name}** (equipe principale)\n"
                f"Nom du joueur ou `.` si aucun :"
            )
        else:
            await dm_channel.send(
                f"📋 **{team_name}**\n"
                f"Nom du joueur ou `.` si aucun :"
            )

        while True:
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=120)
                player_name = msg.content.strip()

                if player_name == "." or player_name.lower() == "stop" or not player_name:
                    break

                if len(player_name) < 2:
                    await dm_channel.send("Nom trop court, reessaie :")
                    continue
                if len(player_name) > 50:
                    await dm_channel.send("Nom trop long, reessaie :")
                    continue

                try:
                    await Player.create(self.bot.db_pool, username, player_name, team_id)
                    await dm_channel.send(f"Joueur **{player_name}** ajoute ! (`.` pour terminer, ou autre nom) :")
                except Exception as e:
                    error_msg = str(e)
                    if "unique_player_per_team" in error_msg or "duplicate key" in error_msg.lower():
                        await dm_channel.send(f"Le joueur **{player_name}** existe deja. Autre nom ou `.` :")
                    else:
                        logger.error(f"Erreur creation joueur: {e}")
                        await dm_channel.send(f"Erreur. Reessaie :")

            except asyncio.TimeoutError:
                await dm_channel.send("Temps ecoule.")
                break

        await asyncio.sleep(0.3)

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
            await interaction.response.defer()
            return
        self.accepted = True
        try:
            await interaction.response.edit_message(content="Charte acceptee !", view=None)
        except discord.errors.InteractionResponded:
            pass
        self.stop()

    @discord.ui.button(label="Je refuse", style=ButtonStyle.red)
    async def refuse(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            await interaction.response.defer()
            return
        self.accepted = False
        try:
            await interaction.response.edit_message(content="Charte refusee.", view=None)
        except discord.errors.InteractionResponded:
            pass
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
            await interaction.response.defer()
            return
        self.answer = True
        try:
            await interaction.response.edit_message(view=None)
        except discord.errors.InteractionResponded:
            pass
        self.stop()

    @discord.ui.button(label="Non", style=ButtonStyle.secondary)
    async def no(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            await interaction.response.defer()
            return
        self.answer = False
        try:
            await interaction.response.edit_message(view=None)
        except discord.errors.InteractionResponded:
            pass
        self.stop()


class NextButtonView(View):
    """Vue avec bouton Suivant."""

    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)
        self.member = member

    @discord.ui.button(label="Suivant", style=ButtonStyle.primary, emoji="➡️")
    async def next(self, interaction: Interaction, button: Button):
        if interaction.user != self.member:
            await interaction.response.defer()
            return
        try:
            await interaction.response.edit_message(content="─" * 30, view=None)
        except discord.errors.InteractionResponded:
            pass
        self.stop()


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(RegistrationCog(bot))
