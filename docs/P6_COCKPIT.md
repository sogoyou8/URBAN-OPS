# P6 — Urban Ops | Cockpit de mobilité

## Statut et périmètre

P6 est une application web statique, conçue pour explorer les **capturations réelles** de Vélib' Métropole déjà vérifiées par le pipeline P3 (SHA-256 de chaque archive au replay). Aucun backend payant et **aucun déploiement automatique** : GitHub Actions produit un fichier `network.json` et un artefact web prévisualisable. Aucune donnée synthétique n'est publiée en production.

### P6.1 — Architecture

`GitHub Releases` (archives P3 réelles) → `scripts.replay_capture` (SQLite) → `scripts.export_p6` (schéma JSON V1) → `web/` (cockpit). L'export sélectionne le **dernier run réussi** et fait une jointure exacte sur `run_id` avec les stations, sans récupérer des faits anciens pour les stations absentes. Seules les stations `is_usable=1` comptent dans les totaux de vélos et de bornes. Si une station n'a pas de mesure exploitable, sa disponibilité reste **inconnue**, jamais zéro.

Les 48 captures les plus récentes (parmi les trois dernières journées publiées) sont rejouées dans le workflow, et jusqu'à 96 peuvent être rendues en mode local. Les gaps entre capturations ne sont ni inventés ni interpolés. Les courbes se coupent lorsque l'écart dépasse 20 minutes. L'écran distingue la date de capture de la date d'export, et ne prétend jamais présenter les disponibilités en temps réel.

### P6.2 — Direction produit

Expérience mono-écran sur desktop (avec défilement interne des listes), surfaces sombre bleu-noir, typographie fine, lignes de séparation plutôt que cartes gonflées et arrondies. Carte interactive géoréférencée sur **vraies coordonnées** ; styles MapLibre/OpenFreeMap avec attribution OpenStreetMap. Dégradation progressive vers un tracé géographique SVG/HTML si la bibliothèque ou le fond de carte externes ne sont pas accessibles. L'accessibilité inclut une liste navigable au clavier et des intitulés d'états lisibles.

### P6.3 — Composants

- **Réseau** : indicateurs qualifiés, carte avec clustering, couleur par statut, recherche par nom/code/ID, filtres, inspection complète des stations.
- **Territoires** : 4 quadrants délimités par la médiane des coordonnées P3, **pas des arrondissements** ni des communes. Les indicateurs comparent les quadrants sur les seules données qualifiées.
- **Fiabilité** : sources, horodatage, observations exploitables et nombres d'anomalies **par événement**, non par station distincte.
- **Continuum des captures** : série des totaux réseau réellement observés, interrompue si 20+ minutes sans capture. Si une seule capture : aucun graphique temporel trompeur.
- **Prévisions** : statut P5 explicitement **indisponible**, en attente de validation chronologique sur historique réel. Ce volet n'affiche aucune estimation fictive.

Le fond cartographique nécessite l'accès Internet. Si un fournisseur gratuit change ses conditions, remplacer la source par un fond conforme à son attribution/licence, ou utiliser le mode de secours sans tuiles. Les dépendances visuelles sont servies depuis un CDN; les sélecteurs et la logique locale fonctionnent indépendamment du CDN.

### P6.4 — P5 et architecture de la prédiction

Aucun modèle P5 non validé ne doit injecter des chiffres dans l'UI. Le contrat JSON V1 n'accepte que `forecast.status = unavailable`. Un futur contrat v2 nécessitera provenance, temps de prédiction, version de modèle et mesure de performance hors échantillon établie sur des archives authentiques; ce changement devra être testé avant activation.

### P6.5 — Validation et utilisation

Tests hors ligne :

```powershell
python -m pip install -e '.[test]'
python -m pytest -q tests/test_p6_export.py
node --test web/src/core.test.mjs
```

Regénération réelle CI : `Actions → P6 Urban Ops cockpit — checks and verified real snapshot → Run workflow`, qui rejoue les archives P3 et publie 2 artefacts pendant 7 jours (`urban-ops-p6-real-data` et `urban-ops-p6-static-preview`). Sans archive réelle, le workflow échoue clairement; aucun remplacement par des fixtures.

Un **seul dossier local** (même méthode que Power BI) :

```powershell
cd "$env:USERPROFILE\Desktop\ABYSS\ProjetDATA\UrbanOps"
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\scripts\sync-p6.ps1
python -m http.server 5173 --directory web
# puis http://localhost:5173
```

La commande `sync-p6.ps1` télécharge le dernier dataset GitHub vers `web/data/network.json`, refuse d'écraser un fichier local modifié, et peut sauvegarder l'ancienne version explicitement avec `-ReplaceLocalData`. Elle ne touche pas au PBIP.

### Limites et suite

- L'écran est un **observatoire des archives**, pas un contrôle direct du service Vélib'. Ne pas afficher « live » si la capture date de plusieurs minutes/heures.
- Le `network.json` généré n'est jamais versionné dans Git, pour ne pas gonfler le dépôt ou mélanger données et code.
- La publication sur Vercel ou GitHub Pages **n'est pas activée**. Elle peut se faire ultérieurement, après validation utilisateur, via fichiers statiques et budget vérifié.
- Validation de lecture sur un vrai navigateur Windows, UX responsive, disponibilité du fond de carte et performance d'affichage sur 1 500 stations à contrôler avec l'utilisateur. Pas de promesse de recette visuelle complète sans navigateur connecté.
- Le déclencheur Cloudflare / GitHub P3.5 continue d'accumuler les snapshots; il est distinct du build P6.

**Source** : Vélib' Métropole open data, ODbL, non affilié à l'opérateur.
## P6.6 — Recette corrective après captures utilisateur (20/10/2026)

- **P6.6-A** : sur certains navigateurs, le fond OpenFreeMap s'affichait mais les 1 517 marqueurs GeoJSON n'étaient pas visibles. La couche de repères est maintenant un **canvas géographique indépendant des sources/layers du style MapLibre**, projetant les coordonnées des stations réelles (regroupement pour éviter la surcharge à faible zoom, clic station et zoom sur regroupement). Le compteur annonce les repères effectivement tracés. Si MapLibre/son style n'est pas disponible, les coordonnées restent navigables via boutons du mode de secours.
- **P6.6-B** : pour desktop >= 861 px, la mise en page est contrainte à `100dvh` : titre, quatre KPI, carte / inspection, mini-historique et pied de page. L'inspecteur défile localement. Tablettes/mobiles conservent le défilement vertical normal.
- **P6.6-C** : contraste des libellés secondaires accru; couche de points au-dessus du fond, légende et filtres au-dessus des points; davantage de distinction des états de disponibilité.
- **P6.6-D** : titres, sous-titres et 4 KPI propres aux vues Réseau, Territoires, Fiabilité et Prévisions. Les 4 zones géographiques restent des **quadrants d'analyse, jamais des arrondissements**. Les catégories qualité ont des libellés français compréhensibles. Les prévisions P5 restent **indisponibles**, sans faux score.
- **P6.6-E** : tests Node des coordonnées/agrégations/sélections, plus test Chromium de l'interface en mode offline simulé (desktop 1440×900, laptop 1024×768 et mobile 390×844, affichage canvas malgré absence de styles externes, navigation et interactions, secours sans MapLibre). La fixture du navigateur est **synthétique et non publiée**. Les mesures Vélib' réelles restent vérifiées séparément par le job `real-export`.

**Limites non dissimulées** : le test CI du navigateur simule le moteur cartographique et ne prouve pas l'affichage externe OpenFreeMap sur le PC Windows. L'utilisateur doit recharger son application locale via Git + synchronisation P6 et confirmer les points, la fluidité, les différentes vues et l'absence de défilement global. Aucun nouveau déploiement Vercel, Workers, R2, Railway ou abonnement.

## P6.7 — Parcours, audit P3 et préparation P5 (20/10/2026)

- **Explorer** : les points continuent à utiliser les coordonnées archivées ; les groupes zooment puis ouvrent une liste de stations lorsqu'ils restent superposés à zoom élevé. Les fiches conservent les filtres et la recherche ; touche Échap pour revenir. Bouton « Recentrer » sans réinitialisation forcée des filtres.
- **Qualité** : pour chaque station, P3 expose les motifs de rejet de **la même capture** et le fait que les opérations sont autorisées ou non. La vue Fiabilité distingue « station sans statut » de « observation reçue mais non exploitable » et peut ouvrir la liste des stations concernées. Les compteurs d'événements d'anomalie sont des événements et peuvent être multiples par station.
- **P5** : à chaque export P6, `scripts.p5_inventory` consulte la liste réelle des assets GitHub Releases (dix derniers jours) et injecte son compteur, l'étendue calendaire et la couverture dans `p5_readiness`. Ce sont des **noms de fichiers inventoriés**, pas des archives vérifiées par replay SHA, ni des paires +30 minutes prouvées, ni un entraînement valide. Même si tous les seuils quantitatifs sont atteints, P5 reste indisponible tant que le workflow P5 n'a pas entraîné et prouvé le gain hors échantillon.
- **Tests** : fixtures strictement synthétiques utilisées pour les tests JavaScript et Chromium ; le job real-export rejoue les véritables captures et refuse toute donnée fictive. L'exploration reste utilisable sans librairie externe grâce au repli HTML. Le déploiement public et les abonnements restent désactivés.

Recette manuelle : après `git pull --ff-only origin main` puis `powershell -ExecutionPolicy Bypass -File .\\scripts\\sync-p6.ps1`, actualiser `http://localhost:5173` avec Ctrl+F5 ; tester recherche → fiche → retour, filtre Non qualifiées, Territoires, Fiabilité → liste des rejets, P5 → compteurs d'archives, déplacement/zoom/recentrage carte.

## P6.8 — Recette de navigation et compteurs cartographiques

- **Changement de section** : toute transition vers une autre section recentre la carte sur l'étendue des **stations réellement référencées** (bornes géographiques, zoom de synthèse maximal 11,5). Cliquer sur la section déjà active conserve le zoom et les filtres de l'exploration courante. Zooms de station et de secteur inchangés.
- **Comptages géographiques** : trois valeurs distinctes : **stations filtrées sur tout le réseau**, **stations dont les coordonnées projetées tombent dans la fenêtre cartographique** et **repères réellement dessinés** (un repère peut contenir plusieurs stations). Les points entièrement hors du viewport sont exclus du calcul et du tracé, au lieu de la marge de 20 pixels utilisée jusqu'ici. Un intitulé détaillé rappelle qu'un groupe représente plusieurs stations. Même distinction en mode de secours sans tuiles.
- **Panneaux** : tout changement de section réinitialise explicitement le défilement du panneau; parcours Fiabilité → stations non qualifiées → fiche → motif → retour couvert par test Chromium. L'ouverture d'une fiche conserve les filtres existants.
- **Validation** : tests Node du périmètre écran et des grappes, test Chromium en zoom fort puis changement de section, navigation répétée dans la même section et défilement, plus le pipeline P3 et l'export de véritables archives. Aucun nouveau service ni déploiement public.


## C2.3 — Compréhension dès l'arrivée et historique honnête (21/10/2026)

**Objectif produit.** Un visiteur non familier de P3–P6 doit savoir immédiatement qu'il consulte un **observatoire du réseau Vélib’ Métropole**, des **captures historiques** et non une application de disponibilité temps réel. L'introduction tient dans le bandeau déjà présent (sans écran de bienvenue, sans panneau latéral permanent). Les quatre vues gardent des descriptions en français courant.

**« Comprendre ».** Un bouton discret en en-tête ouvre, sans quitter le cockpit, une fenêtre contenant : le sujet, la provenance officielle GBFS/ODbL, les limites des chiffres, la distinction « station non qualifiée ≠ station vide », les quatre sections et la validation encore absente de P5. Une explication dépend de la section active. La fenêtre est utilisable au clavier (focus initial sur Fermer, tabulation contenue dans la fenêtre, Échap / clic arrière-plan pour fermer et retour du focus au déclencheur). Le panneau défile en interne sur les petits écrans.

**Historique P3.** Les colonnes `history[].bikes`, `history[].usable`, `history[].observed` et `history[].connected_to_previous` du **replay vérifié P3** sont utilisées sans les réécrire. On affiche :
- l'axe des vélos **à partir de 0**, avec borne haute chiffrée (au lieu de zoomer sur le minimum local) ;
- les points de capture authentiques avec leur nombre de vélos ; au survol, nombre de stations utilisables rapporté au nombre de stations référencées ;
- une bande de petites marques bleues/orange pour la **couverture des stations exploitables**, distincte du total de vélos ;
- un **point orange** si une capture comptabilise strictement moins de **90 % du maximum des stations exploitables observé dans la fenêtre affichée**. Ce seuil de 10 % de baisse est une **heuristique de présentation**, choisie pour signaler une non-comparabilité potentielle ; ce n'est pas un changement des critères de qualité P3 ni une mesure de la mobilité ;
- **aucun segment** avant ou après un point orange ; les lacunes temporelles déjà détectées restent sans interpolation. Si le nombre de stations exploitables est inconnu, la comparabilité est également inconnue, et aucune ligne continue n'est inventée.

Le point orange garde sa **véritable valeur** de vélos ; aucune donnée n'est corrigée, imputée ou supprimée. Le visiteur ne doit pas interpréter ce creux comme une disparition attestée de vélos, puisqu'il peut aussi refléter un rejet de nombreuses stations.

**Recette** : tests purs de rupture, du seuil, des métadonnées manquantes, de l'absence de remplacement des valeurs et des créneaux temporels ; tests Chromium synthétiques à 1440×900, 1024×768, 390×844 et 320×700 (ouverture/fermeture du guide, focus, maintien du sans-scroll et lisibilité). L'export réel signé SHA-256 est contrôlé en CI sans déploiement et produit une capture supplémentaire `guide-real-1440x900.png`. La vérification du fond OpenFreeMap sur le navigateur Windows de l'utilisateur demeure distincte des tests sans Internet.

**Ce chantier ne modifie pas P3, les règles d'éligibilité P5, l'ingestion, les captures archivées, les sommes de contrôle, ou les décisions de publication.**
