#!/bin/bash
# =============================================================================
# Arrête le bot Discord et le serveur web
# =============================================================================

BOT_SESSION="bot_session"
WEB_SESSION="web_session"

# Arrêter le bot
if tmux has-session -t $BOT_SESSION 2>/dev/null; then
    tmux kill-session -t $BOT_SESSION
    echo "Bot arrêté"
else
    echo "Aucune session bot active"
fi

# Arrêter le serveur web
if tmux has-session -t $WEB_SESSION 2>/dev/null; then
    tmux kill-session -t $WEB_SESSION
    echo "Serveur web arrêté"
else
    echo "Aucune session web active"
fi
