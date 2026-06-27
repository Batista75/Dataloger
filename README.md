# Dataloger

Collecteur de mesures energetiques (Refoss EM06P) avec API FastAPI et extension temperature/humidite Tuya.

## Environnements
- Dev: machine locale `192.168.1.5`
- Prod: Raspberry `192.168.1.87`

## Workflow recommande
1. Charger le profil d environnement local:

```powershell
./scripts/use_env.ps1 -Profile dev
```

2. Lancer la maquette locale:

```powershell
./scripts/dev_start.ps1 -BindHost 0.0.0.0 -Port 8000
```

3. Quand valide, deployer sur Raspberry:

```powershell
./scripts/deploy_raspberry.ps1 -RemoteHost 192.168.1.87 -RemoteUser mb
```

## GitHub
Nom de projet cible: `Dataloger`

```powershell
git init -b main
git add .
git commit -m "chore: bootstrap Dataloger"
git remote add origin https://github.com/YOUR_GITHUB_USER/Dataloger.git
git push -u origin main
```

## Documentation
- Guide principal: `docs/installation_rapide.md`
