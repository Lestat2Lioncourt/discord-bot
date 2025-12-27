"""
Tests pour models/schemas.py
"""

import pytest
from pydantic import ValidationError

from models.schemas import (
    PlayerCreate,
    LocationInput,
    LocationUpdate,
    UserIdInput,
    LanguageInput,
    ApprovalAction,
    MIN_PSEUDO_LENGTH,
    MAX_PSEUDO_LENGTH,
    MAX_USERNAME_LENGTH,
)


class TestPlayerCreate:
    """Tests pour le schema PlayerCreate."""

    def test_valid_player(self):
        """Joueur valide accepte."""
        player = PlayerCreate(
            player_name="MonJoueur",
            team_id=1,
            member_username="user123"
        )
        assert player.player_name == "MonJoueur"
        assert player.team_id == 1
        assert player.member_username == "user123"

    def test_strip_whitespace(self):
        """Espaces retires automatiquement."""
        player = PlayerCreate(
            player_name="  MonJoueur  ",
            team_id=1,
            member_username="  user123  "
        )
        assert player.player_name == "MonJoueur"
        assert player.member_username == "user123"

    def test_empty_player_name_rejected(self):
        """Nom vide refuse."""
        with pytest.raises(ValidationError) as exc:
            PlayerCreate(
                player_name="",
                team_id=1,
                member_username="user"
            )
        assert "vide" in str(exc.value).lower()

    def test_player_name_too_short(self):
        """Nom trop court refuse."""
        with pytest.raises(ValidationError) as exc:
            PlayerCreate(
                player_name="A",
                team_id=1,
                member_username="user"
            )
        assert str(MIN_PSEUDO_LENGTH) in str(exc.value)

    def test_player_name_too_long(self):
        """Nom trop long refuse."""
        long_name = "A" * (MAX_PSEUDO_LENGTH + 1)
        with pytest.raises(ValidationError) as exc:
            PlayerCreate(
                player_name=long_name,
                team_id=1,
                member_username="user"
            )
        assert str(MAX_PSEUDO_LENGTH) in str(exc.value)

    def test_player_name_exact_limits(self):
        """Noms aux limites exactes acceptes."""
        # Limite min
        player_min = PlayerCreate(
            player_name="A" * MIN_PSEUDO_LENGTH,
            team_id=1,
            member_username="user"
        )
        assert len(player_min.player_name) == MIN_PSEUDO_LENGTH

        # Limite max
        player_max = PlayerCreate(
            player_name="A" * MAX_PSEUDO_LENGTH,
            team_id=1,
            member_username="user"
        )
        assert len(player_max.player_name) == MAX_PSEUDO_LENGTH

    def test_html_tags_rejected(self):
        """Balises HTML refusees."""
        with pytest.raises(ValidationError) as exc:
            PlayerCreate(
                player_name="<script>alert(1)</script>",
                team_id=1,
                member_username="user"
            )
        assert "non autorises" in str(exc.value).lower()

    def test_quotes_rejected(self):
        """Guillemets refuses."""
        with pytest.raises(ValidationError):
            PlayerCreate(
                player_name='Player"Name',
                team_id=1,
                member_username="user"
            )

    def test_sql_comment_rejected(self):
        """Commentaires SQL refuses."""
        with pytest.raises(ValidationError):
            PlayerCreate(
                player_name="player--comment",
                team_id=1,
                member_username="user"
            )

    def test_semicolon_rejected(self):
        """Points-virgules refuses."""
        with pytest.raises(ValidationError):
            PlayerCreate(
                player_name="player;DROP TABLE",
                team_id=1,
                member_username="user"
            )

    def test_team_id_1_valid(self):
        """Team ID 1 valide."""
        player = PlayerCreate(player_name="Test", team_id=1, member_username="user")
        assert player.team_id == 1

    def test_team_id_2_valid(self):
        """Team ID 2 valide."""
        player = PlayerCreate(player_name="Test", team_id=2, member_username="user")
        assert player.team_id == 2

    def test_team_id_3_invalid(self):
        """Team ID 3 refuse."""
        with pytest.raises(ValidationError) as exc:
            PlayerCreate(player_name="Test", team_id=3, member_username="user")
        assert "1 ou 2" in str(exc.value)

    def test_empty_member_username_rejected(self):
        """Username vide refuse."""
        with pytest.raises(ValidationError):
            PlayerCreate(player_name="Test", team_id=1, member_username="")


class TestLocationInput:
    """Tests pour le schema LocationInput."""

    def test_valid_location(self):
        """Localisation valide acceptee."""
        loc = LocationInput(query="Paris, France")
        assert loc.query == "Paris, France"

    def test_strip_whitespace(self):
        """Espaces retires."""
        loc = LocationInput(query="  Paris  ")
        assert loc.query == "Paris"

    def test_empty_location_rejected(self):
        """Localisation vide refusee."""
        with pytest.raises(ValidationError):
            LocationInput(query="")

    def test_location_too_long(self):
        """Localisation trop longue refusee."""
        with pytest.raises(ValidationError) as exc:
            LocationInput(query="A" * 201)
        assert "200" in str(exc.value)

    def test_html_in_location_rejected(self):
        """HTML dans localisation refuse."""
        with pytest.raises(ValidationError):
            LocationInput(query="<script>Paris</script>")


class TestLocationUpdate:
    """Tests pour le schema LocationUpdate."""

    def test_valid_update(self):
        """Mise a jour valide."""
        loc = LocationUpdate(
            localisation="Paris, France",
            latitude=48.8566,
            longitude=2.3522,
            location_display="Ile-de-France"
        )
        assert loc.latitude == 48.8566
        assert loc.longitude == 2.3522

    def test_latitude_out_of_range_low(self):
        """Latitude trop basse refusee."""
        with pytest.raises(ValidationError) as exc:
            LocationUpdate(
                localisation="Test",
                latitude=-91,
                longitude=0
            )
        assert "-90" in str(exc.value)

    def test_latitude_out_of_range_high(self):
        """Latitude trop haute refusee."""
        with pytest.raises(ValidationError):
            LocationUpdate(
                localisation="Test",
                latitude=91,
                longitude=0
            )

    def test_longitude_out_of_range(self):
        """Longitude hors limites refusee."""
        with pytest.raises(ValidationError):
            LocationUpdate(
                localisation="Test",
                latitude=0,
                longitude=181
            )

    def test_extreme_valid_coordinates(self):
        """Coordonnees extremes valides."""
        loc = LocationUpdate(
            localisation="Test",
            latitude=-90,
            longitude=-180
        )
        assert loc.latitude == -90
        assert loc.longitude == -180


class TestUserIdInput:
    """Tests pour le schema UserIdInput."""

    def test_valid_discord_id(self):
        """ID Discord valide accepte."""
        user = UserIdInput(discord_id=123456789012345678)
        assert user.discord_id == 123456789012345678

    def test_19_digit_id_valid(self):
        """ID 19 chiffres valide."""
        user = UserIdInput(discord_id=1234567890123456789)
        assert user.discord_id == 1234567890123456789

    def test_negative_id_rejected(self):
        """ID negatif refuse."""
        with pytest.raises(ValidationError) as exc:
            UserIdInput(discord_id=-123)
        assert "positif" in str(exc.value).lower()

    def test_zero_id_rejected(self):
        """ID zero refuse."""
        with pytest.raises(ValidationError):
            UserIdInput(discord_id=0)

    def test_id_too_short_rejected(self):
        """ID trop court refuse."""
        with pytest.raises(ValidationError) as exc:
            UserIdInput(discord_id=12345)
        assert "17-19" in str(exc.value)

    def test_id_too_long_rejected(self):
        """ID trop long refuse."""
        with pytest.raises(ValidationError):
            UserIdInput(discord_id=12345678901234567890)


class TestLanguageInput:
    """Tests pour le schema LanguageInput."""

    def test_fr_lowercase(self):
        """FR minuscule accepte et normalise."""
        lang = LanguageInput(language="fr")
        assert lang.language == "FR"

    def test_en_lowercase(self):
        """EN minuscule accepte et normalise."""
        lang = LanguageInput(language="en")
        assert lang.language == "EN"

    def test_fr_uppercase(self):
        """FR majuscule accepte."""
        lang = LanguageInput(language="FR")
        assert lang.language == "FR"

    def test_mixed_case(self):
        """Casse mixte acceptee."""
        lang = LanguageInput(language="Fr")
        assert lang.language == "FR"

    def test_with_whitespace(self):
        """Espaces geres."""
        lang = LanguageInput(language=" en ")
        assert lang.language == "EN"

    def test_invalid_language(self):
        """Langue invalide refusee."""
        with pytest.raises(ValidationError) as exc:
            LanguageInput(language="de")
        assert "FR ou EN" in str(exc.value)

    def test_empty_language(self):
        """Langue vide refusee."""
        with pytest.raises(ValidationError):
            LanguageInput(language="")


class TestApprovalAction:
    """Tests pour le schema ApprovalAction."""

    def test_valid_approve(self):
        """Action approve valide."""
        action = ApprovalAction(
            target_username="user123",
            action="approve"
        )
        assert action.action == "approve"
        assert action.reason is None

    def test_valid_refuse_with_reason(self):
        """Action refuse avec raison valide."""
        action = ApprovalAction(
            target_username="user123",
            action="refuse",
            reason="Compte inactif"
        )
        assert action.action == "refuse"
        assert action.reason == "Compte inactif"

    def test_invalid_action(self):
        """Action invalide refusee."""
        with pytest.raises(ValidationError) as exc:
            ApprovalAction(
                target_username="user123",
                action="ban"
            )
        assert "'approve' ou 'refuse'" in str(exc.value)

    def test_empty_target_rejected(self):
        """Cible vide refusee."""
        with pytest.raises(ValidationError):
            ApprovalAction(
                target_username="",
                action="approve"
            )

    def test_reason_too_long(self):
        """Raison trop longue refusee."""
        with pytest.raises(ValidationError) as exc:
            ApprovalAction(
                target_username="user",
                action="refuse",
                reason="A" * 501
            )
        assert "500" in str(exc.value)

    def test_reason_with_dangerous_chars(self):
        """Raison avec caracteres dangereux refusee."""
        with pytest.raises(ValidationError):
            ApprovalAction(
                target_username="user",
                action="refuse",
                reason="<script>bad</script>"
            )
