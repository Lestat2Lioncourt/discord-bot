import asyncio
import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from models.user_profile import UserProfile
from utils.database import Database  # Importer le module dédié pour les interactions avec la base de données
from datetime import datetime  # Importer le module datetime pour obtenir la date et l'heure actuelles
import os

class EventsCog(commands.Cog):
    """Cog pour gérer les événements du bot."""

    def __init__(self, bot):
        self.bot = bot
        self.active_profiles = {}  # Dictionnaire pour stocker les profils actifs
        self.db = Database(bot.db_pool)  # Initialiser le module de base de données
        self.welcome_sent = False  # Flag pour vérifier si le message de bienvenue a été envoyé

    @commands.Cog.listener()
    async def on_ready(self):
        """Événement déclenché lorsque le bot est prêt."""
        print(f"**{self.bot.user} est connecté et prêt à discuter.**")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Événement déclenché lorsqu'un utilisateur rejoint le serveur."""
        # Récupération du canal où envoyer le message de bienvenue
        welcome_channel = discord.utils.get(member.guild.text_channels, name="général")
        if welcome_channel:
            await welcome_channel.send(f"👋 Bonjour {member.mention}, bienvenue sur **{member.guild.name}** ! 🎉")

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Événement déclenché lorsqu'un utilisateur change de statut."""
        print(f"🔔 Événement on_presence_update déclenché pour {after.name}")
        print(f"Statut avant: {before.status}, Statut après: {after.status}")

        # Mettre à jour le champ last_connection lors de la connexion
        if before.status != after.status and after.status in (discord.Status.online, discord.Status.idle):
            print(f"🔔 Utilisateur connecté : Username = {after.name}, Pseudo = {after.display_name}")

            # Vérifier et mettre à jour discord_name et last_connection si nécessaire
            async with self.bot.db_pool.acquire() as db_connection:
                user_profile = await UserProfile.get_or_create_user(after.name, db_connection, after)
                user_profile.last_connection = datetime.now()
                await user_profile.save()
                self.active_profiles[after.name] = user_profile
                print(f"✅ Profil chargé pour {after.display_name} [{after.name}] avec last_connection mis à jour")

            # Vérifier si l'utilisateur a validé la charte
            total_clauses = await self.db.get_total_clauses()
            print(f"Total clauses: {total_clauses}")
            user_validations = await self.db.get_user_validations(after.name)
            print(f"Validations de {after.name}: {user_validations}")
            if not await self.db.is_fully_validated(after.name, total_clauses):
                print(f"Lancement de la validation de la charte pour {after.name}")
                await self.start_charte_validation(after)

        # Mettre à jour le champ last_connection lors de la déconnexion
        elif before.status in (discord.Status.online, discord.Status.idle) and after.status == discord.Status.offline:
            print(f"🔔 Utilisateur déconnecté : Username = {after.name}, Pseudo = {after.display_name}")

            # Vérifier et mettre à jour last_connection si nécessaire
            async with self.bot.db_pool.acquire() as db_connection:
                user_profile = await UserProfile.get_or_create_user(after.name, db_connection, after)
                user_profile.last_connection = datetime.now()
                await user_profile.save()
                print(f"✅ Profil mis à jour pour {after.display_name} [{after.name}] avec last_connection")

    async def start_charte_validation(self, member):
        """Démarre le processus de validation de la charte dans le chat personnel de l'utilisateur."""
        print(f"Démarrage de la validation de la charte pour {member.name}")
        username = str(member.name)
        dm_channel = await member.create_dm()

        if not self.welcome_sent:
            # Afficher la clause 0a
            clause_0a_path = "data/texts/charte_0a_intro.txt"
            with open(clause_0a_path, "r", encoding="utf-8") as f:
                clause_0a_text = f.read()
            await dm_channel.send(f"{clause_0a_text}")
            self.welcome_sent = True  # Marquer le message de bienvenue comme envoyé

        # Vérifier s'il reste des clauses non validées
        user_validations = await self.db.get_user_validations(username)
        validated_clause_ids = [clause_idx for clause_idx, validation in user_validations if validation == 1]
        total_clauses = await self.db.get_total_clauses()

        if len(validated_clause_ids) < total_clauses:
            # Afficher la clause 0b
            clause_0b_path = "data/texts/charte_0b_intro.txt"
            with open(clause_0b_path, "r", encoding="utf-8") as f:
                clause_0b_text = f.read()
            await dm_channel.send(f"{clause_0b_text}")

            # Calculer le nombre de clauses restantes à valider
            remaining_clauses = total_clauses - len(validated_clause_ids)
            await dm_channel.send(f"**Il te reste {remaining_clauses} clauses à valider**")

            # Afficher les clauses non validées une par une
            charte_data = await self.db.get_charte_data()
            for clause in charte_data:
                if clause["idx"] not in validated_clause_ids and clause["validation"] == 1:
                    clause_path = clause["path"]
                    with open(clause_path, "r", encoding="utf-8") as f:
                        clause_text = f.read()

                    # Créer les boutons "J'accepte" et "Je refuse"
                    view = View()
                    accept_button = Button(label="J'accepte", style=ButtonStyle.green)
                    refuse_button = Button(label="Je refuse", style=ButtonStyle.red)

                    async def accept_callback(interaction: Interaction):
                        await self.db.add_validation(username, clause["idx"], 1)
                        await interaction.response.edit_message(content="Clause validée avec succès !", view=None)
                        await self.start_charte_validation(member)  # Relancer la validation pour la clause suivante

                    async def refuse_callback(interaction: Interaction):
                        await self.db.add_validation(username, clause["idx"], 0)
                        await interaction.response.edit_message(content="Clause dévalidée.", view=None)
                        await self.start_charte_validation(member)  # Relancer la validation pour la clause suivante

                    accept_button.callback = accept_callback
                    refuse_button.callback = refuse_callback

                    view.add_item(accept_button)
                    view.add_item(refuse_button)

                    await dm_channel.send(f"{clause_text}", view=view)
                    break  # Sortir de la boucle pour afficher une seule clause à la fois

        # Vérifier si l'utilisateur a validé toutes les clauses
        if await self.db.is_fully_validated(username, total_clauses):
            await dm_channel.send("Félicitations ! Vous avez validé toutes les clauses de la charte. Vous êtes désormais membre !")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Événement déclenché lorsqu'un utilisateur est mis à jour."""
        print(f"🔔Changement détecté : {before.status} → {after.status}")
        # Si l'utilisateur vient de passer en ligne
        if before.status != discord.Status.online and after.status in (discord.Status.online, discord.Status.idle):
            username = str(after.name)  # Récupère le nom d'utilisateur

            # Effectuer la vérification dans la base de données
            async with self.bot.db_pool.acquire() as connection:
                user_exists = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM users WHERE username = $1)", username
                )

            # Détermine le message à envoyer
            if user_exists:
                message = f"👋 Bienvenue {after.mention} ! Tu es déjà enregistré dans notre base de données. 👍"
            else:
                message = f"👋 Salut {after.mention} ! Tu n'es pas encore enregistré dans notre base de données. 🤔"

            # Récupérer le canal général pour envoyer le message
            general_channel = discord.utils.get(after.guild.text_channels, name="général")
            if general_channel:
                await general_channel.send(message)

# ===============================================================================
# setup : Ajoute le cog des événements au bot
# ===============================================================================
async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(EventsCog(bot))
