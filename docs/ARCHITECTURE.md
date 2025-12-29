# Architecture du Bot Discord This Is PSG

> Documentation technique de l'architecture du projet.

---

## Vue d'ensemble

Bot Discord de la team This Is PSG sur Tennis Clash.

**Fonctionnalités principales :**
- Inscription des membres avec validation de charte
- Gestion des joueurs in-game (2 équipes)
- Localisation des membres (carte interactive)
- Validation par les Sages (modérateurs)

---

## Structure des fichiers

```
discord-bot/
├── bot.py                 # Point d'entrée, initialisation
├── config.py              # Configuration (.env)
├── constants.py           # Constantes (statuts, timeouts)
│
├── cogs/                  # Modules Discord (commandes)
│   ├── events.py          # Événements (on_member_join, on_ready)
│   ├── registration.py    # Inscription, profil, localisation
│   ├── sages.py           # Commandes modération (valider, refuser)
│   ├── user_commands.py   # Commandes utilisateur (aide, carte)
│   └── private.py         # Commandes privées (MP)
│
├── models/                # Modèles de données
│   ├── user_profile.py    # Profil membre Discord
│   ├── player.py          # Joueur in-game + Team
│   ├── schemas.py         # Validation Pydantic
│   └── member_approval.py # (legacy)
│
├── utils/                 # Utilitaires
│   ├── database.py        # Classe Database
│   ├── discord_helpers.py # Recherche de membres
│   ├── geocoding.py       # Géocodage avec cache
│   ├── map_generator.py   # Génération carte HTML
│   ├── i18n.py            # Traductions FR/EN
│   ├── logger.py          # Logging structuré
│   ├── cache.py           # Cache TTL
│   ├── rate_limit.py      # Rate limiting
│   ├── validators.py      # Validation inputs
│   ├── migrations.py      # Migrations auto
│   ├── roles.py           # Gestion des rôles
│   └── image_processing.py # OCR (pytesseract)
│
├── migrations/            # Scripts SQL
│   ├── 001_multi_team_support.sql
│   ├── 002_discord_id_migration.sql
│   ├── 003_username_history.sql
│   ├── 004_location_display.sql
│   └── 005_drop_charte_tables.sql
│
├── locales/               # Traductions
│   ├── fr.json
│   └── en.json
│
├── data/                  # Templates
│   └── map_template.html
│
├── docs/                  # Documentation
│   └── carte.html         # Carte générée (GitHub Pages)
│
└── tests/                 # Tests pytest
    ├── conftest.py
    ├── test_models/
    └── test_utils/
```

---

## Flow d'inscription

```
┌─────────────────────────────────────────────────────────────────┐
│                     INSCRIPTION (!inscription)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Choix de langue │
                    │    (FR / EN)    │
                    └────────┬────────┘
                             │
                              ▼
                    ┌─────────────────┐
                    │ Lecture charte  │
                    │   + Validation  │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │    Profil existant ?         │
              └──────────────┬──────────────┘
                    ┌────────┴────────┐
                    │                 │
                   OUI               NON
                    │                 │
                    ▼                 │
          ┌─────────────────┐         │
          │ Conserver ou    │         │
          │ réinitialiser ? │         │
          └────────┬────────┘         │
                   │                  │
                   ▼                  ▼
          ┌─────────────────────────────────┐
          │     Saisie des joueurs          │
          │  (Team 1 puis Team 2, facultatif)│
          └────────────────┬────────────────┘
                           │
                           ▼
          ┌─────────────────────────────────┐
          │     Saisie localisation         │
          │     (facultatif, géocodée)      │
          └────────────────┬────────────────┘
                           │
                           ▼
          ┌─────────────────────────────────┐
          │   Inscription terminée          │
          │   → Statut: PENDING             │
          │   → Attente validation Sage     │
          └────────────────┬────────────────┘
                           │
                           ▼
          ┌─────────────────────────────────┐
          │   Sage: !valider ou !refuser    │
          │   → Statut: APPROVED / REFUSED  │
          │   → Attribution rôle "Membre"   │
          └─────────────────────────────────┘
```

---

## Schéma de base de données

### Table `user_profile`

| Colonne | Type | Description |
|---------|------|-------------|
| `discord_id` | BIGINT PK | ID Discord (snowflake) |
| `username` | VARCHAR | Nom utilisateur Discord |
| `discord_name` | VARCHAR | Nom d'affichage |
| `language` | VARCHAR(2) | FR ou EN |
| `charte_validated` | BOOLEAN | Charte acceptée |
| `approval_status` | VARCHAR | pending / approved / refused |
| `localisation` | TEXT | Adresse saisie |
| `latitude` | FLOAT | Coordonnée GPS |
| `longitude` | FLOAT | Coordonnée GPS |
| `location_display` | VARCHAR | Région/Pays (anonymisé) |
| `creation_date` | TIMESTAMP | Date création profil |
| `last_connection` | TIMESTAMP | Dernière connexion |

### Table `players`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | SERIAL PK | ID auto |
| `member_username` | VARCHAR FK | Lien vers user_profile |
| `team_id` | INT FK | 1 ou 2 |
| `player_name` | VARCHAR | Nom du joueur in-game |
| `created_at` | TIMESTAMP | Date ajout |

### Table `teams`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INT PK | 1 ou 2 |
| `name` | VARCHAR | "This Is PSG" ou "This Is PSG 2" |
| `created_at` | TIMESTAMP | Date création |

### Table `username_history`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | SERIAL PK | ID auto |
| `discord_id` | BIGINT | ID Discord |
| `username` | VARCHAR | Ancien username |
| `discord_name` | VARCHAR | Ancien display_name |
| `changed_at` | TIMESTAMP | Date du changement |

### Table `schema_migrations`

| Colonne | Type | Description |
|---------|------|-------------|
| `name` | VARCHAR PK | Nom du fichier migration |
| `applied_at` | TIMESTAMP | Date d'application |

---

## Responsabilités des Cogs

### `events.py`
- `on_ready` : Connexion du bot
- `on_member_join` : Accueil nouveau membre
- `on_member_update` : Détection changement username

### `registration.py` (722 lignes)
- `!inscription` : Flow complet d'inscription
- `!profil` : Affiche le profil
- `!joueur` / `!player` : Gestion des joueurs
- `!localisation` / `!location` : Définir la position
- `!langue` / `!language` : Changer la langue

### `sages.py`
- `!pending` : Liste des inscriptions en attente
- `!valider <membre>` : Approuver un membre
- `!refuser <membre>` : Refuser un membre
- `!profil-admin <membre>` : Voir profil complet
- `!reset <membre>` : Réinitialiser un profil
- `!audit-permissions` : Export des permissions Discord

### `user_commands.py`
- `!aide` / `!help` : Affiche l'aide
- `!carte` / `!map` : Lien vers la carte
- `!users` / `!membres` : Liste des membres
- `!template` : OCR screenshot Tennis Clash

### `private.py`
- Gestion des messages privés

---

## Modules utilitaires

| Module | Responsabilité |
|--------|----------------|
| `database.py` | Opérations CRUD simplifiées |
| `discord_helpers.py` | `find_member()`, `find_member_strict()` |
| `geocoding.py` | Nominatim avec cache 24h |
| `map_generator.py` | Génère carte Leaflet, push GitHub |
| `i18n.py` | Traductions `get_text(key, lang)` |
| `logger.py` | Logging avec rotation |
| `cache.py` | Cache TTL générique |
| `rate_limit.py` | Rate limiting par utilisateur |
| `validators.py` | Validation inputs utilisateur |
| `migrations.py` | Exécution migrations au boot |

---

## Carte des membres

La carte est générée en HTML (Leaflet.js) et hébergée sur GitHub Pages.

**Flow de mise à jour :**
1. Membre saisit/modifie sa localisation
2. `geocoding.py` → coordonnées GPS (cache 24h)
3. `map_generator.py` → génère `docs/carte.html`
4. Push automatique vers GitHub
5. GitHub Pages sert la carte

**URL :** `https://lestat2lioncourt.github.io/discord-bot/carte.html`

---

## Configuration

Variables d'environnement (`.env`) :

```env
# Discord
DISCORD_TOKEN=...
GUILD_ID=...

# Base de données PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=discord_bot
DB_USER=...
DB_PASSWORD=...

# GitHub (pour la carte)
GITHUB_TOKEN=...
GITHUB_REPO=Lestat2Lioncourt/discord-bot

# URLs
SITE_URL=https://lestat2lioncourt.github.io/discord-bot/
WEB_URL=https://lestat2lioncourt.github.io/discord-bot/carte.html

# Timeouts (optionnel)
TIMEOUT_LANGUAGE_SELECT=300
TIMEOUT_CHARTE_READ=600
```

---

## Tests

```bash
# Lancer tous les tests
python -m pytest tests/ -v

# Avec couverture
python -m pytest tests/ --cov=utils --cov=models

# 183 tests actuellement
```

---

## Dépendances principales

| Package | Usage |
|---------|-------|
| `discord.py` | API Discord |
| `asyncpg` | PostgreSQL async |
| `geopy` | Géocodage Nominatim |
| `pydantic` | Validation schémas |
| `opencv-python-headless` | Preprocessing OCR |
| `pytesseract` | OCR |
| `pillow` | Traitement images |

---

*Dernière mise à jour : 28/12/2024*
