# P4 — Registre de validation

**Données source** : snapshots publics Vélib' réels archivés en P3 ; seuls les tests locaux utilisent les fixtures synthétiques.

## Contrôles prévus

1. Réimport d'archives P3 via `scripts.replay_capture` avec vérification des SHA-256 bruts.
2. Export P4 sous forme de 9 tables analytiques CSV + manifeste de provenance.
3. Validation SQLite unitaire et d'intégration; PostgreSQL 16 via GitHub Actions CI.
4. Validation des taux calculés uniquement à partir d'observations qualifiées (pas de trajets ni de durées).
5. Évaluation des périodes manquantes dans `fact_capture_intervals.csv` (pas d'interpolation).
6. Conservation UTC + heure locale Europe/Paris et son décalage (DST).
7. Artifact ZIP de données réelles prêt pour import dans Power BI Desktop.

## Résultats

_À remplir uniquement à partir d'un run GitHub Actions terminé et vérifié. Ne pas renseigner des nombres issus des fixtures comme données réelles._

### Limitations pour la soutenance

- Aucun `.pbix` n'est produit par l'environnement CI, car Power BI Desktop n'y est pas présent.
- `powerbi/MODEL.md` décrit les quatre pages et les relations; `powerbi/measures.dax` fournit les mesures, `powerbi/fxLoadUrbanCSV.pq` la fonction d'import et `powerbi/urbanops_theme.json` le thème.
- L'artifact CSV réel téléchargé depuis Actions expire après 14 jours; les sources Bronze historiques persistent dans les Releases P3.
- Le périmètre du run pilote télécharge jusqu'aux 3 dernières releases de données et sélectionne les 24 captures les plus récentes, afin de limiter le temps et les ressources CI. Cela ne prouve **pas** des tendances multi-semaines.

## Exécution vérifiée sur des archives réelles (19 octobre 2026)

- [P4 — export des données réelles](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39332540165) : **succès**.
- [CI P3/P4 et PostgreSQL](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39332540144) : **succès**.
- Archives téléchargées : **1** (et non 24). Station disponibles dans l'archive : **1 517**. Anomalies enregistrées : **34**.
- Neuf fichiers de tables CSV, un manifeste SHA-256 et les sources Power BI ont été livrés en artifact temporaire GitHub Actions.
- Horodatage minimum = maximum : **2026-10-19T21:30:59Z**. Aucun profil horaire/journalier intertemporel, aucune durée de rupture et aucune tendance ne peuvent encore être établis avec cette seule capture.
- Le planificateur P3 n'a pas montré d'exécutions répétées au moment du contrôle. Avant de présenter un historique dans un entretien, contrôler de nouveau ses déclenchements et la croissance des Releases.
- Le fichier final `.pbix` et l'assemblage des quatre pages sont **encore à produire dans Power BI Desktop** (impossible de les ouvrir/valider sur GitHub Actions).