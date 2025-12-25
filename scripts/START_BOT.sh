#!/bin/bash
# =============================================================================
# Démarre le bot Discord dans une session tmux
# =============================================================================

set -e

BOT_DIR="${BOT_DIR:-~/Projects/discord_bot}"
BOT_SESSION="bot_session"

if tmux has-session -t $BOT_SESSION 2>/dev/null; then
    echo "Le bot est déjà en cours d'exécution"
    echo "Utilisez ./scripts/SHOW_BOT.sh pour voir les logs"
    exit 0
fi

tmux new-session -d -s $BOT_SESSION "cd $BOT_DIR && uv run python bot.py"
echo "Bot démarré dans la session '$BOT_SESSION'"
echo "Utilisez ./scripts/SHOW_BOT.sh pour voir les logs"
