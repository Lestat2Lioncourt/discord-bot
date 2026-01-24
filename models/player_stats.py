"""
Modele PlayerStats - Statistiques de joueurs Tennis Clash.

Stocke les captures d'ecran analysees par OCR pour le suivi
de l'evolution des joueurs.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from utils.logger import get_logger

logger = get_logger("models.player_stats")


@dataclass
class PlayerStats:
    """Statistiques d'un personnage Tennis Clash a un instant T.

    Attributs:
        id: Identifiant en base de donnees
        discord_id: ID Discord du membre proprietaire
        player_id: ID du joueur in-game (table players)
        character_name: Nom du personnage (Mei-Li, Ingrid, etc.)
        points: Trophees
        global_power: Puissance globale
        agility: Agilite
        endurance: Endurance
        serve: Service
        volley: Volee
        forehand: Coup droit
        backhand: Revers
        build_type: Type de gameplay (Service-Volee, etc.)
        comment: Commentaire libre
        captured_at: Date de capture
    """
    id: Optional[int]
    discord_id: int
    player_id: Optional[int]
    character_name: str
    points: Optional[int] = None
    global_power: Optional[int] = None
    agility: Optional[int] = None
    endurance: Optional[int] = None
    serve: Optional[int] = None
    volley: Optional[int] = None
    forehand: Optional[int] = None
    backhand: Optional[int] = None
    build_type: Optional[str] = None
    comment: Optional[str] = None
    captured_at: Optional[datetime] = None

    @classmethod
    async def create(cls, db_pool, discord_id: int, player_id: Optional[int],
                     character_name: str, points: Optional[int] = None,
                     global_power: Optional[int] = None, agility: Optional[int] = None,
                     endurance: Optional[int] = None, serve: Optional[int] = None,
                     volley: Optional[int] = None, forehand: Optional[int] = None,
                     backhand: Optional[int] = None, build_type: Optional[str] = None,
                     comment: Optional[str] = None) -> 'PlayerStats':
        """Cree une nouvelle entree de statistiques.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_id: ID Discord du membre
            player_id: ID du joueur in-game (optionnel)
            character_name: Nom du personnage
            points: Trophees
            global_power: Puissance globale
            agility: Agilite
            endurance: Endurance
            serve: Service
            volley: Volee
            forehand: Coup droit
            backhand: Revers
            build_type: Type de gameplay
            comment: Commentaire libre

        Returns:
            Instance PlayerStats creee
        """
        query = """
        INSERT INTO player_stats (
            discord_id, player_id, character_name, points, global_power,
            agility, endurance, serve, volley, forehand, backhand,
            build_type, comment
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING id, captured_at
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query, discord_id, player_id, character_name, points,
                global_power, agility, endurance, serve, volley,
                forehand, backhand, build_type, comment
            )
            logger.info(f"Stats enregistrees pour {character_name} (discord_id={discord_id})")
            return cls(
                id=row['id'],
                discord_id=discord_id,
                player_id=player_id,
                character_name=character_name,
                points=points,
                global_power=global_power,
                agility=agility,
                endurance=endurance,
                serve=serve,
                volley=volley,
                forehand=forehand,
                backhand=backhand,
                build_type=build_type,
                comment=comment,
                captured_at=row['captured_at']
            )

    @classmethod
    async def get_by_discord_id(cls, db_pool, discord_id: int,
                                 limit: int = 50) -> List['PlayerStats']:
        """Recupere toutes les stats d'un membre Discord.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_id: ID Discord du membre
            limit: Nombre max de resultats

        Returns:
            Liste de PlayerStats triee par date decroissante
        """
        query = """
        SELECT id, discord_id, player_id, character_name, points, global_power,
               agility, endurance, serve, volley, forehand, backhand,
               build_type, comment, captured_at
        FROM player_stats
        WHERE discord_id = $1
        ORDER BY captured_at DESC
        LIMIT $2
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, discord_id, limit)
            return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_by_character(cls, db_pool, discord_id: int,
                                character_name: str) -> List['PlayerStats']:
        """Recupere l'historique d'un personnage pour un membre.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_id: ID Discord du membre
            character_name: Nom du personnage (recherche insensible a la casse)

        Returns:
            Liste de PlayerStats triee par date decroissante
        """
        query = """
        SELECT id, discord_id, player_id, character_name, points, global_power,
               agility, endurance, serve, volley, forehand, backhand,
               build_type, comment, captured_at
        FROM player_stats
        WHERE discord_id = $1 AND LOWER(character_name) = LOWER($2)
        ORDER BY captured_at DESC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, discord_id, character_name)
            return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_all_for_character(cls, db_pool, character_name: str) -> List['PlayerStats']:
        """Recupere toutes les stats d'un personnage (tous joueurs confondus).

        Utile pour comparer les builds d'un meme personnage entre joueurs.

        Args:
            db_pool: Pool de connexions asyncpg
            character_name: Nom du personnage

        Returns:
            Liste de PlayerStats triee par date decroissante
        """
        query = """
        SELECT id, discord_id, player_id, character_name, points, global_power,
               agility, endurance, serve, volley, forehand, backhand,
               build_type, comment, captured_at
        FROM player_stats
        WHERE LOWER(character_name) = LOWER($1)
        ORDER BY captured_at DESC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, character_name)
            return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_summary_by_character(cls, db_pool) -> List[dict]:
        """Recupere un resume des captures par personnage.

        Returns:
            Liste de dicts avec character_name, capture_count, player_count
            triee par nombre de captures decroissant
        """
        query = """
        SELECT
            character_name,
            COUNT(*) as capture_count,
            COUNT(DISTINCT player_id) as player_count
        FROM player_stats
        GROUP BY character_name
        ORDER BY capture_count DESC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [
                {
                    'character_name': row['character_name'],
                    'capture_count': row['capture_count'],
                    'player_count': row['player_count']
                }
                for row in rows
            ]

    @classmethod
    async def get_total_count(cls, db_pool) -> int:
        """Compte le nombre total de captures."""
        query = "SELECT COUNT(*) FROM player_stats"
        async with db_pool.acquire() as conn:
            return await conn.fetchval(query)

    @classmethod
    async def get_latest_by_player(cls, db_pool, player_id: int) -> Optional['PlayerStats']:
        """Recupere les dernieres stats d'un joueur in-game.

        Args:
            db_pool: Pool de connexions asyncpg
            player_id: ID du joueur in-game

        Returns:
            Dernieres PlayerStats ou None
        """
        query = """
        SELECT id, discord_id, player_id, character_name, points, global_power,
               agility, endurance, serve, volley, forehand, backhand,
               build_type, comment, captured_at
        FROM player_stats
        WHERE player_id = $1
        ORDER BY captured_at DESC
        LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, player_id)
            return cls._from_row(row) if row else None

    @classmethod
    async def get_latest_for_build(cls, db_pool, player_id: int,
                                    character_name: str, build_type: str) -> Optional['PlayerStats']:
        """Recupere les dernieres stats pour un joueur/personnage/build.

        Args:
            db_pool: Pool de connexions asyncpg
            player_id: ID du joueur in-game
            character_name: Nom du personnage
            build_type: Type de build

        Returns:
            Dernieres PlayerStats ou None
        """
        query = """
        SELECT id, discord_id, player_id, character_name, points, global_power,
               agility, endurance, serve, volley, forehand, backhand,
               build_type, comment, captured_at
        FROM player_stats
        WHERE player_id = $1
          AND LOWER(character_name) = LOWER($2)
          AND build_type = $3
        ORDER BY captured_at DESC
        LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, player_id, character_name, build_type)
            return cls._from_row(row) if row else None

    def is_same_as(self, other: 'PlayerStats') -> bool:
        """Compare les valeurs de stats avec une autre instance.

        Compare points, global_power et les 6 stats principales.

        Args:
            other: Autre instance PlayerStats a comparer

        Returns:
            True si les valeurs sont identiques
        """
        if not other:
            return False

        return (
            self.points == other.points and
            self.global_power == other.global_power and
            self.agility == other.agility and
            self.endurance == other.endurance and
            self.serve == other.serve and
            self.volley == other.volley and
            self.forehand == other.forehand and
            self.backhand == other.backhand
        )

    @classmethod
    async def delete(cls, db_pool, stats_id: int, discord_id: int) -> bool:
        """Supprime une entree de stats (verification du proprietaire).

        Args:
            db_pool: Pool de connexions asyncpg
            stats_id: ID de l'entree a supprimer
            discord_id: ID Discord du demandeur (verification)

        Returns:
            True si supprime, False sinon
        """
        query = "DELETE FROM player_stats WHERE id = $1 AND discord_id = $2"
        async with db_pool.acquire() as conn:
            result = await conn.execute(query, stats_id, discord_id)
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"Stats ID {stats_id} supprimees")
            return deleted

    @classmethod
    def _from_row(cls, row) -> 'PlayerStats':
        """Construit une instance depuis une ligne de base de donnees."""
        return cls(
            id=row['id'],
            discord_id=row['discord_id'],
            player_id=row['player_id'],
            character_name=row['character_name'],
            points=row['points'],
            global_power=row['global_power'],
            agility=row['agility'],
            endurance=row['endurance'],
            serve=row['serve'],
            volley=row['volley'],
            forehand=row['forehand'],
            backhand=row['backhand'],
            build_type=row['build_type'],
            comment=row['comment'],
            captured_at=row['captured_at']
        )

    def to_embed_fields(self) -> dict:
        """Retourne les stats formatees pour un embed Discord."""
        return {
            "Personnage": self.character_name,
            "Points": str(self.points) if self.points else "-",
            "Puissance": str(self.global_power) if self.global_power else "-",
            "Agilite": str(self.agility) if self.agility else "-",
            "Endurance": str(self.endurance) if self.endurance else "-",
            "Service": str(self.serve) if self.serve else "-",
            "Volee": str(self.volley) if self.volley else "-",
            "Coup Droit": str(self.forehand) if self.forehand else "-",
            "Revers": str(self.backhand) if self.backhand else "-",
            "Build": self.build_type or "-",
        }
