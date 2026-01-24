"""
Modele CaptureQueue - File d'attente des captures Tennis Clash.

Les images sont soumises via !capture, stockees en attente,
puis traitees par Claude Vision sur une machine locale.
L'utilisateur valide/refuse ensuite les resultats.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

from utils.logger import get_logger

logger = get_logger("models.capture_queue")


class CaptureStatus:
    """Statuts possibles d'une capture."""
    PENDING = "pending"          # En attente de traitement
    PROCESSING = "processing"    # En cours de traitement par Claude
    COMPLETED = "completed"      # Traite, en attente de validation utilisateur
    VALIDATED = "validated"      # Valide par l'utilisateur
    REJECTED = "rejected"        # Refuse par l'utilisateur
    FAILED = "failed"            # Erreur lors du traitement


@dataclass
class CaptureQueue:
    """Capture en file d'attente.

    Attributs:
        id: Identifiant en base de donnees
        discord_user_id: ID Discord de l'utilisateur
        discord_username: @username Discord
        discord_display_name: Pseudo affiche
        player_name: Nom du joueur TC (optionnel)
        image_data: Image en bytes
        image_filename: Nom du fichier original
        status: Statut de la capture
        submitted_at: Date de soumission
        processed_at: Date de traitement
        validated_at: Date de validation
        result_json: Resultat de l'analyse Claude
        error_message: Message d'erreur si echec
    """
    id: Optional[int]
    discord_user_id: int
    discord_username: str
    discord_display_name: Optional[str] = None
    player_name: Optional[str] = None
    image_data: Optional[bytes] = None
    image_filename: Optional[str] = None
    status: str = CaptureStatus.PENDING
    submitted_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    result_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    @classmethod
    async def create(cls, db_pool, discord_user_id: int, discord_username: str,
                     image_data: bytes, discord_display_name: Optional[str] = None,
                     player_name: Optional[str] = None,
                     image_filename: Optional[str] = None) -> 'CaptureQueue':
        """Cree une nouvelle capture en file d'attente.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_user_id: ID Discord de l'utilisateur
            discord_username: @username Discord
            image_data: Image en bytes
            discord_display_name: Pseudo affiche
            player_name: Nom du joueur TC
            image_filename: Nom du fichier original

        Returns:
            CaptureQueue: Instance creee
        """
        query = """
            INSERT INTO capture_queue
                (discord_user_id, discord_username, discord_display_name,
                 player_name, image_data, image_filename, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, submitted_at
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                discord_user_id,
                discord_username,
                discord_display_name,
                player_name,
                image_data,
                image_filename,
                CaptureStatus.PENDING
            )

        logger.info(f"Capture creee id={row['id']} pour {discord_username}")

        return cls(
            id=row['id'],
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            discord_display_name=discord_display_name,
            player_name=player_name,
            image_data=image_data,
            image_filename=image_filename,
            status=CaptureStatus.PENDING,
            submitted_at=row['submitted_at']
        )

    @classmethod
    async def get_by_id(cls, db_pool, capture_id: int) -> Optional['CaptureQueue']:
        """Recupere une capture par son ID.

        Args:
            db_pool: Pool de connexions asyncpg
            capture_id: ID de la capture

        Returns:
            CaptureQueue ou None si non trouvee
        """
        query = "SELECT * FROM capture_queue WHERE id = $1"
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, capture_id)

        if not row:
            return None

        return cls._from_row(row)

    @classmethod
    async def get_pending(cls, db_pool) -> List['CaptureQueue']:
        """Recupere toutes les captures en attente de traitement.

        Args:
            db_pool: Pool de connexions asyncpg

        Returns:
            Liste des captures pending
        """
        query = """
            SELECT * FROM capture_queue
            WHERE status = $1
            ORDER BY submitted_at ASC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, CaptureStatus.PENDING)

        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_completed_for_user(cls, db_pool, discord_user_id: int) -> List['CaptureQueue']:
        """Recupere les captures traitees en attente de validation pour un utilisateur.

        Args:
            db_pool: Pool de connexions asyncpg
            discord_user_id: ID Discord de l'utilisateur

        Returns:
            Liste des captures completed pour cet utilisateur
        """
        query = """
            SELECT * FROM capture_queue
            WHERE status = $1 AND discord_user_id = $2
            ORDER BY processed_at ASC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, CaptureStatus.COMPLETED, discord_user_id)

        return [cls._from_row(row) for row in rows]

    @classmethod
    async def count_pending(cls, db_pool) -> int:
        """Compte le nombre de captures en attente.

        Args:
            db_pool: Pool de connexions asyncpg

        Returns:
            Nombre de captures pending
        """
        query = "SELECT COUNT(*) FROM capture_queue WHERE status = $1"
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(query, CaptureStatus.PENDING)
        return count

    async def update_status(self, db_pool, new_status: str,
                            result_json: Optional[Dict] = None,
                            error_message: Optional[str] = None) -> None:
        """Met a jour le statut de la capture.

        Args:
            db_pool: Pool de connexions asyncpg
            new_status: Nouveau statut
            result_json: Resultat JSON (si completed)
            error_message: Message d'erreur (si failed)
        """
        # Determiner quelle date mettre a jour
        date_field = None
        if new_status == CaptureStatus.COMPLETED:
            date_field = "processed_at"
        elif new_status in (CaptureStatus.VALIDATED, CaptureStatus.REJECTED):
            date_field = "validated_at"

        if date_field:
            query = f"""
                UPDATE capture_queue
                SET status = $1, {date_field} = NOW(), result_json = $2, error_message = $3
                WHERE id = $4
            """
        else:
            query = """
                UPDATE capture_queue
                SET status = $1, result_json = $2, error_message = $3
                WHERE id = $4
            """

        async with db_pool.acquire() as conn:
            await conn.execute(
                query,
                new_status,
                json.dumps(result_json) if result_json else None,
                error_message,
                self.id
            )

        self.status = new_status
        if result_json:
            self.result_json = result_json
        if error_message:
            self.error_message = error_message

        logger.info(f"Capture {self.id} mise a jour: status={new_status}")

    async def delete(self, db_pool) -> None:
        """Supprime la capture de la file d'attente.

        Args:
            db_pool: Pool de connexions asyncpg
        """
        query = "DELETE FROM capture_queue WHERE id = $1"
        async with db_pool.acquire() as conn:
            await conn.execute(query, self.id)

        logger.info(f"Capture {self.id} supprimee")

    @classmethod
    def _from_row(cls, row) -> 'CaptureQueue':
        """Cree une instance depuis une row de base de donnees.

        Args:
            row: Row asyncpg

        Returns:
            Instance CaptureQueue
        """
        result_json = row['result_json']
        if isinstance(result_json, str):
            result_json = json.loads(result_json)

        return cls(
            id=row['id'],
            discord_user_id=row['discord_user_id'],
            discord_username=row['discord_username'],
            discord_display_name=row['discord_display_name'],
            player_name=row['player_name'],
            image_data=row['image_data'],
            image_filename=row['image_filename'],
            status=row['status'],
            submitted_at=row['submitted_at'],
            processed_at=row['processed_at'],
            validated_at=row['validated_at'],
            result_json=result_json,
            error_message=row['error_message']
        )
