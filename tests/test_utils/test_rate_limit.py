"""
Tests pour utils/rate_limit.py
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

from utils.rate_limit import (
    RateLimiter,
    inscription_limiter,
    localisation_limiter,
    general_limiter,
)


class TestRateLimiter:
    """Tests pour la classe RateLimiter."""

    def test_init_default(self):
        """Initialisation avec valeurs par defaut."""
        limiter = RateLimiter()
        assert limiter.calls == 5
        assert limiter.period == timedelta(seconds=60)

    def test_init_custom(self):
        """Initialisation avec valeurs personnalisees."""
        limiter = RateLimiter(calls=3, period=300)
        assert limiter.calls == 3
        assert limiter.period == timedelta(seconds=300)

    def test_not_limited_initially(self):
        """Pas de limite au debut."""
        limiter = RateLimiter(calls=5, period=60)

        is_limited, seconds = limiter.is_limited(123)
        assert is_limited is False
        assert seconds is None

    def test_record_call(self):
        """Enregistre un appel."""
        limiter = RateLimiter(calls=5, period=60)

        limiter.record_call(123)

        assert len(limiter._usage[123]) == 1

    def test_limited_after_max_calls(self):
        """Limite atteinte apres max appels."""
        limiter = RateLimiter(calls=3, period=60)

        for _ in range(3):
            limiter.record_call(123)

        is_limited, seconds = limiter.is_limited(123)
        assert is_limited is True
        assert seconds is not None
        assert seconds > 0

    def test_different_users_independent(self):
        """Utilisateurs independants."""
        limiter = RateLimiter(calls=2, period=60)

        limiter.record_call(111)
        limiter.record_call(111)

        # User 111 est limite
        is_limited_111, _ = limiter.is_limited(111)
        assert is_limited_111 is True

        # User 222 n'est pas limite
        is_limited_222, _ = limiter.is_limited(222)
        assert is_limited_222 is False

    def test_cleanup_old_calls(self):
        """Nettoie les vieux appels."""
        limiter = RateLimiter(calls=2, period=60)

        # Ajouter un vieil appel
        old_time = datetime.now() - timedelta(seconds=120)
        limiter._usage[123] = [old_time]

        # Verifier nettoie
        is_limited, _ = limiter.is_limited(123)
        assert is_limited is False
        assert len(limiter._usage[123]) == 0

    def test_reset_user(self):
        """Reset un utilisateur specifique."""
        limiter = RateLimiter(calls=2, period=60)
        limiter.record_call(123)
        limiter.record_call(123)

        limiter.reset(123)

        is_limited, _ = limiter.is_limited(123)
        assert is_limited is False

    def test_reset_nonexistent_user(self):
        """Reset un utilisateur inexistant ne fait rien."""
        limiter = RateLimiter()
        limiter.reset(999)  # Pas d'erreur

    def test_reset_all(self):
        """Reset tous les utilisateurs."""
        limiter = RateLimiter(calls=2, period=60)
        limiter.record_call(111)
        limiter.record_call(222)

        limiter.reset_all()

        assert len(limiter._usage) == 0

    def test_stats(self):
        """Retourne les statistiques."""
        limiter = RateLimiter(calls=5, period=60)
        limiter.record_call(111)
        limiter.record_call(222)

        stats = limiter.stats()

        assert stats["tracked_users"] == 2
        assert stats["active_users"] == 2
        assert stats["calls_allowed"] == 5
        assert stats["period_seconds"] == 60

    def test_stats_with_expired(self):
        """Stats avec utilisateurs expires."""
        limiter = RateLimiter(calls=5, period=60)
        limiter.record_call(111)
        # Ajouter utilisateur expire
        limiter._usage[222] = [datetime.now() - timedelta(seconds=120)]

        stats = limiter.stats()

        assert stats["tracked_users"] == 2
        assert stats["active_users"] == 1


class TestGlobalLimiters:
    """Tests pour les limiters globaux."""

    def test_inscription_limiter_config(self):
        """Verifie config du limiter inscription."""
        assert inscription_limiter.calls == 3
        assert inscription_limiter.period == timedelta(seconds=300)

    def test_localisation_limiter_config(self):
        """Verifie config du limiter localisation."""
        assert localisation_limiter.calls == 5
        assert localisation_limiter.period == timedelta(seconds=60)

    def test_general_limiter_config(self):
        """Verifie config du limiter general."""
        assert general_limiter.calls == 10
        assert general_limiter.period == timedelta(seconds=60)


class TestRateLimitSeconds:
    """Tests pour le calcul des secondes restantes."""

    def test_seconds_calculation(self):
        """Calcul des secondes restantes."""
        limiter = RateLimiter(calls=2, period=60)

        # Enregistrer 2 appels
        limiter.record_call(123)
        limiter.record_call(123)

        is_limited, seconds = limiter.is_limited(123)

        assert is_limited is True
        # Devrait etre proche de 60 secondes
        assert 55 <= seconds <= 60

    def test_seconds_decreases_over_time(self):
        """Secondes diminuent avec le temps."""
        limiter = RateLimiter(calls=1, period=60)

        # Appel il y a 30 secondes
        limiter._usage[123] = [datetime.now() - timedelta(seconds=30)]
        limiter.record_call(123)

        is_limited, seconds = limiter.is_limited(123)

        # Premier appel encore recent, limite atteinte
        # Secondes restantes devraient etre ~30
        assert is_limited is True


class TestRateLimitEdgeCases:
    """Tests pour les cas limites."""

    def test_zero_calls_always_limited(self):
        """Avec 0 appels autorises, toujours limite."""
        limiter = RateLimiter(calls=0, period=60)

        is_limited, _ = limiter.is_limited(123)
        assert is_limited is True

    def test_very_short_period(self):
        """Periode tres courte."""
        limiter = RateLimiter(calls=1, period=1)
        limiter.record_call(123)

        is_limited, _ = limiter.is_limited(123)
        assert is_limited is True

    def test_large_user_id(self):
        """Grand ID Discord."""
        limiter = RateLimiter()
        large_id = 123456789012345678

        limiter.record_call(large_id)
        is_limited, _ = limiter.is_limited(large_id)

        assert is_limited is False
