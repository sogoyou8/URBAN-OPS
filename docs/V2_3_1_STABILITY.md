# Urban Ops V2.3.1 — Diagnostic stabilité et candidats sans déploiement

## Pourquoi V2.3.1 ?

Le 27 octobre 2026, V2.3 a comparé trois méthodes sur 20 000 observations réelles : persistance **MAE 0,9786**, régression résiduelle **0,9790**, régression conservatrice **0,9790**. Le candidat ML était légèrement meilleur sur certaines stations évolutives, mais son coût sur les stations stables empêchait toute amélioration globale. La RMSE légèrement plus basse ne remplace **pas** le critère MAE. Aucune promotion n'a été autorisée.

Ces scores sont **historiques** et dépendent d'un replay précis (2 134 captures, 7,469 jours), de sa validation (24–25 octobre, exclusivement week-end), de sa règle de sampling et de ses données. Un run V2.3.1 peut utiliser plus de captures et une autre fenêtre : il est incorrect de comparer des MAE entre ces runs comme si la validation était identique.

## Nouveaux candidats

Outre la persistance, la régression résiduelle brute et le filtrage conservateur V2.3, la branche ajoute :

1. **Tendance courte bornée** : exploiter les variations observées sur les 30 minutes précédentes (ou 15/5 min en l'absence du lag long), sans interpolation. Extrapolation plafonnée à ±4 vélos ; amplitude de correction et seuil minimal calibrés sur l'entraînement.
2. **Détection de changement + correction résiduelle** : un classifieur estime la *probabilité que le nombre de vélos change à +30 minutes*, ce qui est différent de la probabilité de trouver un vélo à la station. La régression des changements reste inchangée ; elle n'est appliquée que si la probabilité estimée et l'amplitude prédite dépassent des seuils définis.

**Le classifieur n'utilise jamais la vérité de T+30 au moment de prédire.** Les exemples synthétiques ne servent qu'à tester les contrats des fonctions ; les seules métriques revendiquées comme réelles proviennent du replay P3.

## Contrôle de fuite et d'optimisation

- Données : archivage réel P3, contrôle de provenance par inventaire, restauration des archives avec validation SHA-256, mesures `is_usable`, horizon +30 ±2 min.
- Split chronologique de l'historique : ancien protocole train (60 %), validation (20 %), ancien bloc test (20 %) **exclu du V2.3.1**, avec purge des étiquettes franchissant les frontières.
- Les 60 % d'entraînement sont séparés chronologiquement en cœur d'entraînement et calibration interne. La régression et la classification sont entraînées sur le cœur seulement.
- Les seuils de probabilité, d'amplitude, de tendance et les facteurs de prudence sont choisis uniquement sur la **calibration de l'entraînement**. La correction zéro (simple persistance) est toujours une option recevable. Égalités de MAE non arrondie départagées en faveur de **moins de corrections**, pour protéger les stations stables.
- L'ancienne validation extérieure sert à **décrire les résultats et non à régler des paramètres** ; ses jours représentés sont publiés dans le JSON. L'ancien bloc test est exclu, même des récapitulatifs.
- Aucune nouvelle métrique V2.3.1 ne prouve une amélioration future. Un jeu de données créé après fixation de cette approche, incluant des jours ouvrés et des week-ends, est obligatoire pour V2.4.
- Les modèles scikit-learn désactivent `early_stopping` pour ne pas introduire un sous-ensemble aléatoire non temporel.
- Le statut de publication reste **`safe_to_publish_forecasts=false`** même si une validation historique est encourageante.

## Exécution GitHub

- Branche isolée : `research/v2-3-1-stability-gating` ; PR brouillon séparée de `main`.
- `src/urban_ops/v231_stability.py` : règles et comparaisons.
- `scripts/train_v231.py` : orchestration de l'audit sur base P3 validée, **aucun export de poids ni prévisions par station**.
- `tests/test_v231_stability.py` : tests synthétiques de fuites, plafonnement, calibration, sûreté des fichiers de sortie.
- `.github/workflows/v231-stability.yml` : tests puis traitement des vraies archives, artifact **JSON uniquement**.

### À conclure après le traitement réel

Rapporter les MAE/RMSE, les fractions de prédictions modifiées, les jours couverts en validation et les règles effectivement choisies *sur la calibration interne*, sans réinterpréter un modèle égal à la persistance comme une victoire ML.

**Prochaine phase V2.4 :** verrouiller méthode et réglages, collecter des données **futures inédites**, puis mesurer si la MAE bat réellement la persistance sur jours ouvrés et week-end ; ne déployer qu'après validation explicite.
