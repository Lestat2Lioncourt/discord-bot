#!/bin/bash
# =============================================================================
# Redémarre le bot Discord
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Arrêt du bot..."
"$SCRIPT_DIR/STOP_BOT.sh"

sleep 2

echo "Démarrage du bot..."
"$SCRIPT_DIR/START_BOT.sh"
