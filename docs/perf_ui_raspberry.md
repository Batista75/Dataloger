# Performance UI — Raspberry Pi 2

> Validé le 2026-06-29 sur Raspberry Pi 2 Model B (920 Mo RAM), service `datalogger` + SQLite ~39k mesures.

## Contexte

Le dashboard affiche beaucoup d’informations (cartes énergie, graphe 24 h, climat, historique). Sur Pi 2, la lenteur au démarrage ne venait pas d’une saturation CPU/RAM permanente du service Python, mais de **pics de charge** : gros JSON, calculs JavaScript, et requêtes SQLite répétées trop souvent.

## Optimisations implémentées

### 1. Endpoint léger `/api/energy/today`

**Avant** : le navigateur appelait `/api/measurements?from_ts_utc=<minuit>&limit=10000` toutes les **3 s**, puis calculait C1/A2 côté client.

**Après** : une requête SQL agrégée (`MIN`/`MAX` sur les index cumulés depuis minuit local) renvoie directement les métriques métier :

| Champ | Description |
|-------|-------------|
| `c1_net_kwh` | Réseau EDF net (prélèvement − injection) |
| `a2_production_kwh` | Production PV |
| `conso_reelle_kwh` | C1 + A2 |
| `conso_fact_kwh` | max(0, C1) |
| `surplus_kwh` | \|C1\| si C1 < 0 |
| `autoconso_kwh` | A2 − surplus |
| `taux_autoconso_pct` | Autoconso / A2 × 100 |
| `taux_autoproduction_pct` | Autoconso / conso réelle × 100 |

Paramètre : `from_ts_utc` = minuit **local** du navigateur en ISO UTC (ex. `2026-06-28T22:00:00.000Z` pour Paris été).

Logique partagée : `src/core/energy_metrics.py`.

### 2. Séparation chargement léger / lourd

| Couche | Contenu | Intervalle par défaut |
|--------|---------|------------------------|
| **Léger** (`updateAllData`) | `/api/status`, `/api/measurements/latest`, `/api/temperature/latest` | **5 s** |
| **Énergie jour** (`refreshTodayEnergy`) | `/api/energy/today` | **45 s** |
| **Graphe puissance** (`refreshPowerAnalytics`) | `/api/measurements` (24 h, max 3000 lignes) | **60 s** |
| **Graphe climat** (`refreshClimateAnalytics`) | `/api/temperature/history` (max 3000 lignes) | **60 s** |
| **Qualité** | `/api/quality/latest` | **5 min** (inchangé) |
| **Historique résumé** | `/api/history/daily-summary` | À l’ouverture de l’onglet + cache 24 h |

Au **démarrage** : affichage immédiat du léger, puis chargement différé (~80 ms) des trois flux lourds en parallèle (`scheduleBootHeavyLoads`).

### 3. Plafonds d’échantillons graphes

- Puissance : `CHART_MAX_SAMPLE_LIMIT = 3000` (au lieu de 5000)
- Climat : `CLIMATE_MAX_SAMPLE_LIMIT = 3000` (au lieu de 10000)

## Intervalles configurables (frontend)

Dans `static/js/app.js` → objet `CONFIG` :

```javascript
REFRESH_INTERVAL: 5000,           // statut / dernière mesure
TODAY_ENERGY_REFRESH_MS: 45000,  // cartes kWh + facture jour
CHART_REFRESH_INTERVAL: 60000,    // graphes 24 h
CHART_MAX_SAMPLE_LIMIT: 3000,
CLIMATE_MAX_SAMPLE_LIMIT: 3000,
```

L’intervalle de rafraîchissement global (Paramètres → secondes) ne concerne que la couche **légère**.

## Résultats mesurés (Pi 2, 2026-06-29)

| Endpoint | Temps | Taille réponse | Notes |
|----------|-------|----------------|-------|
| `/api/energy/today` | **~0,19 s** | **~430 o** | Agrège ~10k mesures du jour en SQL |
| `/api/measurements/latest` | ~0,01 s | ~630 o | Couche légère boot |
| `/api/status` | ~0,01 s | — | Couche légère boot |
| `/api/measurements?limit=3000` (24 h) | ~1,1 s | ~1,6 Mo | Graphe uniquement, toutes les 60 s |

**Avant** (mesure comparable) : `/api/measurements?limit=10000` pour le jour toutes les 3 s ≈ **1–3 s** et **plusieurs Mo** à chaque appel.

Charge API typique après optimisation :

- **~0,15 req/s** en régime établi (léger 5 s + agrégats 45–60 s), au lieu de pics **>1 req/s** avec 10k+ lignes toutes les 3 s.

## Recommandations d’usage Pi 2

1. Consulter le dashboard depuis un **PC/tablette** sur le LAN plutôt que Chromium sur le Pi (le navigateur local consomme autant que l’API).
2. Masquer les canaux inutilisés (Paramètres) pour alléger le graphe.
3. Réduire `CHART_HOURS` à 12 h si le graphe reste lent.
4. Ne pas descendre `TODAY_ENERGY_REFRESH_MS` sous 30 s sur Pi 2.

## Fichiers concernés

| Fichier | Rôle |
|---------|------|
| `src/core/energy_metrics.py` | Formules métier C1/A2 |
| `src/db/repository.py` | `get_energy_deltas_since()` |
| `src/api/main.py` | `GET /api/energy/today` |
| `static/js/app.js` | Throttle, boot différé, appels API |

## Évolutions possibles

- Endpoint `/api/measurements/chart` avec agrégation serveur (bucket 5 min) pour supprimer le calcul W côté navigateur.
- Pré-calcul nocturne des totaux journaliers en base.
- Migration matérielle Pi 4/5 si usage navigateur embarqué fréquent.
