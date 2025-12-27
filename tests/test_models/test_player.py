"""
Tests pour models/player.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from models.player import Player, Team


class TestPlayer:
    """Tests pour la classe Player."""

    def test_player_dataclass(self):
        """Verifie la creation d'un Player."""
        player = Player(
            id=1,
            member_username="test_user",
            team_id=1,
            team_name="Test Team",
            player_name="PlayerOne",
            created_at=datetime.now()
        )
        assert player.id == 1
        assert player.member_username == "test_user"
        assert player.team_id == 1
        assert player.team_name == "Test Team"
        assert player.player_name == "PlayerOne"

    def test_player_optional_fields(self):
        """Verifie les champs optionnels."""
        player = Player(
            id=None,
            member_username="test_user",
            team_id=None,
            team_name=None,
            player_name="PlayerOne"
        )
        assert player.id is None
        assert player.team_id is None
        assert player.team_name is None
        assert player.created_at is None


class TestPlayerCreate:
    """Tests pour Player.create()"""

    @pytest.fixture
    def mock_pool(self):
        """Mock du pool de connexion."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'created_at': datetime(2024, 1, 1, 12, 0, 0)
        })
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.mark.asyncio
    async def test_create_player(self, mock_pool):
        """Cree un joueur avec succes."""
        player = await Player.create(mock_pool, "test_user", "PlayerOne", team_id=1)

        assert player.id == 1
        assert player.member_username == "test_user"
        assert player.player_name == "PlayerOne"
        assert player.team_id == 1

    @pytest.mark.asyncio
    async def test_create_player_without_team(self, mock_pool):
        """Cree un joueur sans team."""
        player = await Player.create(mock_pool, "test_user", "PlayerOne")

        assert player.id == 1
        assert player.team_id is None


class TestPlayerGetByMember:
    """Tests pour Player.get_by_member()"""

    @pytest.fixture
    def mock_pool_with_players(self):
        """Mock avec des joueurs existants."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {
                'id': 1,
                'member_username': 'test_user',
                'team_id': 1,
                'team_name': 'Team A',
                'player_name': 'Player1',
                'created_at': datetime(2024, 1, 1)
            },
            {
                'id': 2,
                'member_username': 'test_user',
                'team_id': 2,
                'team_name': 'Team B',
                'player_name': 'Player2',
                'created_at': datetime(2024, 1, 2)
            }
        ])
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.fixture
    def mock_pool_empty(self):
        """Mock sans joueurs."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.mark.asyncio
    async def test_get_by_member_with_players(self, mock_pool_with_players):
        """Recupere les joueurs d'un membre."""
        players = await Player.get_by_member(mock_pool_with_players, "test_user")

        assert len(players) == 2
        assert players[0].player_name == "Player1"
        assert players[1].player_name == "Player2"

    @pytest.mark.asyncio
    async def test_get_by_member_empty(self, mock_pool_empty):
        """Retourne liste vide si aucun joueur."""
        players = await Player.get_by_member(mock_pool_empty, "unknown_user")

        assert len(players) == 0
        assert players == []


class TestPlayerGetByMembers:
    """Tests pour Player.get_by_members()"""

    @pytest.mark.asyncio
    async def test_get_by_members_empty_list(self):
        """Retourne dict vide si liste vide."""
        result = await Player.get_by_members(None, [])
        assert result == {}

    @pytest.fixture
    def mock_pool_multiple(self):
        """Mock avec plusieurs membres."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {'id': 1, 'member_username': 'user1', 'team_id': 1, 'team_name': 'Team', 'player_name': 'P1', 'created_at': None},
            {'id': 2, 'member_username': 'user1', 'team_id': 1, 'team_name': 'Team', 'player_name': 'P2', 'created_at': None},
            {'id': 3, 'member_username': 'user2', 'team_id': 1, 'team_name': 'Team', 'player_name': 'P3', 'created_at': None},
        ])
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.mark.asyncio
    async def test_get_by_members(self, mock_pool_multiple):
        """Recupere les joueurs de plusieurs membres."""
        result = await Player.get_by_members(mock_pool_multiple, ["user1", "user2", "user3"])

        assert len(result["user1"]) == 2
        assert len(result["user2"]) == 1
        assert len(result["user3"]) == 0  # Aucun joueur


class TestPlayerDelete:
    """Tests pour les methodes de suppression."""

    @pytest.fixture
    def mock_pool_delete_success(self):
        """Mock pour suppression reussie."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 1")
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.fixture
    def mock_pool_delete_none(self):
        """Mock pour suppression sans resultat."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 0")
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_pool_delete_success):
        """Suppression reussie."""
        result = await Player.delete(mock_pool_delete_success, 1)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_pool_delete_none):
        """Suppression sans resultat."""
        result = await Player.delete(mock_pool_delete_none, 999)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_by_name_success(self, mock_pool_delete_success):
        """Suppression par nom reussie."""
        result = await Player.delete_by_name(mock_pool_delete_success, "user", "Player1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_all_for_member(self, mock_pool_delete_success):
        """Supprime tous les joueurs d'un membre."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 3")
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        count = await Player.delete_all_for_member(pool, "test_user")
        assert count == 3

    @pytest.mark.asyncio
    async def test_delete_by_team_for_member(self, mock_pool_delete_success):
        """Supprime les joueurs d'une team pour un membre."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 2")
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        count = await Player.delete_by_team_for_member(pool, "test_user", 1)
        assert count == 2


class TestTeam:
    """Tests pour la classe Team."""

    def test_team_dataclass(self):
        """Verifie la creation d'une Team."""
        team = Team(id=1, name="This Is PSG")
        assert team.id == 1
        assert team.name == "This Is PSG"
        assert team.created_at is None

    @pytest.fixture
    def mock_pool_teams(self):
        """Mock avec des teams."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {'id': 1, 'name': 'This Is PSG', 'created_at': None},
            {'id': 2, 'name': 'This Is PSG 2', 'created_at': None}
        ])
        conn.fetchrow = AsyncMock(return_value={'id': 1, 'name': 'This Is PSG', 'created_at': None})
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))
        return pool

    @pytest.mark.asyncio
    async def test_get_all(self, mock_pool_teams):
        """Recupere toutes les teams."""
        teams = await Team.get_all(mock_pool_teams)
        assert len(teams) == 2
        assert teams[0].name == "This Is PSG"

    @pytest.mark.asyncio
    async def test_get_by_id(self, mock_pool_teams):
        """Recupere une team par ID."""
        team = await Team.get_by_id(mock_pool_teams, 1)
        assert team is not None
        assert team.name == "This Is PSG"

    @pytest.mark.asyncio
    async def test_get_by_name(self, mock_pool_teams):
        """Recupere une team par nom."""
        team = await Team.get_by_name(mock_pool_teams, "PSG")
        assert team is not None
        assert team.id == 1

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        """Retourne None si team non trouvee."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        team = await Team.get_by_id(pool, 999)
        assert team is None
