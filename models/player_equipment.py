"""
Modele PlayerEquipment - Equipements d'une capture Tennis Clash.

Stocke les 6 cartes equipees (Raquette, Grip, Chaussures, Poignet, Nutrition, Entrainement).
"""

from dataclasses import dataclass
from typing import Optional, List

from constants import EquipmentSlots
from utils.logger import get_logger

logger = get_logger("models.player_equipment")


@dataclass
class PlayerEquipment:
    """Un equipement d'une capture Tennis Clash.

    Attributs:
        id: Identifiant en base de donnees
        stats_id: ID de la capture (player_stats)
        slot: Numero du slot (1-6)
        card_name: Nom de la carte (Le marteau, Le koi...)
        card_level: Niveau de la carte (12, 13...)
    """
    id: Optional[int]
    stats_id: int
    slot: int
    card_name: Optional[str] = None
    card_level: Optional[int] = None

    @property
    def slot_name(self) -> str:
        """Retourne le nom du slot (Raquette, Grip...)."""
        return EquipmentSlots.get_name(self.slot)

    @classmethod
    async def create_many(cls, db_pool, stats_id: int,
                          equipments: List[dict]) -> List['PlayerEquipment']:
        """Cree plusieurs equipements pour une capture.

        Args:
            db_pool: Pool de connexions asyncpg
            stats_id: ID de la capture player_stats
            equipments: Liste de dicts avec slot, card_name, card_level

        Returns:
            Liste des PlayerEquipment crees
        """
        if not equipments:
            return []

        query = """
        INSERT INTO player_equipment (stats_id, slot, card_name, card_level)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """

        results = []
        async with db_pool.acquire() as conn:
            for eq in equipments:
                row = await conn.fetchrow(
                    query,
                    stats_id,
                    eq.get('slot'),
                    eq.get('card_name'),
                    eq.get('card_level')
                )
                results.append(cls(
                    id=row['id'],
                    stats_id=stats_id,
                    slot=eq.get('slot'),
                    card_name=eq.get('card_name'),
                    card_level=eq.get('card_level')
                ))

        logger.info(f"{len(results)} equipements enregistres pour stats_id={stats_id}")
        return results

    @classmethod
    async def get_by_stats_id(cls, db_pool, stats_id: int) -> List['PlayerEquipment']:
        """Recupere tous les equipements d'une capture.

        Args:
            db_pool: Pool de connexions asyncpg
            stats_id: ID de la capture

        Returns:
            Liste des equipements tries par slot
        """
        query = """
        SELECT id, stats_id, slot, card_name, card_level
        FROM player_equipment
        WHERE stats_id = $1
        ORDER BY slot
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, stats_id)
            return [cls(
                id=row['id'],
                stats_id=row['stats_id'],
                slot=row['slot'],
                card_name=row['card_name'],
                card_level=row['card_level']
            ) for row in rows]

    @classmethod
    async def delete_by_stats_id(cls, db_pool, stats_id: int) -> int:
        """Supprime tous les equipements d'une capture.

        Args:
            db_pool: Pool de connexions asyncpg
            stats_id: ID de la capture

        Returns:
            Nombre d'equipements supprimes
        """
        query = "DELETE FROM player_equipment WHERE stats_id = $1"
        async with db_pool.acquire() as conn:
            result = await conn.execute(query, stats_id)
            count = int(result.split()[-1]) if result.startswith("DELETE") else 0
            if count > 0:
                logger.info(f"{count} equipements supprimes pour stats_id={stats_id}")
            return count

    def to_string(self) -> str:
        """Formate l'equipement pour affichage."""
        if self.card_name and self.card_level:
            return f"{self.slot_name}: {self.card_name} (niv.{self.card_level})"
        elif self.card_name:
            return f"{self.slot_name}: {self.card_name}"
        elif self.card_level:
            return f"{self.slot_name}: ??? (niv.{self.card_level})"
        else:
            return f"{self.slot_name}: ???"
