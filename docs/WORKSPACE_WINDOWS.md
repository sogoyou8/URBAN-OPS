# Urban Ops — un seul dossier Windows, synchronisé avec GitHub

**Objectif :** travailler dans `C:\Users\yoann\Desktop\ABYSS\ProjetDATA\UrbanOps`, sans réextraire une V2/V3. Le dépôt Git contient le code; le rapport `.pbip` et les CSV réels sont téléchargés **automatiquement** depuis le dernier artefact GitHub Actions P4 réussi dans ce même dossier. Ils sont ignorés par Git pour éviter de publier des fichiers locaux.

## Préparation (une seule fois)

1. **Fermer Power BI Desktop** et conserver ses modifications (Menu Fichier > Enregistrer).
2. Installer **Git for Windows** et **GitHub CLI** si nécessaires : `winget install --id Git.Git -e` puis `winget install --id GitHub.cli -e` (ouvrir un nouveau terminal après installation).
3. Ouvrir **PowerShell** et exécuter les commandes ci-dessous. **Ne supprimer aucun dossier existant avant contrôle.**

```powershell
cd "$env:USERPROFILE\Desktop\ABYSS\ProjetDATA"
# Une seule sauvegarde provisoire du travail Power BI actuel.
Rename-Item -LiteralPath .\UrbanOps -NewName 'UrbanOps-avant-git'
git clone https://github.com/sogoyou8/URBAN-OPS.git UrbanOps
cd .\UrbanOps
gh auth login
powershell -ExecutionPolicy Bypass -File .\scripts\sync-urbanops.ps1
```

Si le chemin ou les noms diffèrent, les adapter. **Ne pas relancer `Rename-Item` lors des futures mises à jour.** Le dossier `UrbanOps-avant-git` est uniquement une sauvegarde de migration (pas une V2). Le comparer avec la nouvelle version et ne l'effacer manuellement qu'après confirmation que ton travail Power BI éventuel a bien été préservé. Le script **ne l'efface jamais**.

Le rapport sera directement à :

```text
C:\Users\yoann\Desktop\ABYSS\ProjetDATA\UrbanOps\UrbanOps.pbip
```

Les fichiers du modèle sont `UrbanOps.Report\`, `UrbanOps.SemanticModel\`; les CSV sont dans `data\`. `DataFolder` pointe automatiquement vers ce `data\` local stable : **aucune reconfiguration de chemin à chaque version**.

## Mise à jour habituelle (la seule commande)

Enregistrer le rapport et **fermer Power BI Desktop**, puis dans **PowerShell** :

```powershell
cd "$env:USERPROFILE\Desktop\ABYSS\ProjetDATA\UrbanOps"
powershell -ExecutionPolicy Bypass -File .\scripts\sync-urbanops.ps1
```

Le script : (1) `git pull --ff-only` pour le code; (2) interroge **uniquement la dernière exécution P4 réussie sur `main`** et télécharge l'artefact automatiquement avec `gh`; (3) vérifie les neuf CSV et leurs SHA-256; (4) met à jour le PBIP **dans le même dossier**, sans archives V2/V3; (5) conserve la base de données locale et les éventuelles captures Bronze hors du rapport; (6) enregistre l'identifiant d'exécution dans `.urbanops-local/sync-state.json` pour éviter les téléchargements identiques.

**Protection des modifications personnelles :** si Power BI Desktop a modifié, ajouté ou supprimé des fichiers du rapport, le script refuse l'écrasement. Pour conserver un ZIP de sauvegarde **seulement en cas de conflit**, puis accepter explicitement le remplacement :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-urbanops.ps1 -BackupAndReplace
```

Les sauvegardes exceptionnelles sont rangées dans `.urbanops-local\backups\` **à l'intérieur du même dossier** et ignorées par Git. Évaluer les différences personnelles avant de remplacer. Ne pas activer cette option automatiquement.

## Notes importantes

- L'artefact GitHub Actions P4 expire après **14 jours**; le script ne déclenche pas de nouveaux builds ni de déploiements. Si aucun artefact récent n'existe, ouvrir `Actions > P4 real analytics and Power BI export > Run workflow` (déclenchement ponctuel) ou demander une nouvelle génération.
- La collecte Vélib' toutes les 5 minutes reste **best-effort** : il faut un historique de plusieurs captures pour interpréter des séries temporelles. Le script refuse de fabriquer des observations.
- En cas de modifications sur une branche Git différente de `main` ou de changements locaux suivis non validés, le script s'arrête avant `git pull` : il n'emploie jamais `git reset --hard` ni `git clean`.
- Ne pas modifier le contenu des données brutes comme s'il s'agissait d'observations réelles. Les modifications manuelles au PBIP sont locales et doivent être sauvegardées avant de récupérer un nouveau rapport généré.
- **Le présent document ne signifie pas que la migration de ton PC a déjà eu lieu.** Elle doit être effectuée une fois par toi dans PowerShell.