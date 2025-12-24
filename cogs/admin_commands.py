import discord
from discord.ext import commands
import json
import os
from utils.database import Database  # Importer le module de base de données

class AdminCommandsCog(commands.Cog):
    """Cog pour les commandes d'administration."""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database(bot.db_pool)  # Initialiser le module de base de données
        self.charte_path = "data/charte.json"

    @commands.command(name="set_charte")
    @commands.has_permissions(administrator=True)  # Limiter à ceux qui ont la permission d'administrateur
    async def set_charte(self, ctx):
        """Remplit la table Charte en fonction du fichier charte.json."""
        if not os.path.exists(self.charte_path):
            await ctx.send("❌ Le fichier `charte.json` n'existe pas.")
            return

        with open(self.charte_path, "r", encoding="utf-8") as f:
            charte_data = json.load(f)

        await self.db.set_charte(charte_data)
        await ctx.send("✅ La table `Charte` a été mise à jour avec succès.")

# ===============================================================================
# setup : Ajoute le cog des commandes d'administration au bot
# ===============================================================================
async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(AdminCommandsCog(bot))
