#!/bin/bash

# Vérifie si la session existe avant de la tuer
if tmux has-session -t bot_session 2>/dev/null; then
    tmux kill-session -t bot_session
    echo "Bot arrêté et session tmux 'bot_session' terminée."
else
    echo "Pas de session de bot active"
fi

