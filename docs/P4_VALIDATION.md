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