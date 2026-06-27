# Playbook Playwright - Datalogueur EM06

## Objectif
Ce playbook explique comment utiliser Playwright, comme on le fait dans cette maintenance, pour:
- reproduire un bug frontend
- identifier la cause runtime
- verifier un correctif en conditions reelles
- valider le deploiement

## 1) Flux de travail standard
1. Ouvrir la page cible.
2. Lire l etat visible (snapshot).
3. Reproduire le symptome (clic, navigation, reload).
4. Inspecter l etat interne JS (Chart, fetch, erreurs).
5. Corriger le code.
6. Recharger et verifier les criteres attendus.
7. Deployer puis revalider en live.

## 2) Outils utilises (dans cette session)
- open_browser_page: ouvre une page web et renvoie un pageId.
- read_page: lit la structure visible (titre, textes, controles).
- navigate_page: reload/back/forward.
- click_element: clique sur un bouton ou un element.
- type_in_page: saisie texte ou touches clavier.
- run_playwright_code: execute du JS dans la page (inspection fine).
- screenshot_page: capture visuelle si besoin de preuve.

## 3) Pattern de diagnostic rapide
1. Ouvrir la page de prod.
2. Verifier le statut affiche (ex: Verification..., Capteur connecte).
3. Faire un reload puis attendre 1 a 3 secondes.
4. Verifier:
- que les cartes se remplissent
- que le graphe existe
- que les labels/ticks sont conformes

## 4) Pattern de diagnostic avance (runtime)
Utiliser run_playwright_code pour verifier:
- resultats de fetch('/api/status')
- erreurs JS globales (error, unhandledrejection)
- presence de l instance Chart.js
- labels, datasets, ticks, valeurs

Exemples de controles utiles:
- status text: element #status-text
- chart datasets: Chart.getChart(canvas).data.datasets
- ticks X: chart.scales.x.ticks

## 5) Pattern de validation de correctif
Apres patch:
1. Reload page.
2. Attendre courte stabilisation (1 a 3 s).
3. Lire un objet de verification unique avec:
- status
- valeurs cartes
- infos systeme
- datasets du graphe
- labels et ticks
4. Comparer au comportement attendu.

## 6) Criteres de recette utilises ici
- Le statut sort de Verification... et passe a Capteur connecte.
- Le graphe se rend sans erreur.
- Axe X:
- verticales tous les 15 min
- labels toutes les 30 min
- Lissage actif (resampling + moyenne mobile).
- Logique canaux:
- un canal = une puissance signee
- generateur = valeurs negatives
- une seule courbe par canal selectionne

## 7) Bonnes pratiques
- Toujours valider localement avant de deployer.
- Verifier la version servie (cache busting si necessaire).
- Tester avec un vrai reload de page.
- Verifier a la fois le visible (UI) et le runtime (JS).
- Garder des checks objectifs (boolean, compte datasets, etc.).

## 8) Limites et vigilance
- Une page peut sembler chargee mais rester partiellement inactive (bootstrap non execute).
- Un cache navigateur peut masquer un correctif.
- Sans instrumentation runtime, certains bugs ne sont pas visibles au snapshot.

## 9) Mini checklist d execution
- Page ouverte
- Statut API affiche correctement
- Donnees cartes mises a jour
- Graphe present
- Datasets conformes
- Ticks conformes
- Deploiement effectue
- Revalidation post deploiement

## 10) Commandes pretes a copier

### A. Verifier que la version servie est la bonne
Objectif: confirmer que le serveur sert bien les marqueurs attendus dans index et app.js.

```powershell
$ProgressPreference='SilentlyContinue'; try { 
	$index=(Invoke-WebRequest -UseBasicParsing http://192.168.1.87:8000/).Content; 
	$app=(Invoke-WebRequest -UseBasicParsing http://192.168.1.87:8000/js/app.js).Content; 
	"INDEX_HAS_LOADER=" + [bool]($index -match 'App Script with cache busting'); 
	"APP_HAS_DOM_READY=" + [bool]($app -match 'DOMContentLoaded'); 
	"APP_HAS_BOOTSTRAP_GUARD=" + [bool]($app -match 'Bootstrap error:'); 
	"APP_HAS_OPTIONAL_CHAINING=" + [bool]($app -match '\?\.closest'); 
} catch { $_ | Out-String }
```

### B. Verifier rapidement l API
Objectif: confirmer que l API repond et expose un statut coherent.

```powershell
$ProgressPreference='SilentlyContinue'; try {
	(Invoke-WebRequest -UseBasicParsing http://192.168.1.87:8000/api/status).Content
} catch { $_ | Out-String }
```

### C. Deployer les assets frontend
Objectif: pousser index + js sur la cible Raspberry.

```powershell
scp static/index.html static/js/app.js mb@192.168.1.87:/home/mb/datalogger/static/
```

### D. Controle post-deploiement minimal
Objectif: verifier que les fichiers cibles ont bien ete remplaces.

```powershell
$ProgressPreference='SilentlyContinue'; try {
	$index=(Invoke-WebRequest -UseBasicParsing http://192.168.1.87:8000/).Content;
	$app=(Invoke-WebRequest -UseBasicParsing http://192.168.1.87:8000/js/app.js).Content;
	"HOME_OK=" + [bool]($index -match 'Datalogueur EM06');
	"JS_OK=" + [bool]($app.Length -gt 1000);
} catch { $_ | Out-String }
```

### E. Test Playwright de verification UI (manuel, ligne directrice)
Objectif: verifier les invariants UI apres correctif.

Checks a executer via Playwright:
- Ouvrir la page de prod.
- Reload + attente courte (1 a 3 s).
- Verifier texte de statut.
- Verifier presence et datasets du graphe.
- Verifier ticks axe X (15 min verticales, 30 min labels).
- Verifier les cartes canaux (puissance signee, pas de ligne production).

Sortie attendue:
- statut connecte
- graphe present
- datasets conformes
- aucune erreur runtime bloquante

### F. Effacer l historique des donnees serveur
Objectif: purger l historique `measurements` sur le serveur, avec sauvegarde automatique.

Commande depuis le poste local:

```powershell
ssh mb@192.168.1.87 "cd /home/mb/datalogger && python3 tools/reset_history.py --yes"
```

Variantes:

```powershell
# Purger aussi les evenements systeme
ssh mb@192.168.1.87 "cd /home/mb/datalogger && python3 tools/reset_history.py --yes --include-events"

# Purger sans sauvegarde
ssh mb@192.168.1.87 "cd /home/mb/datalogger && python3 tools/reset_history.py --yes --no-backup"
```
