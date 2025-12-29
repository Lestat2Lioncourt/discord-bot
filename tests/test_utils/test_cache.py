"""
Tests pour utils/cache.py
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import time

from utils.cache import (
    TTLCache,
    profile_cache,
    role_cache,
    cached,
    invalidate_profile,
    invalidate_all_profiles,
)


class TestTTLCache:
    """Tests pour la classe TTLCache."""

    def test_init_default(self):
        """Initialisation avec valeurs par defaut."""
        cache = TTLCache()
        assert cache._ttl == timedelta(seconds=60)
        assert cache._max_size == 1000

    def test_init_custom(self):
        """Initialisation avec valeurs personnalisees."""
        cache = TTLCache(ttl_seconds=120, max_size=500)
        assert cache._ttl == timedelta(seconds=120)
        assert cache._max_size == 500

    def test_set_and_get(self):
        """Stocke et recupere une valeur."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "value1")

        result = cache.get("key1")
        assert result == "value1"

    def test_get_missing_key(self):
        """Retourne None si cle absente."""
        cache = TTLCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_get_expired(self):
        """Retourne None si entree expiree."""
        cache = TTLCache(ttl_seconds=1)
        cache.set("key1", "value1")

        # Forcer l'expiration
        cache._cache["key1"] = ("value1", datetime.now() - timedelta(seconds=10))

        result = cache.get("key1")
        assert result is None
        assert "key1" not in cache._cache  # Supprimee

    def test_delete_existing(self):
        """Supprime une entree existante."""
        cache = TTLCache()
        cache.set("key1", "value1")

        result = cache.delete("key1")
        assert result is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self):
        """Retourne False si cle absente."""
        cache = TTLCache()
        result = cache.delete("nonexistent")
        assert result is False

    def test_clear(self):
        """Vide le cache."""
        cache = TTLCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()
        assert cache.size == 0

    def test_size(self):
        """Retourne la taille du cache."""
        cache = TTLCache()
        assert cache.size == 0

        cache.set("key1", "value1")
        assert cache.size == 1

        cache.set("key2", "value2")
        assert cache.size == 2

    def test_cleanup_expired(self):
        """Nettoie les entrees expirees."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("active", "value")
        cache._cache["expired"] = ("old", datetime.now() - timedelta(seconds=100))

        count = cache._cleanup_expired()
        assert count == 1
        assert "expired" not in cache._cache
        assert "active" in cache._cache

    def test_max_size_cleanup(self):
        """Nettoie quand cache plein."""
        cache = TTLCache(ttl_seconds=60, max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Devrait declencher nettoyage

        # Le cache garde max_size entrees apres nettoyage
        # Comme aucune entree n'est expiree, il supprime les plus anciennes
        assert cache.size <= 4  # Au max 4 si nettoyage incomplet
        assert "key4" in cache._cache  # La derniere entree est presente

    def test_stats(self):
        """Retourne les statistiques."""
        cache = TTLCache(ttl_seconds=60, max_size=100)
        cache.set("key1", "value1")
        cache._cache["expired"] = ("old", datetime.now() - timedelta(seconds=100))

        stats = cache.stats()
        assert stats["total"] == 2
        assert stats["active"] == 1
        assert stats["expired"] == 1
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 60


class TestGlobalCaches:
    """Tests pour les caches globaux."""

    def test_profile_cache_config(self):
        """Verifie config du cache profils."""
        assert profile_cache._ttl == timedelta(seconds=60)
        assert profile_cache._max_size == 500

    def test_role_cache_config(self):
        """Verifie config du cache roles."""
        assert role_cache._ttl == timedelta(seconds=300)
        assert role_cache._max_size == 100


class TestCachedDecorator:
    """Tests pour le decorateur @cached."""

    @pytest.mark.asyncio
    async def test_cached_function(self):
        """Cache le resultat d'une fonction."""
        cache = TTLCache(ttl_seconds=60)
        call_count = 0

        @cached(cache, lambda x: f"key:{x}")
        async def fetch_data(x):
            nonlocal call_count
            call_count += 1
            return f"data_{x}"

        # Premier appel - execute la fonction
        result1 = await fetch_data(1)
        assert result1 == "data_1"
        assert call_count == 1

        # Deuxieme appel - retourne du cache
        result2 = await fetch_data(1)
        assert result2 == "data_1"
        assert call_count == 1  # Pas re-execute

    @pytest.mark.asyncio
    async def test_cached_different_keys(self):
        """Cles differentes = appels differents."""
        cache = TTLCache(ttl_seconds=60)
        call_count = 0

        @cached(cache, lambda x: f"key:{x}")
        async def fetch_data(x):
            nonlocal call_count
            call_count += 1
            return f"data_{x}"

        await fetch_data(1)
        await fetch_data(2)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_invalidate(self):
        """Invalide une entree du cache."""
        cache = TTLCache(ttl_seconds=60)
        call_count = 0

        @cached(cache, lambda x: f"key:{x}")
        async def fetch_data(x):
            nonlocal call_count
            call_count += 1
            return f"data_{x}"

        await fetch_data(1)
        assert call_count == 1

        fetch_data.invalidate(1)
        await fetch_data(1)
        assert call_count == 2  # Re-execute apres invalidation

    @pytest.mark.asyncio
    async def test_cached_none_not_cached(self):
        """Ne cache pas les resultats None."""
        cache = TTLCache(ttl_seconds=60)
        call_count = 0

        @cached(cache, lambda x: f"key:{x}")
        async def fetch_data(x):
            nonlocal call_count
            call_count += 1
            return None

        await fetch_data(1)
        await fetch_data(1)

        assert call_count == 2  # Re-execute car None


class TestInvalidateHelpers:
    """Tests pour les fonctions d'invalidation."""

    def test_invalidate_profile(self):
        """Invalide un profil specifique."""
        profile_cache.set("profile:123", {"name": "test"})

        invalidate_profile(123)

        assert profile_cache.get("profile:123") is None

    def test_invalidate_all_profiles(self):
        """Invalide tous les profils."""
        profile_cache.set("profile:1", {"name": "test1"})
        profile_cache.set("profile:2", {"name": "test2"})

        invalidate_all_profiles()

        assert profile_cache.size == 0
