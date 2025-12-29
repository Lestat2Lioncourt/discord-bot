#!/bin/bash
# =============================================================================
# Arrête le bot Discord
# =============================================================================

BOT_SESSION="bot_session"

if tmux has-session -t $BOT_SESSION 2>/dev/null; then
    tmux kill-session -t $BOT_SESSION
    echo "Bot arrêté"
else
    echo "Aucune session bot active"
fi
