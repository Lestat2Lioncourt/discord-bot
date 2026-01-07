# Bot Discord This Is PSG

Bot Discord pour la team **This Is PSG** sur Tennis Clash.

## Chiffres clés

| Métrique | Valeur |
|----------|--------|
| **Version** | 1.1.0 |
| **Lignes de code** | 9 336 |
| **Fichiers Python** | 47 |
| **Commandes** | 25 |
| **Tests automatisés** | 196 |
| **Langues** | FR, EN |

---

## Commandes utilisateur

| Commande | Aliases | Description |
|----------|---------|-------------|
| `!inscription` | - | Lance le processus d'inscription |
| `!profil` | `!profile` | Affiche ton profil |
| `!joueur` | `!player`, `!joueurs` | Modifie tes joueurs Tennis Clash |
| `!localisation` | `!location`, `!loc` | Définit ta position sur la carte |
| `!langue` | `!language`, `!lang` | Change la langue (FR/EN) |
| `!carte` | `!map` | Lien vers la carte des membres |
| `!stats` | `!statistiques` | Statistiques de la communauté |
| `!capture` | `!cap` | Analyse une capture Tennis Clash |
| `!evolution` | `!evo`, `!history` | Évolution d'un personnage |
| `!compare` | `!cmp` | Compare un personnage entre joueurs |
| `!site` | `!website` | Lien vers le site de la team |
| `!users` | `!membres` | Liste des membres enregistrés |
| `!pseudo` | `!nick` | Modifie ton pseudo Discord |
| `!template` | - | Traite une image OCR (legacy) |
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
