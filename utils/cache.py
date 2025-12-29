"""
Cache avec TTL pour le bot Discord.

Fournit un cache en memoire avec expiration automatique.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional, TypeVar, Generic, Callable
from functools import wraps

T = TypeVar('T')


class TTLCache(Generic[T]):
    """Cache avec Time-To-Live (expiration automatique)."""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        """
        Initialise le cache.

        Args:
            ttl_seconds: Duree de vie des entrees en secondes
            max_size: Nombre maximum d'entrees
        """
        self._cache: dict[str, tuple[T, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_size = max_size

    def get(self, key: str) -> Optional[T]:
        """
        Recupere une valeur du cache.

        Args:
            key: Cle de l'entree

        Returns:
            La valeur ou None si absente/expiree
        """
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]
        if datetime.now() > expires_at:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: T) -> None:
        """
        Stocke une valeur dans le cache.

        Args:
            key: Cle de l'entree
            value: Valeur a stocker
        """
        # Nettoyage si cache plein
        if len(self._cache) >= self._max_size:
            self._cleanup_expired()

        # Si toujours plein, supprimer les plus anciennes
        if len(self._cache) >= self._max_size:
            oldest_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k][1]
            )[:len(self._cache) // 4]
            for k in oldest_keys:
                del self._cache[k]

        expires_at = datetime.now() + self._ttl
        self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """
        Supprime une entree du cache.

        Args:
            key: Cle de l'entree

        Returns:
            True si supprimee, False si absente
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Vide le cache."""
        self._cache.clear()

    def _cleanup_expired(self) -> int:
        """
        Supprime les entrees expirees.

        Returns:
            Nombre d'entrees supprimees
        """
        now = datetime.now()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for key in expired:
            del self._cache[key]
        return len(expired)

    @property
    def size(self) -> int:
        """Nombre d'entrees dans le cache (inclut les expirees)."""
        return len(self._cache)

    def stats(self) -> dict:
        """Statistiques du cache."""
        now = datetime.now()
        expired = sum(1 for _, exp in self._cache.values() if now > exp)
        return {
            "total": len(self._cache),
            "active": len(self._cache) - expired,
            "expired": expired,
            "max_size": self._max_size,
            "ttl_seconds": self._ttl.total_seconds()
        }


# Caches globaux pour le bot
profile_cache: TTLCache = TTLCache(ttl_seconds=60, max_size=500)
role_cache: TTLCache = TTLCache(ttl_seconds=300, max_size=100)


def cached(cache: TTLCache, key_func: Callable[..., str]):
    """
    Decorateur pour mettre en cache le resultat d'une fonction async.

    Args:
        cache: Instance du cache a utiliser
        key_func: Fonction pour generer la cle a partir des arguments

    Usage:
        @cached(profile_cache, lambda discord_id: f"profile:{discord_id}")
        async def get_profile(discord_id: int):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)

            # Verifier le cache
            result = cache.get(key)
            if result is not None:
                return result

            # Executer la fonction
            result = await func(*args, **kwargs)

            # Stocker en cache si resultat non-None
            if result is not None:
                cache.set(key, result)

            return result

        # Ajouter methode pour invalider le cache
        def invalidate(*args, **kwargs):
            key = key_func(*args, **kwargs)
            cache.delete(key)

        setattr(wrapper, 'invalidate', invalidate)
        setattr(wrapper, 'cache', cache)
        return wrapper

    return decorator


def invalidate_profile(discord_id: int) -> None:
    """Invalide le cache pour un profil specifique."""
    profile_cache.delete(f"profile:{discord_id}")


def invalidate_all_profiles() -> None:
    """Invalide tous les profils en cache."""
    profile_cache.clear()
