# URBAN OPS P4 — Kit Power BI Desktop

Ce kit fournit **un modèle d’import des données analytiques** et des mesures; les jeux de données ne sont authentifiés comme réels que lorsqu’ils sont reconstruits à partir des archives P3 officielles contrôlées; aucun fichier `.pbix` fictif n'est annoncé. Il faut construire et sauvegarder le rapport dans Power BI Desktop.

## 1. Données à charger

Exécuter `python -m scripts.export_p4 --db-url sqlite:///./data/replayed.sqlite --output data/p4-export` après restauration des archives. Le dossier contient ces CSV UTF-8 BOM :

| Table | Grain | Usage |
|---|---|---|
| `dim_station` | 1 station | nom, capacité, latitude, longitude (valeurs les plus récentes disponibles) |
| `dim_date` | 1 journée de calendrier Europe/Paris observée | sélecteur de dates |
| `fact_station_hourly` | station x heure UTC | analyse horaire, changements d'heure sans collisions |
| `fact_station_daily` | station x jour local | bilan journalier, éviter de l'additionner aux données horaires |
| `fact_network_hourly` | heure UTC | tendances agrégées sur observations qualifiées |
| `fact_station_latest` | station x dernier snapshot capturé | carte du dernier état **du jeu exporté**, pas forcément du direct |
| `fact_capture_intervals` | collecte réussie | délais entre captures, détection de trous (> 10 minutes) |
| `fact_issues` | anomalie signalée | contrôles qualité et causes |
| `fact_runs` | tentative de collecte | supervision et fiabilité |
| `manifest.json` | livraison | bornes temporelles, nombre de captures, SHA-256, limites |

Ne pas importer les fixtures depuis `tests/fixtures/` dans un rapport présenté comme réel. Pour Power BI : **Obtenir les données > Texte/CSV** pour chaque table (ou créer `fxLoadUrbanCSV` depuis `fxLoadUrbanCSV.pq` puis une requête `= fxLoadUrbanCSV("nom_table")`). Vérifier que le dossier paramétré dans la fonction correspond au chemin de vos CSV.

### Types explicites à appliquer dans Power Query

- `station_id` : Nombre entier, 64 bits; `station_code` : **Texte** (zéros initiaux conservés).
- `latitude` / `longitude` et moyennes : Nombre décimal.
- `local_date` : Date; `utc_hour_start`, `collected_at`, `feed_updated_at`, `station_reported_at`, `started_at`, `finished_at` : Date/heure ou Date/heure/fuseau horaire selon Power BI Desktop; **les données sources sont en UTC**.
- `is_usable`, `is_installed`, `is_renting`, `is_returning`, `is_weekend` et comptes : Nombre entier.
- `run_id`, `station_name`, `issue_code`, `severity`, `details`, `status` : Texte.
- Éviter la détection automatique qui peut altérer `station_code` ou changer les fuseaux horaires.

### Relations (direction simple, dimension → fait)

| Source 1 | Source * | Type |
|---|---|---|
| `dim_station[station_id]` | `fact_station_hourly[station_id]` | 1 → plusieurs, active |
| `dim_station[station_id]` | `fact_station_daily[station_id]` | 1 → plusieurs, active |
| `dim_station[station_id]` | `fact_station_latest[station_id]` | 1 → plusieurs, active |
| `dim_station[station_id]` | `fact_issues[station_id]` | 1 → plusieurs, active (certaines anomalies n'ont pas de station) |
| `dim_date[local_date]` | `fact_station_hourly[local_date]` | 1 → plusieurs, active |
| `dim_date[local_date]` | `fact_station_daily[local_date]` | 1 → plusieurs, active |
| `fact_runs[run_id]` | `fact_issues[run_id]` | 1 → plusieurs, active |

Ne pas relier directement les faits horaires et journaliers entre eux. `fact_network_hourly` est volontairement indépendant (heures UTC), à utiliser pour les visuels réseau sans filtre par station.

## 2. Mesures

Le fichier `measures.dax` donne les mesures prêtes à copier dans `_Measures`. Les mesures sont définies **à partir de `fact_station_hourly`**, sans moyenner des moyennes déjà arrondies. Taux en format pourcentage (une décimale), comptes en entier, vélos en décimal (une décimale).

## 3. Les quatre pages du rapport

### 01 / Réseau — photographie opérationnelle

Bandeau typographique sobre, dernier horodatage du dataset toujours visible. Indicateurs : stations observées, observations exploitables, part d'observations sans vélo et sans borne. Graphique horaire `fact_network_hourly`, en séparant clairement nombre d'observations et vélo moyen. Ne pas appeler cette page « temps réel » si l'historique n'a pas été rafraîchi.

### 02 / Territoires — distribution spatiale

Carte latitude/longitude de `dim_station`, enrichie avec `fact_station_latest` et filtres de qualité. Codes stations et capacité dans tooltip, clic vers détails. Pas d'arrondissement inventé : `dim_station` ne contient pas cette dimension. Ne pas présenter la carte comme la position GPS des vélos.

### 03 / Stations — évolution vérifiable

Sélection station + fenêtre; série horaire des disponibilités moyennes, nombre de captures qualifiées, comparatif mécanique/électrique et tableau par journée. Les trous d'observation restent des **trous**, aucune ligne artificiellement interpolée. Les heures d'automne 02:00 restent identifiées par `utc_hour_start` et le décalage UTC.

### 04 / Fiabilité — Data Quality & Observabilité

Captures réussies/échouées, anomalies par `issue_code` et `severity`, station avec plus de données invalides, suivi du nombre d'observations par heure. Les enregistrements non exploitables restent dans les faits mais ne rentrent pas dans les moyennes de vélos. La qualité a autant de poids que les chiffres métier.

## 4. Style de restitution

Fond ardoise sombre, contraste typographique, marges généreuses, accents sobres. Éviter le « template IA dashboard » : pas de cartes arrondies systématiques, pas d'ombres artificielles, pas de « 95 % de disponibilité du service » sans mesure métier justifiée. Importer `urbanops_theme.json` dans Affichage → Thèmes → Parcourir.

## 5. Règles de présentation à un recruteur

Un snapshot représente **une observation de disponibilité**, pas un trajet, une demande ni une durée d'indisponibilité. `Part observations sans vélo` = échantillons exploitables à zéro vélo / tous les échantillons exploitables ; la métrique n'est pas une probabilité réelle de rupture ni un indicateur de disponibilité temporelle. `distinct_station_reports` estime la diversité des horodatages de remontée, sans inférer les trajets. Les données qui apparaissent dans `manifest.json` prouvent la provenance et la période réellement couverte. Pour parler de tendances, attendre suffisamment de journées observées.

### Vérification avant publication

Comparer `[Observations]` au nombre de lignes d'état du pipeline P3 filtrées, comparer les comptes d'anomalies et afficher les bornes de dates du `manifest.json`. Si la collecte manque plusieurs heures, le rapport doit l'indiquer, pas dessiner une tendance continue.