# PRD v4 — Dataloger (Datalogueur EM06)

> Document produit dérivé par rétro-ingénierie du code et de la documentation existante.  
> Date de référence : 2026-06-28. Complète `cahier_des_charges_v3.md`.

## 1. Contexte et problème

Un foyer équipé d'un compteur **Refoss EM06P** (6 circuits, consommation et production) et de sondes **Tuya** (température / humidité) a besoin d'un outil local pour :

- suivre la consommation et la production en quasi temps réel ;
- comparer avec le compteur EDF et le générateur ;
- détecter les anomalies de collecte ;
- conserver un historique exploitable (audit, analyse, export).

L'application Refoss native ne suffit pas : il faut une solution **auto-hébergée**, **persistante**, avec **visualisation personnalisée** et **intégration climat**.

### Environnements cibles

| Environnement | Hôte | Usage |
|---------------|------|-------|
| Dev | Machine locale (ex. 192.168.1.5) | Maquette, itération rapide |
| Prod | Raspberry Pi (ex. 192.168.1.87) | Collecte 24/7, dashboard LAN |

## 2. Vision produit

**Dataloger** est un système de supervision énergétique domestique qui :

1. interroge un compteur Refoss EM06P (6 circuits) ;
2. historise les mesures en SQLite ;
3. expose une API REST FastAPI ;
4. affiche un dashboard web (puissance, énergie, qualité des données, climat Tuya) ;
5. tourne en production sur Raspberry Pi avec déploiement reproductible.

## 3. Objectifs produit

| Objectif | Indicateur de succès |
|----------|---------------------|
| Fiabilité collecte 24/7 | `sensor=connected` en continu, uptime service > 99 % |
| Précision métier | Écart < 5 % vs compteur de référence sur 24 h |
| Visibilité instantanée | Refresh UI ≤ 3 s, graphe 24 h fluide |
| Traçabilité | Historique SQLite + export CSV sans erreur |
| Qualité données | Score confiance ≥ 80 % en conditions normales |
| Exploitation simple | Déploiement Raspberry en une commande |

## 4. Personas

| Persona | Besoin principal |
|---------|------------------|
| Propriétaire / utilisateur | Voir conso/prod, tendances, estimation facture |
| Développeur / admin | Déployer, diagnostiquer, purger, importer historique |
| Analyste | Exporter CSV, comparer périodes, comparaison année sur année |

## 5. Architecture fonctionnelle (état actuel)

```
Capteurs                    Backend (FastAPI)              Client
─────────                   ─────────────────              ──────
Refoss EM06P ──HTTP RPC──►  CollectorService ──► SQLite ──► API REST ──► Navigateur
                            (thread polling)                  │
Sondes Tuya ──script──────►  fichiers JSON/CSV ──────────────┘
                            (service systemd séparé)
```

### Couches logicielles

| Couche | Fichiers | Rôle |
|--------|----------|------|
| API | `src/api/main.py` | Endpoints REST, montage statique, qualité, historique journalier |
| Collecteur | `src/collector/service.py` | Boucle polling, intégration Left-Riemann, lissage / outliers |
| Source capteur | `src/collector/em06_client.py` | Multi-mode : RPC Refoss, MQTT, Meross, HTTP JSON, mock |
| Persistance | `src/db/repository.py` | Mesures + événements système |
| Frontend | `static/` | SPA vanilla JS + Chart.js |
| Exploitation | `tools/`, `scripts/`, `systemd/` | Export, import, déploiement, capture Tuya |

## 6. Périmètre fonctionnel

### 6.1 Collecte énergétique — P0 (implémenté)

- Polling périodique configurable (`POLL_SECONDS`, défaut 3 s).
- Support multi-mode capteur avec priorité `refoss_local_socket` (HTTP RPC Digest, `Em.Status.Get`).
- 6 canaux indépendants : `a1`, `b1`, `c1`, `a2`, `b2`, `c2` (conso / prod kWh).
- Intégration Left-Riemann pour index kWh cumulés.
- Lissage et filtrage outliers (hors mode Refoss direct).
- Journalisation erreurs dans `system_events`.
- Interdiction données simulées en production (`REFOSS_ALLOW_SIMULATED_FALLBACK=0`).

### 6.2 Persistance — P0 (implémenté)

- SQLite : mesures horodatées UTC, totaux, tension, fréquence, facteur de puissance, `quality_flag`.
- Reprise d'état au redémarrage (rechargement dernier index kWh).

### 6.3 API REST — P0 (implémenté)

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Santé serveur |
| `GET /api/status` | État capteur, mode, erreurs, config Tuya |
| `GET /api/measurements/latest` | Dernière mesure + fraîcheur |
| `GET /api/measurements` | Historique filtré (minutes, limit) |
| `GET /api/quality/latest` | Score confiance, alertes, comportement UI |
| `GET /api/energy/today` | Agrégats journaliers C1/A2 (léger, Pi 2) |
| `GET /api/history/daily-summary` | Stats journalières, YoY, 12 mois |
| `GET /api/refoss/compare-live` | Comparaison puissance RPC vs reconstruction locale |
| `GET /api/temperature/latest` | Dernière mesure Tuya |
| `GET /api/temperature/history` | Historique Tuya |

### 6.4 Interface web — P0 (implémenté)

**Dashboard**

- Cartes puissance consommation / générateur (signée), tension, fréquence.
- Carte Tuya : température, humidité, MAC, âge mesure.
- Canaux configurables (types : EDF total, générateur, consommation, non utilisé).
- Graphe unifié Chart.js (conso + température / humidité).
- Estimation facture basique (tarif achat, revente optionnelle).
- Bannière qualité + désactivation recommandations si données suspectes.

**Historique**

- Tableau paginé des mesures.
- Résumé statistique : records, moyenne 7 j, comparaison année sur année, 12 mois.

**Paramètres**

- Intervalle refresh, fenêtre graphe, tarifs, types de canaux, association sondes Tuya (localStorage).

### 6.5 Extension climat Tuya — P1 (implémenté)

- Service séparé `datalogger-tuya.service` → `tools/tuya_temperature_capture.py`.
- Modes capture : local, cloud, auto.
- Multi-sondes via `TUYA_TARGET_MACS`.
- Graphe combiné électricité + climat.

### 6.6 Exploitation — P1 (implémenté)

- Export CSV (`tools/export_all_values.py`).
- Purge historique (`tools/reset_measurements_sqlite.py`).
- Import historique EM06 (`tools/import_em06_history_csv.py`).
- Déploiement Windows → Raspberry (`scripts/deploy_raspberry.ps1`).
- Profils env dev / prod, diagnostic (`scripts/doctor.sh`).

### 6.7 Hors périmètre v1

- Prévision charge / production.
- Facturation multi-tarifs (HP/HC, abonnement).
- Multi-sites / multi-utilisateurs.
- Authentification web (table `users` prévue mais inactive).
- Réception webhooks EM06.
- Application mobile native.
- Alertes push / email.

## 7. Modèle de données et règles métier

### Canaux EM06P

| Canal | Rôle métier (installation) |
|-------|------------------------------|
| **c1** | **Réseau EDF** — mesure à la sortie du circuit électrique ; référence des kWh facturés (net = prélèvement − injection ; **négatif** si excédent PV) |
| **a2** | **Photovoltaïque** — générateur (production) |
| **b2, c2** | Consommateurs monitorés |
| **a1, b1** | Non utilisés (masqués) |

### Bilan énergétique

En règle générale :

`C1 ≈ B2 + A2 + C2 + appareils non monitorés`

- **C1** est la référence EDF (prélèvement réseau − injection réseau).
- Si la production PV (**A2**) dépasse la consommation totale du foyer, **C1 devient négatif** (excédent exporté).
- **Autoconsommation PV** (journalière) : `max(0, production_A2 − injection_C1)`.
- **Taux d'autoconsommation** : `autoconsommation / production_A2 × 100` (si production > 0).

L'historique journalier et le graphe 12 mois s'appuient sur **C1** (prélèvement réseau) et **A2** (production PV), pas sur la somme brute de tous les canaux.

Configurable par l'utilisateur dans Paramètres (localStorage) pour les libellés et l'affichage graphe.

### Pipeline de traitement

1. Lecture instantanée (W ou kW selon la source).
2. Lissage (moyenne mobile 4 échantillons, filtre outliers 50 %) — sauf mode `refoss_local_socket`.
3. Intégration Left-Riemann → index kWh cumulés persistés.
4. Frontend recalcule la puissance instantanée W à partir des deltas kWh / temps.

### Règles de validation

- Puissance instantanée ∈ [-6000 W, 9000 W].
- Index cumulés ne doivent pas reculer (alerte qualité).
- Gap collecte : alerte si intervalle > `max(POLL_SECONDS × 3, 30)` s.
- `quality_flag = 1` : valide ; autre : suspect (import historique, mock).
- Recommandations UI bloquées si statut qualité ≠ `valide`.

## 8. Exigences non fonctionnelles

| Domaine | Exigence |
|---------|----------|
| Performance | API < 200 ms en local ; collecte non bloquante (thread daemon) |
| Disponibilité | Restart automatique systemd ; tolérance erreurs capteur |
| Sécurité | Credentials capteur en `.env` ; pas de secrets en git ; API LAN uniquement |
| Maintenabilité | Architecture modulaire API / collecteur / client / DB |
| Observabilité | `/api/status`, `/api/quality/latest`, table `system_events` |
| Portabilité | Python 3.11+, Linux ARM (Raspberry), dev Windows |

## 9. Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.11+, FastAPI 0.115, Uvicorn |
| Base | SQLite |
| Frontend | HTML / CSS / JS vanilla, Chart.js |
| IoT EM06 | HTTP RPC Digest, paho-mqtt, requests |
| IoT Tuya | tinytuya 1.17 |
| Déploiement | systemd, scripts PowerShell, SSH |

## 10. Critères d'acceptation globaux

- [ ] Service stable 24 h sans crash.
- [ ] `sensor=connected` avec source réelle EM06P.
- [ ] Écart mesure acceptable vs compteur de référence.
- [ ] Export CSV complet sans erreur.
- [ ] UI cohérente (statut + cartes + graphe + qualité).
- [ ] Tuya affiché si service actif.
- [ ] Déploiement Raspberry reproductible.

## 11. Risques et dépendances

| Risque | Impact | Mitigation |
|--------|--------|------------|
| API Refoss propriétaire / variantes firmware | Collecte instable | Multi-variantes RPC, endpoint compare-live |
| MQTT local indisponible | Mode secours limité | Prioriser HTTP RPC |
| Sondes Tuya « paresseuses » | Trous température | Mode watch + min-delta |
| Pas de tests automatisés | Régressions calculs | Lot A du plan de développement |
| API sans auth | Accès LAN non contrôlé | Hors scope v1, documenter |

## 12. Références

- `docs/cahier_des_charges_v3.md` — cahier des charges initial
- `docs/architecture_et_plan_developpement.md` — architecture (juin 2026)
- `docs/installation_rapide.md` — guide d'installation et exploitation
- `docs/guide_interface_web.md` — guide interface
- API Refoss EM06P : https://docs.refoss.net/open-api/devices/em06p
