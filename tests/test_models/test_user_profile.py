"""
Tests pour models/user_profile.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from models.user_profile import UserProfile


class TestUserProfileInit:
    """Tests pour l'initialisation de UserProfile."""

    def test_init_basic(self):
        """Initialisation basique."""
        conn = MagicMock()
        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user",
            discord_name="Test User"
        )

        assert profile.discord_id == 123456789012345678
        assert profile.username == "test_user"
        assert profile.discord_name == "Test User"
        assert profile.language == "FR"
        assert profile.charte_validated is False
        assert profile.approval_status == "pending"

    def test_init_with_last_connection(self):
        """Initialisation avec last_connection."""
        conn = MagicMock()
        now = datetime.now()
        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user",
            last_connection=now
        )

        assert profile.last_connection == now


class TestUserProfileStatus:
    """Tests pour les methodes de statut."""

    @pytest.fixture
    def profile(self):
        """Cree un profil de test."""
        conn = MagicMock()
        return UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

    def test_is_registration_complete_false(self, profile):
        """Inscription incomplete."""
        profile.charte_validated = False
        assert profile.is_registration_complete() is False

    def test_is_registration_complete_true(self, profile):
        """Inscription complete."""
        profile.charte_validated = True
        assert profile.is_registration_complete() is True

    def test_is_approved_false(self, profile):
        """Non approuve."""
        profile.approval_status = "pending"
        assert profile.is_approved() is False

    def test_is_approved_true(self, profile):
        """Approuve."""
        profile.approval_status = "approved"
        assert profile.is_approved() is True

    def test_is_pending_true(self, profile):
        """En attente."""
        profile.approval_status = "pending"
        assert profile.is_pending() is True

    def test_is_pending_false(self, profile):
        """Plus en attente."""
        profile.approval_status = "approved"
        assert profile.is_pending() is False

    def test_get_status_display_pending(self, profile):
        """Affichage statut en attente."""
        profile.charte_validated = False
        profile.approval_status = "pending"
        display = profile.get_status_display()
        assert "Non validée" in display
        assert "En attente" in display

    def test_get_status_display_approved(self, profile):
        """Affichage statut approuve."""
        profile.charte_validated = True
        profile.approval_status = "approved"
        display = profile.get_status_display()
        assert "Validée" in display
        assert "Approuvé" in display


class TestUserProfileValidateCharte:
    """Tests pour validate_charte()."""

    @pytest.mark.asyncio
    async def test_validate_charte(self):
        """Valide la charte."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        assert profile.charte_validated is False
        await profile.validate_charte()

        assert profile.charte_validated is True
        conn.execute.assert_called_once()


class TestUserProfileApproval:
    """Tests pour approve() et refuse()."""

    @pytest.mark.asyncio
    async def test_approve(self):
        """Approuve un membre."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        await profile.approve()

        assert profile.approval_status == "approved"
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_refuse(self):
        """Refuse un membre."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        await profile.refuse()

        assert profile.approval_status == "refused"
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset(self):
        """Reinitialise un profil."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )
        profile.charte_validated = True
        profile.approval_status = "approved"

        await profile.reset()

        assert profile.charte_validated is False
        assert profile.approval_status == "pending"


class TestUserProfileLocation:
    """Tests pour les methodes de localisation."""

    @pytest.mark.asyncio
    async def test_set_location(self):
        """Definit la localisation."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        await profile.set_location("Paris, France", 48.8566, 2.3522, "Ile-de-France, France")

        assert profile.localisation == "Paris, France"
        assert profile.latitude == 48.8566
        assert profile.longitude == 2.3522
        assert profile.location_display == "Ile-de-France, France"

    @pytest.mark.asyncio
    async def test_clear_location(self):
        """Supprime la localisation."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )
        profile.localisation = "Paris"
        profile.latitude = 48.8566
        profile.longitude = 2.3522

        await profile.clear_location()

        assert profile.localisation is None
        assert profile.latitude is None
        assert profile.longitude is None


class TestUserProfileLanguage:
    """Tests pour set_language()."""

    @pytest.mark.asyncio
    async def test_set_language_fr(self):
        """Definit langue FR."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        await profile.set_language("fr")

        assert profile.language == "FR"

    @pytest.mark.asyncio
    async def test_set_language_en(self):
        """Definit langue EN."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        await profile.set_language("en")

        assert profile.language == "EN"

    @pytest.mark.asyncio
    async def test_set_language_invalid_fallback_fr(self):
        """Langue invalide -> FR par defaut."""
        conn = AsyncMock()
        conn.execute = AsyncMock()

        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user"
        )

        await profile.set_language("de")

        assert profile.language == "FR"


class TestUserProfileGetByDiscordId:
    """Tests pour get_by_discord_id()."""

    @pytest.mark.asyncio
    async def test_get_by_discord_id_found(self):
        """Trouve un profil par discord_id."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            'discord_id': 123456789012345678,
            'username': 'test_user',
            'discord_name': 'Test User',
            'last_connection': datetime.now(),
            'charte_validated': True,
            'approval_status': 'approved',
            'language': 'EN'
        })

        profile = await UserProfile.get_by_discord_id(conn, 123456789012345678)

        assert profile is not None
        assert profile.username == 'test_user'
        assert profile.charte_validated is True
        assert profile.language == 'EN'

    @pytest.mark.asyncio
    async def test_get_by_discord_id_not_found(self):
        """Profil non trouve."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        profile = await UserProfile.get_by_discord_id(conn, 999999999999999999)

        assert profile is None


class TestUserProfileGetByUsername:
    """Tests pour get_by_username()."""

    @pytest.mark.asyncio
    async def test_get_by_username_found(self):
        """Trouve un profil par username."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            'discord_id': 123456789012345678,
            'username': 'test_user',
            'discord_name': 'Test User',
            'last_connection': None,
            'charte_validated': False,
            'approval_status': 'pending',
            'language': 'FR'
        })

        profile = await UserProfile.get_by_username(conn, 'test_user')

        assert profile is not None
        assert profile.discord_id == 123456789012345678

    @pytest.mark.asyncio
    async def test_get_by_username_case_insensitive(self):
        """Recherche insensible a la casse."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            'discord_id': 123456789012345678,
            'username': 'Test_User',
            'discord_name': 'Test User',
            'last_connection': None,
            'charte_validated': False,
            'approval_status': 'pending',
            'language': 'FR'
        })

        profile = await UserProfile.get_by_username(conn, 'TEST_USER')

        assert profile is not None


class TestUserProfileStr:
    """Tests pour __str__()."""

    def test_str_representation(self):
        """Representation string du profil."""
        conn = MagicMock()
        profile = UserProfile(
            discord_id=123456789012345678,
            db_connection=conn,
            username="test_user",
            discord_name="Test User"
        )
        profile.charte_validated = True
        profile.approval_status = "approved"

        string = str(profile)

        assert "test_user" in string
        assert "123456789012345678" in string
        assert "Test User" in string
        assert "approved" in string
