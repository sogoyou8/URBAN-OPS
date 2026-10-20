# Urban Ops — Cloudflare P3.5 : préparation, sans activation ni frais

## Statut et périmètre

**Implémenté et testé hors ligne**, pas déployé. Aucun bucket R2 créé, aucune souscription R2 demandée, aucune carte bancaire enregistrée, aucune tâche Cron Cloudflare en production.

L'application Node.js `cloudflare/src/collector.mjs` reçoit un événement Cron, interroge les **deux endpoints officiels** Vélib' Métropole, vérifie leur taille, la quantité de stations, l'horodatage global et les sommes SHA-256 des réponses brutes. Elle conserve un objet **JSON.gz** dans un bucket R2 privé et en classe **Standard**, indexé par l'heure UTC programmée. Aucun endpoint HTTP ne permet d'exposer les archives ou de lancer la collecte publiquement.

Il s'agit d'un format Cloudflare V1 distinct du TAR GitHub P3. Le convertisseur `scripts/convert_r2_snapshot.py` le transforme **sans inventer de données** en TAR compatible avec `scripts.archive_capture.unpack` et `scripts.replay_capture.py` (Bronze → Silver → Gold). L'objectif est de conserver le pipeline Python/SQL comme source unique de transformations.

## Vérifications hors ligne, gratuites

Depuis le dépôt local :

```powershell
cd cloudflare
node --test
cd ..
python -m unittest discover -s tests -p test_cloudflare_import.py -v
```

Les tests simulent les réponses Vélib' et une liaison R2 en mémoire : **ils ne sont pas des captures du réseau réel**. La CI GitHub effectue les mêmes vérifications sur chaque PR et push qui modifie ce module. Il n'est pas nécessaire d'installer Wrangler ni de se connecter à Cloudflare pour les lancer.

Avec un compte Cloudflare existant, `wrangler dev --test-scheduled` peut tester Cron et un **R2 émulé localement**, par défaut sans accès distant. Ne pas exécuter `wrangler deploy` à ce stade. La configuration `cloudflare/wrangler.toml` contient déjà un Cron de 5 minutes ; tout déploiement de ce fichier créerait le déclenchement automatique.

## Budget, quotas et activation

- Workers Free : **100 000 requêtes/jour** et **10 ms de CPU par invocation** ; une exécution toutes les 5 minutes représente environ **288 invocations/jour**, mais le temps CPU de l'archivage gzip et des empreintes reste **à mesurer sur le vrai runtime Cloudflare**. Le succès en Node local ne démontre pas le respect des 10 ms.
- R2 **Standard** : inclus **10 GB-month de stockage**, **1 million d'opérations Classe A/mois**, **10 millions Classe B/mois**. Les opérations du pilote envisagé sont largement sous ces quotas, mais le stockage s'accumule et ne repart pas de zéro chaque mois.
- Une ancienne archive GitHub pesait **96 590 octets**. À titre purement indicatif, 288 archives de cette taille par jour représenteraient ~0,83 Go par 30 jours. Le nouveau format JSON.gz doit être mesuré sur de vraies données avant toute prévision budgétaire.
- R2 requiert une **souscription et une étape de paiement / checkout** : hors quotas gratuits, Cloudflare peut facturer. Le quota gratuit n'est **pas une garantie de zéro dépense**. Aucune facturation n'est autorisée par le présent chantier.
- Avant d'activer la collecte réelle : convenir d'une politique de rétention (par exemple **30 jours** via règles de cycle de vie R2), vérifier les quotas et alertes Cloudflare, confirmer la possibilité d'utiliser une carte bancaire, et tester un lancement ponctuel avec mesure du CPU et de la taille d'objet. Ne pas activer le Cron avant ces points.
- Tant que cette décision n'est pas prise, **GitHub Actions reste le collecteur actif**, en mode best effort avec ses limites explicites.

Sources officielles (octobre 2026) :

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- https://developers.cloudflare.com/r2/pricing/
- https://developers.cloudflare.com/r2/get-started/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/

## Passage du stockage R2 au pipeline Python existant (après activation seulement)

Les objets du bucket privé peuvent être récupérés avec l'interface Cloudflare ou le client CLI authentifié. Téléchargez un fichier `snapshot-...json.gz` localement, dans le dossier `data/` exclu de Git, sans rendre le bucket public.

```powershell
# depuis la racine du projet UrbanOps
python -m scripts.convert_r2_snapshot data\snapshot-YYYYMMDDTHHMMSSZ.json.gz --output-dir data\captures
python -m scripts.replay_capture --db-url sqlite:///./data/r2-history.sqlite data\captures\capture-YYYYMMDDTHHMMSSZ-xxxxxxxx.tar.gz
```

Remplacer les noms par ceux réellement produits : aucune capture n'est fournie dans ce dépôt. Le script crée des TAR compatibles avec le replay P3, conserve l'heure de collecte réelle et vérifie les sommes SHA-256. Les écrasements sont interdits.

## Points ouverts avant migration

1. Confirmer que le Worker passe dans **10 ms de CPU** en conditions réelles ou réduire le traitement.
2. Valider l'accès à R2 Standard et sa configuration de rétention et de budget. Aucune activation sans accord explicite.
3. Après mise en service, vérifier plusieurs déclenchements, l'archive R2 et sa restauration SQL ; documenter le taux de captures réussies.
4. Adapter ensuite l'export P4 pour utiliser les archives R2 en plus des Releases GitHub, **sans jamais présenter deux flux redondants comme deux observations distinctes**.
5. Désactiver le collecteur GitHub Actions seulement une fois Cloudflare validé ; éviter les doubles collectes et les frais inutiles.