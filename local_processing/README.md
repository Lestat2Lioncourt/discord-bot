# Local Processing - Analyse d'images Tennis Clash

Ce dossier contient les scripts à exécuter sur ta **machine locale** (pas le Raspberry).

## Pourquoi ?

Le bot Discord tourne sur Raspberry Pi avec des ressources limitées. L'analyse des captures d'écran Tennis Clash utilise Claude Vision (via Claude Code avec ton abonnement MAX), qui nécessite plus de ressources.

## Architecture

```
[User Discord] → !capture → [Bot Raspberry] → INSERT image → [PostgreSQL]
                                                                   ↓
[Ta machine] ← process_queue.py ← SELECT pending ←←←←←←←←←←←←←←←←←
      ↓
[Claude Vision analyse]
      ↓
UPDATE result_json → [PostgreSQL] → [Bot notifie user] → Valider/Refuser
```

## Utilisation

1. Assure-toi d'avoir accès à la base PostgreSQL (même réseau local)
2. Configure `.env.local` avec les infos de connexion
3. Lance le script :

```bash
cd local_processing
python process_queue.py
```

Le script :
- Récupère les captures en attente (status = 'pending')
- Analyse chaque image avec Claude Vision
- Met à jour la base avec les résultats (status = 'completed')
- Affiche un résumé

## Prérequis

- Python 3.11+
- Claude Code installé et configuré (abonnement MAX)
- Accès réseau à PostgreSQL

## Fichiers

- `process_queue.py` - Script principal de traitement
- `requirements.txt` - Dépendances Python
- `.env.local.example` - Exemple de configuration
