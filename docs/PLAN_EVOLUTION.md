# Plan d'évolution du Bot Discord "This Is PSG"

## Contexte

Le bot gère deux équipes de Tennis Clash :
- **This Is PSG** (équipe principale)
- **This Is PSG 2** (équipe secondaire)

Un membre Discord peut avoir plusieurs joueurs (un par équipe).

## Workflow d'inscription

1. Nouveau membre rejoint le serveur Discord
2. Il arrive dans le canal **#accueil**
3. Il utilise `!inscription` pour démarrer le processus
4. Il valide la charte avec `!charte` (envoyée en plusieurs messages)
5. Il enregistre son/ses joueur(s) avec `!joueur <nom> [équipe]`
6. Il peut optionnellement saisir sa localisation avec `!localisation <ville>`
7. Un **Sage** valide ou refuse l'inscription
8. Si validé : le membre reçoit le rôle @Membre et accède aux canaux
9. Si refusé : arbitrage dans un canal dédié

## Rôles Discord

| Rôle | Description |
|------|-------------|
| @Nouveau | Attribué automatiquement à l'arrivée, accès limité à #accueil |
| @Membre | Membre validé, accès complet aux canaux |
| @Sage | Modérateur, peut valider/refuser les inscriptions |

---

## Phases d'implémentation

### Phase 1 : Migration DB (multi-teams, multi-joueurs) ✅ TERMINÉE

- [x] Créer table `teams` (id, name)
- [x] Créer table `players` (id, member_username, team_id, player_name)
- [x] Créer table `member_approval` (id, member_username, sage_username, status, reason, timestamps)
- [x] Ajouter colonnes `charte_validated`, `approval_status` à `user_profile`
- [x] Ajouter colonnes `localisation`, `latitude`, `longitude` à `user_profile`
- [x] Créer modèles Python : `Player`, `Team`, `MemberApproval`
- [x] Créer script de migration `scripts/run_migration.py`
- [x] Ajouter dépendance `geopy` pour géocodage

### Phase 2 : Gestion des rôles Discord ✅ TERMINÉE

- [x] Définir les IDs des rôles dans `.env` :
  - `ROLE_NEWBIE_ID=1453322362484297870`
  - `ROLE_MEMBRE_ID=1453322702571049072`
  - `ROLE_SAGE_ID=1322971425434501161`
  - `CHANNEL_ACCUEIL_ID=1453323021497405451`
- [x] Créer `utils/roles.py` avec fonctions :
  - `assign_newbie_role(member)`
  - `promote_to_membre(member)`
  - `is_sage(member)`, `is_membre(member)`, `is_newbie(member)`
- [x] Event `on_member_join` : attribuer @Newbie automatiquement
- [x] Lors de validation par sage : remplacer @Newbie par @Membre

### Phase 3 : Commandes nouveaux inscrits

| Commande | Description |
|----------|-------------|
| `!inscription` | Démarre le processus d'inscription, affiche les étapes |
| `!charte` | Affiche la charte en plusieurs messages, demande validation |
| `!joueur <nom> [équipe]` | Enregistre un joueur (équipe par défaut : This Is PSG) |
| `!localisation <ville>` | Enregistre la localisation (géocodage via Nominatim) |
| `!statut` | Affiche le statut d'inscription actuel |

**Détails techniques :**
- `!charte` : envoyer en DM, découper en messages < 2000 caractères
- `!joueur` : vérifier que le nom n'existe pas déjà dans l'équipe
- `!localisation` : utiliser geopy/Nominatim, stocker lat/lon

### Phase 4 : Commandes sages

| Commande | Description |
|----------|-------------|
| `!pending` | Liste les inscriptions en attente |
| `!valider <@membre>` | Valide l'inscription d'un membre |
| `!refuser <@membre> <raison>` | Refuse l'inscription avec motif |
| `!info <@membre>` | Affiche les infos complètes d'un membre |

**Détails techniques :**
- Vérifier que l'utilisateur a le rôle @Sage
- `!valider` : mettre à jour `approval_status`, changer rôle, notifier le membre
- `!refuser` : enregistrer la raison, notifier le membre, créer thread arbitrage

### Phase 5 : Commandes membres

| Commande | Description |
|----------|-------------|
| `!profil` | Affiche son propre profil complet |
| `!profil <@membre>` | Affiche le profil d'un autre membre |
| `!team [nom]` | Affiche le roster d'une équipe |
| `!roster` | Alias de `!team` |
| `!who <nom_joueur>` | Cherche un joueur par son nom in-game |

### Phase 6 : Notifications automatiques

- [ ] Notification aux sages quand nouvelle inscription complète
- [ ] Rappel au membre si inscription incomplète après 24h
- [ ] Message de bienvenue personnalisé après validation
- [ ] Log des actions dans un canal #logs (optionnel)

### Phase 7 : Carte des membres (Leaflet)

**Architecture :**
```
discord-bot/
├── web/
│   ├── server.py          # Mini serveur Flask/FastAPI
│   ├── templates/
│   │   └── map.html       # Page avec carte Leaflet
│   └── static/
│       └── style.css
```

**Fonctionnalités :**
- Endpoint `/api/members` : retourne JSON des membres avec localisation
- Page `/map` : carte Leaflet avec marqueurs
- Marqueurs cliquables avec nom Discord et joueurs
- Filtrage par équipe
- Accès protégé (token ou authentification simple)

**Charge estimée sur Raspberry Pi 5 :**
- Flask/FastAPI : ~20-50 Mo RAM
- Requêtes occasionnelles : charge CPU négligeable
- Base de données déjà en place

---

## Configuration requise (.env)

```env
# Discord
DISCORD_TOKEN=xxx
BOT_PREFIX=!

# Base de données
DB_HOST=localhost
DB_PORT=5432
DB_NAME=discord_bot
DB_USER=xxx
DB_PASSWORD=xxx

# Rôles Discord (à ajouter)
ROLE_NOUVEAU_ID=xxx
ROLE_MEMBRE_ID=xxx
ROLE_SAGE_ID=xxx

# Canaux Discord (à ajouter)
CHANNEL_ACCUEIL_ID=xxx
CHANNEL_LOGS_ID=xxx
CHANNEL_ARBITRAGE_ID=xxx

# Carte (Phase 7)
MAP_SECRET_KEY=xxx
MAP_PORT=8080
```

---

## Notes techniques

### Géocodage
- Service : Nominatim (OpenStreetMap)
- Rate limit : 1 requête/seconde
- Stocker lat/lon pour éviter re-géocodage

### Charte multi-messages
- La charte est stockée dans `data/charte.json`
- Découpage automatique en messages < 2000 caractères
- Validation via réaction ou commande `!accepte`

### Sécurité
- Validation des inputs utilisateur
- Pas d'injection SQL (requêtes paramétrées)
- Tokens/secrets dans `.env` (jamais commités)
