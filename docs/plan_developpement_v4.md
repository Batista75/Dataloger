# Plan de développement v4 — Dataloger

> Plan dérivé par rétro-ingénierie du code et de la documentation existante.  
> Date de référence : 2026-06-28. Complète `architecture_et_plan_developpement.md`.

## 1. État des lieux (juin 2026)

### 1.1 Maturité par domaine

| Domaine | Maturité | Commentaire |
|---------|----------|-------------|
| API FastAPI | ✅ Mature | Endpoints riches : qualité, historique journalier, compare-live |
| Collecteur + Left-Riemann | ✅ Opérationnel | Mode Refoss direct sans lissage |
| Client EM06 RPC | ✅ Fonctionnel | Digest auth, parsing multi-format (`em:<id>`, status list) |
| Frontend | ✅ Riche | Dashboard, historique, paramètres, Chart.js, estimation facture |
| Tuya | ✅ Opérationnel | Service systemd séparé, API lecture fichiers JSON/CSV |
| Tests automatisés | ❌ Absents | Priorité haute |
| Auth UI | ❌ Non implémenté | Table `users` en base, inactive |
| Documentation | ⚠️ Partielle | Docs juin 21 ; code plus avancé (qualité, Tuya, compare-live) |

### 1.2 Architecture technique (rappel)

```
src/api/main.py          → API REST + static/
src/collector/service.py → Boucle collecte, Left-Riemann, lissage
src/collector/em06_client.py → Modes capteur (RPC, MQTT, Meross, HTTP, mock)
src/db/repository.py     → SQLite measurements + system_events
static/js/app.js         → UI dashboard / historique / paramètres
tools/                   → Export, import, reset, capture Tuya
scripts/                 → Dev local, déploiement Raspberry
systemd/                 → datalogger.service + datalogger-tuya.service
```

### 1.3 Point technique principal

La collecte réelle EM06P passe par **HTTP JSON-RPC** (`/rpc/Em.Status.Get`) avec authentification Digest. Le collecteur :

- lit la puissance instantanée RPC (mode `refoss_local_socket`) ;
- intègre en index kWh cumulés via Left-Riemann ;
- persiste en SQLite pour historique et dérivation frontend.

Les modes de compatibilité (`mqtt_json`, `meross_local_post`, `http_json`, `mock`) restent disponibles en secours ou dev.

### 1.4 Ce qui est solide

- API stable et lisible.
- Séparation claire API / collecteur / source capteur / DB.
- Scripts d'exploitation utiles (export, import, reset, nettoyage).
- Frontend fonctionnel avec règles métier (canaux, qualité, facture).
- Déploiement reproductible dev → Raspberry.

### 1.5 Risques actuels

- Dépendance à l'API Refoss locale (credentials, firmware).
- Risque métier si fallback simulé activé en production.
- Absence de tests de non-régression sur les calculs kWh / W.
- API et UI sans authentification (LAN uniquement).

---

## 2. Roadmap par lots

### Lot 0 — Stabilisation production (immédiat, 1–2 semaines)

**Objectif** : garantir des mesures fiables en prod Raspberry.

| # | Action | Definition of Done |
|---|--------|-------------------|
| 0.1 | Valider config prod : `EM06_MODE=refoss_local_socket`, credentials Digest, `REFOSS_ALLOW_SIMULATED_FALLBACK=0` | 24 h `sensor=connected` |
| 0.2 | Valider `/api/refoss/compare-live` : écart < 10 % vs RPC natif | Rapport comparaison documenté |
| 0.3 | Vérifier intégrité index kWh post-redémarrage | Pas de saut cumulatif anormal |
| 0.4 | Activer monitoring basique : cron `doctor.sh` + alerte manuelle si `sensor=error` | Checklist ops rédigée |

**Décision immédiate** : conserver `REFOSS_ALLOW_SIMULATED_FALLBACK=0` en environnement réel.

---

### Lot A — Qualité des données (2–3 semaines)

**Objectif** : verrouiller les calculs et éviter les régressions.

| # | Action | Fichiers cibles |
|---|--------|-----------------|
| A.1 | Tests unitaires `_extract_signed_power_w`, `_apply_20s_integration`, outliers | `tests/test_collector.py` |
| A.2 | Tests parsing RPC Refoss (variantes `em:<id>`, status list) | `tests/test_em06_client.py` |
| A.3 | Tests endpoint `/api/quality/latest` | `tests/test_api_quality.py` |
| A.4 | CI minimale (pytest sur push) | `.github/workflows/ci.yml` |

**Definition of Done** : couverture calculs critiques > 80 %, CI verte.

---

### Lot B — Exploitation et observabilité (2 semaines)

**Objectif** : faciliter le run en production.

| # | Action |
|---|--------|
| B.1 | Endpoint `/api/events/recent` (derniers événements `system_events`) |
| B.2 | Affichage erreurs récentes dans l'UI (dashboard ou paramètres) |
| B.3 | Rotation / purge automatique `system_events` et vieux CSV Tuya |
| B.4 | Checklist rollback documentée (restore `.env` + backup DB) |
| B.5 | Backup SQLite planifié (cron quotidien sur Raspberry) |

---

### Lot C — Enrichissements métier (3–4 semaines)

**Objectif** : valeur utilisateur sans sur-ingénierie.

| # | Action | Priorité |
|---|--------|----------|
| C.1 | Tarification HP/HC configurable (2 créneaux) | P2 |
| C.2 | Export CSV depuis l'UI (bouton, pas seulement CLI) | P2 |
| C.3 | Purge historique depuis l'UI (avec confirmation) | P2 |
| C.4 | Alertes simples (seuil puissance, capteur offline > 5 min) | P3 |
| C.5 | Corrélation conso / température (insights basiques) | P3 |

---

### Lot D — Sécurité et multi-utilisateur (optionnel, v2)

| # | Action |
|---|--------|
| D.1 | Auth basique API (token ou session) |
| D.2 | Exploitation table `users` + login UI |
| D.3 | HTTPS reverse proxy (nginx / Caddy) si exposition hors LAN |

---

### Lot E — Évolutions capteur (backlog)

| # | Action | Condition |
|---|--------|-----------|
| E.1 | Consommation webhooks EM06 | URL webhook configurée sur device |
| E.2 | Mode MQTT si broker confirmé | Tests ports réseau OK |
| E.3 | Cloud API Refoss officielle | Credentials app disponibles |
| E.4 | Finaliser ou retirer `refoss_local_client.py` (UDP mock) | RPC HTTP stable en prod |

---

## 3. Priorisation

```
P0 (maintenant)   → Lot 0 : stabilisation prod
P1 (ce mois)      → Lot A : tests calculs
P2 (mois suivant) → Lot B : ops + Lot C.1–C.3
P3 (backlog)      → Lot C.4–C.5, Lot D, Lot E
```

---

## 4. Décisions techniques à trancher

| # | Question | Recommandation |
|---|----------|----------------|
| 1 | Garder le mode mock en dev uniquement ? | Oui, via profil `.env.dev` |
| 2 | Tuya intégré au processus principal ou service séparé ? | Garder séparé (découplage, redémarrage indépendant) |
| 3 | Source de vérité puissance : RPC Refoss vs Left-Riemann ? | RPC en lecture ; Left-Riemann pour index kWh persistés |
| 4 | Tests E2E UI (Playwright) ou tests API seuls d'abord ? | Tests API + calculs d'abord ; E2E ensuite |

---

## 5. Outils d'exploitation (inventaire)

| Outil | Usage |
|-------|-------|
| `tools/export_all_values.py` | Export CSV complet |
| `tools/reset_measurements_sqlite.py` | Purge mesures |
| `tools/import_em06_history_csv.py` | Import historique EM06 |
| `tools/backfill_left_riemann_day.py` | Reconstruction intégration |
| `tools/retro_clean_power_outliers.py` | Nettoyage outliers |
| `tools/zero_pre_switch_consumption.py` | Remise à zéro pré-bascule |
| `tools/tuya_temperature_capture.py` | Collecte Tuya local / cloud / auto |
| `scripts/dev_start.ps1` | Lancement dev local Windows |
| `scripts/deploy_raspberry.ps1` | Déploiement prod Raspberry |
| `scripts/doctor.sh` | Diagnostic rapide |
| `scripts/setup.sh` | Installation initiale Raspberry |

---

## 6. Workflow de développement recommandé

1. Maquetter en local : `./scripts/dev_start.ps1`
2. Valider API : `/health`, `/api/status`, `/api/measurements/latest`
3. Valider UI : dashboard, graphe, qualité
4. Commit Git local
5. Déployer Raspberry : `./scripts/deploy_raspberry.ps1`
6. Vérifier post-déploiement : `curl /health`, `systemctl status datalogger`

---

## 7. Références

- `docs/PRD_v4.md` — product requirements document
- `docs/cahier_des_charges_v3.md` — cahier des charges initial
- `docs/architecture_et_plan_developpement.md` — architecture (juin 2026)
- `docs/installation_rapide.md` — installation et configuration
- `docs/guide_interface_web.md` — guide interface web
