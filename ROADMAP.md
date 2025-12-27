# Plan d'évolution technique - Bot Discord This Is PSG

> Document de référence pour les améliorations techniques du projet.
> Derniere mise a jour : 27/12/2024 (PM)

---

## Légende des priorités

| Priorité | Symbole | Délai suggéré |
|----------|---------|---------------|
| Critique | 🔴 | Immédiat |
| Haute | 🟠 | Avant prochain release |
| Moyenne | 🟡 | Prochaines semaines |
| Basse | 🟢 | Amélioration continue |

---

## 1. Performance

### 🔴 Requêtes N+1
**Fichiers concernés :** `cogs/sages.py`, `cogs/registration.py`

**Problème :**
```python
# Actuel - 1 requête par membre dans la boucle
for member_data in pending:
    players = await Player.get_by_member(...)  # N requêtes!
```

**Solution :**
- Créer une requête JOIN pour récupérer membres + joueurs en 1 query
- Ajouter méthode `Player.get_by_members(usernames: list)` avec IN clause

**Fichiers à modifier :**
- [x] `models/player.py` - Ajouter `get_by_members()` ✅
- [x] `cogs/sages.py:cmd_pending()` - Utiliser la nouvelle méthode ✅
- [ ] `cogs/registration.py:finish_registration()` - Optimiser (pas de N+1 ici)

---

### ✅ Cache des données fréquentes
**Problème :** Profils rechargés plusieurs fois dans le même flow

**Solution :**
- Implémenter un cache simple (TTL 60s) pour les profils
- Utiliser `@lru_cache` ou `cachetools` pour les rôles

**Fichiers créés/modifiés :**
- [x] `utils/cache.py` - Module de cache TTL ✅
- [ ] `models/user_profile.py` - Intégrer le cache (optionnel)
- [ ] `utils/roles.py` - Cache pour `get_role()` (optionnel)

---

### ✅ Rate limiting
**Problème :** Pas de protection contre les abus

**Solution :**
- Ajouter un décorateur `@rate_limit(calls=5, period=60)`
- Appliquer sur `!inscription`, `!localisation`

**Fichiers créés/modifiés :**
- [x] `utils/rate_limit.py` - Module rate limiting ✅
- [ ] `cogs/registration.py` - Appliquer le décorateur (optionnel)

---

## 2. Qualité du code

### 🟠 Refactoriser registration.py (722 lignes)
**Problème :** Fichier monolithique difficile à maintenir

**Solution :** Découper en modules :
```
cogs/
├── registration/
│   ├── __init__.py      # Cog principal
│   ├── views.py         # LanguageSelectView, CharteAcceptView, etc.
│   ├── steps.py         # Étapes d'inscription (langue, charte, profil)
│   └── commands.py      # Commandes (!inscription, !profil, etc.)
```

**Fichiers à créer :**
- [ ] `cogs/registration/__init__.py`
- [ ] `cogs/registration/views.py`
- [ ] `cogs/registration/steps.py`
- [ ] `cogs/registration/commands.py`
- [ ] Supprimer `cogs/registration.py`

---

### 🟠 Extraire le code dupliqué
**Problème :** Recherche de membres répétée dans 4 fichiers

**Solution :**
```python
# utils/discord_helpers.py
async def find_member_by_name(bot, search: str) -> Optional[discord.Member]:
    """Cherche un membre par nom dans toutes les guildes."""
    ...

async def get_user_profile(bot, member: discord.Member) -> UserProfile:
    """Récupère ou crée le profil d'un utilisateur."""
    ...
```

**Fichiers à créer/modifier :**
- [ ] `utils/discord_helpers.py` - Nouveau module
- [ ] `cogs/sages.py` - Utiliser les helpers
- [ ] `cogs/registration.py` - Utiliser les helpers
- [ ] `cogs/events.py` - Utiliser les helpers

---

### 🔴 Logging des erreurs
**Problème :** `except Exception: pass` sans log (4 endroits)

**Solution :**
```python
# Avant
except Exception:
    pass

# Après
except Exception as e:
    logger.error(f"Erreur inattendue: {e}", exc_info=True)
```

**Fichiers à modifier :**
- [x] `cogs/registration.py` - 6 blocs corrigés ✅
- [x] `cogs/sages.py` - 6 blocs corrigés ✅
- [x] `bot.py` - 1 bloc corrigé ✅

---

## 3. Configuration & Constantes

### 🟠 Extraire les valeurs hardcodées
**Problème :** Valeurs répétées en strings dans le code

**Solution :** Créer `constants.py` :
```python
# constants.py

# Statuts d'approbation
class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"

# Équipes
class Teams:
    TEAM1_ID = 1
    TEAM1_NAME = "This Is PSG"
    TEAM2_ID = 2
    TEAM2_NAME = "This Is PSG 2"

# Timeouts (en secondes)
class Timeouts:
    LANGUAGE_SELECT = 300
    CHARTE_READ = 600
    PLAYER_INPUT = 120
    LOCATION_INPUT = 120
```

**Fichiers à créer/modifier :**
- [x] `constants.py` - Nouveau fichier créé ✅
- [x] `cogs/registration.py` - Timeouts et Teams intégrés ✅
- [x] `cogs/sages.py` - Teams intégrés ✅
- [ ] `models/user_profile.py` - À faire (Phase 2)

---

### 🟡 Centraliser la config des timeouts
**Problème :** Timeouts hardcodés (300s, 600s, 120s)

**Solution :** Ajouter dans `config.py` :
```python
# Timeouts (peuvent être overridés via .env)
TIMEOUT_LANGUAGE = int(os.getenv("TIMEOUT_LANGUAGE", "300"))
TIMEOUT_CHARTE = int(os.getenv("TIMEOUT_CHARTE", "600"))
TIMEOUT_INPUT = int(os.getenv("TIMEOUT_INPUT", "120"))
```

**Fichiers à modifier :**
- [ ] `config.py` - Ajouter les timeouts
- [ ] `.env.example` - Documenter les options
- [ ] `cogs/registration.py` - Utiliser la config

---

## 4. Normalisation

### ✅ Cohérence du nommage des langues
**Problème :** `lang.upper() == "FR"` vs `lang.lower() == "fr"` mélangés

**Solution :**
- Convention: toujours en MAJUSCULES (FR, EN)
- `SUPPORTED_LANGUAGES = ["FR", "EN"]`
- `get_text()` normalise avec `.upper()`

**Fichiers modifiés :**
- [x] `utils/i18n.py` - Normalisation en majuscules ✅
- [x] `tests/test_utils/test_i18n.py` - Tests mis à jour ✅

---

### ✅ Nommage des classes Cog
**Problème :** `PrivateCommands` au lieu de `PrivateCommandsCog`

**Solution :** Renommer pour cohérence :
- `PrivateCommands` → `PrivateCommandsCog`

**Fichiers modifiés :**
- [x] `cogs/private.py` - Classe renommée ✅

---

## 5. Documentation

### 🟠 Docstrings manquantes
**Problème :** 60% des fonctions sans documentation

**Solution :** Ajouter docstrings au format Google :
```python
async def find_member_by_name(bot, search: str) -> Optional[discord.Member]:
    """Cherche un membre par nom dans toutes les guildes.

    Args:
        bot: Instance du bot Discord
        search: Nom ou partie du nom à chercher

    Returns:
        Le membre trouvé ou None
    """
```

**Fichiers prioritaires :**
- [ ] `models/user_profile.py` - Toutes les méthodes publiques
- [ ] `models/player.py` - Toutes les méthodes publiques
- [ ] `utils/database.py` - Toutes les méthodes publiques
- [ ] `cogs/*.py` - Au moins les commandes

---

### 🟢 README technique
**Problème :** Pas de documentation du flow d'inscription

**Solution :** Créer `docs/ARCHITECTURE.md` avec :
- Diagramme du flow d'inscription
- Description des cogs et leurs responsabilités
- Schéma de la base de données

**Fichiers à créer :**
- [ ] `docs/ARCHITECTURE.md`
- [ ] `docs/DATABASE.md` - Schéma et relations

---

### ✅ Nettoyer les TODOs obsolètes
**Problème :** `cogs/events.py:67` - TODO obsolète

**Solution :** Supprimer ou implémenter les TODOs restants

**Résultat :**
- [x] Aucun TODO/FIXME trouvé dans le code ✅

---

## 6. Tests

### ✅ Framework de tests
**Problème :** Aucun test automatisé

**Solution :**
1. Installer pytest : `pip install pytest pytest-asyncio pytest-cov`
2. Créer structure de tests :
```
tests/
├── __init__.py
├── conftest.py          # Fixtures (mock DB, mock bot)
├── test_models/
│   ├── test_user_profile.py
│   ├── test_player.py
│   └── test_schemas.py
├── test_utils/
│   ├── test_validators.py
│   ├── test_i18n.py
│   ├── test_cache.py
│   └── test_rate_limit.py
└── test_cogs/
    └── test_registration.py (futur)
```

**Fichiers créés :**
- [x] `tests/conftest.py` - Fixtures de base ✅
- [x] `tests/test_utils/test_validators.py` - 38 tests ✅
- [x] `tests/test_utils/test_i18n.py` - 20 tests ✅
- [x] `tests/test_utils/test_cache.py` - 20 tests ✅
- [x] `tests/test_utils/test_rate_limit.py` - 22 tests ✅
- [x] `tests/test_models/test_user_profile.py` - 24 tests ✅
- [x] `tests/test_models/test_player.py` - 18 tests ✅
- [x] `tests/test_models/test_schemas.py` - 41 tests ✅
- [x] `pyproject.toml` - Configuration pytest ✅
**Total: 183 tests passants**

---

### 🟡 Type checking
**Problème :** Type hints partiels, pas de vérification

**Solution :**
1. Compléter les type hints
2. Ajouter mypy : `pip install mypy`
3. Config dans `pyproject.toml`

**Fichiers à modifier :**
- [ ] `pyproject.toml` - Config mypy
- [ ] Tous les fichiers Python - Compléter les types

---

## 7. Sécurité

### ✅ Validation avec Pydantic
**Problème :** Validation manuelle, risque d'oubli

**Solution :**
```python
# models/schemas.py
from pydantic import BaseModel, field_validator

class PlayerCreate(BaseModel):
    player_name: str
    team_id: int
    member_username: str

    @field_validator('player_name')
    def validate_name(cls, v):
        if len(v) < 2 or len(v) > 50:
            raise ValueError('Nom invalide')
        return v.strip()
```

**Fichiers créés/modifiés :**
- [x] `models/schemas.py` - Schémas Pydantic (PlayerCreate, LocationInput, etc.) ✅
- [x] `pyproject.toml` - Ajout pydantic>=2.0.0 ✅
- [ ] `cogs/registration.py` - Utiliser les schémas (optionnel)

---

### 🟡 Cache géolocalisation
**Problème :** Nominatim peut rate-limit sans cache

**Solution :**
```python
# utils/geocoding.py
from functools import lru_cache

@lru_cache(maxsize=1000)
def geocode_cached(location: str) -> Optional[Location]:
    ...
```

**Fichiers à créer :**
- [ ] `utils/geocoding.py` - Wrapper avec cache

---

## 8. Dépendances

### ✅ Nettoyer requirements
**Problème :** `requirements.txt` et `pyproject.toml` se chevauchent

**Solution :**
- Garder uniquement `pyproject.toml` (UV l'utilise directement)
- Supprimer `requirements.txt`

**Fichiers modifiés :**
- [x] `pyproject.toml` - Source unique ✅
- [x] `requirements.txt` - Supprimé ✅
- [x] `web/` - Supprimé (obsolète, migré vers GitHub Pages) ✅

---

### 🟢 Évaluer opencv-python
**Problème :** Package lourd (100+ MB) pour usage limité

**Solution :** Évaluer si PIL/Pillow suffit pour le traitement d'images

**Fichiers à analyser :**
- [ ] `utils/image_processing.py` - Vérifier les fonctions cv2 utilisées

---

## 9. Base de données

### ✅ Migrations automatiques
**Problème :** Migrations SQL manuelles

**Solution :**
- Table `schema_migrations` pour tracker les migrations appliquées
- Exécution automatique au boot du bot
- Seules les nouvelles migrations sont exécutées

**Fichiers créés/modifiés :**
- [x] `utils/migrations.py` - Système de migrations avec tracking ✅
- [x] `bot.py` - Appel `run_migrations()` au démarrage ✅

---

### 🟢 Transactions DB
**Problème :** Pas de transactions pour opérations multiples

**Solution :**
```python
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute(...)
        await conn.execute(...)
```

**Fichiers à modifier :**
- [ ] `cogs/registration.py` - Inscription complète en transaction
- [ ] `cogs/sages.py` - Validation/refus en transaction

---

## 10. Fonctionnalités utilisateur

### 🟠 Gestion des joueurs : annule et remplace
**Problème :** Un membre ne peut pas supprimer un joueur mal orthographié

**Solution :** Lors de la re-saisie des joueurs (via `!inscription` ou `!joueur`), remplacer complètement les joueurs existants au lieu de les ajouter.

```python
# Flow actuel:
# 1. Membre a ["Player1", "Playeur2"]  (typo)
# 2. !joueur -> ajoute "Player2"
# 3. Résultat: ["Player1", "Playeur2", "Player2"]  # doublon!

# Flow proposé:
# 1. Membre a ["Player1", "Playeur2"]
# 2. !joueur -> saisit "Player1, Player2"
# 3. Résultat: ["Player1", "Player2"]  # remplacé!
```

**Fichiers à modifier :**
- [ ] `cogs/registration.py:ask_players_for_team()` - Supprimer avant d'ajouter

---

### 🟡 Commande !reset (debug/test)
**Problème :** Pour tester l'inscription, il faut modifier la BDD manuellement

**Solution :** Commande `!reset @membre` réservée aux Sages (ou mode debug) :
- Supprime tous les joueurs du membre
- Remet `approval_status = pending`
- Remet `charte_validated = false`
- Permet de relancer `!inscription` proprement

**Fichiers à créer/modifier :**
- [ ] `cogs/sages.py` - Ajouter commande `cmd_reset()`

---

### 🔴 Sélection intelligente des utilisateurs
**Problème :** `_find_member_by_name()` retourne le premier résultat sans avertir si plusieurs correspondent

**Solution :** Créer `utils/discord_helpers.py` avec fonction intelligente :

```python
async def find_member(bot, search: str, require_unique: bool = False):
    """
    Cherche par username OU display_name.

    Returns:
        (members_list, warning_message)
        Si require_unique=True et plusieurs résultats -> (None, error)
    """
```

**Règle simple :**
- **Lecture/affichage** → plusieurs membres OK
- **Écriture/modification** → un seul membre à la fois

**Cas d'utilisation identifiés :**

| Commande | `require_unique` | Type | Raison |
|----------|------------------|------|--------|
| `!valider @nom` | `True` | Écriture | Promotion irréversible |
| `!refuser @nom` | `True` | Écriture | Action destructive |
| `!reset @nom` | `True` | Écriture | Suppression données |
| `!profil-admin @nom` | `False` | Lecture | Affichage uniquement |

**Fichiers à créer/modifier :**
- [ ] `utils/discord_helpers.py` - Nouvelle fonction `find_member()`
- [ ] `cogs/sages.py` - Utiliser la nouvelle fonction

---

### 🟢 Export des permissions Discord
**Problème :** Pas de vue d'ensemble des droits par salon/rôle

**Solution :** Commande `!audit-permissions` (Sages uniquement) :
- Liste tous les salons avec leurs permissions par rôle
- Exporte en CSV ou fichier texte
- Documente les overwrites spécifiques

```python
@commands.command(name="audit-permissions")
@sage_only()
async def audit_permissions(self, ctx):
    """Exporte les permissions par salon et par rôle en CSV."""
```

**Fichiers à créer/modifier :**
- [ ] `cogs/sages.py` - Ajouter commande
- [ ] `docs/COMMANDS.md` - Documenter la commande

---

## Ordre de priorité suggéré

### Phase 1 - Stabilisation ✅ TERMINÉE
1. ✅ Ajouter logging aux try/except
2. ✅ Corriger les requêtes N+1
3. ✅ Créer `constants.py`

### Phase 2 - Qualité du code ✅ TERMINÉE
4. ✅ Sélection intelligente utilisateurs
5. ✅ Gestion joueurs : annule et remplace
6. ✅ Créer `utils/discord_helpers.py`
7. ⏳ Refactoriser `registration.py` (reporté)

### Phase 3 - Outils de debug/admin ✅ TERMINEE
8. ✅ Commande `!reset` pour tests
9. ✅ Commande `!audit-permissions` (par role, format ASCII)

### Phase 3bis - Correctifs et ameliorations ✅ TERMINEE
10. ✅ Rappel charte a la connexion (Membres/Sages sans charte validee)
11. ✅ Privacy localisation : `location_display` (pays/region) dans profil-admin
12. ✅ Nettoyage ancien systeme charte (tables Charte, Validation_charte, charte.json)
13. ✅ Gestion commande inconnue (`on_command_error`)

### Phase 4 - Tests ✅ TERMINEE
14. ✅ Setup pytest (pyproject.toml, conftest.py)
15. ✅ Tests des validateurs (38 tests)
16. ✅ Tests des modeles (42 tests: Player, Team, UserProfile)
17. ✅ Tests i18n (20 tests)
**Total: 100 tests passants**

### Phase 5 - Amelioration continue ✅ TERMINEE
18. ✅ Cache TTL pour profils (utils/cache.py)
19. ✅ Rate limiting (utils/rate_limit.py)
20. ✅ Validation Pydantic (models/schemas.py)
21. ✅ Nettoyage dependances (pyproject.toml simplifie)
**Total: 183 tests passants (+83 nouveaux)**

---

## Suivi des modifications

| Date | Modification | Auteur |
|------|--------------|--------|
| 27/12/2024 | Creation du document | Claude |
| 27/12/2024 | Phase 1 terminee : logging, N+1, constants.py | Claude |
| 27/12/2024 | Ajout section 10 (fonctionnalites) + reorg phases | Claude |
| 27/12/2024 | Phase 2 + Phase 3 terminees | Claude |
| 27/12/2024 | Phase 3bis : rappel charte, privacy loc, nettoyage tables | Claude |
| 27/12/2024 | Phase 4 terminee : 100 tests (validators, i18n, models) | Claude |
| 27/12/2024 | Phase 5 terminee : cache, rate limiting, Pydantic schemas | Claude |

