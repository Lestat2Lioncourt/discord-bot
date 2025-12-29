"""
Module de retry logic avec backoff exponentiel.

Fournit un decorateur @retry pour les appels externes
qui peuvent echouer temporairement (geocoding, APIs, etc.).
"""

import asyncio
import functools
import inspect
from typing import Callable, Type, Tuple, Union

from utils.logger import get_logger

logger = get_logger("utils.retry")


def retry(
    max_attempts: int = 3,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    on_retry: Callable[[Exception, int], None] = None
):
    """Decorateur de retry avec backoff exponentiel.

    Args:
        max_attempts: Nombre maximum de tentatives (defaut: 3)
        backoff: Facteur de backoff exponentiel (defaut: 2.0)
            - Tentative 1: immediate
            - Tentative 2: apres 1s
            - Tentative 3: apres 2s
            - etc.
        exceptions: Exception(s) a intercepter pour retry
        on_retry: Callback optionnel appele avant chaque retry

    Example:
        @retry(max_attempts=3, backoff=2, exceptions=(TimeoutError, ConnectionError))
        def fetch_data():
            ...

        @retry(max_attempts=3, exceptions=GeocoderTimedOut)
        def geocode(location):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = backoff ** (attempt - 1)
                        logger.warning(
                            f"{func.__name__} tentative {attempt}/{max_attempts} echouee: {e}. "
                            f"Retry dans {wait_time:.1f}s..."
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        import time
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} echec apres {max_attempts} tentatives: {e}"
                        )
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry logic error: no exception captured")

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = backoff ** (attempt - 1)
                        logger.warning(
                            f"{func.__name__} tentative {attempt}/{max_attempts} echouee: {e}. "
                            f"Retry dans {wait_time:.1f}s..."
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} echec apres {max_attempts} tentatives: {e}"
                        )
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry logic error: no exception captured")

        # Detecter si la fonction est async ou sync
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def retry_sync(
    max_attempts: int = 3,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
):
    """Version simplifiee pour fonctions synchrones uniquement."""
    return retry(max_attempts=max_attempts, backoff=backoff, exceptions=exceptions)


def retry_async(
    max_attempts: int = 3,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
):
    """Version simplifiee pour fonctions asynchrones uniquement."""
    return retry(max_attempts=max_attempts, backoff=backoff, exceptions=exceptions)
