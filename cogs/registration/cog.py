"""
Cog pour gerer l'inscription des nouveaux membres.

Flow:
1. Choix de la langue (FR/EN)
2. Validation de la charte (fichier HTML + bouton unique)
3. "As-tu des joueurs dans This Is PSG ?" -> saisie jusqu'a vide
4. "As-tu des joueurs dans This Is PSG 2 ?" -> saisie jusqu'a vide
5. Localisation (optionnel, pour la carte des membres)
6. En attente de validation par un Sage
"""

import discord
from discord.ext import commands
import asyncio

from models.user_profile import UserProfile
from models.player import Player
from constants import Teams, Timeouts
from utils.database import Database
from utils.logger import get_logger
from utils.i18n import t
from utils.map_generator import regenerate_map_if_needed
from config import CHARTE_FILES
from cogs.sages import notify_sages_new_registration, notify_sages_returning_member
from .views import LanguageSelectView, CharteAcceptView, KeepOrResetView

logger = get_logger("cogs.registration")


class RegistrationCog(commands.Cog):
    """Cog pour gerer l'inscription des nouveaux membres."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)
        self.active_registrations = {}  # username -> step

    # =========================================================================
    # Etapes d'inscription
    # =========================================================================

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
            lang = profile.language
            await dm_channel.send(t("welcome.already_registered", lang))
            return

        # Marquer comme en cours d'inscription
        self.active_registrations[username] = "language"

        # Etape 1: Choix de la langue
        await self.ask_language(member, dm_channel)

    async def ask_language(self, member: discord.Member, dm_channel: discord.DMChannel):
        """Demande la langue preferee."""
        try:
            view = LanguageSelectView(member)
            await dm_channel.send(
                "**Choisis ta langue / Select your language**",
                view=view
            )

            try:
                await asyncio.wait_for(view.wait(), timeout=Timeouts.LANGUAGE_SELECT)
            except asyncio.TimeoutError:
                await dm_channel.send("Temps ecoule / Time expired.")
                self.active_registrations.pop(member.name, None)
                return

            lang = view.language or "FR"
            logger.info(f"Langue choisie par {member.name}: {lang}")

            # Sauvegarder la langue
            async with self.bot.db_pool.acquire() as conn:
                profile = await UserProfile.get_or_create_user(member.name, conn, member)
                await profile.set_language(lang)
            logger.info(f"Langue sauvegardee pour {member.name}")

            # Message de bienvenue
            await dm_channel.send(t("welcome.title", lang, display_name=member.display_name))
            await dm_channel.send(t("welcome.intro", lang))
            await asyncio.sleep(1)

            # Etape 2: Charte
            await self.send_charte(member, dm_channel, lang)

        except Exception as e:
            logger.error(f"Erreur dans ask_language pour {member.name}: {e}", exc_info=True)
            await dm_channel.send(f"Erreur: {e}")

    async def send_charte(self, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
        """Envoie la charte en fichier HTML et demande validation."""
        username = member.name

        # Message d'intro
        await dm_channel.send(t("charte.intro", lang))
        await asyncio.sleep(0.5)

        # Envoyer le fichier HTML (cles en minuscules)
        charte_file = CHARTE_FILES.get(lang.lower(), CHARTE_FILES["fr"])
        if charte_file.exists():
            file = discord.File(charte_file, filename=f"charte_{lang}.html")
            await dm_channel.send(t("charte.instruction", lang), file=file)
        else:
            logger.error(f"Fichier charte introuvable: {charte_file}")
            await dm_channel.send("Erreur: fichier charte introuvable.")
            return

        await asyncio.sleep(1)

        # Bouton de validation
        view = CharteAcceptView(member, lang)
        await dm_channel.send("", view=view)

        try:
            await asyncio.wait_for(view.wait(), timeout=Timeouts.CHARTE_READ)
        except asyncio.TimeoutError:
            await dm_channel.send(t("charte.timeout", lang))
            self.active_registrations.pop(username, None)
            return

        if not view.accepted:
            await dm_channel.send(t("charte.refused", lang))
            self.active_registrations.pop(username, None)
            return

        # Charte validee
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.validate_charte()

        await dm_channel.send(t("charte.accepted", lang))
        await asyncio.sleep(1)

        # Etape 3: Completer le profil
        await self.complete_profile(member, dm_channel, lang)

    async def complete_profile(self, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
        """Etape 4: Completer le profil (joueurs + localisation)."""
        username = member.name

        await dm_channel.send(t("profile.title", lang))
        await asyncio.sleep(0.5)

        # Verifier si le membre a deja des infos enregistrees
        existing_players = await Player.get_by_member(self.bot.db_pool, username)

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.load_from_db()

        has_existing_data = existing_players or profile.localisation

        if has_existing_data:
            # Afficher les infos existantes
            if lang.upper() == "FR":
                msg = "**Des informations sont deja enregistrees :**\n"
            else:
                msg = "**Some information is already registered:**\n"

            if existing_players:
                team1 = [p.player_name for p in existing_players if p.team_name == Teams.TEAM1_NAME]
                team2 = [p.player_name for p in existing_players if p.team_name == Teams.TEAM2_NAME]
                if team1:
                    msg += f"• {Teams.TEAM1_NAME} : {', '.join(team1)}\n"
                if team2:
                    msg += f"• {Teams.TEAM2_NAME} : {', '.join(team2)}\n"

            if profile.localisation:
                coords = ""
                if profile.latitude and profile.longitude:
                    coords = f" ({profile.latitude:.4f}, {profile.longitude:.4f})"
                msg += f"• 📍 {profile.localisation}{coords}\n"

            msg += "\n" + t("profile.keep_or_reset", lang)

            await dm_channel.send(msg)

            view = KeepOrResetView(member, lang)
            await dm_channel.send(t("profile.choose_option", lang), view=view)

            try:
                await asyncio.wait_for(view.wait(), timeout=Timeouts.KEEP_OR_RESET)
            except asyncio.TimeoutError:
                await dm_channel.send(t("profile.players_kept", lang))
                view.keep = True

            if view.keep:
                # Conserver les infos -> passer directement a la fin
                await self.finish_registration(member, dm_channel, lang)
                return
            else:
                # Effacer les joueurs et la localisation
                await Player.delete_all_for_member(self.bot.db_pool, username)
                if profile.localisation:
                    await profile.clear_location()
                await dm_channel.send(t("profile.players_cleared", lang))
                await asyncio.sleep(0.5)

        # 4.1 Joueurs
        await dm_channel.send(t("players.title", lang))
        await dm_channel.send(t("players.intro", lang))
        await asyncio.sleep(0.5)

        # Team 1
        await self.ask_players_for_team(member, dm_channel, Teams.TEAM1_ID, Teams.TEAM1_NAME, lang, is_main_team=True)

        # Team 2
        await self.ask_players_for_team(member, dm_channel, Teams.TEAM2_ID, Teams.TEAM2_NAME, lang, is_main_team=False)

        # 4.2 Localisation
        await asyncio.sleep(0.5)
        await self.ask_location(member, dm_channel, lang)

    async def ask_players_for_team(self, member: discord.Member, dm_channel: discord.DMChannel,
                                    team_id: int, team_name: str, lang: str, is_main_team: bool = True):
        """Demande les joueurs pour une equipe (annule et remplace, separes par des virgules)."""
        username = member.name

        if is_main_team:
            await dm_channel.send(t("players.team_main", lang, team_name=team_name))
        else:
            await dm_channel.send(t("players.team_other", lang, team_name=team_name))

        def check(m):
            return m.author == member and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=Timeouts.PLAYER_INPUT)
            content = msg.content.strip()

            # Si "." ou vide, conserver les joueurs existants
            if content == "." or not content:
                await dm_channel.send(t("players.skipped", lang, team_name=team_name))
                return

            # Parser les noms separes par des virgules
            player_names = [name.strip() for name in content.split(",") if name.strip()]

            # Valider tous les noms avant de supprimer
            valid_names = []
            seen_names = set()  # Pour detecter les doublons dans la saisie
            for player_name in player_names:
                if len(player_name) < 2:
                    await dm_channel.send(t("players.name_too_short_skip", lang, player_name=player_name))
                    continue
                if len(player_name) > 50:
                    await dm_channel.send(t("players.name_too_long_skip", lang, player_name=player_name))
                    continue
                # Verifier doublon dans la meme saisie (insensible a la casse)
                name_lower = player_name.lower()
                if name_lower in seen_names:
                    await dm_channel.send(t("players.duplicate_in_input", lang, player_name=player_name, team_name=team_name))
                    continue
                seen_names.add(name_lower)
                valid_names.append(player_name)

            if not valid_names:
                await dm_channel.send(t("players.skipped", lang, team_name=team_name))
                return

            # Supprimer les anciens joueurs de cette team (annule et remplace)
            deleted = await Player.delete_by_team_for_member(self.bot.db_pool, username, team_id)
            if deleted > 0:
                logger.debug(f"{deleted} ancien(s) joueur(s) supprime(s) pour {username} (team {team_id})")

            # Ajouter les nouveaux joueurs
            players_added = []
            for player_name in valid_names:
                try:
                    await Player.create(self.bot.db_pool, username, player_name, team_id)
                    players_added.append(player_name)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "unique" in error_msg or "duplicate" in error_msg:
                        await dm_channel.send(t("players.already_exists", lang, member=username, player_name=player_name, team_name=team_name))
                    else:
                        logger.error(f"Erreur creation joueur: {e}")
                        await dm_channel.send(t("players.error", lang))

            if players_added:
                await dm_channel.send(t("players.count", lang, count=len(players_added), team_name=team_name))

        except asyncio.TimeoutError:
            await dm_channel.send(t("players.timeout", lang))

    async def ask_location(self, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
        """Demande la localisation (optionnel)."""
        username = member.name

        # Verifier si une localisation existe deja
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.load_from_db()

        if profile.localisation:
            coords = ""
            if profile.latitude and profile.longitude:
                coords = f" ({profile.latitude:.4f}, {profile.longitude:.4f})"
            existing_msg = f"📍 **Localisation actuelle:** {profile.localisation}{coords}\n\n"
            if lang.upper() == "FR":
                existing_msg += "Tape `.` pour conserver, ou saisis une nouvelle localisation :"
            else:
                existing_msg += "Type `.` to keep, or enter a new location:"
            await dm_channel.send(t("location.title", lang))
            await dm_channel.send(existing_msg)
        else:
            await dm_channel.send(t("location.title", lang))
            await dm_channel.send(t("location.intro", lang))

        def check(m):
            return m.author == member and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=Timeouts.PLAYER_INPUT)
            location = msg.content.strip()

            if location and location != ".":
                await self.save_location(member, dm_channel, location, lang)
            else:
                # Conserver la localisation existante ou passer
                if profile.localisation:
                    kept_msg = "Localisation conservee." if lang.upper() == "FR" else "Location kept."
                    await dm_channel.send(kept_msg)
                else:
                    await dm_channel.send(t("location.skipped", lang))
                await self.finish_registration(member, dm_channel, lang)

        except asyncio.TimeoutError:
            await dm_channel.send(t("location.timeout", lang))
            await self.finish_registration(member, dm_channel, lang)

    async def save_location(self, member: discord.Member, dm_channel: discord.DMChannel, location: str, lang: str):
        """Geocode et sauvegarde la localisation."""
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut

        username = member.name

        await dm_channel.send(t("location.searching", lang))

        try:
            geolocator = Nominatim(user_agent="discord-bot-this-is-psg")
            # addressdetails=True pour obtenir les composants de l'adresse
            loc = geolocator.geocode(location, timeout=Timeouts.GEOCODING, addressdetails=True)

            if loc:
                # Extraire pays/region pour affichage anonymise
                location_display = self._extract_location_display(loc.raw.get('address', {}))

                async with self.bot.db_pool.acquire() as conn:
                    profile = await UserProfile.get_or_create_user(username, conn, member)
                    await profile.set_location(location, loc.latitude, loc.longitude, location_display)

                coords_info = f"\n📍 Coordonnees: {loc.latitude:.4f}, {loc.longitude:.4f}"
                await dm_channel.send(t("location.saved", lang, address=loc.address) + coords_info)
                await dm_channel.send(t("location.map_update", lang))

                # Regenerer la carte (seuls les membres approuves y apparaitront)
                await regenerate_map_if_needed(self.bot.db_pool)
            else:
                await dm_channel.send(t("location.not_found", lang))

        except GeocoderTimedOut:
            await dm_channel.send(t("location.service_error", lang))
        except Exception as e:
            logger.error(f"Erreur geocoding: {e}")
            await dm_channel.send(t("location.error", lang))

        await asyncio.sleep(1)
        await self.finish_registration(member, dm_channel, lang)

    def _extract_location_display(self, address: dict) -> str:
        """Extrait un affichage anonymise (pays + region/etat) depuis les donnees Nominatim.

        Args:
            address: Dictionnaire des composants d'adresse Nominatim

        Returns:
            Chaine au format "Pays" ou "Region, Pays"
        """
        country = address.get('country', '')

        # Chercher le niveau region/etat/departement selon le pays
        region = (
            address.get('state') or           # USA, Allemagne, etc.
            address.get('region') or          # Certains pays
            address.get('county') or          # UK
            address.get('province') or        # Canada, etc.
            address.get('department') or      # France (plus precis que region)
            ''
        )

        if region and country:
            return f"{region}, {country}"
        elif country:
            return country
        elif region:
            return region
        else:
            return "Localisation definie"

    async def finish_registration(self, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
        """Termine l'inscription."""
        username = member.name
        self.active_registrations.pop(username, None)

        # Charger le profil complet
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.load_from_db()

        # Compter les joueurs enregistres
        players = await Player.get_by_member(self.bot.db_pool, username)

        summary = t("finish.title", lang) + "\n\n"

        if players:
            summary += t("finish.your_players", lang) + "\n"
            for p in players:
                summary += f"- {p.player_name} ({p.team_name or 'N/A'})\n"
            summary += "\n"

        # Ajouter la localisation si presente
        if profile.localisation:
            loc_label = "📍 Localisation:" if lang.upper() == "FR" else "📍 Location:"
            summary += f"{loc_label} {profile.localisation}"
            if profile.latitude and profile.longitude:
                summary += f" ({profile.latitude:.4f}, {profile.longitude:.4f})"
            summary += "\n\n"

        summary += t("finish.pending", lang)

        await dm_channel.send(summary)
        logger.info(f"Inscription terminee pour {username}, en attente de validation")

        # Notifier les Sages
        await notify_sages_new_registration(self.bot, member, profile, players)

        # Verifier si c'est un revenant (ancien membre avec nouveau username)
        returning_info = await UserProfile.check_returning_member(
            self.bot.db_pool, member.id, username
        )
        if returning_info:
            await notify_sages_returning_member(self.bot, member, returning_info)

    async def start_player_registration(self, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
        """Demarre uniquement la saisie des joueurs (sans charte)."""
        username = member.name

        await dm_channel.send("═" * 35)
        title = "🎾 **GESTION DE TES JOUEURS** 🎾" if lang.upper() == "FR" else "🎾 **MANAGE YOUR PLAYERS** 🎾"
        await dm_channel.send(title)
        await asyncio.sleep(0.5)

        # Team 1
        await self.ask_players_for_team(member, dm_channel, Teams.TEAM1_ID, Teams.TEAM1_NAME, lang, is_main_team=True)

        # Team 2
        await self.ask_players_for_team(member, dm_channel, Teams.TEAM2_ID, Teams.TEAM2_NAME, lang, is_main_team=False)

        # Resume
        players = await Player.get_by_member(self.bot.db_pool, username)
        if players:
            msg = t("finish.your_players", lang) + "\n"
            for p in players:
                msg += f"- {p.player_name} ({p.team_name})\n"
            await dm_channel.send(msg)
        else:
            await dm_channel.send(t("commands.no_players", lang))

    # =========================================================================
    # Commandes
    # =========================================================================

    @commands.command(name="inscription")
    async def cmd_inscription(self, ctx):
        """Demarre ou reprend le processus d'inscription."""
        if not isinstance(ctx.channel, discord.DMChannel):
            # Recuperer la langue du profil si existant
            async with self.bot.db_pool.acquire() as conn:
                profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
            await ctx.send(t("commands.inscription_public", profile.language))

        await self.start_registration(ctx.author)

    @commands.command(name="profil")
    async def cmd_profil(self, ctx, member: discord.Member = None):
        """Affiche le profil d'un membre."""
        target = member or ctx.author
        username = target.name

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, target)
            await profile.load_from_db()

        lang = profile.language
        players = await Player.get_by_member(self.bot.db_pool, username)

        embed = discord.Embed(
            title=t("profil_cmd.title", lang, name=target.display_name),
            color=discord.Color.blue()
        )

        embed.add_field(
            name=t("profil_cmd.status", lang),
            value=profile.get_status_display(),
            inline=False
        )

        embed.add_field(
            name=t("profil_cmd.language", lang),
            value=t("profil_cmd.lang_fr", lang) if profile.language.upper() == "FR" else t("profil_cmd.lang_en", lang),
            inline=True
        )

        if players:
            team1_players = [p for p in players if p.team_name == Teams.TEAM1_NAME]
            team2_players = [p for p in players if p.team_name == Teams.TEAM2_NAME]

            if team1_players:
                names = ", ".join([p.player_name for p in team1_players])
                embed.add_field(name=Teams.TEAM1_NAME, value=names, inline=False)

            if team2_players:
                names = ", ".join([p.player_name for p in team2_players])
                embed.add_field(name=Teams.TEAM2_NAME, value=names, inline=False)
        else:
            embed.add_field(name=t("profil_cmd.players", lang), value=t("profil_cmd.no_players", lang), inline=False)

        if profile.localisation:
            loc_value = profile.localisation
            if profile.latitude and profile.longitude:
                loc_value += f"\n📍 {profile.latitude:.4f}, {profile.longitude:.4f}"
            embed.add_field(name=t("profil_cmd.location", lang), value=loc_value, inline=False)

        if target == ctx.author:
            embed.set_footer(text=t("profil_cmd.footer", lang))

        await ctx.send(embed=embed)

    @commands.command(name="joueur", aliases=["player", "joueurs", "players"])
    async def cmd_joueur(self, ctx):
        """Affiche les joueurs et permet d'en ajouter."""
        username = ctx.author.name
        member = ctx.author

        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
        lang = profile.language

        players = await Player.get_by_member(self.bot.db_pool, username)

        if players:
            team1 = [p.player_name for p in players if p.team_name == Teams.TEAM1_NAME]
            team2 = [p.player_name for p in players if p.team_name == Teams.TEAM2_NAME]

            msg = t("profile.existing_players", lang) + "\n"
            if team1:
                msg += f"{Teams.TEAM1_NAME} : {', '.join(team1)}\n"
            if team2:
                msg += f"{Teams.TEAM2_NAME} : {', '.join(team2)}\n"
            await ctx.send(msg)
        else:
            await ctx.send(t("commands.no_players", lang))

        await ctx.send(t("commands.joueur_public", lang))

        try:
            dm_channel = await member.create_dm()
            await self.start_player_registration(member, dm_channel, lang)
        except discord.Forbidden:
            await ctx.send(t("errors.dm_failed", lang))

    @commands.command(name="localisation")
    async def cmd_localisation(self, ctx, *, location: str = None):
        """Definit ta localisation. Usage: !localisation MaVille"""
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        lang = profile.language

        if not location:
            if lang.upper() == "FR":
                await ctx.send(
                    "**Usage:** `!localisation MaVille`\n"
                    "**Exemples:**\n"
                    "- `!localisation France`\n"
                    "- `!localisation Paris`\n"
                    "- `!localisation 75001 Paris`"
                )
            else:
                await ctx.send(
                    "**Usage:** `!localisation YourCity`\n"
                    "**Examples:**\n"
                    "- `!localisation France`\n"
                    "- `!localisation London`\n"
                    "- `!localisation 10001 New York`"
                )
            return

        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut

        username = ctx.author.name

        try:
            geolocator = Nominatim(user_agent="discord-bot-this-is-psg")
            loc = geolocator.geocode(location, timeout=Timeouts.GEOCODING, addressdetails=True)

            if loc:
                # Extraire pays/region pour affichage anonymise
                location_display = self._extract_location_display(loc.raw.get('address', {}))

                async with self.bot.db_pool.acquire() as conn:
                    profile = await UserProfile.get_or_create_user(username, conn, ctx.author)
                    await profile.set_location(location, loc.latitude, loc.longitude, location_display)

                await ctx.send(t("location.saved", lang, address=loc.address))
                await ctx.send(t("location.map_update", lang))

                # Regenerer la carte (seuls les membres approuves y apparaitront)
                await regenerate_map_if_needed(self.bot.db_pool)
            else:
                await ctx.send(t("location.not_found", lang))

        except GeocoderTimedOut:
            await ctx.send(t("location.service_error", lang))
        except Exception as e:
            logger.error(f"Erreur geocoding: {e}")
            await ctx.send(t("location.error", lang))

    @commands.command(name="langue", aliases=["language", "lang"])
    async def cmd_langue(self, ctx):
        """Change ta langue preferee."""
        member = ctx.author
        view = LanguageSelectView(member)
        msg = await ctx.send("**Choisis ta langue / Select your language**", view=view)

        try:
            await asyncio.wait_for(view.wait(), timeout=Timeouts.LANGUAGE_CHANGE)
        except asyncio.TimeoutError:
            await msg.edit(content="Temps ecoule / Time expired.", view=None)
            return

        if view.language:
            async with self.bot.db_pool.acquire() as conn:
                profile = await UserProfile.get_or_create_user(member.name, conn, member)
                await profile.set_language(view.language)

            if view.language.upper() == "FR":
                await msg.edit(content=t("langue_cmd.set_fr", "FR"), view=None)
            else:
                await msg.edit(content=t("langue_cmd.set_en", "EN"), view=None)
