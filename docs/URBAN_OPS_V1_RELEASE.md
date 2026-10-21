# Urban Ops — Clôture de l'observatoire V1 (22 octobre 2026)

L'objectif V1 est un **observatoire des archives Vélib’ Métropole**. Les véritables prévisions à +30 minutes sont un chantier P5 distinct ; elles sont masquées tant que le modèle n'est pas validé. Aucun chiffre prédit n'est présenté comme réel.

## Situation vérifiable

| Livrable | Statut | Preuve / prochaine action |
| --- | --- | --- |
| P3 : collecte historique et contrôle qualité | Implémenté, archives réelles en Releases | Vérifier la cadence best effort ; les anomalies restent historisées |
| P4 : tables analytiques et projet Power BI 4 pages | Générés automatiquement | Vérification structurelle `scripts.check_p4_pbip`, puis ouvrir les quatre pages dans **Power BI Desktop Windows** pour clôturer P4 |
| P5 : prévisions à +30 min | Préparé, **NON VALIDÉ** | Attendre >= 7 jours, >= 900 captures et la couverture requise ; puis validation temporelle indépendante sur données réelles |
| P6 : cockpit mono-écran, 4 sections, historique interactif | Terminé côté code et CI | Recette humaine Windows et mobile du paquet précis destiné à être publié |
| C3 : paquet public, SHA-256, provenance, CSP | Préparé côté CI | Déclencher volontairement le workflow Pages après activation de Pages |
| C3 : mise à jour automatique du site | **Pas encore activée** | Après première publication réussie, autoriser le déclencheur planifié (au plus horaire), avec le même filtre de fraîcheur et de qualité |
| Présentation portfolio | Texte validable ci-dessous | Ajouter le projet à Abyss Showcase uniquement après première publication et URL vérifiée |

## Publication manuelle V1 — étapes exactes

**Action préalable par le propriétaire** (GitHub Pages n'était pas activé lors du contrôle du dépôt) :

1. Ouvrir **Settings → Pages → Build and deployment → Source → GitHub Actions** dans `sogoyou8/URBAN-OPS`. Confirmer que le dépôt reste public.
2. Dans **Actions**, sélectionner `P6 Urban Ops cockpit — checks and verified real snapshot`, puis **Run workflow** sur `main`. Ce workflow télécharge uniquement de vraies archives P3, vérifie les sommes SHA, génère `urban-ops-p69-publication-ready` et vérifie Chromium sous le sous-chemin `/URBAN-OPS/`. Vérifier qu'il est **réussi**.
3. Relever le **numéro exact** de cette exécution P6. Dans **Actions**, sélectionner `C3 — Publish reviewed Urban Ops snapshot (manual only)`, puis **Run workflow** sur `main` et fournir son numéro dans `p6_run_id`.
4. C3 refuse un run P6 d'une autre branche, un commit différent de `main`, un run échoué ou un simple aperçu PR. Le paquet doit être SHA-vérifié, conserver `forecast.status=unavailable`, provenir d'une collecte réelle **de moins de trois heures**, et avoir au moins une station mesurée ; sinon **aucune mise en ligne**. Si l'archive a vieilli, refaire l'étape 2 avant de relancer C3.
5. Après un déploiement réussi, utiliser **uniquement l'URL renvoyée par le workflow GitHub Pages**. L'URL prévue pour le dépôt est `https://sogoyou8.github.io/URBAN-OPS/`, mais ne pas la présenter comme active avant vérification effective.
6. Vérifier le site public sur desktop et mobile : carte/fond et fallback, nombre de stations, filtres, sélection de station, historique développé/compact, panneau Comprendre, horodatage archivé, sources et attribution, quatre sections, console sans erreurs. **Prévisions en préparation** ; aucun chiffre prédictif.

**Le workflow Pages n'a pas de cadence automatique : uniquement `workflow_dispatch`.** Son ajout au dépôt ne met donc pas le site en ligne. L'activation d'une publication horaire demandera une étape séparée après l'inspection de la première URL.

## Registre de gel V1

Les critères de gel sont :

- Une publication GitHub Pages réellement réussie et ouverte dans le navigateur Windows et sur mobile ;
- Les chiffres affichés reliés au manifeste et à la date de capture, et jamais présentés comme du temps réel ;
- Rejet par C3 des archives trop vieilles, des données P3 inexploitables, de données factices ou d'un modèle P5 non validé ;
- Une stratégie de rafraîchissement approuvée et testée (ou une fréquence manuelle explicitement retenue), avec échec de collecte ne remplaçant pas un site antérieur fonctionnel ;
- La recette P4 Power BI Desktop, si P4 est inclus dans le périmètre « projet DATA complet » ;
- Documentation et entrée de portfolio cohérentes avec la version effectivement publiée.

Une fois V1 figée, aucune nouvelle refonte esthétique ou fonctionnalité non essentielle. Seules les corrections de sécurité, qualité, panne ou conformité restent autorisées.

## Présentation sobre pour le portfolio, **à utiliser après publication**

**Urban Ops — Observatoire Vélib’ Métropole.** Projet d'ingénierie et d'analyse de données publiques : ingestion régulière de captures réelles, archivage vérifiable, nettoyage et contrôle qualité, export de tables pour Power BI, cartographie interactive et historique daté. Les stations non mesurables restent signalées au lieu d'être assimilées à zéro. Un pipeline de prévision à 30 minutes est en expérimentation, **non activé tant que sa performance n'est pas démontrée**.

Technologies présentes dans le dépôt : Python, SQL/SQLite, PostgreSQL (tests), JavaScript, MapLibre, Power BI PBIP/TMDL, GitHub Actions, tests Chromium. Ne pas présenter Microsoft Fabric comme utilisé dans ce projet.

## Pour P5, plus tard

Le pipeline de validation stricte et la veille de seuil restent séparés des étapes C3. Atteindre sept jours calendaires ne valide pas un modèle : il faut des paires +30 min authentiques, une séparation temporelle sans fuite, une évaluation hors échantillon et une amélioration suffisante face à la persistance. En cas de résultat défavorable, conclure honnêtement « Prévisions non validées ».
