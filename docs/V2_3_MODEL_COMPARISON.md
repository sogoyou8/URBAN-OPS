# Urban Ops V2.3 — Comparaison de modèles (recherche, sans déploiement)

## But

Trouver une méthode de prévision à +30 minutes **plus fiable que la persistance** : conserver le nombre de vélos observé à T. V2.1 a identifié un coût majeur des faux changements quand les stations restent stables ; V2.2 a fourni neuf variables supplémentaires basées exclusivement sur le passé.

**Règle absolue :** pas de nouveau modèle dans V1, pas de production, pas de prévision par station publiée. Les résultats V2.3 sont des **comparaisons sur validation historique**, et **non une autorisation de déployer**.

## Trois méthodes comparées

1. **Persistance** : vélos(T+30) = vélos(T), référence.
2. **ML résiduel** : HistGradientBoostingRegressor entraîné à prédire exclusivement `vélo(T+30) - vélo(T)`, avec perte absolue, les 25 variables (16 P5 et 9 V2.2), bornes physiques 0…capacité.
3. **ML résiduel conservateur** : même modèle, mais correction atténuée (25/50/75/100 %) et/ou ignorée si son amplitude prédite est trop faible (seuils 0 / 0,5 / 1 / 1,5 / 2 vélos). Les réglages sont choisis uniquement sur une **calibration chronologique interne de l'entraînement**, jamais sur la validation externe ni sur le test.

La méthode conservatrice peut être exactement équivalente à la persistance (correction 0) si aucun réglage n'améliore la calibration. Ce n'est **pas** une victoire du modèle : une telle situation sera décrite comme maintien de la méthode simple.

## Politique anti-fuite

1. Source : archives P3 réelles de GitHub Releases, hash SHA-256 vérifié par `scripts.replay_capture`.
2. Seules les observations `is_usable` deviennent caractéristiques et étiquettes ; cible observée T+30 min ±2 min, aucune interpolation.
3. **Train : premier 60 % de l'historique ; validation externe : 20 % suivants ; ancien test P5 : non utilisé**. Les paires à cheval sur les frontières sont supprimées.
4. Au sein du train : 80 % du temps pour apprendre le résiduel, 20 % finaux pour calibrer les filtres de prudence, avec purge supplémentaire à la frontière.
5. Le modèle est entraîné une fois, sans holdout interne aléatoire sklearn (`early_stopping=False`) ni sélection par le test.
6. La validation ne sert qu'au bilan V2.3 : MAE, RMSE, part des prédictions modifiées, couverture des jours, analyse *a posteriori* « réellement stable / réellement changeante ». Ce dernier découpage se fonde sur la cible connue et **ne peut pas être utilisé pour choisir une politique à déployer**.
7. Les archives évoluant quotidiennement, les scores obtenus lors de différents jobs ne sont directement comparables **que s'ils ont exactement les mêmes périodes et mêmes échantillons**.

## Sorties et protections

- Code : `src/urban_ops/v23_candidates.py`, `scripts/train_v23.py`.
- Tests synthétiques de contrat : `tests/test_v23_candidates.py`. Aucun résultat de test synthétique n'est une métrique Vélib' réelle.
- Action recherche isolée : `.github/workflows/v23-compare.yml`, branche `research/v2-3-model-comparison`.
- Résultat réel si Action complète : artifact `urban-ops-v23-validation-only-<run_id>` contenant `V2_3_RESEARCH_COMPARISON.json` + inventaire P3. **Aucun fichier de poids du modèle ni de prévisions**.

## Critères de lecture des résultats

| Observation | Conclusion admissible |
|---|---|
| MAE du candidat supérieure/égale à persistance | V2.3 n'a pas trouvé de gain sur cette validation |
| MAE du candidat inférieure à persistance | Signal exploratoire intéressant ; confirmation V2.4 obligatoire |
| Calibration choisit « correction zéro » | Persistance conserve sa place ; ce n'est pas une victoire ML |
| Validation couvrant seulement week-end | Impossible d'affirmer généralisation semaine/week-end |

**V2.4 est nécessaire même si une comparaison V2.3 montre un gain** : utiliser une **nouvelle période de données futures**, constituée après cette recherche, comportant jours ouvrés et week-end, sans retravailler le modèle à partir de ce test. La règle initiale exige au moins 1 % de gain MAE en validation et gain strictement positif au test réellement inédit.

## Statut

Développement V2.3 intégré dans une branche de recherche distincte ; **résultats réels à renseigner après le job GitHub**, sans inventer de score. Le site `https://urban-ops.vercel.app/` reste la V1 publique figée.


## Résultats de l'exécution réelle du 27 octobre 2026

- **Exécution GitHub :** https://github.com/sogoyou8/URBAN-OPS/actions/runs/40475608204
- **Archive de preuve :** artifact `urban-ops-v23-validation-only-40475608204` (JSON de comparaison + inventaire, rétention 14 jours).
- **Source :** 2 134 replays P3 vérifiés SHA-256 ; 2 085 créneaux UTC distincts sur 2 152 théoriques, soit 96,89 % de couverture indicative, sur 7,469 jours.
- **Échantillons :** 90 000 train / 20 000 validation ; train interne effectivement 72 346 fit et 17 257 calibration. 1 633 989 paires admissibles train et 528 128 validation avant échantillonnage.
- **Découpage :** validation à partir du 24 octobre 2026 à 09:04:06 UTC ; ancien bloc test à partir du 25 octobre à 20:55:09 UTC, explicitement **non évalué** dans V2.3.
- **Limite :** les 20 000 observations de validation appartiennent **uniquement aux 24 et 25 octobre 2026 (week-end)** ; aucune généralisation aux jours de semaine n'est établie.

### Comparaison MAE / RMSE en validation

| Approche | MAE (vélos) ↓ | RMSE (vélos) ↓ | Part des prédictions modifiées |
| --- | ---: | ---: | ---: |
| **Persistance** | **0,9786** | 1,7163 | 0 % |
| Résiduel ML | 0,9790 | **1,7125** | 6,48 % |
| Résiduel conservateur | 0,9790 | 1,7145 | **0,88 %** |

Pour la méthode conservatrice, la calibration interne a retenu **alpha=1** et un seuil de correction de **1 vélo** : 1,0392 MAE, contre 1,0409 pour la persistance sur les seules données de calibration. Ce très faible avantage **ne s'est pas reproduit** sur la validation externe (0,9790 contre 0,9786). Il est interdit de requalifier cette méthode comme gagnante.

### Analyse exploratoire a posteriori sur la validation

| Situation connue après coup | Observations | Persistance MAE | Résiduel ML MAE | Conservateur MAE |
| --- | ---: | ---: | ---: | ---: |
| La station a réellement changé | 10 726 | 1,8246 | **1,8169** | 1,8220 |
| Le nombre de vélos est resté stable | 9 274 | **0,0000** | 0,0099 | 0,0040 |

Le résiduel peut légèrement mieux suivre certains changements mais introduit des erreurs quand les vélos restent identiques. **Il est impossible d'utiliser le vrai statut futur « changé / inchangé » comme entrée du modèle.**

### Décision après V2.3

**Status : `compared_on_existing_validation_only`, pas `validated_model`.** Aucun modèle sérialisé, aucune prévision exportée, aucune modification de V1.

- Aucun candidat ne bat la persistance en MAE sur cette validation ; **ne pas promouvoir un modèle pour V2.4 ni publier de prévisions.**
- Une itération V2.3.1 peut étudier des algorithmes plus simples (correction robuste, modèles à prédiction de changement) et surtout une validation sur plusieurs journées (ouvrées et week-end), en veillant à ne pas suradapter les hyperparamètres aux 24–25 octobre déjà inspectés.
- Après fixation définitive des variables, du modèle et du protocole, V2.4 devra évaluer un **nouveau jeu de données futur**, jamais inspecté pendant la sélection, incluant des jours ouvrés et un week-end.
- Conserver la collecte P3 et V1 sur Vercel ; **aucun déploiement** V2.
