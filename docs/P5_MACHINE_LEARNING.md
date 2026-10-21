# Urban Ops — P5: Prévisions de vélos à +30 minutes

## Question métier

**Combien de vélos seront observés à une station Vélib' dans 30 minutes ?**
La cible est `num_bikes_available` de la **véritable capture future qualifiée**. Il ne s'agit ni d'une fréquentation, ni de trajets, ni de demandes, ni d'un taux de pénurie sur une durée. Les captures manquantes ne sont jamais interpolées.

## Source et provenance

- Entrée : P3, `fact_station_status`, jointure avec `ingestion_runs.status = success` et `dim_stations`.
- Seules les observations marquées `is_usable = 1` servent de caractéristiques et de cible.
- Horizon : **30 min ± 2 min**. Une paire n'existe que si une seconde capture réelle de la même station a été enregistrée à cette échéance. Les flux dont le temps est discontinu sont éliminés.
- La reconstruction CI utilise **uniquement** les archives historiques GitHub Releases `capture-*.tar.gz`, dont les checksums sont validés par `replay_capture` avant la modélisation.
- Les fixtures locales servent **seulement aux tests** et ne peuvent jamais être présentées comme performance réelle.

## Politique : pas d'entraînement trompeur

Le train est bloqué tant que l'historique n'a pas : **7 jours révolus**, **900 captures distinctes** et **40 % de couverture indicative calculée sur les créneaux UTC distincts de cinq minutes** sur la période observée. Plusieurs archives ayant des horodatages différents dans un même créneau comptent pour une seule preuve de couverture. Ce sont des seuils de prudence, pas une garantie statistique. Après extraction : au moins 5 000 paires en entraînement et 1 000 paires pour chacun des deux blocs d'évaluation. L'entraînement ne peut être conclu « validé » à partir de 2, 3 ou 4 captures.

La découpe est *chronologique*, UTC (premiers 60 % pour entraînement, 20 % validation, 20 % test), avec **purge des cibles qui dépassent la frontière de chaque ensemble**. Le test final ne sert ni à sélectionner des paramètres, ni à entraîner.

## Baseline et candidat

- **Baseline** : persistance `vélo(T+30) = vélo(T)`.
- **Modèle** : `HistGradientBoostingRegressor` scikit-learn, plafonné et déterministe.
- Variables : vélos/bornes disponibles T, capacité, types de vélos, retard de remontée, vrais décalages -5/-15 min (sans remplissage des trous), variation mesurée, heure locale en sinus/cosinus, jour de semaine, longitude/latitude.
- Résultats : MAE, RMSE et gain MAE versus baseline, sur validation et période test distincte. Aucune précision inventée.
- Promotion conditionnelle : **≥1 % de gain en validation et gain strictement positif au test**. Sinon résultat « baseline_wins_or_uncertain » ; aucun modèle ni pronostic n'est publié. Ces règles sont fixées avant les données futures.
- Les prédictions sont bornées à `[0, capacité connue]`. Une prévision du nombre de vélos n'est **pas une probabilité de trouver un vélo**, ni une mesure de trajet.

## Exécution sans abonnement payant

GitHub → **Actions** → `P5 real-data 30-minute forecasting (manual, no fake results)` → `Run workflow`. Le workflow vérifie les Releases (sans téléchargement si historique insuffisant), restaure les captures vérifiées, entraîne seulement si admissible et produit un artifact temporaire `urban-ops-p5-evidence-*`. **Aucun Cron P5**, aucun nouveau service ni déploiement.

Localement, sur la base P3 existante :

```powershell
# dans le dossier unique UrbanOps, une fois Python installé
python -m pip install -e '.[ml]'
python -m scripts.train_p5 --db-url sqlite:///./data/p5-history.sqlite --output data/p5-output
```

`P5_STATUS.json` déclare clairement `not_ready`, `insufficient_labeled_pairs`, `baseline_wins_or_uncertain` ou `validated_model`, avec les métriques *uniquement quand elles ont réellement été calculées*. Un `model.joblib` et `station_forecasts_30m.csv` ne sont créés que si le candidat bat les deux tests. Les lignes de prévisions sont associées à leur `as_of_utc` et ne sont **pas nécessairement en temps réel**. Le champ `origin_verified_by_p5` est `false` pour une DB fournie localement : le pipeline CLI seul ne saurait attester son origine.

## Ce qu'il reste avant de présenter P5 comme prédictif

1. Confirmer une archive toutes les ~5 minutes sur une période d'au moins sept jours, surveiller les doublons et interruptions.
2. Lancer le workflow P5 sur données réelles restaurées ; relever les métriques du holdout et la taille réelle des ensembles.
3. Si le modèle ne bat pas la baseline, **garder la baseline** et diagnostiquer les variables/la dérive, sans annoncer de performance prédictive.
4. Contrôler la dérive, la fraîcheur des captures, la stabilité géographique et la réactualisation du modèle avant branchement dans le cockpit P6.
5. Sur le CV, n'annoncer qu'une architecture de prévision et une évaluation chronologique **jusqu'à l'existence d'un backtest réel probant**.
## Préparation de P5 pendant les sept jours de collecte (octobre 2026)

Le **pré-contrôle** de `scripts/p5_inventory.py` inspecte uniquement les noms et horodatages des assets GitHub Releases. Le rapport `data/p5-inventory.json` expose les dates de la première et de la dernière archive, le nombre d'archives, les créneaux de cinq minutes **distincts**, les captures multiples dans un même créneau, les heures manquant encore pour sept jours révolus et les captures restant à obtenir pour atteindre 900. Il ajoute également un résumé dans l'exécution GitHub Actions.

**Deux niveaux doivent rester distincts** :

1. `ready_for_training` ne signifie que « suffisamment d'archives pour tenter une vérification réelle ». À ce stade, les données n'ont pas encore été réimportées et revalidées.
2. Ensuite, la procédure existante télécharge les archives, vérifie les hashes SHA-256, les remonte dans le pipeline P3, exige `is_usable=1`, construit les vraies paires à +30 minutes, applique la séparation temporelle anti-fuite, puis compare le modèle à la persistance. Seul un résultat `validated_model` obtenu sur les deux jeux d'évaluation permet de publier un modèle.

Le chantier de préparation n'abaisse **aucun seuil** et ne lance ni entraînement artificiel, ni collecte externe Pulse. Les trous de P3 demeurent des trous ; des requêtes successives identiques ne sont jamais utilisées pour gonfler la couverture.
