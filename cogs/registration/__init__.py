"""
Module d'inscription pour les nouveaux membres.

Structure:
- cog.py: RegistrationCog avec les commandes et etapes
- views.py: Vues interactives (boutons Discord)
"""

from .cog import RegistrationCog
from .views import LanguageSelectView, CharteAcceptView, KeepOrResetView

__all__ = [
    "RegistrationCog",
    "LanguageSelectView",
    "CharteAcceptView",
    "KeepOrResetView",
    "setup",
]


async def setup(bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(RegistrationCog(bot))
