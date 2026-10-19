# P3 — Mise en exploitation (contrôles obligatoires)

## 1. Démarrage local sur Windows (PowerShell)

Se placer dans le dossier extrait du dépôt, puis :

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[postgres,test]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m urban_ops init
.\.venv\Scripts\python.exe -m urban_ops collect
.\.venv\Scripts\python.exe -m urban_ops report
```

Les commandes `collect` sans `--information-file` et `--status-file` téléchargent **les vraies API Vélib'**. Elles exigent Internet. Vérifier dans la sortie `status=success`, `stations`, `status_samples`, `quality_issues`, `usable_samples`, puis deux fichiers `.json.gz` dans `data/bronze`.

**Ne pas publier `data/`, `.env`, des URLs de connexion ou des identifiants.**

## 2. PostgreSQL local

Si Docker Desktop est installé et lancé :

```powershell
docker compose up -d postgres
$env:URBAN_OPS_DATABASE_URL = 'postgresql+psycopg://urbanops:local_dev_only_change_me@127.0.0.1:5434/urbanops'
.\.venv\Scripts\python.exe -m urban_ops init
.\.venv\Scripts\python.exe -m urban_ops collect
.\.venv\Scripts\python.exe -m urban_ops report
```

`docker compose` utilise **exclusivement** des identifiants de démonstration et écoute sur `127.0.0.1` ; ne jamais exposer ce conteneur sur Internet. Pour la production, utiliser un mot de passe différent fourni par variables d'environnement, TLS et sauvegardes.

## 3. Collecte régulière

Le pipeline exécute un seul instantané par commande. La cadence cible est **5 min**. Le pilote GitHub Actions `collect.yml` est configuré pour une collecte best-effort toutes les cinq minutes ; archives persistantes dans les **Releases**, pas dans l'historique Git. Voir `docs/P3_COLLECTION.md` pour les limites, le contrôle de l'exécution et les conditions de migration vers un scheduler garanti.

**Ne pas utiliser GitHub Actions pour capturer des snapshots réguliers dans le dépôt** : cela produirait des données volumineuses et des commits sans fin. Une tâche Windows reste suspendue quand l'ordinateur est éteint ; elle ne remplace pas une collecte 24/7.

Déclencher périodiquement `python -m urban_ops collect`, avec un seul processus à la fois, dans un environnement où `URBAN_OPS_DATABASE_URL` et `URBAN_OPS_BRONZE_DIR` pointent vers un stockage permanent. Sauvegarder les archives et la base séparément.

## 4. Suivi opérationnel

Après chaque exécution, enregistrer le code de sortie et le JSON console. Vérifier :

- récupération des deux JSON sans erreur et avancement de `ingestion_runs` ;
- absence d'accumulation des `failed` et de retards de collecte ;
- distribution de `reported_lag_seconds` et évolution de `is_usable` ;
- anomalies `over_declared_capacity`, `stale_station_report` ;
- cohérence du nombre de stations `dim_stations` / `fact_station_status` ;
- capacité disque et politique de rétention.

Ne pas interpréter `empty_samples` et `full_samples` comme une **durée** ou des **trajets**. Les instants de collecte, de publication du flux et de remontée station sont des horodatages distincts.

## 5. Conditions de recette P3 opérationnelle

- [x] Tests SQLite et pipeline local sur fixtures synthétiques
- [x] Test PostgreSQL exécuté avec service temporaire en GitHub Actions et résultat visible
- [x] Première collecte HTTPS réelle ponctuelle sur runner GitHub, avec résumé conservé temporairement ([preuve](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39266789480))
- [x] Collecte GitHub Actions configurée ; première sauvegarde distante réussie ([preuve](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39328054063))
- [ ] Contrôle de régularité après **24 h** de cadence programmée : compter les exécutions, les captures, les retards et les manques
- [x] Archive Bronze réelle présente dans une GitHub Release et restauration SQL vérifiée ([preuve](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39328436934))
- [ ] Définir une sauvegarde indépendante de GitHub et une politique de rétention pour un usage durable au-delà du pilote

Une P3 **développée** n'est pas encore une P3 **exploitée en continu**.