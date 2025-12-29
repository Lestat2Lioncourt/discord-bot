"""Tests pour le module retry."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch

from utils.retry import retry


class TestRetryDecorator:
    """Tests pour le decorateur @retry."""

    def test_retry_success_first_attempt(self):
        """Test: succes au premier essai."""
        call_count = 0

        @retry(max_attempts=3, backoff=0.01)
        def always_works():
            nonlocal call_count
            call_count += 1
            return "success"

        result = always_works()
        assert result == "success"
        assert call_count == 1

    def test_retry_success_after_failures(self):
        """Test: succes apres quelques echecs."""
        call_count = 0

        @retry(max_attempts=3, backoff=0.01, exceptions=ValueError)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "success"

        result = fails_twice()
        assert result == "success"
        assert call_count == 3

    def test_retry_all_attempts_fail(self):
        """Test: echec apres toutes les tentatives."""
        call_count = 0

        @retry(max_attempts=3, backoff=0.01, exceptions=ValueError)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent failure")

        with pytest.raises(ValueError, match="permanent failure"):
            always_fails()
        assert call_count == 3

    def test_retry_only_catches_specified_exceptions(self):
        """Test: ne retry que pour les exceptions specifiees."""
        call_count = 0

        @retry(max_attempts=3, backoff=0.01, exceptions=ValueError)
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retried")

        with pytest.raises(TypeError, match="not retried"):
            raises_type_error()
        assert call_count == 1  # Pas de retry

    def test_retry_multiple_exception_types(self):
        """Test: retry pour plusieurs types d'exceptions."""
        call_count = 0

        @retry(max_attempts=4, backoff=0.01, exceptions=(ValueError, TypeError))
        def alternates_errors():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first")
            elif call_count == 2:
                raise TypeError("second")
            elif call_count == 3:
                raise ValueError("third")
            return "success"

        result = alternates_errors()
        assert result == "success"
        assert call_count == 4

    def test_retry_with_on_retry_callback(self):
        """Test: callback on_retry appele a chaque retry."""
        call_count = 0
        retry_calls = []

        def on_retry_callback(exc, attempt):
            retry_calls.append((str(exc), attempt))

        @retry(max_attempts=3, backoff=0.01, exceptions=ValueError, on_retry=on_retry_callback)
        def fails_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first failure")
            return "success"

        result = fails_once()
        assert result == "success"
        assert call_count == 2
        assert len(retry_calls) == 1
        assert retry_calls[0] == ("first failure", 1)

    def test_retry_preserves_function_metadata(self):
        """Test: le decorateur preserve le nom et la docstring."""
        @retry(max_attempts=3, backoff=0.01)
        def my_function():
            """Ma docstring."""
            return 42

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Ma docstring."


class TestRetryAsync:
    """Tests pour le decorateur @retry avec fonctions async."""

    @pytest.mark.asyncio
    async def test_async_retry_success_first_attempt(self):
        """Test async: succes au premier essai."""
        call_count = 0

        @retry(max_attempts=3, backoff=0.01)
        async def async_works():
            nonlocal call_count
            call_count += 1
            return "async success"

        result = await async_works()
        assert result == "async success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_success_after_failures(self):
        """Test async: succes apres echecs."""
        call_count = 0

        @retry(max_attempts=3, backoff=0.01, exceptions=ValueError)
        async def async_fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temp")
            return "success"

        result = await async_fails_twice()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_all_fail(self):
        """Test async: echec apres toutes les tentatives."""
        call_count = 0

        @retry(max_attempts=2, backoff=0.01, exceptions=ValueError)
        async def async_always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await async_always_fails()
        assert call_count == 2


class TestRetryEdgeCases:
    """Tests pour les cas limites."""

    def test_retry_with_max_attempts_one(self):
        """Test: max_attempts=1 (pas de retry)."""
        call_count = 0

        @retry(max_attempts=1, backoff=0.01, exceptions=ValueError)
        def no_retry():
            nonlocal call_count
            call_count += 1
            raise ValueError("no retry")

        with pytest.raises(ValueError):
            no_retry()
        assert call_count == 1

    def test_retry_with_args_and_kwargs(self):
        """Test: les arguments sont passes correctement."""
        @retry(max_attempts=2, backoff=0.01)
        def with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = with_args(1, 2, c=3)
        assert result == "1-2-3"

    def test_retry_returns_none(self):
        """Test: une fonction peut retourner None."""
        @retry(max_attempts=2, backoff=0.01)
        def returns_none():
            return None

        result = returns_none()
        assert result is None
