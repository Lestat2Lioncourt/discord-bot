"""
Tests pour utils/validators.py
"""

import pytest
from utils.validators import (
    validate_pseudo,
    validate_user_id,
    validate_username,
    validate_image_attachment,
    MAX_PSEUDO_LENGTH,
    MIN_PSEUDO_LENGTH,
    MAX_USERNAME_LENGTH,
    ALLOWED_IMAGE_EXTENSIONS,
)


class TestValidatePseudo:
    """Tests pour validate_pseudo()"""

    def test_valid_pseudo(self):
        """Pseudo valide accepte."""
        is_valid, error = validate_pseudo("MonPseudo")
        assert is_valid is True
        assert error is None

    def test_valid_pseudo_with_numbers(self):
        """Pseudo avec chiffres accepte."""
        is_valid, error = validate_pseudo("Player123")
        assert is_valid is True
        assert error is None

    def test_valid_pseudo_with_underscore(self):
        """Pseudo avec underscore accepte."""
        is_valid, error = validate_pseudo("My_Pseudo")
        assert is_valid is True
        assert error is None

    def test_empty_pseudo(self):
        """Pseudo vide refuse."""
        is_valid, error = validate_pseudo("")
        assert is_valid is False
        assert "vide" in error.lower()

    def test_none_pseudo(self):
        """Pseudo None refuse."""
        is_valid, error = validate_pseudo(None)
        assert is_valid is False

    def test_pseudo_too_short(self):
        """Pseudo trop court refuse."""
        is_valid, error = validate_pseudo("A")
        assert is_valid is False
        assert str(MIN_PSEUDO_LENGTH) in error

    def test_pseudo_too_long(self):
        """Pseudo trop long refuse."""
        long_pseudo = "A" * (MAX_PSEUDO_LENGTH + 1)
        is_valid, error = validate_pseudo(long_pseudo)
        assert is_valid is False
        assert str(MAX_PSEUDO_LENGTH) in error

    def test_pseudo_exact_min_length(self):
        """Pseudo longueur minimale accepte."""
        is_valid, error = validate_pseudo("A" * MIN_PSEUDO_LENGTH)
        assert is_valid is True

    def test_pseudo_exact_max_length(self):
        """Pseudo longueur maximale accepte."""
        is_valid, error = validate_pseudo("A" * MAX_PSEUDO_LENGTH)
        assert is_valid is True

    def test_pseudo_with_html_tags(self):
        """Pseudo avec balises HTML refuse."""
        is_valid, error = validate_pseudo("<script>alert(1)</script>")
        assert is_valid is False
        assert "non autorisés" in error.lower()

    def test_pseudo_with_quotes(self):
        """Pseudo avec guillemets refuse."""
        is_valid, error = validate_pseudo('Mon"Pseudo')
        assert is_valid is False

    def test_pseudo_with_sql_comment(self):
        """Pseudo avec commentaire SQL refuse."""
        is_valid, error = validate_pseudo("pseudo--comment")
        assert is_valid is False

    def test_pseudo_with_semicolon(self):
        """Pseudo avec point-virgule refuse."""
        is_valid, error = validate_pseudo("pseudo;DROP TABLE")
        assert is_valid is False


class TestValidateUserId:
    """Tests pour validate_user_id()"""

    def test_valid_user_id(self):
        """ID valide accepte."""
        is_valid, error = validate_user_id(123456789012345678)
        assert is_valid is True
        assert error is None

    def test_valid_user_id_19_digits(self):
        """ID 19 chiffres accepte."""
        is_valid, error = validate_user_id(1234567890123456789)
        assert is_valid is True

    def test_zero_user_id(self):
        """ID zero refuse."""
        is_valid, error = validate_user_id(0)
        assert is_valid is False
        assert "positif" in error.lower()

    def test_negative_user_id(self):
        """ID negatif refuse."""
        is_valid, error = validate_user_id(-123)
        assert is_valid is False
        assert "positif" in error.lower()

    def test_user_id_too_short(self):
        """ID trop court refuse."""
        is_valid, error = validate_user_id(12345)
        assert is_valid is False
        assert "valide" in error.lower()

    def test_user_id_too_long(self):
        """ID trop long refuse."""
        is_valid, error = validate_user_id(12345678901234567890)
        assert is_valid is False


class TestValidateUsername:
    """Tests pour validate_username()"""

    def test_valid_username(self):
        """Username valide accepte."""
        is_valid, error = validate_username("test_user")
        assert is_valid is True
        assert error is None

    def test_empty_username(self):
        """Username vide refuse."""
        is_valid, error = validate_username("")
        assert is_valid is False
        assert "vide" in error.lower()

    def test_none_username(self):
        """Username None refuse."""
        is_valid, error = validate_username(None)
        assert is_valid is False

    def test_username_too_long(self):
        """Username trop long refuse."""
        long_username = "A" * (MAX_USERNAME_LENGTH + 1)
        is_valid, error = validate_username(long_username)
        assert is_valid is False
        assert str(MAX_USERNAME_LENGTH) in error

    def test_username_with_dangerous_chars(self):
        """Username avec caracteres dangereux refuse."""
        is_valid, error = validate_username("user<script>")
        assert is_valid is False

    def test_username_with_backslash(self):
        """Username avec backslash refuse."""
        is_valid, error = validate_username("user\\name")
        assert is_valid is False


class TestValidateImageAttachment:
    """Tests pour validate_image_attachment()"""

    def test_valid_png(self):
        """Fichier PNG valide accepte."""
        is_valid, error = validate_image_attachment("image.png", 1024 * 1024)
        assert is_valid is True
        assert error is None

    def test_valid_jpg(self):
        """Fichier JPG valide accepte."""
        is_valid, error = validate_image_attachment("photo.jpg", 500000)
        assert is_valid is True

    def test_valid_jpeg(self):
        """Fichier JPEG valide accepte."""
        is_valid, error = validate_image_attachment("photo.jpeg", 500000)
        assert is_valid is True

    def test_valid_gif(self):
        """Fichier GIF valide accepte."""
        is_valid, error = validate_image_attachment("animation.gif", 2000000)
        assert is_valid is True

    def test_valid_webp(self):
        """Fichier WebP valide accepte."""
        is_valid, error = validate_image_attachment("image.webp", 1000000)
        assert is_valid is True

    def test_invalid_extension(self):
        """Extension non autorisee refuse."""
        is_valid, error = validate_image_attachment("virus.exe", 1024)
        assert is_valid is False
        assert "non autorisé" in error.lower()

    def test_pdf_rejected(self):
        """Fichier PDF refuse."""
        is_valid, error = validate_image_attachment("document.pdf", 1024)
        assert is_valid is False

    def test_file_too_large(self):
        """Fichier trop volumineux refuse."""
        is_valid, error = validate_image_attachment("huge.png", 11 * 1024 * 1024)
        assert is_valid is False
        assert "volumineux" in error.lower()

    def test_file_exactly_max_size(self):
        """Fichier taille maximale accepte."""
        is_valid, error = validate_image_attachment("image.png", 10 * 1024 * 1024)
        assert is_valid is True

    def test_empty_filename(self):
        """Nom de fichier vide refuse."""
        is_valid, error = validate_image_attachment("", 1024)
        assert is_valid is False
        assert "invalide" in error.lower()

    def test_custom_max_size(self):
        """Taille max personnalisee respectee."""
        # 5 MB max
        is_valid, error = validate_image_attachment("image.png", 6 * 1024 * 1024, max_size_mb=5)
        assert is_valid is False
        assert "5" in error

    def test_uppercase_extension(self):
        """Extension en majuscules acceptee."""
        is_valid, error = validate_image_attachment("IMAGE.PNG", 1024)
        assert is_valid is True

    def test_mixed_case_extension(self):
        """Extension casse mixte acceptee."""
        is_valid, error = validate_image_attachment("image.JpG", 1024)
        assert is_valid is True
