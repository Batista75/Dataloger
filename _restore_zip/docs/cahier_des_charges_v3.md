# Cahier des charges V3

## 1. Objectif
Mettre en place une solution de telemetrie energetique basee sur un Refoss EM06 et un Raspberry Pi 2 Model B, avec affichage des mesures sur tablette Samsung via une interface web personnalisee.

## 2. Perimetre
- Collecte automatique des mesures du Refoss EM06.
- Stockage local fiable sur le Raspberry Pi.
- Exposition des donnees via une API locale.
- Interface web tactile personnalisee pour tablette Samsung S9.
- Fonctionnement en reseau local, sans dependance Internet.

## 3. Hypotheses retenues (a ajuster si besoin)
- Acces: reseau local uniquement (LAN/Wi-Fi) pour la V1.
- Rafraichissement interface: toutes les 3 secondes.
- Conservation des donnees: 12 mois.
- Comptes: 1 compte administrateur pour la V1.
- Mode d affichage: dashboard colore, lisible, optimise tactile.

## 4. Exigences fonctionnelles
1. Le systeme doit collecter periodiquement les mesures exposees par le Refoss EM06.
2. Les mesures minimales a stocker sont:
   - horodatage
   - puissance instantanee (W)
   - energie cumulee (kWh)
   - tension (V)
   - courant (A)
   - frequence et facteur de puissance si disponibles
3. Le systeme doit historiser localement toutes les mesures.
4. Le systeme doit offrir une API locale pour la tablette.
5. L interface tablette doit afficher:
   - puissance en temps reel
   - energie du jour
   - tension et courant
   - etat capteur/serveur (connecte/deconnecte)
6. L interface doit proposer un historique avec filtres de periode.
7. Le systeme doit journaliser les erreurs de communication et de service.
8. Le service doit redemarrer automatiquement apres reboot ou panne.

## 5. Exigences non fonctionnelles
- Compatibilite materielle: Raspberry Pi 2 Model B.
- Performance: affichage des nouvelles mesures en moins de 5 secondes sur tablette.
- Disponibilite: service continu 24/7.
- Robustesse: reprise automatique apres perte reseau/capteur.
- Maintenabilite: architecture modulaire (collecte, stockage, API, UI).
- Installabilite: installation la plus simple possible avec procedure guidee et script unique.
- Reproductibilite: meme resultat d installation sur nouvelle carte SD avec les memes prerequis.

## 6. Architecture cible
- Collecteur: service Python.
- Base locale: SQLite.
- API web: FastAPI.
- Interface: application web responsive (HTML/CSS/JS) servie par le Raspberry Pi.
- Mise a jour front: polling 3 secondes (WebSocket possible en evolution).
- Supervision service: systemd.

## 7. Securite
- Authentification obligatoire sur l interface.
- Session securisee (token de session).
- Acces restreint au reseau local.
- Sauvegarde reguliere de la base locale.
- Rotation des logs.

## 8. Critere d acceptation
1. Collecte continue validee sur 72 heures avec taux de mesures valides > 99%.
2. Reprise automatique apres redemarrage du Raspberry Pi.
3. Interface tablette utilisable en portrait et paysage.
4. Rafraichissement des mesures <= 5 secondes.
5. Acces interdit sans authentification.
6. Export CSV de l historique sans corruption.
7. Installation complete realisable en moins de 15 minutes via une procedure unique.
8. Installation realisable en 3 commandes maximum apres OS installe et reseau actif.
9. En cas d echec d installation, message explicite et piste de correction fournis.

## 9. Hors perimetre V1
- Acces distant depuis Internet.
- Gestion multi-utilisateurs avancee.
- Alertes push (mail/SMS/Telegram).

## 10. Livrables V1
- Code source du collecteur.
- API locale documentee.
- Interface web tablette personnalisee.
- Scripts d installation/deploiement Raspberry Pi.
- Guide d exploitation et sauvegarde.

## 11. Exigences d installation simplifiee
1. Fournir un script unique d installation (setup.sh) qui:
   - installe les dependances systeme et Python
   - cree l environnement virtuel
   - initialise la base
   - configure et active le service systemd
2. Fournir un script de mise a jour (update.sh) sans reinstallation complete.
3. Fournir un script de desinstallation propre (uninstall.sh) optionnel.
4. Fournir un fichier d exemple de configuration (.env.example) avec valeurs par defaut.
5. Fournir une verification post-installation automatique avec rapport de statut.
