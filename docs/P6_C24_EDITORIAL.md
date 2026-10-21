# P6 C2.4 — Vocabulaire clair pour un visiteur

## Objectif
Urban Ops n'est pas un exercice scolaire. Le texte de l'application s'adresse à une personne qui découvre Vélib’ Métropole, sans connaître P3, P5, les contrôles techniques et les expériences ML. Les archives et limites restent transparentes, **les calculs et données restent strictement identiques**.

## Ancien → nouveau, liste des principaux éléments

| Zone | Avant | Après |
| --- | --- | --- |
| Bandeau | Mobility Intelligence | Observatoire Vélib’ |
| En-tête historique | Continuité du réseau / des captures | Historique des vélos |
| Alerte historique | X relevé(s) à couverture réduite | X capture(s) incomplète(s) (en orange) |
| Compteur historique | Captures rejouées | Captures utilisées |
| Délai historique | Écart max. | Plus grande pause |
| Compteur historique | Couverture réduite | Captures incomplètes |
| Explication des points orange | Heuristique de couverture et non-comparabilité | Ces captures contiennent moins de stations mesurées. Les chiffres peuvent sembler plus bas, sans disparition prouvée de vélos. |
| Deux séries historiques | Bande de couverture / relevés qualifiés | Vélos comptés / stations mesurées |
| Bandeau de zone | Analyse spatiale | Comparer les quatre zones |
| Panneau territoires | Découpage analytique en quadrants médians | Comparer les vélos dans quatre zones de la carte, différentes des arrondissements |
| KPI fiabilité | Observations exploitables | Stations avec données fiables |
| KPI fiabilité | Observations non exploitables | Données inutilisables |
| Données absentes | Non qualifiées | Données inconnues |
| Panneau fiabilité | Audit / dernière capture archivée | Dernière capture |
| Panneau fiabilité | Pourquoi des observations sont rejetées | Comprendre les données manquantes |
| Prévisions, titre | Prédire, sans inventer | Prévisions en préparation |
| Prévisions, introduction | Horizon de modélisation et preuves | Prévisions à 30 minutes en préparation ; captures encore à vérifier |
| Prévisions, panneau | Des preuves avant le modèle | Les prévisions sont en préparation |
| Prévisions, progression | Conditions d'entraînement / seuil calendaire | Captures recensées / jours de données / relevés disponibles |
| Prévisions, statut | Évaluation ML vs baseline | Tests des prévisions |
| Prévisions, statut | Paires futures +30 min | Données pour les prévisions |
| Prévisions, KPI | Score prédictif | Fiabilité des prévisions |
| Aide, titre | Mode d'emploi | L'essentiel |
| Aide, méthodes | GBFS, empreintes SHA-256, P3, P5, validation hors échantillon | Données ouvertes officielles Vélib’, captures archivées et vérifications |
| Aide, historique | Couverture réduite par rapport au meilleur niveau | Point orange = moins de stations mesurées qu'aux autres captures |
| Aide, prévisions | Pas de score inventé | Prévisions en préparation |
| Chargement échoué | Synchronise un export P6 vérifié | Impossible de lire les données. Réessayez. |

## Règles conservées

- **Captures ≠ temps réel** : la date de référence reste visible.
- **Donnée inconnue ≠ aucun vélo** : les mesures absentes ou inutilisables ne sont jamais assimilées à zéro.
- **Points orange** : le calcul de C2.3 reste **strictement le même** (moins de 90 % du nombre maximum de stations exploitables dans la fenêtre), mais son explication est compréhensible. Cette couleur est une aide de lecture et non un verdict technique.
- **Prévisions** : pas de nouveaux modèles, de performances, de trajectoires ou de données créées. Les seuils de P5 et la provenance par inventaire de noms restent inchangés.
- Les détails de pipeline, somme SHA, critères et audit restent dans les autres documents techniques du dépôt.

## Recette
Node JS + Python, Chromium desktop et mobile, plus rendu du bundle réel P3 dans le workflow P6 GitHub Actions. Les tests incluent des attentes sur les nouveaux intitulés et refusent le retour des principaux termes techniques dans la section Historique.
