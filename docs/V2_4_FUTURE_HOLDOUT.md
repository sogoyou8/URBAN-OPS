# Urban Ops V2.4 — Expérience future indépendante verrouillée

**Statut au 27 octobre 2026 :** protocole prédéfini et code prêt, **pas de résultat futur possible avant le 4 novembre 2026 à 04:00 UTC**. Travaux dans `research/v2-4-future-holdout`, sans modification de la V1 Vercel.

## Décision scientifique déjà connue

- La méthode de référence est la **persistance des vélos actuellement observés**.
- Dans V2.3.1, l'IA résiduelle a obtenu **0,9544** de MAE contre **0,9486** pour la persistance sur les anciennes données de validation. Les approches conservatrices ont retenu une correction nulle et ont seulement égalé la persistance.
- **Aucun candidat V2.3.1 n'a réussi le seuil de validation historique (au moins 1 % de gain MAE).** Le candidat brut figé ici est donc étudié pour comprendre sa généralisation, **mais non admissible à une publication automatique**, même si les nouveaux chiffres montrent un gain isolé.

## Préenregistrement immuable (UTC)

| Paramètre | Décision fixée le 27/10/2026 |
| --- | --- |
| Identifiant | `urban-ops-v24-20261027-locked-v1` |
| Dernière donnée autorisée dans l'entraînement (exclue) | **27/10/2026 10:40 UTC** |
| Début de la semaine future, inclus | **28/10/2026 00:00 UTC** |
| Fin de la semaine future, exclue | **04/11/2026 00:00 UTC** |
| Première heure autorisée de contrôle final | **04/11/2026 04:00 UTC** (05:00 à Paris) |
| Horizon prédit | **30 minutes ±2 minutes** |
| Jours futurs | 7 dates UTC : **5 jours de semaine + samedi/dimanche** |
| Slots attendus (5 min) | 2 016 |
| Couverture minimale des vrais slots P3 | **75 %**, sans duplication |
| Vraies paires éligibles minimales | 20 000 dont **au moins 1 000 par jour UTC** |
| Diversité minimale | 300 stations différentes |
| Échantillon reproductible du holdout | jusqu'à 40 000 vraies paires, graine 2404 |
| Décision de diffusion | **Aucune promotion automatique** |

Le SHA-256 du protocole est déclaré par `src/urban_ops/v24_protocol.py`, et copié dans les preuves du modèle figé puis du test futur. Le branchement V1 n'est pas modifié.

## Modèle figé avant les résultats futurs

`scripts/v24_freeze.py` utilise **seulement** les observations et étiquettes P3 de stations vérifiées, toutes avant la date d'arrêt de l'entraînement. L'algorithme est l'HistGradientBoostingRegressor résiduel V2.3, avec ses **paramètres déjà décidés**, sans nouveau réglage sur les données futures. Le fichier expérimental `v24_frozen_challenger_research_only.joblib` et son manifeste ne sont stockés **que comme artifact GitHub Actions** (30 jours), avec empreinte SHA-256. Aucun poids du modèle dans Git, aucun CSV de prévisions publiques.

Action de gel : `.github/workflows/v24-freeze.yml`. L'identité de l'exécution retenue est fixée pour l'évaluateur :

- GitHub run **40495787979** ;
- code préenregistré **`69971d07bbde5737da2e985f0b19952e20fee79c`**.

Si ce run de gel échoue, **ne pas substituer un autre modèle après avoir vu la semaine future** ; toute correction nécessaire avant le 28/10 00:00 UTC doit être explicite et accompagnée d'une nouvelle identité de gel.

## Comment s'exécutera le test

`.github/workflows/v24-evaluate.yml` possède un précontrôle sans lecture de cibles futures :

1. **Avant le 04/11 04:00 UTC**, GitHub peut exécuter les tests de protocole et rendre le statut `awaiting_future_data`, mais **ne charge pas le modèle et ne calcule aucun score futur**.
2. Au terme de la semaine, inventaire des assets des sept dates visées. Si les 75 % de créneaux ne sont pas atteints ou si les bords du créneau manquent, la comparaison est bloquée.
3. Vérification de la réussite du **run de gel épinglé**, de son commit Git, du manifeste, de la date de gel et de l'empreinte SHA-256 du modèle.
4. Téléchargement et reconstruction des captures P3 réelles de la période, avec vérification des archives SHA-256.
5. Construction de **vraies** paires observées à +30 min, après les règles `is_usable`, sans interpolation ; conditions minimum par jour, par station et globales.
6. Calcul de MAE, RMSE et analyse descriptive jour par jour, avec répartition des cas réellement stables/changés. Ces segmentations rétrospectives ne servent jamais à choisir les paramètres.
7. Rapport **`V24_FUTURE_HOLDOUT_REPORT.json`**, aucun nouveau modèle exporté, aucune prévision par station activée, aucun déploiement.

**Important sur l'automatisation :** GitHub Actions `schedule` ne démarre que les workflows présents sur la branche GitHub par défaut. Comme la V2 est volontairement conservée sur une branche de recherche et non fusionnée dans `main`, la validation finale ne peut pas être honnêtement présentée comme déclenchée automatiquement le 4 novembre. Une fois la date atteinte, exécuter `V2.4 future independent evaluation` sur la branche V2.4 si GitHub le propose, ou modifier `docs/V24_EVALUATION_TRIGGER.md` dans cette branche pour provoquer le workflow `push`. Ne pas déplacer cette workflow dans `main` juste pour obtenir un cron si cela risque un déploiement Vercel non voulu.

## Conditions de clôture

La préparation, les tests et la preuve de gel peuvent être clos maintenant. **Le résultat scientifique V2.4 reste en attente de la semaine future**, même si les fichiers et la CI sont opérationnels. En cas de données manquantes, indiquer le vrai statut bloqué plutôt que fabriquer des mesures.

V1 : `https://urban-ops.vercel.app/`. Le produit public conserve la section Prévisions désactivée, car aucun modèle n'a passé la validation historique.

Cette expérience n'établit pas de demande ou de trajet à vélo ; seule la disponibilité observée de chaque station est prédite.
