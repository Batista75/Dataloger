# Cahier des charges v3

## 1. Contexte
Le projet datalogueur EM06 collecte, historise et expose des mesures electriques multi-canaux via API et interface web.

## 2. Besoin metier
- Disposer de mesures fiables (consommation/production) en quasi temps reel.
- Visualiser simplement les tendances et anomalies.
- Exporter les donnees pour audit et analyse externe.

## 3. Exigences fonctionnelles
1. Collecte periodique des mesures.
2. Persistance SQLite des mesures et evenements.
3. API de statut, derniere mesure, historique.
4. Interface web de consultation et controle.
5. Export CSV complet.
6. Commande de purge historique.

## 4. Exigences techniques
1. Architecture modulaire: API, collecteur, source capteur, DB.
2. Tolerance aux erreurs source (journalisation des incidents).
3. Lissage et filtrage des valeurs aberrantes.
4. Pas d usage de donnees simulees en production.

## 5. Contraintes connues
- API locale du capteur potentiellement signee/proprietaire.
- MQTT local non disponible sur les ports testes.
- Le mode `refoss_local_socket` reel reste a finaliser.

## 6. Criteres d acceptation (v3)
1. Le service reste stable sur 24h sans plantage.
2. `sensor=connected` en continu avec source reelle.
3. Ecart de mesure acceptable face au compteur de reference.
4. Export CSV complet sans erreur.
5. UI coherent (status + cartes + graphe).

## 7. Hors perimetre actuel
- Prevision de charge/production.
- Facturation complete multi-tarifs.
- Gestion multi-sites.

## 8. Priorites
P1: integration source reelle.
P2: robustesse calculs et tests.
P3: enrichissement documentation et exploitation.
