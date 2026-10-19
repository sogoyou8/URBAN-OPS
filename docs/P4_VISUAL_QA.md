# P4 — Recette visuelle Power BI

Corrections après la recette Windows (pages 02 à 04).

- **Territoires** : nuage de points longitude/latitude sans champ `Category` (`Values` côté Desktop), noms/codes en info-bulles. Un graphique XY n'est pas une carte géographique.
- **Stations** : résumé par date locale, agrégé via mesures sur `fact_station_daily` et filtré par le sélecteur de station; évite les dates répétées pour toutes les stations.
- **Fiabilité** : 0 pour les erreurs de collecte **enregistrées** quand il n'y en a pas; la cadence affiche « Non mesurable » avec moins de deux captures, au lieu d'afficher un zéro trompeur.
- **Cartes** : affichage des comptes exacts, non arrondis en milliers; un seul libellé par indicateur.
- Aucun chiffre fabriqué, aucune série temporelle extrapolée : une capture reste une photographie unique, insuffisante pour analyser les tendances.

Recette de la nouvelle version : après validation CI et fusion, ouvrir le dernier run « P4 real analytics and Power BI export », récupérer le nouvel artefact `urban-ops-p4-real-4pages-PBIP`, décompresser les deux ZIP, ouvrir `UrbanOps.pbip`, définir `DataFolder` vers le `UrbanOps\\data` nouvellement extrait, puis actualiser. Vérifier les 4 pages dans Power BI Desktop. Les fichiers déjà ouverts sur le PC ne se mettent pas à jour automatiquement.
