# Architecture technique et plan de developpement

## 1. Architecture logique

### 1.1 Flux de donnees
1. Refoss EM06 expose les mesures via son protocole disponible.
2. Service collecteur lit les mesures selon une frequence fixe.
3. Les mesures sont normalisees puis stockees dans SQLite.
4. API FastAPI expose les mesures courantes et historiques.
5. Interface web tablette interroge l API toutes les 3 secondes.

### 1.2 Modules applicatifs
- module acquisition:
  - driver Refoss EM06
  - reconnexion automatique
  - validation des trames
- module stockage:
  - insertion mesures
  - requetes historiques
  - retention et purge
- module API:
  - endpoints lectures temps reel
  - endpoints historiques
  - endpoint statut systeme
- module UI:
  - dashboard principal
  - page historique
  - page parametres

## 2. Proposition de structure projet

- src/
  - collector/
    - em06_client.py
    - scheduler.py
  - db/
    - models.py
    - repository.py
    - migrations.py
  - api/
    - main.py
    - routes_measurements.py
    - routes_status.py
    - auth.py
  - web/
    - index.html
    - history.html
    - settings.html
    - assets/
      - css/
      - js/
  - core/
    - config.py
    - logger.py
- scripts/
  - setup.sh
  - update.sh
  - doctor.sh
  - backup.sh
- systemd/
  - datalogger.service
- docs/
  - cahier_des_charges_v3.md
  - architecture_et_plan_developpement.md

## 3. API locale V1 (proposition)
- GET /api/status
  - etat serveur, etat capteur, timestamp dernier point
- GET /api/measurements/latest
  - dernier echantillon
- GET /api/measurements?from=...&to=...
  - historique brut
- GET /api/measurements/aggregate?period=hour|day
  - agregations pour graphiques
- POST /api/auth/login
  - authentification locale
- POST /api/auth/logout
  - fin de session

## 4. Schema de base SQLite (V1)

Table measurements
- id INTEGER PRIMARY KEY
- ts_utc TEXT NOT NULL
- power_w REAL
- energy_kwh REAL
- voltage_v REAL
- current_a REAL
- frequency_hz REAL
- power_factor REAL
- quality_flag INTEGER DEFAULT 1

Table system_events
- id INTEGER PRIMARY KEY
- ts_utc TEXT NOT NULL
- level TEXT NOT NULL
- source TEXT NOT NULL
- message TEXT NOT NULL

Table users
- id INTEGER PRIMARY KEY
- username TEXT UNIQUE NOT NULL
- password_hash TEXT NOT NULL
- role TEXT NOT NULL DEFAULT 'admin'

## 5. Plan de developpement par etapes

### Etape 1 - Socle technique
- Initialiser le projet Python.
- Mettre en place configuration, logs, base SQLite.
- Creer le service systemd.
- Creer le parcours d installation simplifiee (setup.sh + .env.example).

### Etape 2 - Acquisition EM06
- Implementer le client de communication EM06.
- Programmer la collecte periodique.
- Ajouter reprise automatique sur erreurs.

### Etape 3 - API serveur
- Exposer endpoints statut, latest, historique.
- Ajouter authentification de base.
- Ajouter validation des parametres API.

### Etape 4 - Interface tablette personnalisee
- Concevoir dashboard tactile responsive.
- Afficher valeurs temps reel + historique 24h.
- Ajouter ecran statut et configuration.

### Etape 5 - Durcissement et exploitation
- Sauvegarde automatee SQLite.
- Rotation logs.
- Tests endurance 72h.
- Documentation exploitation.
- Ajouter doctor.sh pour verifier la sante du systeme et guider le depannage.

## 8. Strategie d installation simplifiee
- Prerequis utilisateur:
  - Raspberry Pi OS a jour
  - acces Internet pour la premiere installation
  - acces sudo
- Parcours cible:
  - 1) cloner le depot
  - 2) lancer setup.sh
  - 3) ouvrir l URL locale sur la tablette
- Comportement attendu de setup.sh:
  - detecte automatiquement l architecture et les prerequis manquants
  - installe les paquets necessaires sans intervention supplementaire
  - configure systemd et demarre le service
  - affiche un resume final (URL, statut service, emplacement logs)
- Verification post-installation:
  - doctor.sh valide base, API, service, et connectivite locale
  - code retour non nul si un controle critique echoue

## 6. Strategie de tests
- tests unitaires:
  - validation parsing mesures
  - insertion et lecture base
- tests integration:
  - collecteur vers base
  - API vers interface
- tests systeme:
  - redemarrage Pi
  - perte reseau capteur
  - charge continue sur 72h

## 7. Risques et mitigations
- Protocole EM06 non documente localement:
  - mitigation: mode adaptateur pour changer de driver rapidement.
- Ressources limitees du Pi 2B:
  - mitigation: stack legere, pas de services lourds.
- Coupures reseau Wi-Fi:
  - mitigation: buffer local, reconnexion automatique.
