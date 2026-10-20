# P5.2 — Import hors ligne des fenêtres Vélib’ Pulse (non officiel)

## Périmètre

Urban Ops possède **déjà** un collecteur officiel GBFS qui capte le réseau entier
et archive les JSON bruts dans GitHub Releases (P3). Ce composant n'est **pas**
un second collecteur. Il reçoit uniquement des réponses `/api/replay` déjà
obtenues de manière autorisée : il ne contient **aucun accès réseau**, aucune
session automatique, aucun contournement Turnstile ni rafale de requêtes.

Référence de format (projet tiers) :
- https://github.com/angristan/velib/blob/main/src/worker/domain.ts
- https://github.com/angristan/velib/blob/main/src/worker/replay.ts
- https://github.com/angristan/velib/blob/main/docs/architecture.md

Le [ticket d'export](https://github.com/angristan/velib/issues/4) demeure
la voie privilégiée pour l'historique massif. Ne pas lancer 168 appels au
service tiers sans accord et sans politique explicite de débit.

## Utilisation (fichiers préalablement autorisés)

```bash
python -m scripts.import_pulse_replay \
  --output data/pulse-import-001 \
  data/authorized-replays/hour-001.json data/authorized-replays/hour-002.json
```

La commande **n'appelle pas Vélib' Pulse**. Le dossier de sortie doit être
neuf. Les données brutes d'entrée doivent être conservées : le manifeste
atteste leur SHA-256, mais ne les archive pas lui-même. Un fichier incorrect
interrompt l'export sans publier de CSV ou manifeste partiel.

Résultats :
- `pulse_replay_sparse.csv` : états initiaux de toutes les stations d'une
  fenêtre, puis événements **seulement pour les stations modifiées** ; aucun
  remplissage des autres stations à chaque minute ;
- `pulse_replay_manifest.json` : noms, empreintes des octets bruts, fenêtres
  UTC, nombre de stations/frames/changements et provenance non officielle.

Validations effectuées : types, bornes des compteurs, codes positifs,
non-duplication dans chaque baseline/frame, fenêtre 15/30/60 min, liens
`previousSourceUpdatedAt` et ordre des événements. Un fichier identique
fourni deux fois ou un nom réutilisé est rejeté.

## Distinction indispensable avec P3/P5

Les `stationCode` Vélib' Pulse **ne sont pas** les `station_id` GBFS.
Une jointure de correspondance vers la dimension GBFS sera à contrôler.
Le drapeau compact `o` n'est pas équivalent aux trois champs
`is_installed/is_renting/is_returning` du flux officiel. Les `frames`
ne comprennent **pas** l'horodatage de remontée individuel `r` du
baseline. La colonne `station_reported_at_utc` reste donc vide sur chaque
changement, et sur les baselines sans valeur de remontée.

Il n'y a volontairement **aucune insertion** dans
`fact_station_status`, `gold_station_daily`, ni les ensembles
d'entraînement P5. La série *sparse* n'est pas une série reconstruite
de chaque station : elle ne contient que les états initiaux et changements.
La continuité *entre fichiers distincts* n'est pas encore certifiée.
**Aucune performance de prédiction** ne peut être annoncée à partir de cet
export. P5 continue de s'appuyer uniquement sur les archives officielles
P3 vérifiées, selon les seuils de `docs/P5_MACHINE_LEARNING.md`.

## Étape suivante après l'autorisation et les premiers fichiers

1. Valider 1 heure seulement avec le développeur (ou les fichiers fournis).
2. Contrôler les trous et chevauchements *entre* fenêtres et confronter
   les codes au référentiel officiel, sans créer de correspondance fictive.
3. Seulement après audit de qualité, concevoir une reconstruction horaire
   complète, avec une provenance distincte et des règles d'éligibilité P5.
4. Continuer indépendamment l'audit de régularité des captures officielles P3.

Aucune ressource payante ou tâche planifiée n'est activée ici.


## Reconstruction de fenêtres successives — P5.3 (préparation)

Dès que les fichiers sont reçus avec l'accord du propriétaire du service :

```bash
python -m scripts.reconstruct_pulse_replay \
  --output data/pulse-seven-days-audit \
  data/authorized-replays/*.json
```

La commande prend des fichiers **locaux uniquement**, valide intégralement les
chaînes `baseline` + `frames`, trie les fenêtres par horodatage UTC réel,
reconstruit à chaque événement l'état connu de l'ensemble du réseau, puis
sélectionne le **dernier état réellement horodaté de chaque tranche UTC de
5 minutes**. Il n'y a pas de création de nouveaux instants, et les lacunes
restent visibles.

Fichiers livrés :
- `pulse_network_5m.csv` : état de chaque station à chacun des instants
  sélectionnés, y compris les stations dont les compteurs n'ont pas changé
  depuis la baseline, avec l'horodatage réel et les SHA-256 du fichier source ;
- `pulse_network_audit.json` : nombre d'états réseau, stations distinctes,
  couverture indicative des tranches de cinq minutes, durée maximale sans
  nouvelle capture, interruptions de plus de dix minutes, chevauchements
  ignorés, inventaire des fichiers sources et preuve de **non-qualification P5**.

Les collisions avec **même timestamp mais état divergent** sont rejetées.
Dans les périodes qui se chevauchent, le premier rejeu conserve ses observations
et le second repart de sa baseline avant le premier instant plus récent.
Le nombre de chevauchements est exposé : ils ne sont jamais cachés.
Une fenêtre inutilisable bloque l'export entier. Les sorties existantes
ne sont pas écrasées.

### Vérification obligatoire avant P5

- Les 168 appels sont un nombre **théorique** pour sept jours à raison
  d'une heure par fenêtre, non un processus de récupération activé.
- Les sept jours de conservation étant une fenêtre glissante, un historique
  réellement téléchargeable peut avoir une amplitude légèrement inférieure
  à sept jours révolus. **Ne pas réduire artificiellement le seuil P5** :
  examiner la combinaison avec les captures officielles déjà archivées,
  toujours sous provenance et qualification de source.
- Vérifier l'intégralité des fenêtres, l'alignement des codes avec la dimension
  officielle, la fraîcheur et les bornes des compteurs par capacité.
- Un état réseau reconstitué ne fournit pas nécessairement une nouvelle
  observation propre à chaque station, et `operational_flag` ne prouve pas
  les trois indicateurs GBFS. Une adaptation et une évaluation de qualité
  **spécifiques à Pulse** sont nécessaires avant d'utiliser les données
  dans un backtest. L'importeur ne lance **aucun entraînement**.

**Aucun scraping de session, Turnstile ou contournement des limites du site
n'est fourni.** La demande d'export GitHub #4 reste en attente ; ce module
accepte des fichiers reçus ou récupérés avec autorisation.


## Acquisition automatisée multi-fenêtres (P5.3, **non exécutée**)

Le téléchargement manuel station par station ou heure par heure est abandonné.
La source est l'endpoint réseau déjà vérifié : une fenêtre d'une heure
contient la **baseline de toutes les stations** et les **changements**
de la période. 168 fenêtres sont nécessaires **au maximum en théorie**
pour couvrir sept jours avec des fenêtres d'une heure.

**Prérequis obligatoire** : le propriétaire du service doit autoriser le
volume de requêtes et indiquer une cadence acceptable. La demande est
documentée dans https://github.com/angristan/velib/issues/4 .
Ne pas déduire une autorisation des quatre lectures manuelles déjà réalisées.

### Installation locale (une fois)

Depuis le dossier du dépôt Urban Ops :

\`\`\`bash
python -m pip install -e ".[pulse]"
python -m playwright install chromium
\`\`\`

Le navigateur Chromium piloté par Playwright est **visible**. Le programme
ne résout pas Turnstile automatiquement : l'utilisateur doit vérifier
normalement sa session dans la fenêtre du site. Le navigateur est éphémère,
et aucun cookie ni token ne sont écrit sur le disque.

### Prévisualiser le plan sans aucun accès réseau

\`\`\`bash
python -m scripts.collect_pulse_replay_batch --output data/pulse-batch-001 --hours 168
\`\`\`

Cette commande crée un manifeste local avec une ancre horaire UTC fixe,
les bornes estimées, et zéro fichier collecté. Comme la fenêtre de rétention
est **glissante**, ne préparer le plan définitif que lorsque l'accord
est obtenu et la collecte prête à démarrer. Si l'ancre devient périmée,
créer un **nouveau dossier**, sans supprimer les archives déjà reçues.

### Exécuter **seulement après autorisation**

\`\`\`bash
python -m scripts.collect_pulse_replay_batch \
  --output data/pulse-batch-001 \
  --hours 168 \
  --run --owner-approved --interval-seconds N
\`\`\`

Remplacer **N** par le délai (en secondes) accepté par le responsable
de l'API. Il n'existe **aucune cadence présumée autorisée**. La borne
technique minimale du programme est de cinq secondes, mais ce n'est
**pas** une recommandation d'utilisation du serveur. La commande est
inopérante sans les options explicites \`--run\`, \`--owner-approved\`
et \`--interval-seconds\`.

La session vérifiée dans la fenêtre du navigateur est partagée avec les
requêtes HTTP de cette même session. La collecte reste **séquentielle** :
jamais de parallélisme, jamais d'accès à l'historique station par station.
Les périodes les plus anciennes sont récupérées **en premier** afin de
réduire le risque de rétention glissante.

Chaque requête réussie produit \`replay-at-<unix>.json\` validé avant
l'enregistrement, et ajoute une entrée au
\`pulse_batch_manifest.json\` avec son SHA-256, ses dates et ses compteurs.
En cas d'arrêt, la même commande dans le même dossier vérifie les fichiers
existants, puis ne demande que les fenêtres manquantes. Elle ne recharge
pas les fichiers présents ou ne remplace pas silencieusement des fichiers
altérés.

**Arrêts immédiats** : accès refusé ou session invalide (401/403),
limitation 429 avec \`Retry-After\` communiqué sans réessai automatique,
autre code HTTP, JSON invalide, horodatage anormal, retour historique
hors des sept jours. Une erreur n'efface jamais les JSON déjà validés.
Il est interdit de contourner les protections du fournisseur.

### Audit avant toute qualification P5

Après collecte autorisée et uniquement pour les fichiers existants :

\`\`\`bash
python -m scripts.reconstruct_pulse_replay \
  --output data/pulse-batch-audit \
  data/pulse-batch-001/replay-at-*.json
\`\`\`

Le reconstructeur reconnaît les suppressions de stations encodées
par \`m=e=d=o=0\` dans les **frames** de Pulse. Les états initiaux
(\`baseline\`) entièrement nuls ne sont **pas** automatiquement assimilés
à des suppressions. Cette correction évite de continuer à afficher une
station absente pendant les fenêtres suivantes.

Examiner le manifeste, les stations distinctes, la fraîcheur,
les trous, les chevauchements et la couverture par créneau de cinq minutes.
Les fichiers reconstitués demeurent de provenance
\`velib-pulse-unofficial\`, \`training_qualified=false\`.
Aucune écriture automatique dans P3 ni entraînement P5 : une qualification
explicite de la source est requise.
