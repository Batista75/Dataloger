# Installation rapide

## 1. Prerequis
- Python 3.11+
- Acces reseau au capteur Refoss EM06P (ex: 192.168.1.27)
- Acces SSH au Raspberry (ex: mb@192.168.1.87)

## 2. Installation locale
1. Cloner le projet.
2. Creer un environnement virtuel.
3. Installer les dependances.

Exemple PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Configuration
Copier `.env.example` vers `.env` puis ajuster:
- `EM06_MODE`
- `DB_PATH`
- `POLL_SECONDS`
- parametres source (`EM06_HTTP_URL`, `EM06_HTTP_USERNAME`, `EM06_HTTP_PASSWORD`, MQTT, etc.)

Recommande pour EM06P en HTTP JSON-RPC 2.0 (local):
- `EM06_MODE=refoss_local_socket`
- `EM06_HTTP_URL=http://192.168.1.27` (adresse du device, sans `/rpc/...`)
- `EM06_HTTP_USERNAME=admin` (identifiant parametrable)
- `EM06_HTTP_PASSWORD=...` (mot de passe parametrable)

Option EM06P en MQTT:
- `EM06_MODE=mqtt_json`
- `EM06_MQTT_HOST=192.168.1.10` (adresse broker parametrable)
- `EM06_MQTT_PORT=1883`
- `EM06_MQTT_TOPIC=refoss/em06p/telemetry`
- `EM06_MQTT_CLIENT_ID=datalogger-em06p` (identifiant client parametrable)
- `EM06_MQTT_USERNAME=...` (si requis)
- `EM06_MQTT_PASSWORD=...` (si requis)

Option EM06P Webhooks:
- Le device peut envoyer des webhooks vers une URL externe configurable.
- Cette application ne consomme pas directement les webhooks pour l instant.

Extension prevue: collecte temperature Tuya via TinyTuya
- Objectif: enrichir l interface avec des mesures de temperature de sondes Tuya.
- Sonde connue: `2E:82:1D:8A:64:17`.
- Strategie: utiliser un script TinyTuya pour intercepter/collecter les donnees, puis injecter ces mesures dans la couche API/UI.
- Parametres a rendre configurables:
	- `TUYA_ENABLED=1`
	- `TUYA_POLL_SECONDS=30`
	- `TUYA_TARGET_MACS=2E:82:1D:8A:64:17` (liste separee par virgules si plusieurs sondes)
	- `TUYA_TINYTUYA_DEVICE_ID=...`
	- `TUYA_TINYTUYA_LOCAL_KEY=...`
	- `TUYA_TINYTUYA_IP=...`
	- `TUYA_TINYTUYA_VERSION=3.3`
	- `TUYA_CAPTURE_MODE=local` (`local`, `cloud` ou `auto`)
	- `TUYA_CLOUD_API_KEY=...`
	- `TUYA_CLOUD_API_SECRET=...`
	- `TUYA_CLOUD_API_REGION=eu`

Workflow TinyTuya recommande:
1. Scanner les devices Tuya du reseau (wizard TinyTuya) pour recuperer `device_id`, `local_key`, IP et confirmer la MAC.
2. Filtrer les devices sur `TUYA_TARGET_MACS` (incluant `2E:82:1D:8A:64:17`).
3. Poller periodiquement les DPS de temperature via script TinyTuya.
4. Mapper les valeurs en degres C puis publier vers votre pipeline backend (DB/API) pour affichage interface.

Note capteurs "peu locaces":
- Certaines sondes ne remontent une valeur qu en cas de variation de temperature.
- Utiliser le mode watch pour laisser tourner la collecte et capturer le prochain changement.

Script fourni:
- `tools/tuya_temperature_capture.py`

Exemples d usage:

```bash
# Scan LAN et filtrage par MAC cible
python3 tools/tuya_temperature_capture.py --scan --target-macs 2E:82:1D:8A:64:17

# Capture unique temperature et ecriture JSON/CSV
python3 tools/tuya_temperature_capture.py \
	--device-id "$TUYA_TINYTUYA_DEVICE_ID" \
	--local-key "$TUYA_TINYTUYA_LOCAL_KEY" \
	--ip "$TUYA_TINYTUYA_IP" \
	--device-mac 2E:82:1D:8A:64:17

# Watch continu (ecrit seulement si variation >= 0.1 deg C)
python3 tools/tuya_temperature_capture.py \
	--watch \
	--poll-seconds 30 \
	--min-delta-c 0.1 \
	--device-id "$TUYA_TINYTUYA_DEVICE_ID" \
	--local-key "$TUYA_TINYTUYA_LOCAL_KEY" \
	--ip "$TUYA_TINYTUYA_IP" \
	--device-mac 2E:82:1D:8A:64:17

# Capture cloud (utile si le device n est pas joignable en LAN)
python3 tools/tuya_temperature_capture.py \
	--mode cloud \
	--device-id "$TUYA_TINYTUYA_DEVICE_ID" \
	--api-key "$TUYA_CLOUD_API_KEY" \
	--api-secret "$TUYA_CLOUD_API_SECRET" \
	--api-region "$TUYA_CLOUD_API_REGION" \
	--device-mac 2E:82:1D:8A:64:17

# Mode auto: essaie local puis bascule cloud en cas d echec
python3 tools/tuya_temperature_capture.py \
	--mode auto \
	--device-id "$TUYA_TINYTUYA_DEVICE_ID" \
	--local-key "$TUYA_TINYTUYA_LOCAL_KEY" \
	--ip "$TUYA_TINYTUYA_IP" \
	--api-key "$TUYA_CLOUD_API_KEY" \
	--api-secret "$TUYA_CLOUD_API_SECRET" \
	--api-region "$TUYA_CLOUD_API_REGION" \
	--device-mac 2E:82:1D:8A:64:17
```

Astuce test terrain:
- Provoquer une variation douce (ex: tenir la sonde en main 30-60s) puis verifier la mise a jour du JSON latest et du dashboard.

Integration API/UI:
- L API expose `GET /api/temperature/latest` (source: `data/tuya_temperature_latest.json`).
- Le dashboard affiche la temperature Tuya, la MAC et l age de la mesure.

Important:
- En reel, garder `REFOSS_ALLOW_SIMULATED_FALLBACK=0`.

Reference API EM06P:
- https://docs.refoss.net/open-api/devices/em06p

## 4. Lancement

```powershell
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

## 5. Verification rapide
- `GET /health` doit retourner `ok`.
- `GET /api/status` doit repondre avec l etat capteur.
- `GET /api/measurements/latest` doit retourner une mesure recente si la source est active.

## 6. Workflow recommande: maquette locale puis push Raspberry
Objectif: iterer rapidement sur la machine de dev, puis deployer seulement une version valide sur le Raspberry.

### 6.1 Maquetter en local (Windows PowerShell)

```powershell
# depuis la racine du projet
./scripts/dev_start.ps1 -BindHost 127.0.0.1 -Port 8000
```

Le script:
- cree `.venv` si besoin,
- installe les dependances,
- initialise la DB,
- lance l API avec autoreload.

Tests locaux conseilles avant push:
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/api/status`
- `http://127.0.0.1:8000/api/temperature/latest`

### 6.2 Push vers Raspberry apres validation

```powershell
# push code + update services sur le Raspberry cible
./scripts/deploy_raspberry.ps1 -RemoteHost 192.168.1.87 -RemoteUser mb
```

Options utiles:
- inclure aussi `.env` local: `-PushEnv`
- ne pas redemarrer explicitement les services (laisse setup/update gerer): `-SkipRestart`
- port SSH custom: `-SshPort 2222`

Verification post-deploiement:

```bash
ssh mb@192.168.1.87 "curl -fsS http://127.0.0.1:8000/health && echo"
ssh mb@192.168.1.87 "curl -fsS http://127.0.0.1:8000/api/temperature/latest && echo"
```

## 7. Deploiement Raspberry (resume)
 Installer/mettre a jour via scripts:

```bash
chmod +x scripts/*.sh
./scripts/setup.sh
```

 Le setup installe 2 services systemd:
  - `datalogger.service` (API + EM06)
  - `datalogger-tuya.service` (collecte temperature/humidite Tuya)
 Verifier les services:

```bash
sudo systemctl status datalogger.service --no-pager
sudo systemctl status datalogger-tuya.service --no-pager
```

 Exemple de configuration `.env` pour sonde Tuya en fallback local->cloud:

```dotenv
TUYA_ENABLED=1
TUYA_CAPTURE_MODE=auto
TUYA_TINYTUYA_DEVICE_ID=YOUR_DEVICE_ID
TUYA_TINYTUYA_LOCAL_KEY=YOUR_LOCAL_KEY
TUYA_TINYTUYA_IP=YOUR_DEVICE_IP
TUYA_TINYTUYA_VERSION=3.4
TUYA_CLOUD_API_KEY=YOUR_TUYA_API_KEY
TUYA_CLOUD_API_SECRET=YOUR_TUYA_API_SECRET
TUYA_CLOUD_API_REGION=eu
TUYA_TARGET_MACS=AA:BB:CC:DD:EE:FF,11:22:33:44:55:66
TUYA_POLL_SECONDS=30
```

 Profils prets a l emploi:
- `.env.dev.example` pour la maquette locale (machine dev 192.168.1.5)
- `.env.prod.example` pour la production Raspberry (192.168.1.87)

 Basculer rapidement de profil:

```powershell
./scripts/use_env.ps1 -Profile dev
# ou
./scripts/use_env.ps1 -Profile prod
```

 Diagnostic rapide:

```bash
./scripts/doctor.sh
```

 Redemarrage apres changement de `.env`:
- Redemarrer puis controler:

```bash
sudo systemctl restart datalogger-tuya
sudo systemctl status datalogger --no-pager
sudo systemctl status datalogger-tuya --no-pager
sudo systemctl status datalogger --no-pager
```

## 8. Git et GitHub (projet Dataloger)

 Initialisation locale:

```powershell
git init -b main
git add .
git commit -m "chore: bootstrap Dataloger project"
```

 Connexion au repo GitHub (remplacer YOUR_GITHUB_USER):

```powershell
git remote add origin https://github.com/YOUR_GITHUB_USER/Dataloger.git
git push -u origin main
```

 Cycle recommande:
1. Maquetter et valider en local (192.168.1.5)
2. Commit Git local
3. Push GitHub
4. Deploiement Raspberry (192.168.1.87) via `./scripts/deploy_raspberry.ps1`

## 9. Operations utiles
- Export CSV:

```bash
python3 tools/export_all_values.py
```

- Reset historique mesures:

```bash
python3 tools/reset_measurements_sqlite.py
```

- Capture temperature Tuya (ponctuelle):

```bash
python3 tools/tuya_temperature_capture.py --device-id "$TUYA_TINYTUYA_DEVICE_ID" --local-key "$TUYA_TINYTUYA_LOCAL_KEY" --ip "$TUYA_TINYTUYA_IP" --device-mac 2E:82:1D:8A:64:17
```

- Capture temperature Tuya (watch 10 minutes):

```bash
python3 tools/tuya_temperature_capture.py --watch --watch-seconds 600 --poll-seconds 30 --min-delta-c 0.1 --device-id "$TUYA_TINYTUYA_DEVICE_ID" --local-key "$TUYA_TINYTUYA_LOCAL_KEY" --ip "$TUYA_TINYTUYA_IP" --device-mac 2E:82:1D:8A:64:17
```
