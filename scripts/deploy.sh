#!/bin/bash
# =============================================================================
# Script de déploiement vers le Raspberry Pi
# Usage: ./scripts/deploy.sh [options]
# Options:
#   --no-restart  Ne pas redémarrer le bot après le déploiement
#   --deps        Réinstaller les dépendances
# =============================================================================

set -e  # Arrêter en cas d'erreur

# Configuration - À modifier selon votre environnement
RPI_USER="${RPI_USER:-pi}"
RPI_HOST="${RPI_HOST:-raspberrypi.local}"
RPI_PATH="${RPI_PATH:-~/Projects/discord_bot}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_ed25519}"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Options
NO_RESTART=false
INSTALL_DEPS=false

# Parsing des arguments
for arg in "$@"; do
    case $arg in
        --no-restart)
            NO_RESTART=true
            shift
            ;;
        --deps)
            INSTALL_DEPS=true
            shift
            ;;
        *)
            echo -e "${RED}Option inconnue: $arg${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}=== Déploiement du bot Discord ===${NC}"

# Vérification de la connexion SSH
echo -e "${YELLOW}[1/4] Vérification de la connexion SSH...${NC}"
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$RPI_USER@$RPI_HOST" "echo 'OK'" > /dev/null 2>&1; then
    echo -e "${RED}Impossible de se connecter au Raspberry Pi${NC}"
    echo "Vérifiez:"
    echo "  - Que le Raspberry Pi est allumé et connecté au réseau"
    echo "  - Que SSH est activé sur le Raspberry Pi"
    echo "  - Que la clé SSH est configurée (voir docs/SSH_SETUP.md)"
    exit 1
fi
echo -e "${GREEN}Connexion SSH OK${NC}"

# Pull des dernières modifications
echo -e "${YELLOW}[2/4] Récupération des dernières modifications...${NC}"
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "cd $RPI_PATH && git pull origin main"

# Installation des dépendances si demandé
if [ "$INSTALL_DEPS" = true ]; then
    echo -e "${YELLOW}[3/4] Installation des dépendances...${NC}"
    ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "cd $RPI_PATH && source venv/bin/activate && pip install -r requirements.txt"
else
    echo -e "${YELLOW}[3/4] Skip installation dépendances (utilisez --deps pour installer)${NC}"
fi

# Redémarrage du bot
if [ "$NO_RESTART" = false ]; then
    echo -e "${YELLOW}[4/4] Redémarrage du bot...${NC}"
    ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "cd $RPI_PATH && ./scripts/RESTART_BOT.sh"
    echo -e "${GREEN}Bot redémarré avec succès !${NC}"
else
    echo -e "${YELLOW}[4/4] Skip redémarrage (--no-restart)${NC}"
fi

echo -e "${GREEN}=== Déploiement terminé ===${NC}"
