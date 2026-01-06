"""
Commandes du cog Registration.

Toutes les reponses sont envoyees en DM pour eviter de polluer les salons.

Contient les commandes Discord:
- !inscription: Demarre le processus d'inscription
- !profil: Affiche le profil
- !joueur: Gere les joueurs
- !localisation: Definit la localisation
- !langue: Change la langue
"""

import discord
from discord.ext import commands
import asyncio

from models.user_profile import UserProfile
from models.player import Player
from utils.logger import get_logger
from utils.i18n import t
from utils.map_generator import regenerate_map_if_needed
from utils.rate_limit import rate_limit, inscription_limiter, localisation_limiter, general_limiter
from utils.discord_helpers import reply_dm
from constants import Teams, Timeouts

from .views import LanguageSelectView
from . import steps

logger = get_logger("cogs.registration.handlers")


class RegistrationCommands:
    """Mixin contenant les commandes d'inscription.

    Cette classe est heritee par RegistrationCog pour ajouter les commandes.
    """

    @commands.command(name="inscription")
    @rate_limit(inscription_limiter)
    async def cmd_inscription(self, ctx):
        """Demarre ou reprend le processus d'inscription."""
        if not isinstance(ctx.channel, discord.DMChannel):
            async with self.bot.db_pool.acquire() as conn:
                profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
            await ctx.send(t("commands.inscription_public", profile.language))

        await self.start_registration(ctx.author)

    @commands.command(name="profil", aliases=["profile"])
    async def cmd_profil(self, ctx, *, search: str = None):
        """Affiche le profil d'un membre en DM. Usage: !profil [nom]"""
        from utils.discord_helpers import find_member

        is_own_profile = not search
        # Si pas de recherche, afficher son propre profil
        if is_own_profile:
            target = ctx.author
        else:
            # Rechercher le membre par nom partiel
            target, matches, error = await find_member(self.bot, search, ctx.guild)
            if not target:
                await reply_dm(ctx, error or "Membre non trouvé.")
                return
            # Si plusieurs résultats, informer l'utilisateur
            if len(matches) > 1:
                names = ", ".join([f"`{m.display_name}`" for m in matches[:5]])
                await reply_dm(ctx, f"Plusieurs membres trouvés ({len(matches)}): {names}. Affichage du premier.", silent=True)

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

        # Localisation: affichee uniquement sur son propre profil (adresse complete)
        if is_own_profile and profile.localisation:
            embed.add_field(name=t("profil_cmd.location", lang), value=profile.localisation, inline=False)
            embed.set_footer(text=t("profil_cmd.footer", lang))

        # Envoyer en DM
        try:
            await ctx.author.send(embed=embed)
            # Si la commande n'etait pas deja en DM, confirmer
            if not isinstance(ctx.channel, discord.DMChannel):
                await ctx.send(t("commands.sent_dm", lang))
        except discord.Forbidden:
            await ctx.send(t("errors.dm_failed", lang))

    @commands.command(name="joueur", aliases=["player", "joueurs", "players"])
    @rate_limit(general_limiter)
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
            await reply_dm(ctx, msg, silent=True)
        else:
            await reply_dm(ctx, t("commands.no_players", lang), silent=True)

        await reply_dm(ctx, t("commands.joueur_public", lang), silent=True)

        try:
            dm_channel = await member.create_dm()
            await steps.start_player_registration(self, member, dm_channel, lang)
            # Confirmer si depuis un salon public
            if ctx.guild:
                await ctx.send("📬 Reponse envoyee en DM.")
        except discord.Forbidden:
            await ctx.send(t("errors.dm_failed", lang))

    @commands.command(name="localisation", aliases=["location", "loc"])
    @rate_limit(localisation_limiter)
    async def cmd_localisation(self, ctx, *, location: str = None):
        """Definit ta localisation (en DM). Usage: !localisation MaVille"""
        async with self.bot.db_pool.acquire() as conn:
            profile = await UserProfile.get_or_create_user(ctx.author.name, conn, ctx.author)
        lang = profile.language

        if not location:
            if lang.upper() == "FR":
                await reply_dm(ctx,
                    "**Usage:** `!localisation MaVille`\n"
                    "**Exemples:**\n"
                    "- `!localisation France`\n"
                    "- `!localisation Paris`\n"
                    "- `!localisation 75001 Paris`"
                )
            else:
                await reply_dm(ctx,
                    "**Usage:** `!localisation YourCity`\n"
                    "**Examples:**\n"
                    "- `!localisation France`\n"
                    "- `!localisation London`\n"
                    "- `!localisation 10001 New York`"
                )
            return

        from utils.geocoding import geocode

        username = ctx.author.name
        result = await geocode(location)

        if result:
            async with self.bot.db_pool.acquire() as conn:
                profile = await UserProfile.get_or_create_user(username, conn, ctx.author)
                await profile.set_location(location, result.latitude, result.longitude, result.location_display)

            await reply_dm(ctx, t("location.saved", lang, address=result.address), silent=True)
            await reply_dm(ctx, t("location.map_update", lang))
            await regenerate_map_if_needed(self.bot.db_pool)
        else:
            await reply_dm(ctx, t("location.not_found", lang))

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
