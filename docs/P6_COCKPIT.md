# P6 — Urban Ops | Cockpit de mobilité

## Statut et périmètre

P6 est une application web statique, conçue pour explorer les **capturations réelles** de Vélib' Métropole déjà vérifiées par le pipeline P3 (SHA-256 de chaque archive au replay). Aucun backend payant et **aucun déploiement automatique** : GitHub Actions produit un fichier `network.json` et un artefact web prévisualisable. Aucune donnée synthétique n'est publiée en production.

### P6.1 — Architecture

`GitHub Releases` (archives P3 réelles) → `scripts.replay_capture` (SQLite) → `scripts.export_p6` (schéma JSON V1) → `web/` (cockpit). L'export sélectionne le **dernier run réussi** et fait une jointure exacte sur `run_id` avec les stations, sans récupérer des faits anciens pour les stations absentes. Seules les stations `is_usable=1` comptent dans les totaux de vélos et de bornes. Si une station n'a pas de mesure exploitable, sa disponibilité reste **inconnue**, jamais zéro.

Les 48 captures les plus récentes (parmi les trois dernières journées publiées) sont rejouées dans le workflow, et jusqu'à 96 peuvent être rendues en mode local. Les gaps entre capturations ne sont ni inventés ni interpolés. Les courbes se coupent lorsque l'écart dépasse 20 minutes. L'écran distingue la date de capture de la date d'export, et ne prétend jamais présenter les disponibilités en temps réel.

### P6.2 — Direction produit

Expérience mono-écran sur desktop (avec défilement interne des listes), surfaces sombre bleu-noir, typographie fine, lignes de séparation plutôt que cartes gonflées et arrondies. Carte interactive géoréférencée sur **vraies coordonnées** ; styles MapLibre/OpenFreeMap avec attribution OpenStreetMap. Dégradation progressive vers un tracé géographique SVG/HTML si la bibliothèque ou le fond de carte externes ne sont pas accessibles. L'accessibilité inclut une liste navigable au clavier et des intitulés d'états lisibles.

### P6.3 — Composants

- **Réseau** : indicateurs qualifiés, carte avec clustering, couleur par statut, recherche par nom/code/ID, filtres, inspection complète des stations.
- **Territoires** : 4 quadrants délimités par la médiane des coordonnées P3, **pas des arrondissements** ni des communes. Les indicateurs comparent les quadrants sur les seules données qualifiées.
- **Fiabilité** : sources, horodatage, observations exploitables et nombres d'anomalies **par événement**, non par station distincte.
- **Continuum des captures** : série des totaux réseau réellement observés, interrompue si 20+ minutes sans capture. Si une seule capture : aucun graphique temporel trompeur.
- **Prévisions** : statut P5 explicitement **indisponible**, en attente de validation chronologique sur historique réel. Ce volet n'affiche aucune estimation fictive.

Le fond cartographique nécessite l'accès Internet. Si un fournisseur gratuit change ses conditions, remplacer la source par un fond conforme à son attribution/licence, ou utiliser le mode de secours sans tuiles. Les dépendances visuelles sont servies depuis un CDN; les sélecteurs et la logique locale fonctionnent indépendamment du CDN.

### P6.4 — P5 et architecture de la prédiction

Aucun modèle P5 non validé ne doit injecter des chiffres dans l'UI. Le contrat JSON V1 n'accepte que `forecast.status = unavailable`. Un futur contrat v2 nécessitera provenance, temps de prédiction, version de modèle et mesure de performance hors échantillon établie sur des archives authentiques; ce changement devra être testé avant activation.

### P6.5 — Validation et utilisation

Tests hors ligne :

```powershell
python -m pip install -e '.[test]'
python -m pytest -q tests/test_p6_export.py
node --test web/src/core.test.mjs
```

Regénération réelle CI : `Actions → P6 Urban Ops cockpit — checks and verified real snapshot → Run workflow`, qui rejoue les archives P3 et publie 2 artefacts pendant 7 jours (`urban-ops-p6-real-data` et `urban-ops-p6-static-preview`). Sans archive réelle, le workflow échoue clairement; aucun remplacement par des fixtures.

Un **seul dossier local** (même méthode que Power BI) :

```powershell
cd "$env:USERPROFILE\Desktop\ABYSS\ProjetDATA\UrbanOps"
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\scripts\sync-p6.ps1
python -m http.server 5173 --directory web
# puis http://localhost:5173
```

La commande `sync-p6.ps1` télécharge le dernier dataset GitHub vers `web/data/network.json`, refuse d'écraser un fichier local modifié, et peut sauvegarder l'ancienne version explicitement avec `-ReplaceLocalData`. Elle ne touche pas au PBIP.

### Limites et suite

- L'écran est un **observatoire des archives**, pas un contrôle direct du service Vélib'. Ne pas afficher « live » si la capture date de plusieurs minutes/heures.
- Le `network.json` généré n'est jamais versionné dans Git, pour ne pas gonfler le dépôt ou mélanger données et code.
- La publication sur Vercel ou GitHub Pages **n'est pas activée**. Elle peut se faire ultérieurement, après validation utilisateur, via fichiers statiques et budget vérifié.
- Validation de lecture sur un vrai navigateur Windows, UX responsive, disponibilité du fond de carte et performance d'affichage sur 1 500 stations à contrôler avec l'utilisateur. Pas de promesse de recette visuelle complète sans navigateur connecté.
- Le déclencheur Cloudflare / GitHub P3.5 continue d'accumuler les snapshots; il est distinct du build P6.

**Source** : Vélib' Métropole open data, ODbL, non affilié à l'opérateur.