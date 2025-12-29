#!/bin/bash
# =============================================================================
# Affiche les logs du bot Discord (attache à la session tmux)
# Appuyez sur Ctrl+B puis D pour détacher sans arrêter le bot
# =============================================================================

SESSION_NAME="bot_session"

if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Connexion à la session '$SESSION_NAME'..."
    echo "Appuyez sur Ctrl+B puis D pour détacher sans arrêter le bot"
    tmux attach-session -t $SESSION_NAME
else
    echo "Aucune session de bot active"
    echo "Utilisez ./scripts/START_BOT.sh pour démarrer le bot"
fi
