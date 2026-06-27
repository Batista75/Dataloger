# Guide interface web

## 1. Objectif
L interface web permet de:
- visualiser l etat capteur
- suivre les puissances et energies
- inspecter les tendances sur graphe
- controler rapidement la coherence des donnees.

## 2. Ecrans et sections
- Bandeau statut (etat serveur/capteur).
- Cartes de synthese (consommation, production, net, canaux).
- Graphe de tendance.
- Parametres utilisateur (rafraichissement, fenetre de graphe, regles canaux).

## 3. Donnees affichees
- Les valeurs proviennent de:
	- `/api/status`
	- `/api/measurements/latest`
	- `/api/measurements`
- Les puissances sont derivees a partir des index kWh (delta/temps).

## 4. Regles d interpretation
- Une valeur positive represente une consommation.
- Une valeur negative represente une production (canaux generateurs selon configuration).
- En cas de trou ou reset index, certaines puissances instantanees peuvent etre nulles sur un intervalle.

## 5. Verification UI apres deploiement
Checklist:
1. La page charge sans erreur JS.
2. Le statut n est pas bloque sur "Verification".
3. Le graphe contient des datasets et des labels coherents.
4. Les cartes evoluent dans le temps (pas de valeurs figees).

## 6. Symptomes frequents
- Statut `sensor=error`:
	- verifier mode capteur et connectivite source.
- Valeurs absurdes:
	- verifier si fallback simule actif.
	- verifier les mappings de canaux et conventions de signe.

## 7. Bonnes pratiques
- Toujours verifier API + UI apres deploiement.
- Garder la meme convention de signe dans backend et frontend.
- Documenter chaque changement metier impactant les cartes/graphe.
