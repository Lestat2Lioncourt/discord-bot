#!/bin/bash
# =============================================================================
# Arrête le bot Discord
# =============================================================================

SESSION_NAME="bot_session"

if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    tmux kill-session -t $SESSION_NAME
    echo "Bot arrêté et session '$SESSION_NAME' terminée"
else
    echo "Aucune session de bot active"
fi
