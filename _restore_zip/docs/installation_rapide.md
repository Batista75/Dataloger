# Installation rapide Raspberry Pi

## Prerequis
- Raspberry Pi OS avec acces reseau
- utilisateur avec droits sudo
- depot du projet deja copie sur le Raspberry Pi

## Installation en 3 commandes
1. cd /chemin/vers/Projet_Datalogueur
2. chmod +x scripts/*.sh
3. ./scripts/setup.sh

## Accès à l'interface web (UI)
Après l'installation, accédez à l'interface depuis votre tablette Samsung S9F:
- **URL**: `http://<IP_RASPBERRY>:8000`
  - Remplacez `<IP_RASPBERRY>` par l'IP du Raspberry Pi (affichée en fin de setup.sh)
- **Exemple**: `http://192.168.1.50:8000`

### Dashboard (page principale)
- **4 cartes de mesures**: Puissance (W), Énergie (kWh), Tension (V), Intensité (A)
- **Graphique 24h**: Visualisation des tendances puissance et énergie
- **Infos système**: État du capteur, mode collecte, dernier relevé, fréquence

### Page Historique
- Sélectionner plage de dates (De/À)
- Tableau de toutes les mesures avec colonnes: Heure, Puissance, Énergie, Tension, Intensité
- Auto-rafraîchissement toutes les 3 secondes

### Page Paramètres
- Intervalle de rafraîchissement (1-60 secondes)
- Heures de données affichées dans le graphique (1-720 heures)
- État système complet

## Vérification
- ./scripts/doctor.sh
- Ouvrir ensuite l URL affichee a la fin de setup.sh depuis la tablette Samsung.

## Configuration EM06
- Par defaut, le mode `mock` genere des mesures de test.
- Pour activer une source HTTP JSON:
	- modifier .env
	- definir `EM06_MODE=http_json`
	- definir `EM06_HTTP_URL=http://IP_EM06/endpoint`
	- redemarrer: `sudo systemctl restart datalogger.service`
- Exemple actuel du projet:
	- `EM06_MODE=meross_local_post`
	- `EM06_HTTP_URL=http://192.168.1.27/config`
	- `EM06_NAMESPACE=Appliance.Control.Electricity`
- Le parseur accepte une reponse directe ou une reponse enveloppee dans `data`, `result`, `payload` ou `status`.

## Fallback MQTT (choix 2)
- Utiliser ce mode si l API locale officielle refuse les requetes non signees.
- Parametres a renseigner dans .env:
	- `EM06_MODE=mqtt_json`
	- `EM06_MQTT_HOST=<ip_broker_mqtt>`
	- `EM06_MQTT_PORT=1883`
	- `EM06_MQTT_TOPIC=<topic_mesures_em06>`
	- `EM06_MQTT_USERNAME=<optionnel>`
	- `EM06_MQTT_PASSWORD=<optionnel>`
- Le payload MQTT doit etre un JSON contenant des champs type `power_w`, `voltage_v`, `current_a`, `energy_kwh`.
- Apres modification:
	- `./scripts/update.sh`
	- `sudo systemctl restart datalogger.service`
## Mode local Refoss (socket broadcast - RECOMMANDÉ)
- Approche la plus simple: découverte automatique sur LAN via socket broadcast port 9989.
- Aucune auth cloud ni MQTT nécessaire.
- Configuration:
  - `EM06_MODE=refoss_local_socket`
  - `REFOSS_PORT=9989` (défaut)
- Avantages:
  - Pas de dépendance externe (cloud/MQTT)
  - Découverte automatique sur le même réseau
  - Communication directe device <-> Pi
- Après modification:
  - `./scripts/update.sh`
  - `sudo systemctl restart datalogger.service`
## Test brut API officielle
- Requete locale attendue (POST JSON):
  - `curl -i -sS -X POST -H "Content-Type: application/json" --data '{"header":{"messageId":"1234567890abcdef1234567890abcdef","namespace":"Appliance.Control.Electricity","triggerSrc":"Local","sign":"","payloadVersion":1},"payload":{}}' http://192.168.1.27/config`
- Si la reponse est `Empty reply from server`, le module exige probablement une signature ou un mecanisme d authentification locale supplementaire.

## Mise a jour
- ./scripts/update.sh

## Desinstallation
- ./scripts/uninstall.sh
- ./scripts/uninstall.sh --purge-db
