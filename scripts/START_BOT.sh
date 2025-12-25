#!/bin/bash
# =============================================================================
# Démarre le bot Discord et le serveur web dans des sessions tmux
# =============================================================================

set -e

BOT_DIR="${BOT_DIR:-~/Projects/discord_bot}"
BOT_SESSION="bot_session"
WEB_SESSION="web_session"

# Démarrer le bot
if tmux has-session -t $BOT_SESSION 2>/dev/null; then
    echo "Le bot est déjà en cours d'exécution"
else
    tmux new-session -d -s $BOT_SESSION "cd $BOT_DIR && uv run python bot.py"
    echo "Bot démarré dans la session '$BOT_SESSION'"
fi

# Démarrer le serveur web
if tmux has-session -t $WEB_SESSION 2>/dev/null; then
    echo "Le serveur web est déjà en cours d'exécution"
else
    tmux new-session -d -s $WEB_SESSION "cd $BOT_DIR && uv run python -m web.server"
    echo "Serveur web démarré dans la session '$WEB_SESSION'"
fi

echo ""
echo "Utilisez:"
echo "  ./scripts/SHOW_BOT.sh  - voir les logs du bot"
echo "  ./scripts/SHOW_WEB.sh  - voir les logs du serveur web"
