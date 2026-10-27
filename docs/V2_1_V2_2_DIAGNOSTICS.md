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
