# Urban Ops — Bilan scientifique définitif V2.4 (4 novembre 2026)

> **Statut : évaluation indépendante terminée ; V2 non admissible à la publication ; V1 officielle inchangée.**
>
> Document de clôture scientifique sur la branche de recherche uniquement. Ne pas confondre succès de GitHub Actions et validation d'un modèle pour la production.

## Traçabilité

- Évaluation : https://github.com/sogoyou8/URBAN-OPS/actions/runs/41876461000 — **success**, terminée le 04/11/2026 à 18:05:36 UTC.
- Artifact source : `urban-ops-v24-future-audit-41876461000` (ID `13348969648`), contenant `V24_FUTURE_HOLDOUT_REPORT.json`. Le fichier brut reste accessible dans l'Action jusqu'à expiration selon GitHub.
- Préenregistrement : `urban-ops-v24-20261027-locked-v1` ; fingerprint `68e05c9528f6a5698a8ae9b0947d7fe7b335d841e40bfb4e69c1d3ec7dc98fa5`.
- Modèle gelé le 27/10/2026 à 12:02 UTC, SHA-256 `36ad4e13e59c5c4d02d094262488bde46b491d8c4d4563e3833b28ff270efc5d`.
- Référence immuable du gel : run `40495787979`, code `69971d07bbde5737da2e985f0b19952e20fee79c`.
- Période future indépendante : 28/10/2026 00:00 UTC → 04/11/2026 00:00 UTC (fin exclue), horizon de prévision à +30 min ±2 min.
- Aucune refonte ou adaptation du modèle aux résultats de cette période.

## Qualité des données réelles

- Couverture temporelle : 2 014 créneaux uniques sur 2 016, soit 99,901 %.
- Archives authentiques rejouées et vérifiées : 2 046.
- Stations avec étiquettes : 1 500.
- Paires réelles qualifiées : 2 681 975, dont 40 000 sélectionnées selon l'échantillonnage préenregistré pour l'évaluation.
- Répartition : 5 jours ouvrés et 2 jours de week-end.
- Toutes les conditions minimales de qualité et de provenance sont satisfaites.

## Comparaison sur l'échantillon indépendant (40 000 paires)

| Méthode | MAE, vélos | RMSE, vélos |
|---|---:|---:|
| Persistance (vélos observés maintenant) | 1,2398 | 2,1282 |
| IA résiduelle V2.3 gelée | **1,2370** | **2,1179** |

Amélioration relative de MAE : **+0,226 %** (soit environ **0,23 %**) contre la persistance. Cette amélioration est faible et ne constitue pas, à elle seule, une preuve d'utilité opérationnelle.

La moyenne des 7 jours n'est pas un protocole de sélection de paramètres. L'IA est meilleure sur 4 des 7 jours en MAE, moins bonne sur 3.

## Décision finale

Le critère de **sélection historique indépendant** imposait au moins **1 % de gain en MAE**. Le modèle expérimental avait obtenu **0,9544**, contre **0,9486** pour la persistance ; le critère historique était donc **non satisfait**.

Le test futur est positif mais ne répare pas cette condition manquante. Résultat officiel du JSON :
- `future_gain_positive: true`
- `historical_selection_passed: false`
- `promotion_eligible: false`
- `new_model_not_authorized_for_public_predictions: true`
- `safe_to_publish_forecasts: false`
- `status: future_evaluated_research_only`

**Décision : ne pas fusionner la recherche V2 dans `main`, ne pas déployer de prévisions IA, ne pas modifier la V1 publique.**

La V1 sur https://urban-ops.vercel.app/ constitue la version publique stable. La phase V2.4 peut être **clôturée scientifiquement**, avec un résultat honnête et reproductible. Tout développement V2 ultérieur nécessiterait un nouveau protocole de sélection et de validation, sans réutiliser le holdout du 28/10 au 04/11 comme terrain de réglage.
