"""
Modèle MemberApproval - Gestion des approbations par les sages.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger

logger = get_logger("models.member_approval")


class ApprovalStatus(Enum):
    """Statuts possibles pour une approbation."""
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"


@dataclass
class MemberApproval:
    """Représente une approbation/refus par un sage."""
    id: Optional[int]
    member_username: str
    sage_username: str
    status: ApprovalStatus
    reason: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    async def create(cls, db_pool, member_username: str, sage_username: str,
                     status: ApprovalStatus, reason: str = None) -> 'MemberApproval':
        """Crée une nouvelle approbation."""
        query = """
        INSERT INTO member_approval (member_username, sage_username, status, reason)
        VALUES ($1, $2, $3, $4)
        RETURNING id, created_at
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, member_username, sage_username, status.value, reason)
            logger.info(f"Approbation créée: {member_username} -> {status.value} par {sage_username}")
            return cls(
                id=row['id'],
                member_username=member_username,
                sage_username=sage_username,
                status=status,
                reason=reason,
                created_at=row['created_at']
            )

    @classmethod
    async def get_by_member(cls, db_pool, member_username: str) -> Optional['MemberApproval']:
        """Récupère l'approbation d'un membre (la plus récente)."""
        query = """
        SELECT id, member_username, sage_username, status, reason, created_at, updated_at
        FROM member_approval
        WHERE member_username = $1
        ORDER BY created_at DESC
        LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, member_username)
            if row:
                return cls(
                    id=row['id'],
                    member_username=row['member_username'],
                    sage_username=row['sage_username'],
                    status=ApprovalStatus(row['status']),
                    reason=row['reason'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            return None

    @classmethod
    async def get_pending(cls, db_pool) -> List['MemberApproval']:
        """Récupère toutes les demandes en attente."""
        query = """
        SELECT ma.id, ma.member_username, ma.sage_username, ma.status,
               ma.reason, ma.created_at, ma.updated_at
        FROM member_approval ma
        INNER JOIN (
            SELECT member_username, MAX(created_at) as max_created
            FROM member_approval
            GROUP BY member_username
        ) latest ON ma.member_username = latest.member_username
                AND ma.created_at = latest.max_created
        WHERE ma.status = 'pending'
        ORDER BY ma.created_at ASC
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [cls(
                id=row['id'],
                member_username=row['member_username'],
                sage_username=row['sage_username'],
                status=ApprovalStatus(row['status']),
                reason=row['reason'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            ) for row in rows]

    @classmethod
    async def approve(cls, db_pool, member_username: str, sage_username: str) -> 'MemberApproval':
        """Approuve un membre."""
        # Mettre à jour le statut dans member_approval
        approval = await cls.create(db_pool, member_username, sage_username, ApprovalStatus.APPROVED)

        # Mettre à jour user_profile
        query = """
        UPDATE user_profile
        SET approval_status = 'approved'
        WHERE username = $1
        """
        async with db_pool.acquire() as conn:
            await conn.execute(query, member_username)

        logger.info(f"Membre {member_username} approuvé par {sage_username}")
        return approval

    @classmethod
    async def refuse(cls, db_pool, member_username: str, sage_username: str,
                     reason: str = None) -> 'MemberApproval':
        """Refuse un membre."""
        approval = await cls.create(db_pool, member_username, sage_username,
                                    ApprovalStatus.REFUSED, reason)

        # Mettre à jour user_profile
        query = """
        UPDATE user_profile
        SET approval_status = 'refused'
        WHERE username = $1
        """
        async with db_pool.acquire() as conn:
            await conn.execute(query, member_username)

        logger.info(f"Membre {member_username} refusé par {sage_username}: {reason}")
        return approval

    @classmethod
    async def get_pending_count(cls, db_pool) -> int:
        """Retourne le nombre de demandes en attente."""
        query = """
        SELECT COUNT(DISTINCT member_username)
        FROM user_profile
        WHERE approval_status = 'pending'
          AND charte_validated = TRUE
        """
        async with db_pool.acquire() as conn:
            return await conn.fetchval(query) or 0
