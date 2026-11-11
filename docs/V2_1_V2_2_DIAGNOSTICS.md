# Urban Ops V2.1 + V2.2 — Diagnostic scientifique et variables temporelles

**Statut : recherche séparée, aucune modification de V1 ni déploiement.**

## État de départ (P5 évalué le 26/10/2026)

- Persistance à +30 min = conserver le dernier nombre réellement observé de vélos.
- MAE validation : persistance **0,8374** / candidat **0,9731** vélo.
- MAE test final : persistance **1,1549** / candidat **1,2203** vélo.
- RMSE test : persistance **2,0117** / candidat **1,9411** vélo.
- Décision de P5 : `baseline_wins_or_uncertain`; aucun modèle ni pronostic autorisé en V1.

**Interprétation limitée :** le modèle réduit la RMSE sur le test, mais perd au regard de la MAE, notre critère préenregistré. Cela ne démontre ni biais géographique, ni défaut d'horaire, ni que de nouvelles variables amélioreront la prévision. Ce sont des hypothèses à analyser.

## V2.1 — Questions de diagnostic

Le script `scripts/v2_diagnose.py` repart des **archives P3 réelles vérifiées SHA-256** et rejoue exactement le candidat P5 initial, sans sauvegarder le modèle. Il produit :

- Effectifs admissibles et échantillonnés par période (train, validation, test).
- MAE/RMSE agrégées du candidat et de la persistance pour validation et test.
- Découpage descriptif **de la validation uniquement** : amplitude du vrai changement de vélos, période de la journée, semaine/week-end, disponibilité courante, trous -5/-15 min, et stations avec recul suffisant.
- La performance sur le test est publiée uniquement au niveau **agrégé** : ne pas adapter les variables aux exemples individuels de cette période.

Ces diagnostics doivent permettre d'identifier le type d'erreur plutôt que supposer à l'avance sa cause. Chaque sous-groupe trop petit est signalé comme non concluant.

## V2.2 — Neuf variables expérimentales

Conserver les 16 variables P5 intactes. Le module `src/urban_ops/v2_research.py` ajoute :

| Nom technique | Sens | Source autorisée |
|---|---|---|
| bikes_10m_ago | vélos observés vers T-10 min | capture passée réelle ±2 min |
| bikes_30m_ago | vélos observés vers T-30 min | capture passée réelle ±2 min |
| delta_30m | variation T moins T-30 | seulement si capture T-30 existe |
| bikes_fraction_of_capacity | remplissage actuel du stock vélos | capture actuelle qualifiée + capacité |
| docks_fraction_of_capacity | part de bornes libres | capture actuelle qualifiée + capacité |
| qualified_history_30m_count | nombre de captures utilisables depuis T-30 | observations passées uniquement |
| qualified_history_30m_volatility | écart-type des vélos sur T-30...T | observations passées + actuelle |
| minutes_since_prior_qualified | intervalle depuis dernière mesure exploitable | observation passée |
| qualified_history_30m_range | amplitude des vélos sur T-30...T | observations passées + actuelle |

Les lag temporels **ne sont jamais interpolés**. Toute donnée future, d'une autre station ou de la même minute injectée dans l'historique est rejetée. Les valeurs indisponibles restent `NaN`. Les statistiques de glissement n'utilisent que la fenêtre révolue avant ou à T.

Le workflow échantillonne les vrais couples à T+30 ±2 min selon **le même découpage chronologique purgé** et publie la disponibilité des neuf variables, **sans entraîner de nouveau modèle**.

## Conditions d'exécution et lecture du résultat

1. CI branche `research/v2-1-v2-2-data-diagnostics`, pas `main`.
2. Tests de fonctions sur fixtures synthétiques : tests de sûreté **uniquement**, jamais scores revendiqués.
3. Inventaire P3 + téléchargement des archives publiques + restauration SHA.
4. Diagnostic segmenté de l'ancien modèle et disponibilité V2.2 sur les observations réelles.
5. Artifact `V2_1_V2_2_DIAGNOSTICS.json` pour preuves. **Aucun `model.joblib` ni `station_forecasts_30m.csv` écrit.**

Le workflow peut être lent car il restaure jusqu'à 10 jours de captures réelles. Un résultat de pipeline `in_progress` ne prouve aucune analyse statistique terminée.

## Décision pour V2.3 et V2.4

Ne pas annoncer de gain V2 avant l'entraînement suivant et **une nouvelle période de test future et strictement indépendante**. Le test P5 original sert de référence historique ; après inspection des erreurs, il ne peut plus être qualifié de « test entièrement inédit » pour une nouvelle sélection de modèles.

Ce chantier reste indépendant de `https://urban-ops.vercel.app/`, qui continue ses instantanés archivés P3, et de la page portfolio Abyss.

## Résultats observés sur les captures réelles — exécution du 27/10/2026

**Preuve :** [GitHub Actions #40468762518](https://github.com/sogoyou8/URBAN-OPS/actions/runs/40468762518) ; artifact `urban-ops-v2-1-v2-2-research-40468762518` contenant `V2_1_V2_2_DIAGNOSTICS.json` et `v2-p5-inventory.json` (rétention GitHub de 14 jours).

### Qualité et volume de la source

- 2 121 captures P3 rejouées et vérifiées ; 2 072 créneaux UTC distincts de cinq minutes sur 2 139 attendus : **96,87 %** de couverture indicative en 7,424 jours.
- 49 captures supplémentaires dans des créneaux déjà occupés (elles n'augmentent pas artificiellement la couverture).
- 1 623 839 paires chronologiques admissibles à l'entraînement, 526 372 à la validation, 578 842 au test, **avant échantillonnage**.
- Échantillon P5 comparatif : 100 000 / 25 000 / 25 000 exemples (entraînement / validation / test).
- L'échantillon V2.2 de disponibilité des variables : 10 000 / 5 000 / 5 000 exemples ; ces effectifs ne doivent pas être présentés comme le total des stations/captures.
- Bornes de séparation UTC : validation à partir du 24/10/2026 08:25:09 ; test à partir du 25/10/2026 20:03:12.

### Diagnostic V2.1 : ancien modèle contre persistance (+30 min)

| Ensemble | Persistance MAE | Ancien modèle MAE | Écart ML moins persistance | Verdict |
| --- | ---: | ---: | ---: | --- |
| Validation (25 000 exemples) | 0,9670 | 1,0756 | **+0,1086** vélo | persistance gagnante |
| Test agrégé (25 000 exemples) | 0,9926 | 1,0510 | **+0,0584** vélo | persistance gagnante |

Ces scores concernent **ce nouveau replay de 2 121 captures**, et ne remplacent pas les chiffres du premier run P5 du 26/10/2026 : son historique et son découpage temporel étaient différents.

**Découverte principale — validation uniquement :**
- **11 593 / 25 000 observations (46,4 %) : aucun changement réel de vélos à +30 min.** La persistance fait exactement 0,0 erreur moyenne, tandis que l'ancien modèle produit 0,3341 vélo d'erreur moyenne.
- Quand l'évolution est de **1–2 vélos** (10 919 exemples), l'ancien modèle est légèrement meilleur : 1,2268 contre 1,2895 de MAE (gain 0,0627 vélo).
- Quand l'évolution est d'au moins **3 vélos** (2 488 exemples), l'ancien modèle est meilleur : 3,8667 contre 4,0571 (gain 0,1904 vélo).
- Ces gains ponctuels ne compensent **pas** les corrections erronées du modèle sur les stations stables.
- Parmi les stations ayant actuellement 0 vélo (1 391 exemples), l'ancien modèle perd davantage : MAE 0,7880 contre 0,5751 (écart +0,2129).
- Le soir (18–23 h Paris), l'écart est de +0,1467 vélo, contre +0,0722 l'après-midi (12–17 h).

**Limite temporelle importante :** l'ensemble de **validation se situe entièrement sur le samedi 24 et le dimanche 25 octobre 2026** (`day_type.weekend = 25 000`). Les conclusions sur la comparaison semaine/week-end sont donc **impossibles** avec cette validation. La partition complète de 7,424 jours est admissible selon le protocole P5, mais insuffisante pour une généralisation robuste aux jours ouvrés dans les diagnostics V2.

Les stations « pires cas » contiennent seulement 25–28 observations par station dans le rapport. Elles sont **des exemples exploratoires**, pas une preuve généralisable de mauvais fonctionnement de ces stations.

### Disponibilité des variables expérimentales V2.2

| Variable candidate | Manquants en validation | Remarque |
| --- | ---: | --- |
| vélos vers T-10 min | 4,86 % | Ne pas interpoler |
| vélos vers T-30 min | 1,08 % | Ne pas interpoler |
| variation T - T-30 | 1,08 % | Dépend du précédent |
| fraction vélos / capacité | 0 % | Disponible |
| fraction bornes / capacité | 0 % | Disponible |
| nombre de captures qualifiées sur 30 min | 0 % | Disponible (zéro possible) |
| volatilité sur 30 min | 0 % | Disponible, dépend de l'historique présent |
| délai depuis observation passée qualifiée | 0 % | Disponible en validation ; 0,14 % manquants en entraînement |
| amplitude des vélos sur 30 min | 0 % | Disponible, dépend de l'historique présent |

Le fait qu'une valeur calculée ait **0 % de manquants** ne garantit pas que l'historique contient plusieurs captures : la volatilité et l'amplitude peuvent valoir zéro sur une seule observation. Les variables de comptage servent à rendre ce cas identifiable.

### Décisions après V2.1/V2.2

1. **V2.1 terminé** : l'échec sur les situations stables est maintenant mesuré ; l'hypothèse d'un manque systématique de données n'est pas confirmée.
2. **V2.2 terminé en préparation** : les neuf caractéristiques sont définies, testées sans fuite et leur couverture est mesurée sur captures vérifiées. **Aucun nouveau modèle entraîné**.
3. **V2.3 recommandé** : entraîner/évaluer sur validation des méthodes conservatrices de correction de la persistance, dont une correction résiduelle qui peut rester à zéro et un filtrage des prédictions sur stations stables ; comparer aussi des modèles simples avant de complexifier.
4. **V2.4 obligatoire avant tout déploiement** : réserver **une nouvelle période future entièrement inconnue des choix V2.1–V2.3**, comprenant des jours ouvrés et des week-ends. L'ancienne période test n'est plus « totalement vierge » après examen de ses métriques agrégées. Ne pas annoncer de gains réels V2 pour le moment.
5. **V1 inchangée** : aucune prévision exportée, `safe_to_publish_forecasts=false`, ni modèle sérialisé.

**Conclusion : la recherche ne dépend plus de la fin d'un traitement GitHub.** On peut commencer V2.3. Une période future réellement indépendante reste nécessaire pour décider de publier le modèle.
