# =============================================================================
# Script de déploiement vers le Raspberry Pi (PowerShell pour Windows)
# Usage: .\scripts\deploy.ps1 [-NoRestart] [-InstallDeps]
# =============================================================================

param(
    [switch]$NoRestart,
    [switch]$InstallDeps
)

# Configuration - À modifier selon votre environnement
$RPI_USER = if ($env:RPI_USER) { $env:RPI_USER } else { "pi" }
$RPI_HOST = if ($env:RPI_HOST) { $env:RPI_HOST } else { "raspberrypi.local" }
$RPI_PATH = if ($env:RPI_PATH) { $env:RPI_PATH } else { "~/Projects/discord_bot" }
$SSH_KEY = if ($env:SSH_KEY) { $env:SSH_KEY } else { "$env:USERPROFILE\.ssh\id_ed25519" }

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host "[$Step] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Red
}

Write-Host "=== Deploiement du bot Discord ===" -ForegroundColor Green

# Vérification de la connexion SSH
Write-Step "1/4" "Verification de la connexion SSH..."
$sshTest = ssh -i $SSH_KEY -o ConnectTimeout=5 "$RPI_USER@$RPI_HOST" "echo OK" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "Impossible de se connecter au Raspberry Pi"
    Write-Host "Verifiez:"
    Write-Host "  - Que le Raspberry Pi est allume et connecte au reseau"
    Write-Host "  - Que SSH est active sur le Raspberry Pi"
    Write-Host "  - Que la cle SSH est configuree (voir docs/SSH_SETUP.md)"
    exit 1
}
Write-Success "Connexion SSH OK"

# Pull des dernières modifications
Write-Step "2/4" "Recuperation des dernieres modifications..."
ssh -i $SSH_KEY "$RPI_USER@$RPI_HOST" "cd $RPI_PATH && git pull origin main"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Erreur lors du git pull"
    exit 1
}

# Installation des dépendances si demandé
if ($InstallDeps) {
    Write-Step "3/4" "Installation des dependances..."
    ssh -i $SSH_KEY "$RPI_USER@$RPI_HOST" "cd $RPI_PATH && source venv/bin/activate && pip install -r requirements.txt"
} else {
    Write-Step "3/4" "Skip installation dependances (utilisez -InstallDeps pour installer)"
}

# Redémarrage du bot
if (-not $NoRestart) {
    Write-Step "4/4" "Redemarrage du bot..."
    ssh -i $SSH_KEY "$RPI_USER@$RPI_HOST" "cd $RPI_PATH && ./scripts/RESTART_BOT.sh"
    Write-Success "Bot redemarre avec succes !"
} else {
    Write-Step "4/4" "Skip redemarrage (-NoRestart)"
}

Write-Host "=== Deploiement termine ===" -ForegroundColor Green
