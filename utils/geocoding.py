"""
Module de geocodage avec cache et retry.

Wrapper autour de geopy.Nominatim avec:
- Cache TTL pour eviter les rate-limits
- Retry automatique avec backoff exponentiel
- Gestion des erreurs centralisee
- Extraction automatique du pays/region
"""

from dataclasses import dataclass
from typing import Optional
from functools import lru_cache
import time

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeopyError

from utils.logger import get_logger
from utils.retry import retry
from constants import Timeouts

logger = get_logger("utils.geocoding")

# User agent pour Nominatim (requis)
USER_AGENT = "discord-bot-this-is-psg"

# Cache TTL en secondes (24h - les adresses ne changent pas souvent)
CACHE_TTL = 86400

# Cache simple avec TTL
_cache: dict[str, tuple[float, Optional["GeoResult"]]] = {}


@dataclass
class GeoResult:
    """Resultat d'un geocodage."""
    address: str
    latitude: float
    longitude: float
    location_display: str  # Pays/region anonymise
    raw: dict  # Donnees brutes Nominatim


def _extract_location_display(address: dict) -> str:
    """Extrait un affichage anonymise (pays + region/etat)."""
    country = address.get('country', '')
    region = (
        address.get('state') or
        address.get('region') or
        address.get('county') or
        address.get('province') or
        address.get('department') or
        ''
    )

    if region and country:
        return f"{region}, {country}"
    elif country:
        return country
    elif region:
        return region
    else:
        return "Localisation definie"


def _get_from_cache(location: str) -> Optional[GeoResult]:
    """Recupere du cache si valide."""
    key = location.lower().strip()
    if key in _cache:
        timestamp, result = _cache[key]
        if time.time() - timestamp < CACHE_TTL:
            logger.debug(f"Cache hit: {location}")
            return result
        else:
            del _cache[key]
    return None


def _set_cache(location: str, result: Optional[GeoResult]) -> None:
    """Ajoute au cache."""
    key = location.lower().strip()
    _cache[key] = (time.time(), result)


@retry(max_attempts=3, backoff=2.0, exceptions=(GeocoderTimedOut, GeocoderServiceError))
def _geocode_api_call(location: str):
    """Appel API Nominatim avec retry automatique.

    Leve une exception en cas d'echec (interceptee par le decorateur retry).
    Retourne None si l'adresse n'est pas trouvee (pas une erreur).
    """
    geolocator = Nominatim(user_agent=USER_AGENT)
    return geolocator.geocode(
        location,
        timeout=Timeouts.GEOCODING,
        addressdetails=True
    )


def geocode(location: str) -> Optional[GeoResult]:
    """
    Geocode une adresse avec cache et retry.

    Args:
        location: Adresse ou lieu a geocoder

    Returns:
        GeoResult ou None si non trouve
    """
    # Verifier le cache d'abord
    cached = _get_from_cache(location)
    if cached is not None:
        return cached

    try:
        loc = _geocode_api_call(location)

        if loc:
            address_data = loc.raw.get('address', {})
            result = GeoResult(
                address=loc.address,
                latitude=loc.latitude,
                longitude=loc.longitude,
                location_display=_extract_location_display(address_data),
                raw=loc.raw
            )
            _set_cache(location, result)
            logger.debug(f"Geocode OK: {location} -> {result.latitude}, {result.longitude}")
            return result
        else:
            _set_cache(location, None)
            logger.debug(f"Geocode not found: {location}")
            return None

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        # Echec apres tous les retries
        logger.error(f"Geocode echec definitif pour {location}: {e}")
        return None
    except GeopyError as e:
        # Autres erreurs geopy (pas de retry)
        logger.error(f"Geocode error: {e}")
        return None


def invalidate_cache(location: str) -> bool:
    """Invalide une entree specifique du cache.

    Args:
        location: Adresse a invalider

    Returns:
        True si l'entree existait et a ete supprimee
    """
    key = location.lower().strip()
    if key in _cache:
        del _cache[key]
        logger.debug(f"Cache invalidated: {location}")
        return True
    return False


def clear_cache() -> int:
    """Vide le cache. Retourne le nombre d'entrees supprimees."""
    count = len(_cache)
    _cache.clear()
    return count


def cache_stats() -> dict:
    """Retourne les stats du cache."""
    now = time.time()
    valid = sum(1 for ts, _ in _cache.values() if now - ts < CACHE_TTL)
    return {
        "total": len(_cache),
        "valid": valid,
        "expired": len(_cache) - valid
    }
