# URBAN OPS — Observatoire des archives Vélib’ Métropole

**Statut au 22 octobre 2026 : observatoire P6 validé en CI, publication GitHub Pages non encore activée, prévisions P5 non validées.** Le collecteur P3 GitHub Actions fonctionne de façon récurrente en *best effort* et archive les captures réelles dans des Releases. Le projet Power BI P4 est généré automatiquement mais son rendu dans Power BI Desktop Windows reste à vérifier.

**Clôture V1 et mise en ligne :** [voir les étapes réelles, les critères de gel et la procédure GitHub Pages](docs/URBAN_OPS_V1_RELEASE.md).

Ce dépôt est indépendant de FPT, Commerce 360 et France Électricité 2024. Les sections historiques ci-dessous décrivent les jalons de développement et peuvent contenir des constats datant du démarrage du projet.

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

## P3 — Pilotage et historique GitHub (sans nouveau service payant)

Un workflow GitHub Actions best-effort 5 min archive chaque capture validée dans les **Releases journalières**, sans encombrer l'historique Git. Une base SQLite éphémère valide chaque collecte ; l'historique durable vient des archives horodatées, importables dans PostgreSQL par replay. **Attention : aucune SLA GitHub Actions, des captures peuvent manquer.** Mode d'emploi, limitations et contrôle 24 h : [`docs/P3_COLLECTION.md`](docs/P3_COLLECTION.md).

Vérifications réelles du pilote : [premier archivage](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39328054063), [Release du 19 octobre](https://github.com/sogoyou8/URBAN-OPS/releases/tag/velib-data-2026-10-19) et [replay indépendant](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39328436934). La cadence programmée reste best-effort et doit être évaluée sur 24 h.


## P4 — Analytics / Power BI (nouvelle phase)

Le module `urban_ops.analytics` construit des tables analytiques **à partir des seules
observations P3 enregistrées**, sans interpolation ni données fabriquées. Il exporte
`dim_station`, `dim_date`, `fact_station_hourly`, `fact_station_daily`,
`fact_network_hourly`, `fact_station_latest`, `fact_issues`, `fact_runs` et
`fact_capture_intervals` en CSV UTF-8 + manifeste JSON SHA-256.

Après avoir rejoué des captures réelles depuis les Releases :

```bash
python -m scripts.export_p4 --db-url sqlite:///./data/historique.sqlite --output data/p4-export
```

Le workflow **[P4 real analytics and Power BI export](.github/workflows/p4-analytics.yml)**
lance un export réel borné et publie un ZIP téléchargeable dans les artifacts GitHub
Actions (14 jours de rétention). Voir [`powerbi/MODEL.md`](powerbi/MODEL.md)
(4 pages, relations, DAX, M, thème) et [`docs/P4_VALIDATION.md`](docs/P4_VALIDATION.md).
Ce kit n'est **pas** un `.pbix` préconstruit : l'assemblage visuel final doit être
réalisé et vérifié dans Power BI Desktop.

## P3.5 — Historique et régularité

La collecte GitHub Actions est **best effort** ; deux captures espacées de plusieurs heures prouvent que le rythme visé n'est pas garanti. Un audit indépendant des archives de Releases est exécuté périodiquement et sur demande ; il remonte les écarts, l'âge de la dernière archive et une couverture indicative sur 24 h. Voir [P3.5 — Fiabilité de la collecte](docs/P35_COLLECTOR_RELIABILITY.md). Aucun événement passé n'est recréé.

## P3.5 — Cloudflare : code préparé, **non déployé**

Un Worker Cron (toutes les 5 minutes dans la configuration) et un archivage R2 Standard sont prêts et testés hors ligne, avec un convertisseur vers le replay Bronze/Silver/Gold existant. **Aucun bucket, abonnement ou déploiement Cloudflare n'a été créé.** R2 requiert une souscription et peut générer des frais au-delà des quotas gratuits; l'activation devra être explicitement approuvée. Voir [guide Cloudflare](docs/P35_CLOUDFLARE_PREPARATION.md).

## P3.5 — Chemin gratuit sans abonnement R2

Pour respecter la contrainte **strictement sans carte ni abonnement payant**, utiliser le [déclencheur Cloudflare Workers Free vers GitHub Actions](docs/P35_FREE_WORKER_GITHUB.md). Il ne contient aucune liaison R2 et ne déploie rien automatiquement : le programme est livré et testé, l'activation nécessite la configuration personnelle d'un jeton GitHub limité. Les captures demeurent des archives GitHub Releases. L'ancien prototype R2 reste non déployé.


## P5 — Machine Learning sous contrôle historique

Prévision **des vélos disponibles à chaque station dans 30 minutes**, avec historique P3 vérifié, baseline de persistance, modèle de gradient boosting, séparation temporelle avec purge anti-fuite et mesure MAE/RMSE sur données futures. **Aucune métrique réelle n’est annoncée tant que nous n’avons pas au moins sept jours, 900 captures et une couverture suffisante.** Le workflow GitHub `P5 real-data 30-minute forecasting` exécute d’abord cette vérification, puis entraîne uniquement si les archives sont suffisantes. Voir [P5 — Machine Learning](docs/P5_MACHINE_LEARNING.md). Aucune infrastructure payante nouvelle.


## P6 — Cockpit Web Urban Ops

Un cockpit géographique statique dans `web/` présente les **capturations réelles P3 archivées**, la qualité, les vélos qualifiés et les quatre quadrants analytiques. Filtrage, recherche et inspection des stations; courbe discontinue en cas de trous; **P5 est bloqué** tant que la validation réelle est insuffisante. `scripts/export_p6.py` fabrique `web/data/network.json` depuis les archives SQL restaurées; `scripts/sync-p6.ps1` récupère le dernier artifact P6 sur GitHub dans **le même dossier local UrbanOps**. Le workflow `P6 Urban Ops cockpit — checks and verified real snapshot` publie des artefacts sur GitHub Actions, **sans déploiement ni paiement**. [Guide P6](docs/P6_COCKPIT.md).


## P6.9 — Paquet vérifiable, **aucun déploiement**

Le workflow P6, après rejeu SHA-256 de vraies archives P3, fabrique `dist/p6-public/` avec données et bibliothèque MapLibre auto-hébergée, politique CSP, `manifest.json` SHA-256 et `provenance.json`. Chromium teste le **bundle final** sous un sous-chemin HTTP, sans publier. L'artefact `urban-ops-p69-publication-ready` est disponible dans GitHub Actions pendant 7 jours; **GitHub Pages n'est pas configuré ni activé**. La stratégie de publication gratuite, à soumettre pour autorisation explicite, est détaillée dans [P6.9 — Publication readiness](docs/P69_PUBLICATION_READINESS.md). P5 demeure non validé.


## Mise au point — avancer pendant la collecte P3 (21 octobre 2026)

**Ne pas attendre la fin des sept jours pour développer ni préparer la publication.** Les archives P3 continuent d'être collectées en tâche indépendante ; le pipeline P6 construit un observatoire sur les captures effectivement disponibles. Les critères de validation P5 **7 jours / 900 captures / 40 % de couverture des créneaux de cinq minutes** ne sont pas assouplis.

L'étape `scripts/p5_exploratory.py`, exécutée depuis le rejeu P3 SHA-256 de P6, mesure les **vraies paires à +30 minutes**, la baseline et, si assez de paires existent, un **essai de modèle expérimental**. Elle produit seulement `P5_EXPLORATORY_ONLY.json`, sans `.joblib` ni prévisions, et mentionne toujours `NOT_VALIDATED`. L'entraînement final et la promotion restent dans `scripts/train_p5.py` avec leur propre contrôle indépendant.

La préparation de publication produit désormais aussi `data/c3-preflight.json` après vérification du paquet public : **contrôle technique sans hébergement**. La checklist `docs/C3_PUBLICATION_CHECKLIST.md` documente les actions restantes, les limites et la nécessité de confirmer explicitement toute activation de GitHub Pages. C3 et P5 peuvent donc avancer **en parallèle**, sans prétendre que les prévisions existent déjà.


## C3 — Publication volontaire, sans prévisions fictives

Le dépôt propose désormais **deux étapes distinctes** : `.github/workflows/p6-cockpit.yml` produit un paquet intégralement contrôlé depuis les archives réelles, puis `.github/workflows/c3-pages-publish.yml` permet, **uniquement à la demande**, de le publier sur GitHub Pages. Ce second workflow impose le succès de P6 sur le commit exact de `main`, la fraîcheur des captures (moins de trois heures), des données de stations réellement exploitables et le maintien de P5 désactivé. **Aucun déclencheur automatique ni URL publique active n'est présumé.**

Le projet Power BI est structurellement vérifié avec `scripts/check_p4_pbip.py`, mais les quatre pages devront être ouvertes et actualisées dans Power BI Desktop pour confirmer leur rendu réel. Les détails exacts et la présentation portfolio factuelle sont dans `docs/URBAN_OPS_V1_RELEASE.md`.
