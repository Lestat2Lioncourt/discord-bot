"""
Tests pour utils/i18n.py
"""

import pytest
from unittest.mock import patch

# Importer apres avoir mock les traductions
import utils.i18n as i18n_module


class TestGetText:
    """Tests pour get_text() et t()"""

    @pytest.fixture(autouse=True)
    def setup_translations(self):
        """Setup des traductions de test."""
        # Sauvegarder les vraies traductions
        original_translations = i18n_module.TRANSLATIONS.copy()

        # Injecter des traductions de test (cles en majuscules)
        i18n_module.TRANSLATIONS = {
            "FR": {
                "welcome": {
                    "title": "Bienvenue",
                    "message": "Bonjour {name} !",
                    "nested": {
                        "deep": "Profond"
                    }
                },
                "simple": "Texte simple"
            },
            "EN": {
                "welcome": {
                    "title": "Welcome",
                    "message": "Hello {name}!",
                    "nested": {
                        "deep": "Deep"
                    }
                },
                "simple": "Simple text"
            }
        }

        yield

        # Restaurer les vraies traductions
        i18n_module.TRANSLATIONS = original_translations

    def test_simple_key_fr(self):
        """Recupere une cle simple en FR."""
        result = i18n_module.t("simple", "fr")
        assert result == "Texte simple"

    def test_simple_key_en(self):
        """Recupere une cle simple en EN."""
        result = i18n_module.t("simple", "en")
        assert result == "Simple text"

    def test_nested_key(self):
        """Recupere une cle imbriquee."""
        result = i18n_module.t("welcome.title", "fr")
        assert result == "Bienvenue"

    def test_deeply_nested_key(self):
        """Recupere une cle profondement imbriquee."""
        result = i18n_module.t("welcome.nested.deep", "fr")
        assert result == "Profond"

    def test_variable_substitution(self):
        """Substitue les variables dans le texte."""
        result = i18n_module.t("welcome.message", "fr", name="Alice")
        assert result == "Bonjour Alice !"

    def test_variable_substitution_en(self):
        """Substitue les variables en anglais."""
        result = i18n_module.t("welcome.message", "en", name="Bob")
        assert result == "Hello Bob!"

    def test_default_language_fr(self):
        """Utilise FR par defaut si langue non specifiee."""
        result = i18n_module.t("simple")
        assert result == "Texte simple"

    def test_uppercase_language(self):
        """Accepte la langue en majuscules."""
        result = i18n_module.t("simple", "FR")
        assert result == "Texte simple"

    def test_mixed_case_language(self):
        """Accepte la langue en casse mixte."""
        result = i18n_module.t("simple", "Fr")
        assert result == "Texte simple"

    def test_unknown_language_fallback(self):
        """Fallback vers FR si langue inconnue."""
        result = i18n_module.t("simple", "de")  # Allemand non supporte
        assert result == "Texte simple"

    def test_missing_key_returns_key(self):
        """Retourne la cle si traduction manquante."""
        result = i18n_module.t("unknown.key", "fr")
        assert result == "unknown.key"

    def test_missing_nested_key_returns_key(self):
        """Retourne la cle si partie du chemin manquante."""
        result = i18n_module.t("welcome.unknown", "fr")
        assert result == "welcome.unknown"

    def test_none_language_uses_default(self):
        """Utilise la langue par defaut si None."""
        result = i18n_module.t("simple", None)
        assert result == "Texte simple"


class TestTranslator:
    """Tests pour la classe Translator."""

    @pytest.fixture(autouse=True)
    def setup_translations(self):
        """Setup des traductions de test."""
        original_translations = i18n_module.TRANSLATIONS.copy()
        i18n_module.TRANSLATIONS = {
            "FR": {"hello": "Bonjour", "name": "Nom: {value}"},
            "EN": {"hello": "Hello", "name": "Name: {value}"}
        }
        yield
        i18n_module.TRANSLATIONS = original_translations

    def test_translator_default_language(self):
        """Translator utilise FR par defaut."""
        tr = i18n_module.Translator()
        assert tr("hello") == "Bonjour"

    def test_translator_custom_language(self):
        """Translator avec langue personnalisee."""
        tr = i18n_module.Translator("en")
        assert tr("hello") == "Hello"

    def test_translator_with_variables(self):
        """Translator avec substitution de variables."""
        tr = i18n_module.Translator("en")
        assert tr("name", value="Test") == "Name: Test"

    def test_translator_set_lang(self):
        """Changer la langue du Translator."""
        tr = i18n_module.Translator("fr")
        assert tr("hello") == "Bonjour"

        tr.set_lang("en")
        assert tr("hello") == "Hello"

    def test_translator_set_lang_invalid(self):
        """set_lang ignore les langues non supportees."""
        tr = i18n_module.Translator("FR")
        tr.set_lang("de")  # Non supporte
        assert tr.lang == "FR"  # Reste en FR


class TestLoadTranslations:
    """Tests pour load_translations()."""

    def test_supported_languages(self):
        """Verifie les langues supportees."""
        assert "FR" in i18n_module.SUPPORTED_LANGUAGES
        assert "EN" in i18n_module.SUPPORTED_LANGUAGES

    def test_default_language(self):
        """Verifie la langue par defaut."""
        assert i18n_module.DEFAULT_LANGUAGE == "FR"
