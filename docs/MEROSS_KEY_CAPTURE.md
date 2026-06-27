# Capture de la clé Meross avec Docker + Wireshark

## Prérequis
- Docker & Docker Compose installés
- L'app Refoss sur ton téléphone (connectée au même réseau)
- Accès réseau au device `192.168.1.27`

## Mode 1 : Capture simple (recommandé)

### Étape 1 : Créer le répertoire captures
```bash
mkdir -p captures
```

### Étape 2 : Lancer la capture
```bash
docker-compose -f docker-compose.wireshark.yml up -d wireshark-capture
```

### Étape 3 : Pendant que le conteneur tourne
1. **Ouvre l'app Refoss** sur ton téléphone
2. **Clique sur le device EM06** pour trigger des lectures (il faut ≥ 5 requêtes)
3. Attends 2-3 minutes

### Étape 4 : Arrêter la capture
```bash
docker-compose -f docker-compose.wireshark.yml stop wireshark-capture
```

### Étape 5 : Parser le fichier .pcap
```bash
# Convertir le .pcap en JSON readable
tshark -r captures/capture.pcap -Y 'http.request.method == "POST"' -T json > captures/parsed.json

# Puis parser pour extraire clé
python3 tools/parse_meross_capture.py captures/parsed.json
```

---

## Mode 2 : Capture automatique avec Docker (tout-en-un)

```bash
docker-compose -f docker-compose.wireshark.yml up --build
```

Cela va :
1. Construire l'image Wireshark
2. Capturer pendant 5 min
3. Parser automatiquement en JSON

Résultat dans `captures/parsed.json`

---

## Mode 3 : Capture sur Raspberry Pi

Si tu veux capturer directement sur le Raspberry (192.168.1.87) :

```bash
ssh mb@192.168.1.87 'mkdir -p /tmp/capture'

# Sur le Raspberry, installe tshark
ssh mb@192.168.1.87 'sudo apt-get update && sudo apt-get install -y tshark'

# Lance la capture
ssh mb@192.168.1.87 'sudo tshark -i eth0 -f "tcp port 80 and dst 192.168.1.27" -w /tmp/capture.pcap -a duration:120'

# Pendant ce temps, lance l'app Refoss sur téléphone (5-10 clics)

# Récupère le fichier
scp mb@192.168.1.87:/tmp/capture.pcap captures/capture.pcap

# Parser
python3 tools/parse_meross_capture.py captures/capture.pcap
```

---

## Interprétation du résultat

Si tu vois :
```
✅ Trouvé POST vers http://192.168.1.27/config
  messageId: abc123...
  timestamp: 1624876543
  sign: d4f3a8e2c1b9...

💡 Avec ces infos, on peut brute-force la clé!
   sign = MD5('abc123...' + KEY + '1624876543')
```

Cela signifie qu'on a les données nécessaires pour **brute-force** la clé (tester combinaisons). Dis-moi et je créerai un brute-forcer.

---

## Dépannage

| Symptôme | Solution |
|----------|----------|
| `Aucune requête POST /config trouvée` | L'app Refoss n'a pas communiqué pendant la capture. Relance et clique sur le device. |
| Permission denied sur tshark | Utilise `sudo` ou rajoute ton user au groupe wireshark |
| Fichier .pcap vide | Vérifie que 192.168.1.27 est accessible (`ping 192.168.1.27`) |

---

## Extraction de la clé en brute-force

Une fois qu'on a `messageId`, `timestamp`, et `sign`, on peut tester 10 000+ combinaisons par seconde pour trouver la clé !

### Étape 6 : Brute-force de la clé

**Option A : Depuis le JSON parsé**
```bash
python3 tools/meross_bruteforcer.py captures/parsed.json
```

**Option B : Directement avec les valeurs**
```bash
python3 tools/meross_bruteforcer.py "abc123xyz" 1624876543 "d4f3a8e2c1b9..."
```

### Résultat

Si la clé est trouvée :
```
✅ KEY FOUND: 23x17ahWarFH6w29

🎉 SUCCESS! Key: 23x17ahWarFH6w29
```

Copie cette clé dans le `.env` :
```
EM06_MEROSS_KEY=23x17ahWarFH6w29
```

Puis redémarre le datalogger et vérifie :
```bash
curl http://192.168.1.87:8000/api/measurements/latest
```

---

## Stratégies de brute-force (ordre de test)

1. **Patterns communs** (100 clés) — instantané
2. **Hex 32 chars** (100k combinaisons) — ~10 secondes
3. **Alphanumériques** (50k combinaisons) — ~5 secondes

Si rien ne marche, la clé est probablement unique et très complexe. Dans ce cas :
- Contacte Refoss support pour obtenir la clé
- Ou essaie `ssh admin@192.168.1.27` sur le device directement
