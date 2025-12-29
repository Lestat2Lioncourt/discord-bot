"""
Schemas Pydantic pour la validation des donnees.

Ces schemas assurent une validation coherente des entrees utilisateur
avant leur traitement par le bot.
"""

import re
from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict


# Constantes de validation
MIN_PSEUDO_LENGTH = 2
MAX_PSEUDO_LENGTH = 50
MAX_USERNAME_LENGTH = 100
FORBIDDEN_PATTERNS = [
    r'<[^>]+>',     # HTML tags
    r'"',           # Double quotes (simples autorisees pour noms: O'Brien)
    r'--',          # SQL comments
    r';',           # SQL separator
    r'\\',          # Backslash
]


class PlayerCreate(BaseModel):
    """Schema pour la creation d'un joueur."""

    model_config = ConfigDict(str_strip_whitespace=True)

    player_name: str
    team_id: int
    member_username: str

    @field_validator('player_name')
    @classmethod
    def validate_player_name(cls, v: str) -> str:
        if not v:
            raise ValueError("Le nom du joueur ne peut pas etre vide")

        if len(v) < MIN_PSEUDO_LENGTH:
            raise ValueError(
                f"Le nom doit contenir au moins {MIN_PSEUDO_LENGTH} caracteres"
            )

        if len(v) > MAX_PSEUDO_LENGTH:
            raise ValueError(
                f"Le nom ne peut pas depasser {MAX_PSEUDO_LENGTH} caracteres"
            )

        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, v):
                raise ValueError("Le nom contient des caracteres non autorises")

        return v

    @field_validator('team_id')
    @classmethod
    def validate_team_id(cls, v: int) -> int:
        if v not in (1, 2):
            raise ValueError("L'ID de team doit etre 1 ou 2")
        return v

    @field_validator('member_username')
    @classmethod
    def validate_member_username(cls, v: str) -> str:
        if not v:
            raise ValueError("Le username ne peut pas etre vide")
        if len(v) > MAX_USERNAME_LENGTH:
            raise ValueError(
                f"Le username ne peut pas depasser {MAX_USERNAME_LENGTH} caracteres"
            )
        return v


class LocationInput(BaseModel):
    """Schema pour la saisie de localisation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v:
            raise ValueError("La localisation ne peut pas etre vide")

        if len(v) > 200:
            raise ValueError("La localisation est trop longue (max 200 caracteres)")

        # Verifier les caracteres dangereux
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, v):
                raise ValueError("La localisation contient des caracteres non autorises")

        return v


class LocationUpdate(BaseModel):
    """Schema pour la mise a jour de localisation en DB."""

    localisation: str
    latitude: float
    longitude: float
    location_display: Optional[str] = None

    @field_validator('latitude')
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("La latitude doit etre entre -90 et 90")
        return v

    @field_validator('longitude')
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("La longitude doit etre entre -180 et 180")
        return v


class UserIdInput(BaseModel):
    """Schema pour valider un ID Discord."""

    discord_id: int

    @field_validator('discord_id')
    @classmethod
    def validate_discord_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("L'ID Discord doit etre positif")

        # Discord IDs sont des snowflakes de 17-19 chiffres
        str_id = str(v)
        if len(str_id) < 17 or len(str_id) > 19:
            raise ValueError("L'ID Discord n'est pas valide (17-19 chiffres)")

        return v


class LanguageInput(BaseModel):
    """Schema pour la selection de langue."""

    language: str

    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        normalized = v.upper().strip()
        if normalized not in ('FR', 'EN'):
            raise ValueError("La langue doit etre FR ou EN")
        return normalized


class ApprovalAction(BaseModel):
    """Schema pour les actions d'approbation/refus."""

    target_username: str
    action: str
    reason: Optional[str] = None

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ('approve', 'refuse'):
            raise ValueError("L'action doit etre 'approve' ou 'refuse'")
        return v

    @field_validator('target_username')
    @classmethod
    def validate_target(cls, v: str) -> str:
        if not v:
            raise ValueError("Le membre cible est requis")
        if len(v) > MAX_USERNAME_LENGTH:
            raise ValueError("Le nom du membre est trop long")
        return v

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if len(v) > 500:
                raise ValueError("La raison ne peut pas depasser 500 caracteres")
            # Nettoyer les caracteres dangereux
            for pattern in FORBIDDEN_PATTERNS:
                if re.search(pattern, v):
                    raise ValueError("La raison contient des caracteres non autorises")
        return v
