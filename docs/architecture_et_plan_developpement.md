# Architecture et plan de developpement

## 1. Situation au 2026-06-21

### 1.1 Etat global
- API FastAPI operationnelle sur le Raspberry.
- Frontend web deploye et charge correctement (index, js, css servis).
- Pipeline collecteur actif avec integration a pas fixe 20s + lissage + filtrage outliers.
- Export et reset SQLite disponibles via scripts outils.

### 1.2 Point bloquant principal
- La source reelle Refoss n est pas encore exploitable.
- En mode `refoss_local_socket`, le parser local n est pas implemente quand le fallback simule est coupe.
- Les essais HTTP locaux sur `192.168.1.27:80` montrent:
	- `GET /config` -> 405
	- `POST /config` -> connexion fermee sans reponse
	- comportement compatible avec un protocole signe/proprietaire.

### 1.3 Consequence fonctionnelle
- Tant que la source reelle n est pas branchee, le service est soit:
	- en erreur (fallback simule desactive),
	- soit en donnees simulees (non fiables metier).

## 2. Architecture technique

### 2.1 Couches
- `src/api/main.py`
	- Expose `/api/status`, `/api/measurements`, `/api/measurements/latest`.
	- Monte les fichiers statiques de `static/`.
- `src/collector/service.py`
	- Boucle de collecte.
	- Conversion en puissances signees par canal.
	- Integration Left-Riemann a pas 20s.
	- Lissage moyenne mobile et validation d outliers.
- `src/collector/em06_client.py`
	- Multiples modes: `refoss_local_socket`, `mqtt_json`, `meross_local_post`, `http_json`, mock.
- `src/collector/refoss_local_client.py`
	- Discovery UDP local.
	- Fallback mock uniquement si autorise.
	- Parser reel manquant.
- `src/db/repository.py` + `data/measurements.db`
	- Persistance des mesures + evenements.

### 2.2 Outils d exploitation
- `tools/export_all_values.py`: export CSV complet.
- `tools/reset_measurements_sqlite.py`: purge sans dependances applicatives.

## 3. Revue projet

### 3.1 Ce qui est solide
- API stable et lisible.
- Separation claire API / collecteur / source capteur / DB.
- Scripts de support utiles pour debug et operations.
- Frontend fonctionnel et deja adapte aux regles metier discutees.

### 3.2 Risques actuels
- Dependance forte a une integration capteur non finalisee.
- Risque metier si fallback simule active en production.
- Documentation incomplete (plusieurs pages vides avant cette mise a jour).

### 3.3 Priorites techniques (ordre recommande)
1. Implementer une source reelle fiable (priorite absolue).
2. Ajouter des tests de non-regression sur la conversion kWh -> W et filtres.
3. Ajouter garde-fous explicites pour interdire les donnees simulees en mode prod.
4. Finaliser la documentation d exploitation et de debug.

## 4. Plan de developpement

### Lot A - Source reelle EM06
Objectif: obtenir des mesures physiques fiables et continues.

Actions:
1. Option HTTP signee: implementer la signature locale si cle/secrets disponibles.
2. Option Cloud API: integrer endpoint officiel si credentials app disponibles.
3. Option MQTT: activer `mqtt_json` seulement si broker/topic reels confirmes.

Definition of done:
- `sensor=connected`
- pas d erreur recurrente collecteur
- mesures coherentes avec compteur de reference sur 24h.

### Lot B - Qualite donnees
Actions:
1. Tests unitaires pour `_extract_signed_power_w` et `_apply_20s_integration`.
2. Tests sur outliers et stabilisation.
3. Verification horodatage et gestion des trous de donnees.

### Lot C - Exploitation
Actions:
1. Checklist de mise en production.
2. Procedure rollback simple (config + restart service).
3. Dashboard de statut minimal (etat capteur, age derniere mesure, erreurs).

## 5. Decision immediate
- Conserver `REFOSS_ALLOW_SIMULATED_FALLBACK=0` en environnement reel.
- Travailler la prochaine iteration sur l integration source reelle avant toute optimisation UI supplementaire.
