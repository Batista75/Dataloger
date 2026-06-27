# Interface Web - Guide Utilisateur

## Vue d'ensemble
L'interface web du Datalogueur EM06 est conçue pour être responsive et tactile, optimisée pour l'affichage sur tablette Samsung (portrait et paysage).

## Accès
- **URL**: `http://<IP_RASPBERRY>:8000`
- Accessible uniquement sur le réseau local (LAN)
- Auto-refresh automatique chaque 3 secondes

## Navigation
Trois onglets principaux en bas de l'écran:
- 📊 **Dashboard** - Vue d'ensemble temps réel
- 📈 **Historique** - Données passées avec filtres
- ⚙️ **Paramètres** - Configuration et état système

## Dashboard

### Cartes de mesures (4 principales)
Chaque carte affiche la mesure actuelle:
1. **Puissance** - Watts (W)
2. **Énergie** - Kilowatt-heures (kWh)
3. **Tension** - Volts (V)
4. **Intensité** - Ampères (A)

### Graphique 24 heures
- Visualisation double axe:
  - Axe gauche: Puissance (W) en bleu
  - Axe droit: Énergie (kWh) en vert
- Affiche les 24 dernières heures de données
- Interaction: Survoler pour voir les valeurs exactes

### Informations système
- **État capteur**: Vérification / Connecté / Erreur
- **Dernier relevé**: Heure du dernier enregistrement
- **Mode collecte**: refoss_local_socket / http_json / mqtt_json / etc.
- **Fréquence**: Fréquence réseau (Hz)

### En-tête
- Logo et titre "⚡ Datalogueur EM06"
- Indicateur d'état (point vert = ok, rouge = erreur)
- Statut de connexion

## Historique

### Sélection de dates
- **De**: Date de début (par défaut: -7 jours)
- **À**: Date de fin (par défaut: aujourd'hui)
- **Appliquer**: Bouton pour charger les données

### Tableau de mesures
Affiche toutes les mesures dans la plage sélectionnée:
- **Heure**: Heure exacte du relevé
- **Puissance (W)**: Valeur instantanée
- **Énergie (kWh)**: Cumul de consommation
- **Tension (V)**: Tension du réseau
- **Intensité (A)**: Courant consommé

### Pagination
- **Nombre de mesures**: Affiche le nombre de lignes chargées
- **Boutons**: Précédent/Suivant pour naviguer

## Paramètres

### Configuration
- **Intervalle de rafraîchissement**: 1-60 secondes
  - Défaut: 3 secondes
  - Affecte le Dashboard et la page d'Historique
- **Heures de graphique**: 1-720 heures
  - Défaut: 24 heures
  - Change l'affichage du graphique 24h du Dashboard

**Bouton Enregistrer**: Sauvegarde les paramètres dans le navigateur (localStorage)

### État système
Informations de diagnostic:
- **Serveur**: Running / Erreur
- **Capteur**: Connecting / Connected / Error / Mock
- **Dernier relevé**: Timestamp du dernier enregistrement
- **Mode EM06**: Mode de collecte actuellement actif
- **Dernier erreur**: Affichée en rouge si problème

## Responsivité

### Portrait (par défaut)
- Écran vertical optimisé pour lecture verticale
- Grille 2x2 pour les 4 cartes de mesures
- Tableau scrollable horizontalement

### Paysage
- Écran horizontal
- Grille 4x1 pour les 4 cartes de mesures
- Graphique plus grand

### Tactile (touch)
- Boutons et zones cliquables minimum 44x44 pixels
- Navigation fluide avec transitions
- Aucun hover (adapté au tactile)

## Indicateurs d'état

### En-tête
- 🟢 Point vert pulsant = Connecté
- 🔴 Point rouge = Erreur
- Texte: "Connecté" ou "Erreur"

### Capteur
- "Vérification..." = Démarrage
- "Connecté" = OK
- "Erreur" = Problème de communication

## Dépannage

### Page blanche
- Vérifier que le Raspberry Pi est accessible (ping)
- Attendre 5-10 secondes le chargement complet
- Rafraîchir la page (F5)

### "Erreur" affiché
- Vérifier que le service est actif: `sudo systemctl status datalogger.service`
- Consulter les logs: `sudo journalctl -u datalogger.service -f`
- Vérifier la configuration .env

### Pas de données dans le graphique/historique
- Attendre au moins quelques minutes de collecte
- Vérifier que le capteur/device est allumé
- Consulter la page Paramètres pour voir l'état du capteur

### Performance lente
- Réduire l'intervalle de rafraîchissement (Paramètres)
- Réduire les heures affichées dans le graphique
- Vérifier la charge CPU du Raspberry Pi: `top`

## Technologies
- **Framework**: FastAPI + HTML5/CSS3/JavaScript
- **Graphiques**: Chart.js 4.4
- **Responsive**: CSS Grid + Flexbox
- **Performance**: ~50KB CSS + JS combiné

## Sécurité
- Interface accessible uniquement sur LAN (pas d'exposition internet par défaut)
- Pas de login requise en v0.1.0 (TODO: authentification pour production)

## Historique des versions

### v0.1.0 (Actuelle)
- Dashboard temps réel (4 cartes + graphique 24h)
- Page Historique avec filtres dates
- Page Paramètres avec configuration
- Responsive mobile/tablette/desktop
- Auto-refresh toutes les 3 secondes
- Support Chart.js pour graphiques
- localStorage pour paramètres utilisateur
