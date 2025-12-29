"""
Module de metriques simples pour le monitoring.

Fournit des compteurs et timers pour suivre:
- Nombre de commandes executees
- Temps de reponse
- Erreurs par type
- Statistiques cache/DB
"""

import time
from dataclasses import dataclass, field
from typing import Dict
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("utils.metrics")


@dataclass
class Metrics:
    """Conteneur de metriques globales."""

    # Compteurs de commandes
    commands_total: int = 0
    commands_success: int = 0
    commands_error: int = 0

    # Par commande
    command_counts: Dict[str, int] = field(default_factory=dict)

    # Temps de reponse (en ms)
    response_times: list = field(default_factory=list)

    # Erreurs par type
    errors_by_type: Dict[str, int] = field(default_factory=dict)

    # DB
    db_queries: int = 0
    db_errors: int = 0

    # Cache
    cache_hits: int = 0
    cache_misses: int = 0

    # Demarrage
    start_time: datetime = field(default_factory=datetime.now)

    def record_command(self, name: str, success: bool = True, duration_ms: float = 0):
        """Enregistre l'execution d'une commande."""
        self.commands_total += 1
        if success:
            self.commands_success += 1
        else:
            self.commands_error += 1

        self.command_counts[name] = self.command_counts.get(name, 0) + 1

        if duration_ms > 0:
            self.response_times.append(duration_ms)
            # Garder seulement les 1000 dernieres mesures
            if len(self.response_times) > 1000:
                self.response_times = self.response_times[-1000:]

    def record_error(self, error_type: str):
        """Enregistre une erreur."""
        self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1

    def record_db_query(self, success: bool = True):
        """Enregistre une requete DB."""
        self.db_queries += 1
        if not success:
            self.db_errors += 1

    def record_cache(self, hit: bool):
        """Enregistre un acces cache."""
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def get_uptime_seconds(self) -> float:
        """Retourne le temps depuis le demarrage."""
        return (datetime.now() - self.start_time).total_seconds()

    def get_avg_response_time(self) -> float:
        """Retourne le temps de reponse moyen."""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    def get_cache_hit_rate(self) -> float:
        """Retourne le taux de hit du cache."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total * 100

    def get_summary(self) -> dict:
        """Retourne un resume des metriques."""
        return {
            "uptime_seconds": round(self.get_uptime_seconds(), 1),
            "commands": {
                "total": self.commands_total,
                "success": self.commands_success,
                "error": self.commands_error,
                "by_name": dict(self.command_counts),
            },
            "response_time_avg_ms": round(self.get_avg_response_time(), 2),
            "errors_by_type": dict(self.errors_by_type),
            "db": {
                "queries": self.db_queries,
                "errors": self.db_errors,
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate_percent": round(self.get_cache_hit_rate(), 1),
            },
        }

    def log_summary(self):
        """Log le resume des metriques."""
        summary = self.get_summary()
        logger.info(f"Metrics summary: {summary}")


# Instance globale
metrics = Metrics()


class Timer:
    """Context manager pour mesurer le temps d'execution."""

    def __init__(self, name: str = "operation"):
        self.name = name
        self.start_time: float = 0
        self.duration_ms: float = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        self.duration_ms = (end_time - self.start_time) * 1000
        return False  # Ne pas supprimer les exceptions


def timed_command(name: str):
    """Decorateur pour mesurer et enregistrer le temps d'une commande."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            success = True
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                success = False
                metrics.record_error(type(e).__name__)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                metrics.record_command(name, success, duration_ms)
        return wrapper
    return decorator
