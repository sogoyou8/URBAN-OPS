# P3 — Collecte historique hébergée : pilote sans nouvel abonnement

## Décision

- **Exécution** : GitHub Actions `collect.yml`, fréquence *demandée* 5 minutes (`2-57/5 * * * *` en UTC) ; calendrier **best effort**, sans SLA ni exactitude temporelle garantie. GitHub peut retarder ou ignorer des exécutions et désactive automatiquement les crons des dépôts publics après 60 jours sans activité.
- **Stockage persistant** : chaque capture est une archive immuable `capture-YYYYMMDDTHHMMSSZ-<runid>.tar.gz`, attachée à une **GitHub Release journalière** nommée `velib-data-YYYY-MM-DD`. Aucune capture n'est commitée dans l'historique git.
- **Calculs** : SQLite éphémère et Bronze/Silver/Gold exécutés à chaque collecte pour *valider* l'échantillon ; **ce n'est pas la base historique**. L'historique est constitué par les archives de capture. Les données sont réimportables dans PostgreSQL ultérieurement par replay.
- **Coût additionnel attendu** : 0 € pour ce **pilote sur dépôt public**, sous réserve du respect des politiques/quotas GitHub. Ni Railway, ni Vercel, ni API payante ne sont sollicités. La tarification peut évoluer ; ne pas assimiler ce pilote à une solution de production garantie.
- **Capacité** : 288 captures au maximum nominal par journée ; moins de 1 000 assets par release GitHub. Cette hypothèse devra être surveillée si d'autres fichiers sont ajoutés ; pas de garantie que tous les jobs s'exécutent.

## Ce qui est enregistré

Un fichier `manifest.json` (numéro de schéma 1, `run_id`, `collected_at`, dates de publication des deux feeds, compteurs qualité, hashes des octets bruts), et les deux JSON bruts `.json.gz`. `collected_at` provient de la base d'ingestion et ne remplace jamais les `last_reported` des stations. Les objets capturés sont de la donnée publique Vélib' Métropole (ODbL), pas des données inventées.

La publication est interdite si ingestion échouée, absence d'une source, SHA-256 non conforme, moins de 1 000 états de station, ou date globale du flux manifestement obsolète. Les anomalies de station isolées sont **conservées** et comptabilisées, sans correction arbitraire.

## Pilotage

- Actions : `https://github.com/sogoyou8/URBAN-OPS/actions/workflows/collect.yml`
- Captures : `https://github.com/sogoyou8/URBAN-OPS/releases` (tags `velib-data-YYYY-MM-DD`)
- En cas d'échec : vérifier GitHub Actions et le résumé de diagnostic à rétention 7 jours ; la première exécution est déclenchée par le commit du workflow.
- Pour **arrêter** la collecte : désactiver le workflow dans GitHub → Actions → P3 best-effort Velib collector → `...` → Disable workflow. Les archives déjà publiées ne seront pas effacées.
- Surveiller : (1) dernier asset publié (date réelle de collecte), (2) nombre d'exécutions par heure (12 prévues), (3) échecs, (4) `quality_issues`, (5) `usable_samples`, (6) taille quotidienne de stockage.

## Reconstruction hors ligne

L'historique Silver/Gold peut être reconstruit depuis les fichiers de Releases, de manière idempotente.

```bash
# Prérequis : gh CLI authentifié, Python et environnement du projet.
python -m pip install -e .
mkdir -p data/downloaded
# Exemple : télécharger une journée (remplacer la date).
gh release download velib-data-2026-10-19 --repo sogoyou8/URBAN-OPS --pattern 'capture-*.tar.gz' --dir data/downloaded
python -m scripts.replay_capture --db-url sqlite:///./data/historique.sqlite data/downloaded/*.tar.gz
```

Pour PostgreSQL, fournir `--db-url postgresql+psycopg://...` par méthode sûre (ne pas afficher ni enregistrer les secrets dans les logs). Sur Windows PowerShell, passer les chemins des fichiers de manière compatible avec le shell.

Le replay recalcule Silver/Gold et les anomalies, mais **ne recrée pas des instants jamais capturés**. Ce n'est pas une mesure du trafic ni des trajets individuels.

## Revue 24 h et limites

Une seule exécution réussie ne prouve **pas** la collecte régulière. Il faudra contrôler au bout de 24 h : au moins plusieurs heures de captures effectivement archivées, les décalages entre captures et les trous de planification. GitHub n'est pas un planificateur garanti. Pour une collecte 24/7 plus robuste, migrer vers un scheduler dédié et object storage (p. ex. R2), une fois compte, limites et coût approuvés.

### Sources des règles techniques

- GitHub scheduled workflow : https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub Release assets : https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- Vélib' open data : https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole