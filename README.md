# Bot Discord This Is PSG

Bot Discord pour la team **This Is PSG** sur Tennis Clash.

## Chiffres clés

| Métrique | Valeur |
|----------|--------|
| **Version** | 2.0.0 |
| **Lignes de code** | 12 701 |
| **Fichiers Python** | 53 |
| **Commandes** | 26 |
| **Tests automatisés** | 196 |
| **Langues** | FR, EN |

---

## Commandes utilisateur

### Inscription & Profil

| Commande | Aliases | Description |
|----------|---------|-------------|
| `!inscription` | - | Lance le processus d'inscription |
| `!profil` | `!profile` | Affiche ton profil |
| `!joueur` | `!player`, `!joueurs` | Modifie tes joueurs Tennis Clash |
| `!localisation` | `!location`, `!loc` | Définit ta position sur la carte |
| `!langue` | `!language`, `!lang` | Change la langue (FR/EN) |
| `!pseudo` | `!nick` | Modifie ton pseudo Discord |

### Stats Joueurs (Tennis Clash)

| Commande | Aliases | Description |
|----------|---------|-------------|
| `!capture` | `!cap` | Soumet une capture d'écran pour analyse IA |
| `!captures` | `!stats-list` | Liste tes captures enregistrées |
| `!evolution` | `!evo`, `!history` | Évolution d'un personnage dans le temps |
| `!compare` | `!cmp` | Compare un personnage entre joueurs |
| `!builds` | `!profils` | Liste les joueurs par type de build |

### Communauté

| Commande | Aliases | Description |
|----------|---------|-------------|
| `!carte` | `!map` | Lien vers la carte des membres |
| `!stats` | `!statistiques` | Statistiques de la communauté |
| `!site` | `!website` | Lien vers le site de la team |
| `!users` | `!membres` | Liste des membres enregistrés |
| `!db_status` | - | Vérifie la connexion BDD |

---

## Commandes Sages (modérateurs)

| Commande | Aliases | Description |
|----------|---------|-------------|
| `!pending` | `!attente` | Liste les inscriptions en attente |
| `!valider` | `!approve` | Valide un membre |
| `!refuser` | `!refuse` | Refuse un membre |
| `!delete` | `!supprimer` | Supprime un membre (RGPD) |
| `!check_users` | - | Renvoie toutes les notifications |
| `!profil-admin` | - | Voir le profil complet d'un membre |
| `!audit-permissions` | `!perms` | Export des droits Discord |
| `!metrics` | `!status` | Statistiques techniques du bot |
| `!reset` | - | Réinitialise un membre (debug) |
| `!sudo` | - | Droits Sage temporaires (debug) |

---

## Santé de l'application

| Aspect | Note | État |
|--------|------|------|
| Structure | 9/10 | Excellente |
| Qualité du code | 8/10 | Bonne |
| Sécurité | 8/10 | Bonne |
| Maintenabilité | 8/10 | Bonne |
| Fiabilité | 8/10 | Bonne |
| Performance | 8/10 | Bonne |
| Tests | 6/10 | Correcte |
| Documentation | 8/10 | Bonne |
| **Score global** | **7.9/10** | Bon |

---

## Installation

1. Cloner le repository
2. Copier `.env.example` vers `.env` et configurer
3. Installer les dépendances : `pip install -e .`
4. Lancer : `python bot.py`

## Documentation technique

- [Architecture](docs/ARCHITECTURE.md) - Structure du code
- [Roadmap](ROADMAP.md) - Plan d'évolution et audits
- [SSH Setup](docs/SSH_SETUP.md) - Configuration serveur

---

*Dernière mise à jour : Janvier 2026*
