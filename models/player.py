"""
Modèle Player - Représente un joueur in-game lié à un membre Discord.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger

logger = get_logger("models.player")


@dataclass
class Player:
    """Représente un joueur in-game."""
    id: Optional[int]
    member_username: str
    team_id: Optional[int]
    team_name: Optional[str]
    player_name: str
    created_at: Optional[datetime] = None

    @classmethod
    async def create(cls, db_pool, member_username: str, player_name: str, team_id: int = None) -> 'Player':
        """Crée un nouveau joueur en base de données."""
        query = """
        INSERT INTO players (member_username, team_id, player_name)
        VALUES ($1, $2, $3)
        RETURNING id, created_at
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, member_username, team_id, player_name)
            logger.info(f"Joueur '{player_name}' créé pour {member_username}")
            return cls(
                id=row['id'],
                member_username=member_username,
                team_id=team_id,
                team_name=None,
                player_name=player_name,
                created_at=row['created_at']
            )

    @classmethod
    async def get_by_member(cls, db_pool, member_username: str) -> List['Player']:
        """Récupère tous les joueurs d'un membre."""
        query = """
        SELECT p.id, p.member_username, p.team_id, t.name as team_name,
               p.player_name, p.created_at
        FROM players p
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE p.member_username = $1
        ORDER BY t.name, p.player_name
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, member_username)
            return [cls(
                id=row['id'],
                member_username=row['member_username'],
                team_id=row['team_id'],
                team_name=row['team_name'],
                player_name=row['player_name'],
                created_at=row['created_at']
            ) for row in rows]

    @classmethod
    async def get_by_team(cls, db_pool, team_id: int) -> List['Player']:
        """Récupère tous les joueurs d'une team."""
        query = """
        SELECT p.id, p.member_username, p.team_id, t.name as team_name,
               p.player_name, p.created_at
        FROM players p
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE p.team_id = $1
        ORDER BY p.player_name
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, team_id)
            return [cls(
                id=row['id'],
                member_username=row['member_username'],
                team_id=row['team_id'],
                team_name=row['team_name'],
                player_name=row['player_name'],
                created_at=row['created_at']
            ) for row in rows]

    @classmethod
    async def find_by_name(cls, db_pool, player_name: str) -> Optional['Player']:
        """Trouve un joueur par son nom (recherche partielle)."""
        query = """
        SELECT p.id, p.member_username, p.team_id, t.name as team_name,
               p.player_name, p.created_at
        FROM players p
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE LOWER(p.player_name) LIKE LOWER($1)
        LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, f"%{player_name}%")
            if row:
                return cls(
                    id=row['id'],
                    member_username=row['member_username'],
                    team_id=row['team_id'],
                    team_name=row['team_name'],
                    player_name=row['player_name'],
                    created_at=row['created_at']
                )
            return None

    @classmethod
    async def delete(cls, db_pool, player_id: int) -> bool:
        """Supprime un joueur par son ID."""
        query = "DELETE FROM players WHERE id = $1"
        async with db_pool.acquire() as conn:
            result = await conn.execute(query, player_id)
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"Joueur ID {player_id} supprimé")
            return deleted

    @classmethod
    async def delete_by_name(cls, db_pool, member_username: str, player_name: str) -> bool:
        """Supprime un joueur par son nom pour un membre donné."""
        query = """
        DELETE FROM players
        WHERE member_username = $1 AND LOWER(player_name) = LOWER($2)
        """
        async with db_pool.acquire() as conn:
            result = await conn.execute(query, member_username, player_name)
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"Joueur '{player_name}' supprimé pour {member_username}")
            return deleted

    @classmethod
    async def delete_all_for_member(cls, db_pool, member_username: str) -> int:
        """Supprime tous les joueurs d'un membre. Retourne le nombre de joueurs supprimés."""
        query = "DELETE FROM players WHERE member_username = $1"
        async with db_pool.acquire() as conn:
            result = await conn.execute(query, member_username)
            # result format: "DELETE N"
            count = int(result.split()[-1]) if result.startswith("DELETE") else 0
            if count > 0:
                logger.info(f"{count} joueur(s) supprimé(s) pour {member_username}")
            return count


@dataclass
class Team:
    """Représente une team."""
    id: int
    name: str
    created_at: Optional[datetime] = None

    @classmethod
    async def get_all(cls, db_pool) -> List['Team']:
        """Récupère toutes les teams."""
        query = "SELECT id, name, created_at FROM teams ORDER BY name"
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [cls(id=row['id'], name=row['name'], created_at=row['created_at']) for row in rows]

    @classmethod
    async def get_by_name(cls, db_pool, name: str) -> Optional['Team']:
        """Récupère une team par son nom (recherche partielle, insensible à la casse)."""
        query = """
        SELECT id, name, created_at FROM teams
        WHERE LOWER(name) LIKE LOWER($1)
        LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, f"%{name}%")
            if row:
                return cls(id=row['id'], name=row['name'], created_at=row['created_at'])
            return None

    @classmethod
    async def get_by_id(cls, db_pool, team_id: int) -> Optional['Team']:
        """Récupère une team par son ID."""
        query = "SELECT id, name, created_at FROM teams WHERE id = $1"
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, team_id)
            if row:
                return cls(id=row['id'], name=row['name'], created_at=row['created_at'])
            return None

    @classmethod
    async def create(cls, db_pool, name: str) -> 'Team':
        """Crée une nouvelle team."""
        query = """
        INSERT INTO teams (name) VALUES ($1)
        RETURNING id, name, created_at
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, name)
            logger.info(f"Team '{name}' créée")
            return cls(id=row['id'], name=row['name'], created_at=row['created_at'])
