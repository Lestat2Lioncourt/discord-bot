#!/bin/bash
# =============================================================================
# Démarre le bot Discord dans une session tmux
# =============================================================================

set -e

BOT_DIR="${BOT_DIR:-~/Projects/discord_bot}"
SESSION_NAME="bot_session"

# Vérifier si une session existe déjà
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Le bot est déjà en cours d'exécution dans la session '$SESSION_NAME'"
    echo "Utilisez ./scripts/SHOW_BOT.sh pour voir les logs"
    exit 0
fi

# Démarrer le bot dans une nouvelle session tmux
tmux new-session -d -s $SESSION_NAME "cd $BOT_DIR && source .venv/bin/activate && python bot.py"

echo "Bot démarré dans la session tmux '$SESSION_NAME'"
echo "Utilisez ./scripts/SHOW_BOT.sh pour voir les logs"
