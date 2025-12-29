"""
Module d'audit logging pour tracer les actions sensibles.

Actions tracees:
- VALIDATE: Validation d'un membre par un Sage
- REFUSE: Refus d'un membre par un Sage
- RESET: Reset du profil d'un membre
"""

from typing import Optional
import asyncpg

from utils.logger import get_logger

logger = get_logger("utils.audit")


class AuditAction:
    """Constantes pour les types d'actions."""
    VALIDATE = "VALIDATE"
    REFUSE = "REFUSE"
    RESET = "RESET"


async def log_action(
    pool: asyncpg.Pool,
    action: str,
    target_username: str,
    sage_username: str,
    sage_discord_id: int,
    target_discord_id: Optional[int] = None,
    details: Optional[str] = None,
    conn: Optional[asyncpg.Connection] = None
) -> None:
    """Enregistre une action dans la table audit_log.

    Args:
        pool: Pool de connexions asyncpg
        action: Type d'action (VALIDATE, REFUSE, RESET)
        target_username: Username du membre cible
        sage_username: Username du Sage qui effectue l'action
        sage_discord_id: Discord ID du Sage
        target_discord_id: Discord ID du membre cible (optionnel)
        details: Details supplementaires (optionnel)
        conn: Connexion existante pour les transactions (optionnel)
    """
    query = """
        INSERT INTO audit_log (action, target_username, target_discord_id,
                               sage_username, sage_discord_id, details)
        VALUES ($1, $2, $3, $4, $5, $6)
    """

    try:
        if conn:
            await conn.execute(
                query, action, target_username, target_discord_id,
                sage_username, sage_discord_id, details
            )
        else:
            async with pool.acquire() as conn:
                await conn.execute(
                    query, action, target_username, target_discord_id,
                    sage_username, sage_discord_id, details
                )
        logger.info(f"Audit: {action} sur {target_username} par {sage_username}")
    except asyncpg.PostgresError as e:
        # Ne pas bloquer l'action principale si l'audit echoue
        logger.error(f"Erreur audit logging: {e}", exc_info=True)


async def get_audit_history(
    pool: asyncpg.Pool,
    target_username: Optional[str] = None,
    sage_username: Optional[str] = None,
    limit: int = 50
) -> list:
    """Recupere l'historique d'audit.

    Args:
        pool: Pool de connexions asyncpg
        target_username: Filtrer par membre cible
        sage_username: Filtrer par Sage
        limit: Nombre max de resultats

    Returns:
        Liste des enregistrements d'audit
    """
    query = "SELECT * FROM audit_log WHERE 1=1"
    params: list[str | int] = []
    param_idx = 1

    if target_username:
        query += f" AND target_username = ${param_idx}"
        params.append(target_username)
        param_idx += 1

    if sage_username:
        query += f" AND sage_username = ${param_idx}"
        params.append(sage_username)
        param_idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${param_idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        return await conn.fetch(query, *params)
