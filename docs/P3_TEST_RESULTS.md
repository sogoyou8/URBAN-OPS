# P3 — Rapport de vérification (19 octobre 2026)

## Ce qui a réellement été exécuté

- `PYTHONPATH=src python -m pytest -q` : **10 tests passés**.
- `python -m compileall -q src` : OK.
- `python -m pip install -e . --no-deps --no-build-isolation` : OK dans l'environnement de test.
- `urban-ops --help` : CLI installée et accessible.
- `init` puis `collect` avec `tests/fixtures/*.json`, puis `report` : OK.
- Test d'ingestion de **1 519 stations de simulation** : OK (ce n'est PAS un échantillon public réel).

## Exemple de sortie du test CLI (fixtures, trois stations fictives)

```json
{"stations": 3, "status_samples": 3, "usable_samples": 1, "quality_issues": 2, "quarantined": 0, "status": "success"}
```

## Points non exécutés

- **Collecte HTTP directe** depuis cet environnement : le domaine Vélib' n'a pu être résolu.
  Les réponses publiques avaient été consultées et auditées lors de la P2 à travers un service de consultation externe.
- PostgreSQL / Docker : aucun serveur ni client Docker disponible ici.
- Planification permanente sur un hôte et archivage vers Parquet : non mis en service.
- Historique réel en production : non constitué.

La P3 livre donc le **socle implémenté et testé localement**, pas un pipeline
24/7 déjà opérationnel. Le passage en exploitation demandera un hôte,
les accès Internet et un test de bout en bout PostgreSQL sur des données réelles.

## Validation GitHub Actions réelle (19 octobre 2026)

- [Run de validation P3](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39266106117) : **succès**.
- Environnement du run : Python 3.12, PostgreSQL 16 éphémère, SQLAlchemy, psycopg.
- **11 tests réussis**, y compris le test d'intégration PostgreSQL / Bronze → Silver → Gold.
- L'archive a été vérifiée par SHA-256 avant extraction et publication du code dans `main`.
- Tests réalisés sur fixtures synthétiques ; **aucune collecte HTTP réelle ni collecte permanente** n'a été mise en service.
