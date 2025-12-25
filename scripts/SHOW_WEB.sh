#!/bin/bash
# =============================================================================
# Affiche les logs du serveur web (Ctrl+B puis D pour détacher)
# =============================================================================

WEB_SESSION="web_session"

if tmux has-session -t $WEB_SESSION 2>/dev/null; then
    echo "Attachement à la session '$WEB_SESSION'..."
    echo "(Ctrl+B puis D pour détacher sans arrêter)"
    tmux attach-session -t $WEB_SESSION
else
    echo "Le serveur web n'est pas en cours d'exécution"
    echo "Lancez ./scripts/START_BOT.sh pour démarrer"
fi
