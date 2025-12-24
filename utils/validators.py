"""
Fonctions de validation des inputs utilisateur.
"""

import re
from typing import Optional, Tuple

# Limites de validation
MAX_PSEUDO_LENGTH = 32
MIN_PSEUDO_LENGTH = 2
MAX_USERNAME_LENGTH = 100
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def validate_pseudo(pseudo: str) -> Tuple[bool, Optional[str]]:
    """
    Valide un pseudo Discord.

    Args:
        pseudo: Le pseudo à valider

    Returns:
        Tuple (is_valid, error_message)
    """
    if not pseudo:
        return False, "Le pseudo ne peut pas être vide"

    if len(pseudo) < MIN_PSEUDO_LENGTH:
        return False, f"Le pseudo doit contenir au moins {MIN_PSEUDO_LENGTH} caractères"

    if len(pseudo) > MAX_PSEUDO_LENGTH:
        return False, f"Le pseudo ne peut pas dépasser {MAX_PSEUDO_LENGTH} caractères"

    # Vérifier les caractères dangereux (injection SQL/XSS basique)
    dangerous_patterns = [
        r'[<>"\']',  # Caractères HTML/SQL
        r'--',       # Commentaire SQL
        r';',        # Fin de requête SQL
        r'\\x',      # Séquences hexadécimales
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, pseudo):
            return False, "Le pseudo contient des caractères non autorisés"

    return True, None


def validate_user_id(user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Valide un ID utilisateur Discord.

    Args:
        user_id: L'ID à valider

    Returns:
        Tuple (is_valid, error_message)
    """
    # Les IDs Discord sont des snowflakes (entiers positifs de 17-19 chiffres)
    if user_id <= 0:
        return False, "L'ID utilisateur doit être un nombre positif"

    if len(str(user_id)) < 17 or len(str(user_id)) > 19:
        return False, "L'ID utilisateur n'est pas un ID Discord valide"

    return True, None


def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Valide un nom d'utilisateur.

    Args:
        username: Le nom d'utilisateur à valider

    Returns:
        Tuple (is_valid, error_message)
    """
    if not username:
        return False, "Le nom d'utilisateur ne peut pas être vide"

    if len(username) > MAX_USERNAME_LENGTH:
        return False, f"Le nom d'utilisateur ne peut pas dépasser {MAX_USERNAME_LENGTH} caractères"

    # Vérifier les caractères dangereux
    if re.search(r'[<>"\';\\]', username):
        return False, "Le nom d'utilisateur contient des caractères non autorisés"

    return True, None


def validate_image_attachment(filename: str, file_size: int, max_size_mb: int = 10) -> Tuple[bool, Optional[str]]:
    """
    Valide une pièce jointe image.

    Args:
        filename: Nom du fichier
        file_size: Taille du fichier en bytes
        max_size_mb: Taille maximale en MB

    Returns:
        Tuple (is_valid, error_message)
    """
    if not filename:
        return False, "Nom de fichier invalide"

    # Vérifier l'extension
    ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ', '.join(ALLOWED_IMAGE_EXTENSIONS)
        return False, f"Type de fichier non autorisé. Extensions acceptées: {allowed}"

    # Vérifier la taille
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        return False, f"Fichier trop volumineux (max {max_size_mb} MB)"

    return True, None
