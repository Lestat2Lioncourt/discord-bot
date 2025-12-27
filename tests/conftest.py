"""
Fixtures pytest pour les tests du bot Discord.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

# Configurer les variables d'environnement AVANT d'importer les modules
os.environ.setdefault("DISCORD_TOKEN", "test_token")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test_db")
os.environ.setdefault("DB_USER", "test_user")
os.environ.setdefault("DB_PASSWORD", "test_password")


@pytest.fixture
def mock_db_pool():
    """Mock du pool de connexion asyncpg."""
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock())
    return pool


@pytest.fixture
def mock_bot(mock_db_pool):
    """Mock du bot Discord."""
    bot = MagicMock()
    bot.db_pool = mock_db_pool
    bot.guilds = []
    return bot


@pytest.fixture
def mock_member():
    """Mock d'un membre Discord."""
    member = MagicMock()
    member.id = 123456789012345678
    member.name = "test_user"
    member.display_name = "Test User"
    member.roles = []
    return member


@pytest.fixture
def mock_guild():
    """Mock d'un serveur Discord."""
    guild = MagicMock()
    guild.id = 987654321098765432
    guild.name = "Test Server"
    guild.members = []
    guild.get_member = MagicMock(return_value=None)
    return guild


@pytest.fixture
def mock_db_connection():
    """Mock d'une connexion DB."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    return conn
