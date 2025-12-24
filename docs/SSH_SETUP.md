# Configuration SSH avec clé pour le déploiement

Ce guide explique comment configurer l'authentification SSH par clé pour le déploiement automatique vers le Raspberry Pi.

## Avantages de l'authentification par clé

- Plus sécurisé que le mot de passe
- Pas besoin de taper le mot de passe à chaque connexion
- Indispensable pour les scripts de déploiement automatisés

## Étapes de configuration

### 1. Générer une paire de clés SSH (sur Windows)

Ouvrez PowerShell et exécutez :

```powershell
ssh-keygen -t ed25519 -C "votre-email@example.com"
```

- Appuyez sur Entrée pour accepter l'emplacement par défaut (`C:\Users\VotreNom\.ssh\id_ed25519`)
- Optionnel : entrez une passphrase pour plus de sécurité

### 2. Copier la clé publique sur le Raspberry Pi

```powershell
# Afficher la clé publique
type $env:USERPROFILE\.ssh\id_ed25519.pub

# Copier manuellement sur le Raspberry Pi
ssh pi@raspberrypi.local "mkdir -p ~/.ssh && echo 'CONTENU_DE_LA_CLE' >> ~/.ssh/authorized_keys"
```

Ou en une commande (remplacez `pi` et `raspberrypi.local` par vos valeurs) :

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh pi@raspberrypi.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### 3. Tester la connexion

```powershell
ssh pi@raspberrypi.local
```

Vous devriez vous connecter sans mot de passe !

### 4. Configuration SSH (optionnel mais recommandé)

Créez ou éditez le fichier `~/.ssh/config` :

```
Host rpi
    HostName raspberrypi.local
    User pi
    IdentityFile ~/.ssh/id_ed25519
```

Vous pourrez ensuite vous connecter simplement avec :

```powershell
ssh rpi
```

## Configuration du script de déploiement

Le script utilise des variables d'environnement. Vous pouvez les définir dans PowerShell :

```powershell
$env:RPI_USER = "pi"
$env:RPI_HOST = "raspberrypi.local"
$env:RPI_PATH = "~/Projects/discord_bot"
$env:SSH_KEY = "$env:USERPROFILE\.ssh\id_ed25519"
```

Ou les ajouter de façon permanente dans votre profil PowerShell :

```powershell
notepad $PROFILE
```

## Utilisation du script de déploiement

### Déploiement standard (avec redémarrage)

```powershell
.\scripts\deploy.ps1
```

### Déploiement sans redémarrage

```powershell
.\scripts\deploy.ps1 -NoRestart
```

### Déploiement avec réinstallation des dépendances

```powershell
.\scripts\deploy.ps1 -InstallDeps
```

## Dépannage

### "Permission denied (publickey)"

1. Vérifiez que la clé publique est bien copiée sur le Raspberry Pi :
   ```bash
   cat ~/.ssh/authorized_keys
   ```

2. Vérifiez les permissions :
   ```bash
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```

### "Host key verification failed"

Supprimez l'ancienne entrée :
```powershell
ssh-keygen -R raspberrypi.local
```

### Le Raspberry Pi n'est pas trouvé

- Vérifiez qu'il est bien connecté au réseau
- Essayez avec l'adresse IP directe au lieu de `raspberrypi.local`
- Vérifiez que SSH est activé sur le Raspberry Pi (via `raspi-config`)
