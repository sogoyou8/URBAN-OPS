# Urban Ops — P3: décisions et contrôles

## Données observées en P2, 2026-10-19 (échantillon réel distinct des tests)

- `station_information.json` et `station_status.json` : HTTP 200, 1 519 stations chacune.
- 1 519 identifiants uniques par source; aucune clé orpheline dans cet échantillon.
- 11 cas où `num_bikes_available + num_docks_available > capacity`.
- 19 stations n'étaient pas simultanément installées, ouvertes à la location et au retour.
- 20 remontées individuelles dépassaient 1 h de décalage avec `lastUpdatedOther`.
- Le décalage médian observé était 1 225 s. Ce n'est pas une série temporelle ni une SLA.

## Modèle

Bronze : chaque paire de réponses est archivée telle quelle en `.json.gz` avec SHA-256.
Silver : stations UPSERT; états de stations horodatés par `collected_at`, `feed_updated_at`,
`station_reported_at`, et qualifiés via `is_usable`.
Quarantaine : états sans référence ou identifiants invalides/dupliqués.
Gold : agrégats par station et journée **UTC**. Les parts et comptes sont des **observations**,
pas des durées de rupture. L'absence d'échantillons utilisables laisse les moyennes NULL.

## Fraîcheur et statut

Le flux global ne prouve pas la fraîcheur d'une station. Un enregistrement est utilisable
pour les KPI uniquement si la station est opérationnelle, le rapport a entre 0 et 3600 s
de décalage, les compteurs et sous-types sont cohérents et `bikes + docks <= capacity`.
Ce seuil est une décision de projet, pas une promesse contractuelle du fournisseur.

## Gestion des problèmes

Les valeurs brutes ne sont pas réécrites. Toutes les anomalies sont conservées avec leur
run_id. En cas d'erreur bloquante, la transaction Silver/Gold est annulée, la collecte
est enregistrée comme `failed`, et les archives Bronze éventuellement créées subsistent.
Une relance du même `run_id` réussi n'insère aucun doublon.

## Limites et jalons ultérieurs

- API live : le réseau du conteneur de test ne résout pas le domaine officiel; l'essai live
  doit être réalisé depuis la machine qui hébergera le collecteur.
- PostgreSQL : le DDL et l'accès via SQLAlchemy/psycopg sont intégrés; test d'intégration
  PostgreSQL **non exécuté ici** faute d'un serveur.
- Le process tourne ponctuellement; **aucun scheduler permanent n'est activé**.
- SQLite permet de tester localement, mais le stockage longue durée doit être PostgreSQL.
- Les archives Parquet / DuckDB et politiques de rétention seront finalisées après des
  mesures réelles de volume; ne pas affirmer qu'elles sont déjà intégrées.
- Les sources officielles sont soumises à la licence ODbL; vérifier l'attribution et le
  partage des dérivés avant publication publique.
