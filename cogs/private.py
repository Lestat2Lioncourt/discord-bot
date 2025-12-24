from discord.ext import commands

class PrivateCommands(commands.Cog):
    """Commandes privées envoyées en DM."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def secret(self, ctx):
        """Répond en privé."""
        await ctx.author.send("Voici une réponse privée ! 🤫")

# La fonction setup doit être une coroutine qui utilise `await`
async def setup(bot):
    await bot.add_cog(PrivateCommands(bot))
