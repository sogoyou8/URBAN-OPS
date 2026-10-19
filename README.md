# URBAN OPS — P3 Data Engineering

**Statut : implémentation locale + tests sur fixtures synthétiques.** Aucun collecteur permanent
ni serveur distant n'a été mis en route. Ce dépôt de travail est indépendant de FPT,
Commerce 360 et France Électricité 2024.

## Objectif

Transformer les flux publics Vélib' Métropole en données fiables, traçables et analysables :

- **Bronze** : préserver les JSON sources exacts en `.json.gz`, SHA-256 et historique de collecte ;
- **Silver** : référentiel des stations + observations conservant **trois horodatages** ;
- **Quality** : anomalies explicitement consignées, valeurs brutes non inventées, quarantaine ;
- **Gold** : agrégats d'observations **journaliers UTC** par station.

Les deux API principales sont :

- https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_information.json
- https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_status.json

Sources et licence : données Vélib' Métropole, réutilisation à vérifier au regard de l'ODbL.
Ne présentez pas les fixtures comme des données réelles.

## Installation et premier test LOCAL (Python 3.10+)

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e '.[test]'
pytest
python -m urban_ops init
```

**Simulation explicite**, sans appel réseau, à partir de 3 stations imaginaires :

```bash
python -m urban_ops collect \\
  --information-file tests/fixtures/station_information.json \\
  --status-file tests/fixtures/station_status.json
python -m urban_ops report
```

L'exécution ci-dessus crée `data/urban_ops.sqlite` et deux archives Bronze dans `data/bronze/`.
Ces fichiers et la base sont ignorés par Git.

## Collecte avec les VRAIES API — seulement sur une machine avec Internet

```bash
python -m urban_ops collect
python -m urban_ops report
```

La collecte est **one-shot** : chaque exécution déclenche deux GET HTTPS séquentiels,
un traitement local transactionnel et se termine. Aucune tâche récurrente n'est lancée. Un **exemple de cron non activé**
est fourni dans `scripts/scheduler_example.txt`.
Les GET comportent des temporisations et tentatives limitées. Vérifier les règles
applicables à l'API avant d'activer une collecte périodique.

## PostgreSQL local (optionnel)

Avec Docker disponible sur la machine :

```bash
docker compose up -d postgres
pip install -e '.[postgres,test]'
export URBAN_OPS_DATABASE_URL='postgresql+psycopg://urbanops:local_dev_only_change_me@localhost:5434/urbanops'
python -m urban_ops init
python -m urban_ops collect
```

Le Docker Compose utilise un mot de passe de **développement local uniquement** et
n'expose PostgreSQL que sur `127.0.0.1`. Pour un service hébergé, fournir l'URL et les
secrets via l'environnement, activer TLS et limiter l'accès réseau. **L'accès PostgreSQL
n'a pas été testé dans l'environnement de génération** (pas de Docker ni serveur PG).

## Modèle et métriques

| Table / Vue | Contenu |
|---|---|
| `ingestion_runs` | État, empreintes et compteurs de chaque capture |
| `raw_snapshots` | Chemins des deux JSON bruts archivés |
| `dim_stations` | Identifiants `BIGINT`, stationCode conservé en texte |
| `fact_station_status` | Snapshots horodatés; compteurs nullables, drapeau qualité |
| `data_quality_issues` | Signalement par station et collecte |
| `quarantined_records` | Éléments non intégrables, JSON d'origine conservé |
| `gold_station_daily` | KPI basés sur les **échantillons qualifiés**, jour UTC |
| `vw_station_latest` | Dernière observation collectée par station |

`is_usable` nécessite les 3 flags opérationnels, compteurs non négatifs, sous-types
cohérents, station connue, disponibilité dans capacité et lag de remontée 0 à 3600 s.
Une station indisponible reste historisée mais exclue des moyennes de disponibilité.
Les journées et ratios ne constituent **pas** des durées de pénurie.

## Idempotence et erreurs

Chaque `run_id` identifie un lot; relancer un `run_id` déjà réussi ne recrée pas
les observations. Une nouvelle collecte reçoit un autre `run_id`. Une répétition d'un
flux identique peut correspondre à une nouvelle interrogation; elle est conservée
comme nouveau snapshot, avec son SHA-256 pour détecter les répétitions.

Les exceptions annulent les insertions Silver/Gold en cours. Le run devient `failed`.
Les archives Bronze déjà écrites restent disponibles pour investiguer l'incident.
On peut rejouer ces fichiers `.json.gz` via `collect --information-file ... --status-file ...`
avec un nouvel identifiant de collecte, après correction de la cause d'échec.
Ne pas lancer deux collecteurs simultanément avec la même base SQLite.

## État de la P3 et reste à réaliser

- Inclus : pipeline, DDL SQLite/PostgreSQL, traitements, CLI, fixtures, tests unitaires et
  bout-en-bout **SQLite**, documents de conception.
- Non prouvé ici : collecte réelle depuis ce conteneur, test d'intégration PostgreSQL,
  exécution 24/7, cadence de 5 minutes en production, archivage Parquet, export Power BI.
- Pour finaliser opérationnellement : exécuter sur une machine avec réseau, valider
  PostgreSQL, choisir un ordonnanceur durable, observer les KPI de qualité pendant
  plusieurs jours, fixer une politique de rétention/archivage puis publier.

Aucun déploiement Vercel requis à cette étape. Voir `docs/P3_AUDIT_AND_DECISIONS.md` et `docs/P3_OPERATIONS.md`.

## Intégration continue

Le workflow `.github/workflows/ci.yml` lance les tests SQLite **et** un test
PostgreSQL 16 sur service éphémère ; aucun flux réel, déploiement ou ordonnanceur
n’est lancé par ce workflow. Le test PostgreSQL est volontairement ignoré
si `URBAN_OPS_TEST_DATABASE_URL` n’est pas défini en local.
