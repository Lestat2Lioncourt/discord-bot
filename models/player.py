"""
Modèle Player - Représente un joueur in-game lié à un membre Discord.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from utils.logger import get_logger

logger = get_logger("models.player")


@dataclass
class Player:
    """Représente un joueur in-game lié à un membre Discord.

    Attributs:
        id: Identifiant en base de données
        member_username: Username Discord du propriétaire
        team_id: ID de l'équipe (1 ou 2)
        team_name: Nom de l'équipe (récupéré par JOIN)
        player_name: Nom du joueur in-game
        created_at: Date de création
    """
    id: Optional[int]
    member_username: str
    team_id: Optional[int]
    team_name: Optional[str]
    player_name: str
    created_at: Optional[datetime] = None

    @classmethod
    async def create(cls, db_pool, member_username: str, player_name: str,
                     team_id: Optional[int] = None, conn=None) -> 'Player':
        """Crée un nouveau joueur en base de données.

        Args:
            db_pool: Pool de connexions asyncpg
            member_username: Username du membre Discord
            player_name: Nom du joueur in-game
            team_id: ID de l'équipe (optionnel)
            conn: Connexion existante pour transaction (optionnel)

        Returns:
            Instance Player créée

        Raises:
            asyncpg.UniqueViolationError: Si le joueur existe déjà pour ce membre/team
        """
        query = """
        INSERT INTO players (member_username, team_id, player_name)
        VALUES ($1, $2, $3)
        RETURNING id, created_at
        """

        async def _execute(connection):
            row = await connection.fetchrow(query, member_username, team_id, player_name)
            logger.info(f"Joueur '{player_name}' créé pour {member_username}")
            return cls(
                id=row['id'],
                member_username=member_username,
                team_id=team_id,
                team_name=None,
                player_name=player_name,
                created_at=row['created_at']
            )

        if conn:
            return await _execute(conn)
        async with db_pool.acquire() as connection:
            return await _execute(connection)

    @classmethod
    async def get_by_member(cls, db_pool, member_username: str) -> List['Player']:
        """Récupère tous les joueurs d'un membre.

        Args:
            db_pool: Pool de connexions asyncpg
            member_username: Username du membre Discord

        Returns:
            Liste de Players triée par team puis par nom
        """
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
    async def get_by_id(cls, db_pool, player_id: int) -> Optional['Player']:
        """Récupère un joueur par son ID.

        Args:
            db_pool: Pool de connexions asyncpg
            player_id: ID du joueur

        Returns:
            Instance Player ou None si non trouvé
        """
        query = """
        SELECT p.id, p.member_username, p.team_id, t.name as team_name,
               p.player_name, p.created_at
        FROM players p
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE p.id = $1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, player_id)
            if not row:
                return None
            return cls(
                id=row['id'],
                member_username=row['member_username'],
                team_id=row['team_id'],
                team_name=row['team_name'],
                player_name=row['player_name'],
                created_at=row['created_at']
            )

    @classmethod
    async def get_by_members(cls, db_pool, usernames: List[str]) -> dict:
        """Récupère tous les joueurs pour plusieurs membres en une seule requête.

        Args:
            db_pool: Pool de connexion à la base de données
            usernames: Liste des noms d'utilisateurs

        Returns:
            Dictionnaire {username: [Player, ...]}
        """
        if not usernames:
            return {}

        query = """
        SELECT p.id, p.member_username, p.team_id, t.name as team_name,
               p.player_name, p.created_at
        FROM players p
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE p.member_username = ANY($1)
        ORDER BY p.member_username, t.name, p.player_name
        """
        result: dict[str, List['Player']] = {username: [] for username in usernames}
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, usernames)
            for row in rows:
                player = cls(
                    id=row['id'],
                    member_username=row['member_username'],
                    team_id=row['team_id'],
                    team_name=row['team_name'],
                    player_name=row['player_name'],
                    created_at=row['created_at']
                )
                result[row['member_username']].append(player)
        return result

    @classmethod
    async def get_by_team(cls, db_pool, team_id: int) -> List['Player']:
        """Récupère tous les joueurs d'une équipe.

        Args:
            db_pool: Pool de connexions asyncpg
            team_id: Identifiant de l'équipe

        Returns:
            Liste de Players triée par nom
        """
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
        """Trouve un joueur par son nom (recherche partielle, insensible à la casse).

        Args:
            db_pool: Pool de connexions asyncpg
            player_name: Nom ou partie du nom à chercher

        Returns:
            Premier Player correspondant ou None
        """
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
        """Supprime un joueur par son identifiant.

        Args:
            db_pool: Pool de connexions asyncpg
            player_id: Identifiant du joueur en base

        Returns:
            True si supprimé, False si non trouvé
        """
        query = "DELETE FROM players WHERE id = $1"
        async with db_pool.acquire() as conn:
            result = await conn.execute(query, player_id)
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"Joueur ID {player_id} supprimé")
            return deleted

    @classmethod
    async def delete_by_name(cls, db_pool, member_username: str, player_name: str) -> bool:
        """Supprime un joueur par son nom pour un membre donné.

        Args:
            db_pool: Pool de connexions asyncpg
            member_username: Username du membre Discord
            player_name: Nom du joueur (insensible à la casse)

        Returns:
            True si supprimé, False si non trouvé
        """
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
    async def delete_all_for_member(cls, db_pool, member_username: str, conn=None) -> int:
        """Supprime tous les joueurs d'un membre.

        Args:
            db_pool: Pool de connexions asyncpg
            member_username: Username du membre Discord
            conn: Connexion existante pour transaction (optionnel)

        Returns:
            Nombre de joueurs supprimés
        """
        query = "DELETE FROM players WHERE member_username = $1"

        async def _execute(connection):
            result = await connection.execute(query, member_username)
            count = int(result.split()[-1]) if result.startswith("DELETE") else 0
            if count > 0:
                logger.info(f"{count} joueur(s) supprimé(s) pour {member_username}")
            return count

        if conn:
            return await _execute(conn)
        async with db_pool.acquire() as connection:
            return await _execute(connection)

    @classmethod
    async def delete_by_team_for_member(cls, db_pool, member_username: str, team_id: int,
                                         conn=None) -> int:
        """Supprime les joueurs d'une équipe spécifique pour un membre.

        Args:
            db_pool: Pool de connexions asyncpg
            member_username: Username du membre Discord
            team_id: Identifiant de l'équipe
            conn: Connexion existante pour transaction (optionnel)

        Returns:
            Nombre de joueurs supprimés
        """
        query = "DELETE FROM players WHERE member_username = $1 AND team_id = $2"

        async def _execute(connection):
            result = await connection.execute(query, member_username, team_id)
            count = int(result.split()[-1]) if result.startswith("DELETE") else 0
            if count > 0:
                logger.info(f"{count} joueur(s) supprime(s) pour {member_username} (team {team_id})")
            return count

        if conn:
            return await _execute(conn)
        async with db_pool.acquire() as connection:
            return await _execute(connection)


@dataclass
class Team:
    """Représente une équipe (This Is PSG, This Is PSG 2).

    Attributs:
        id: Identifiant en base (1 ou 2)
        name: Nom de l'équipe
        created_at: Date de création
    """
    id: int
    name: str
    created_at: Optional[datetime] = None

    @classmethod
    async def get_all(cls, db_pool) -> List['Team']:
        """Récupère toutes les équipes triées par nom."""
        query = "SELECT id, name, created_at FROM teams ORDER BY name"
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [cls(id=row['id'], name=row['name'], created_at=row['created_at']) for row in rows]

    @classmethod
    async def get_by_name(cls, db_pool, name: str) -> Optional['Team']:
        """Récupère une équipe par son nom (recherche partielle).

        Args:
            db_pool: Pool de connexions asyncpg
            name: Nom ou partie du nom (insensible à la casse)

        Returns:
            Première Team correspondante ou None
        """
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
        """Récupère une équipe par son identifiant.

        Args:
            db_pool: Pool de connexions asyncpg
            team_id: Identifiant de l'équipe

        Returns:
            Instance Team ou None si non trouvée
        """
        query = "SELECT id, name, created_at FROM teams WHERE id = $1"
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, team_id)
            if row:
                return cls(id=row['id'], name=row['name'], created_at=row['created_at'])
            return None

    @classmethod
    async def create(cls, db_pool, name: str) -> 'Team':
        """Crée une nouvelle équipe.

        Args:
            db_pool: Pool de connexions asyncpg
            name: Nom de l'équipe

        Returns:
            Instance Team créée
        """
        query = """
        INSERT INTO teams (name) VALUES ($1)
        RETURNING id, name, created_at
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, name)
            logger.info(f"Team '{name}' créée")
            return cls(id=row['id'], name=row['name'], created_at=row['created_at'])
