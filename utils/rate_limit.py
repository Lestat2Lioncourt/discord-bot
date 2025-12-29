"""
Rate limiting pour les commandes Discord.

Protege contre les abus en limitant le nombre d'appels par utilisateur.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Callable, TYPE_CHECKING
from functools import wraps
from collections import defaultdict

if TYPE_CHECKING:
    from discord.ext import commands

from utils.i18n import t


class RateLimiter:
    """Gestionnaire de rate limiting par utilisateur."""

    def __init__(self, calls: int = 5, period: int = 60):
        """
        Initialise le rate limiter.

        Args:
            calls: Nombre d'appels autorises
            period: Periode en secondes
        """
        self.calls = calls
        self.period = timedelta(seconds=period)
        self._usage: dict[int, list[datetime]] = defaultdict(list)

    def is_limited(self, user_id: int) -> tuple[bool, Optional[int]]:
        """
        Verifie si un utilisateur est rate-limited.

        Args:
            user_id: ID Discord de l'utilisateur

        Returns:
            (is_limited, seconds_until_reset)
        """
        now = datetime.now()
        cutoff = now - self.period

        # Nettoyer les anciens appels
        self._usage[user_id] = [
            ts for ts in self._usage[user_id] if ts > cutoff
        ]

        if self.calls <= 0:
            # Toujours limite si 0 appels autorises
            return True, int(self.period.total_seconds())

        if len(self._usage[user_id]) >= self.calls:
            # Calculer le temps restant
            oldest = min(self._usage[user_id])
            reset_at = oldest + self.period
            seconds_left = int((reset_at - now).total_seconds())
            return True, max(1, seconds_left)

        return False, None

    def record_call(self, user_id: int) -> None:
        """Enregistre un appel pour un utilisateur."""
        self._usage[user_id].append(datetime.now())

    def reset(self, user_id: int) -> None:
        """Reset le compteur pour un utilisateur."""
        if user_id in self._usage:
            del self._usage[user_id]

    def reset_all(self) -> None:
        """Reset tous les compteurs."""
        self._usage.clear()

    def stats(self) -> dict:
        """Statistiques du rate limiter."""
        now = datetime.now()
        cutoff = now - self.period

        active_users = 0
        for user_id, timestamps in self._usage.items():
            active = [ts for ts in timestamps if ts > cutoff]
            if active:
                active_users += 1

        return {
            "tracked_users": len(self._usage),
            "active_users": active_users,
            "calls_allowed": self.calls,
            "period_seconds": self.period.total_seconds()
        }


# Rate limiters globaux
inscription_limiter = RateLimiter(calls=3, period=300)  # 3 par 5 min
localisation_limiter = RateLimiter(calls=5, period=60)  # 5 par minute
general_limiter = RateLimiter(calls=10, period=60)  # 10 par minute


def rate_limit(limiter: RateLimiter, silent: bool = False):
    """
    Decorateur de rate limiting pour les commandes Discord.

    Args:
        limiter: Instance du RateLimiter a utiliser
        silent: Si True, ne pas envoyer de message d'erreur

    Usage:
        @commands.command()
        @rate_limit(inscription_limiter)
        async def inscription(self, ctx):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            user_id = ctx.author.id
            is_limited, seconds_left = limiter.is_limited(user_id)

            if is_limited:
                if not silent:
                    lang = getattr(ctx.author, 'language', 'FR')
                    if hasattr(self, 'bot') and hasattr(self.bot, 'db_pool'):
                        # Essayer de recuperer la langue du profil
                        try:
                            from models.user_profile import UserProfile
                            async with self.bot.db_pool.acquire() as conn:
                                profile = await UserProfile.get_by_discord_id(
                                    conn, user_id
                                )
                                if profile:
                                    lang = profile.language
                        except Exception:
                            pass

                    message = t("errors.rate_limited", lang, seconds=seconds_left)
                    await ctx.send(message)
                return None

            # Enregistrer l'appel et executer
            limiter.record_call(user_id)
            return await func(self, ctx, *args, **kwargs)

        return wrapper
    return decorator


def rate_limit_check(limiter: RateLimiter) -> Callable:
    """
    Cree un check Discord.py pour le rate limiting.

    Usage:
        @commands.command()
        @commands.check(rate_limit_check(general_limiter))
        async def ma_commande(self, ctx):
            ...
    """
    async def predicate(ctx):
        from discord.ext.commands import CheckFailure

        is_limited, _ = limiter.is_limited(ctx.author.id)
        if is_limited:
            raise CheckFailure("Rate limited")
        limiter.record_call(ctx.author.id)
        return True

    return predicate
