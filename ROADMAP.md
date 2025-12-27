# Plan d'évolution technique - Bot Discord This Is PSG

> Document de référence pour les améliorations techniques du projet.
> Dernière mise à jour : 27/12/2024

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

### 🟡 Cache des données fréquentes
**Problème :** Profils rechargés plusieurs fois dans le même flow

**Solution :**
- Implémenter un cache simple (TTL 60s) pour les profils
- Utiliser `@lru_cache` ou `cachetools` pour les rôles

**Fichiers à créer/modifier :**
- [ ] `utils/cache.py` - Nouveau module de cache
- [ ] `models/user_profile.py` - Intégrer le cache
- [ ] `utils/roles.py` - Cache pour `get_role()`

---

### 🟡 Rate limiting
**Problème :** Pas de protection contre les abus

**Solution :**
- Ajouter un décorateur `@rate_limit(calls=5, period=60)`
- Appliquer sur `!inscription`, `!localisation`

**Fichiers à créer/modifier :**
- [ ] `utils/rate_limit.py` - Nouveau module
- [ ] `cogs/registration.py` - Appliquer le décorateur

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

### 🟡 Cohérence du nommage des langues
**Problème :** `lang.upper() == "FR"` vs `lang.lower() == "fr"` mélangés

**Solution :**
- Toujours stocker en minuscules dans la DB
- Normaliser dès la réception : `lang = lang.lower()`
- Créer un helper : `utils/i18n.py:normalize_lang()`

**Fichiers à modifier :**
- [ ] `utils/i18n.py` - Ajouter `normalize_lang()`
- [ ] `cogs/registration.py` - Normaliser à la source
- [ ] `models/user_profile.py` - Normaliser dans `set_language()`

---

### 🟡 Nommage des classes Cog
**Problème :** `PrivateCommands` au lieu de `PrivateCommandsCog`

**Solution :** Renommer pour cohérence :
- `PrivateCommands` → `PrivateCommandsCog`

**Fichiers à modifier :**
- [ ] `cogs/private.py` - Renommer la classe

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

### 🟢 Nettoyer les TODOs obsolètes
**Problème :** `cogs/events.py:67` - TODO obsolète

**Solution :** Supprimer ou implémenter les TODOs restants

**Fichiers à vérifier :**
- [ ] `cogs/events.py` - Ligne 67
- [ ] Grep global pour "TODO" et "FIXME"

---

## 6. Tests

### 🔴 Framework de tests
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
│   └── test_player.py
├── test_utils/
│   ├── test_validators.py
│   └── test_i18n.py
└── test_cogs/
    └── test_registration.py
```

**Fichiers à créer :**
- [ ] `tests/conftest.py` - Fixtures de base
- [ ] `tests/test_utils/test_validators.py` - Tests des validateurs
- [ ] `tests/test_models/test_user_profile.py` - Tests du modèle
- [ ] `pytest.ini` ou section dans `pyproject.toml`

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

### 🟡 Validation avec Pydantic
**Problème :** Validation manuelle, risque d'oubli

**Solution :**
```python
# models/schemas.py
from pydantic import BaseModel, validator

class PlayerCreate(BaseModel):
    player_name: str
    team_id: int

    @validator('player_name')
    def validate_name(cls, v):
        if len(v) < 2 or len(v) > 50:
            raise ValueError('Nom invalide')
        return v.strip()
```

**Fichiers à créer/modifier :**
- [ ] `models/schemas.py` - Schémas Pydantic
- [ ] `cogs/registration.py` - Utiliser les schémas
- [ ] `requirements.txt` - Ajouter pydantic

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

### 🟢 Nettoyer requirements
**Problème :** `requirements.txt` et `pyproject.toml` se chevauchent

**Solution :**
- Garder uniquement `pyproject.toml` (moderne)
- Générer `requirements.txt` si besoin : `pip-compile`

**Fichiers à modifier :**
- [ ] `pyproject.toml` - Source unique
- [ ] `requirements.txt` - Généré ou supprimé

---

### 🟢 Évaluer opencv-python
**Problème :** Package lourd (100+ MB) pour usage limité

**Solution :** Évaluer si PIL/Pillow suffit pour le traitement d'images

**Fichiers à analyser :**
- [ ] `utils/image_processing.py` - Vérifier les fonctions cv2 utilisées

---

## 9. Base de données

### 🟡 Migrations automatiques
**Problème :** Migrations SQL manuelles

**Solution :**
- Lancer les migrations au boot du bot
- Versionner les migrations

**Fichiers à modifier :**
- [ ] `bot.py` - Appeler les migrations au démarrage
- [ ] `scripts/run_migration.py` - Intégrer au boot

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

## Ordre de priorité suggéré

### Phase 1 - Stabilisation (1-2 jours)
1. 🔴 Ajouter logging aux try/except
2. 🔴 Corriger les requêtes N+1
3. 🟠 Créer `constants.py`

### Phase 2 - Qualité (3-5 jours)
4. 🟠 Refactoriser `registration.py`
5. 🟠 Créer `utils/discord_helpers.py`
6. 🟠 Ajouter docstrings prioritaires

### Phase 3 - Tests (2-3 jours)
7. 🔴 Setup pytest
8. 🟡 Tests des validateurs
9. 🟡 Tests des modèles

### Phase 4 - Amélioration continue
10. 🟡 Cache et rate limiting
11. 🟡 Pydantic pour validation
12. 🟢 Documentation architecture
13. 🟢 Nettoyage dépendances

---

## Suivi des modifications

| Date | Modification | Auteur |
|------|--------------|--------|
| 27/12/2024 | Création du document | Claude |
| 27/12/2024 | Phase 1 terminée : logging, N+1, constants.py | Claude |

