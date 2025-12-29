"""
Etapes du processus d'inscription.

Contient les fonctions de flow appelees par le cog:
- ask_language: Choix de la langue
- send_charte: Envoi et validation de la charte
- complete_profile: Saisie joueurs et localisation
- ask_players_for_team: Saisie des joueurs pour une equipe
- ask_location: Saisie de la localisation
- save_location: Geocodage et sauvegarde
- finish_registration: Finalisation et notification aux Sages
"""

import asyncpg
import asyncio
import discord

from pydantic import ValidationError

from models.user_profile import UserProfile
from models.player import Player
from models.schemas import PlayerCreate, LocationInput
from utils.logger import get_logger
from utils.i18n import t
from utils.map_generator import regenerate_map_if_needed
from config import CHARTE_FILES, URL_CHARTE
from constants import Teams, Timeouts

from .views import LanguageSelectView, CharteAcceptView, KeepOrResetView

logger = get_logger("cogs.registration.steps")


async def ask_language(cog, member: discord.Member, dm_channel: discord.DMChannel):
    """Demande la langue preferee.

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
    """
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
            cog.active_registrations.pop(member.name, None)
            return

        lang = view.language or "FR"
        logger.info(f"Langue choisie par {member.name}: {lang}")

        # Sauvegarder la langue
        async with cog.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(member.name, conn, member)
            await profile.set_language(lang)
        logger.info(f"Langue sauvegardee pour {member.name}")

        # Message de bienvenue
        await dm_channel.send(t("welcome.title", lang, display_name=member.display_name))
        await dm_channel.send(t("welcome.intro", lang))
        await asyncio.sleep(1)

        # Etape 2: Charte
        await send_charte(cog, member, dm_channel, lang)

    except discord.HTTPException as e:
        logger.error(f"Erreur dans ask_language pour {member.name}: {e}", exc_info=True)
        await dm_channel.send(f"Erreur: {e}")


async def send_charte(cog, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
    """Envoie le lien vers la charte et demande validation.

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        lang: Code langue (FR/EN)
    """
    username = member.name

    # Message d'intro
    await dm_channel.send(t("charte.intro", lang))
    await asyncio.sleep(0.5)

    # Envoyer le lien ou le fichier HTML
    if URL_CHARTE:
        # Utiliser l'URL en ligne
        await dm_channel.send(t("charte.instruction_url", lang, url=URL_CHARTE))
    else:
        # Fallback: envoyer le fichier HTML
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
        cog.active_registrations.pop(username, None)
        return

    if not view.accepted:
        await dm_channel.send(t("charte.refused", lang))
        cog.active_registrations.pop(username, None)
        return

    # Charte validee
    async with cog.bot.db_pool.acquire() as conn:
        profile = await UserProfile.get_or_create_user(username, conn, member)
        await profile.validate_charte()

    await dm_channel.send(t("charte.accepted", lang))
    await asyncio.sleep(1)

    # Etape 3: Completer le profil
    await complete_profile(cog, member, dm_channel, lang)


async def complete_profile(cog, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
    """Complete le profil (joueurs + localisation).

    Flow simplifie : on demande toujours joueurs et localisation.
    Les nouvelles saisies remplacent les anciennes (annule et remplace).

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        lang: Code langue (FR/EN)
    """
    # Titre principal
    await dm_channel.send(t("profile.title", lang))
    await asyncio.sleep(0.5)

    # 4.1 Team 1
    await ask_players_for_team(cog, member, dm_channel, Teams.TEAM1_ID, Teams.TEAM1_NAME, lang, is_main_team=True)

    # 4.2 Team 2
    await ask_players_for_team(cog, member, dm_channel, Teams.TEAM2_ID, Teams.TEAM2_NAME, lang, is_main_team=False)

    # 4.3 Localisation
    await asyncio.sleep(0.5)
    await ask_location(cog, member, dm_channel, lang)


async def ask_players_for_team(cog, member: discord.Member, dm_channel: discord.DMChannel,
                                team_id: int, team_name: str, lang: str, is_main_team: bool = True):
    """Demande les joueurs pour une equipe (annule et remplace).

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        team_id: ID de l'equipe (1 ou 2)
        team_name: Nom de l'equipe
        lang: Code langue (FR/EN)
        is_main_team: True si equipe principale
    """
    username = member.name

    if is_main_team:
        await dm_channel.send(t("players.team_main", lang, team_name=team_name))
    else:
        await dm_channel.send(t("players.team_other", lang, team_name=team_name))

    def check(m):
        return m.author == member and isinstance(m.channel, discord.DMChannel)

    try:
        msg = await cog.bot.wait_for("message", check=check, timeout=Timeouts.PLAYER_INPUT)
        content = msg.content.strip()

        # Si "." ou vide, conserver les joueurs existants
        if content == "." or not content:
            await dm_channel.send(t("players.skipped", lang, team_name=team_name))
            return

        # Parser les noms separes par des virgules
        player_names = [name.strip() for name in content.split(",") if name.strip()]

        # Valider tous les noms avec Pydantic avant de supprimer
        valid_names = []
        seen_names = set()
        for player_name in player_names:
            # Validation Pydantic (longueur, caracteres interdits)
            try:
                validated = PlayerCreate(
                    player_name=player_name,
                    team_id=team_id,
                    member_username=username
                )
                player_name = validated.player_name  # Nom nettoye (strip)
            except ValidationError as e:
                # Extraire le message d'erreur
                error_msg = str(e.errors()[0]['msg']) if e.errors() else str(e)
                if "au moins" in error_msg or "moins" in error_msg:
                    await dm_channel.send(t("players.name_too_short_skip", lang, player_name=player_name))
                elif "depasser" in error_msg:
                    await dm_channel.send(t("players.name_too_long_skip", lang, player_name=player_name))
                else:
                    await dm_channel.send(t("players.invalid_name", lang, player_name=player_name))
                continue

            # Verifier doublon dans la meme saisie
            name_lower = player_name.lower()
            if name_lower in seen_names:
                await dm_channel.send(t("players.duplicate_in_input", lang, player_name=player_name, team_name=team_name))
                continue
            seen_names.add(name_lower)
            valid_names.append(player_name)

        if not valid_names:
            await dm_channel.send(t("players.skipped", lang, team_name=team_name))
            return

        # Transaction: Supprimer les anciens et ajouter les nouveaux
        players_added = []
        async with cog.bot.db_pool.acquire() as conn:
            async with conn.transaction():
                # Supprimer les anciens joueurs de cette team
                deleted = await Player.delete_by_team_for_member(
                    cog.bot.db_pool, username, team_id, conn=conn
                )
                if deleted > 0:
                    logger.debug(f"{deleted} ancien(s) joueur(s) supprime(s) pour {username} (team {team_id})")

                # Ajouter les nouveaux joueurs
                for player_name in valid_names:
                    try:
                        await Player.create(
                            cog.bot.db_pool, username, player_name, team_id, conn=conn
                        )
                        players_added.append(player_name)
                    except asyncpg.UniqueViolationError:
                        await dm_channel.send(t("players.already_exists", lang, member=username, player_name=player_name, team_name=team_name))
                    except asyncpg.PostgresError as e:
                        logger.error(f"Erreur creation joueur: {e}")
                        await dm_channel.send(t("players.error", lang))
                        raise

        if players_added:
            await dm_channel.send(t("players.count", lang, count=len(players_added), team_name=team_name))

    except asyncio.TimeoutError:
        await dm_channel.send(t("players.timeout", lang))


async def ask_location(cog, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
    """Demande la localisation (optionnel).

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        lang: Code langue (FR/EN)
    """
    username = member.name

    # Verifier si une localisation existe deja
    async with cog.bot.db_pool.acquire() as conn:
        profile = await UserProfile.get_or_create_user(username, conn, member)
        await profile.load_from_db()

    # Titre + instruction
    msg = t("location.title", lang) + "\n" + t("location.intro", lang)
    if profile.localisation:
        msg += f"\n\n📍 *Actuel : {profile.localisation}*"
    await dm_channel.send(msg)

    def check(m):
        return m.author == member and isinstance(m.channel, discord.DMChannel)

    try:
        msg = await cog.bot.wait_for("message", check=check, timeout=Timeouts.PLAYER_INPUT)
        location = msg.content.strip()

        if location and location != ".":
            await save_location(cog, member, dm_channel, location, lang)
        else:
            # Conserver la localisation existante ou passer
            if profile.localisation:
                kept_msg = "Localisation conservee." if lang.upper() == "FR" else "Location kept."
                await dm_channel.send(kept_msg)
            else:
                await dm_channel.send(t("location.skipped", lang))
            await finish_registration(cog, member, dm_channel, lang)

    except asyncio.TimeoutError:
        await dm_channel.send(t("location.timeout", lang))
        await finish_registration(cog, member, dm_channel, lang)


async def save_location(cog, member: discord.Member, dm_channel: discord.DMChannel, location: str, lang: str):
    """Geocode et sauvegarde la localisation.

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        location: Adresse saisie
        lang: Code langue (FR/EN)
    """
    from utils.geocoding import geocode

    username = member.name

    # Validation Pydantic (longueur, caracteres interdits)
    try:
        validated = LocationInput(query=location)
        location = validated.query
    except ValidationError:
        await dm_channel.send(t("location.invalid", lang))
        await finish_registration(cog, member, dm_channel, lang)
        return

    await dm_channel.send(t("location.searching", lang))

    result = geocode(location)

    if result:
        async with cog.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(username, conn, member)
            await profile.set_location(location, result.latitude, result.longitude, result.location_display)

        await dm_channel.send(t("location.saved", lang, address=result.address))
        await dm_channel.send(t("location.map_update", lang))
        await regenerate_map_if_needed(cog.bot.db_pool)
    else:
        await dm_channel.send(t("location.not_found", lang))

    await asyncio.sleep(1)
    await finish_registration(cog, member, dm_channel, lang)


async def finish_registration(cog, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
    """Termine l'inscription et notifie les Sages.

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        lang: Code langue (FR/EN)
    """
    from cogs.sages import notify_sages_new_registration, notify_sages_returning_member

    username = member.name
    cog.active_registrations.pop(username, None)

    # Charger le profil complet
    async with cog.bot.db_pool.acquire() as conn:
        profile = await UserProfile.get_or_create_user(username, conn, member)
        await profile.load_from_db()

    # Compter les joueurs enregistres
    players = await Player.get_by_member(cog.bot.db_pool, username)

    summary = t("finish.title", lang) + "\n\n"

    if players:
        summary += t("finish.your_players", lang) + "\n"
        for p in players:
            summary += f"- {p.player_name} ({p.team_name or 'N/A'})\n"
        summary += "\n"

    # Ajouter la localisation si presente (sans coordonnees GPS pour la vie privee)
    if profile.localisation:
        loc_label = "📍 Localisation:" if lang.upper() == "FR" else "📍 Location:"
        summary += f"{loc_label} {profile.localisation}\n\n"

    summary += t("finish.pending", lang)

    await dm_channel.send(summary)
    logger.info(f"Inscription terminee pour {username}, en attente de validation")

    # Notifier les Sages
    await notify_sages_new_registration(cog.bot, member, profile, players)

    # Verifier si c'est un revenant (info stockee au debut de l'inscription)
    returning_key = f"{username}_returning"
    returning_info = cog.active_registrations.pop(returning_key, None)
    if returning_info:
        await notify_sages_returning_member(cog.bot, member, returning_info)


async def start_player_registration(cog, member: discord.Member, dm_channel: discord.DMChannel, lang: str):
    """Demarre uniquement la saisie des joueurs (sans charte).

    Args:
        cog: Instance du RegistrationCog
        member: Membre Discord
        dm_channel: Canal DM
        lang: Code langue (FR/EN)
    """
    username = member.name

    await dm_channel.send("═" * 35)
    title = "🎾 **GESTION DE TES JOUEURS** 🎾" if lang.upper() == "FR" else "🎾 **MANAGE YOUR PLAYERS** 🎾"
    await dm_channel.send(title)
    await asyncio.sleep(0.5)

    # Team 1
    await ask_players_for_team(cog, member, dm_channel, Teams.TEAM1_ID, Teams.TEAM1_NAME, lang, is_main_team=True)

    # Team 2
    await ask_players_for_team(cog, member, dm_channel, Teams.TEAM2_ID, Teams.TEAM2_NAME, lang, is_main_team=False)

    # Resume
    players = await Player.get_by_member(cog.bot.db_pool, username)
    if players:
        msg = t("finish.your_players", lang) + "\n"
        for p in players:
            msg += f"- {p.player_name} ({p.team_name})\n"
        await dm_channel.send(msg)
    else:
        await dm_channel.send(t("commands.no_players", lang))
