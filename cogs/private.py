"""
Cog pour les commandes privees (envoyees en DM).

Commandes:
- !secret: Repond en prive (test)
"""

from discord.ext import commands


class PrivateCommandsCog(commands.Cog):
    """Commandes privées envoyées en DM."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def secret(self, ctx):
        """Répond en privé."""
        await ctx.author.send("Voici une réponse privée ! 🤫")

async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(PrivateCommandsCog(bot))
