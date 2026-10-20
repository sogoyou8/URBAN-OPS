# P5.2 — Import hors ligne des fenêtres Vélib’ Pulse (non officiel)

## Périmètre

Urban Ops possède **déjà** un collecteur officiel GBFS qui capte le réseau entier
et archive les JSON bruts dans GitHub Releases (P3). Ce composant n'est **pas**
un second collecteur. Le module d'import traite hors ligne les fichiers déjà obtenus. Un collecteur optionnel, décrit ci-dessous, utilise le navigateur avec vérification humaine, sans contourner Turnstile.

Référence de format (projet tiers) :
- https://github.com/angristan/velib/blob/main/src/worker/domain.ts
- https://github.com/angristan/velib/blob/main/src/worker/replay.ts
- https://github.com/angristan/velib/blob/main/docs/architecture.md

Le [ticket d'export](https://github.com/angristan/velib/issues/4) demeure une voie à faible charge pour l'historique massif. Une session valide ne donne pas de permission illimitée : consulter les règles du fournisseur et respecter ses restrictions.

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

Une fois des fichiers rejoués disponibles localement :

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


## Récupération séquentielle en une commande — P5.3

Le collecteur évite le téléchargement manuel heure par heure : il prépare
jusqu'à 168 fenêtres réseau de 60 minutes et les récupère chronologiquement,
une par une. Il ne télécharge jamais chaque station séparément.

### Prérequis et sécurité

- Revoir les conditions d'utilisation de Vélib’ Pulse avant d'entreprendre
  un téléchargement volumineux. La validation de session n'est pas une
  autorisation générale d'extraction massive. L'issue de demande d'export
  https://github.com/angristan/velib/issues/4 demeure ouverte.
- Vérifier la session dans Chromium visible ; aucun cookie n'est copié
  manuellement ni sauvegardé. Aucune résolution automatisée de Turnstile.
- Le téléchargement n'est **jamais** lancé par défaut ; seul \`--run\` le démarre.
  Le drapeau artificiel \`--owner-approved\` a été supprimé : son absence
  ne modifie pas les droits d'accès ni les règles du fournisseur.
- Une requête à la fois, attente de **60 secondes par défaut** et **30
  secondes minimum** ; aucune rafale parallèle ni réessai automatique après
  un HTTP 403/429. Ces durées sont des choix de prudence internes, pas
  un débit validé par le propriétaire du service.

### Installation (une fois)

\`\`\`powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pulse]"
.\.venv\Scripts\python.exe -m playwright install chromium
\`\`\`

### Prévisualiser sans accéder au service

\`\`\`powershell
.\.venv\Scripts\python.exe -m scripts.collect_pulse_replay_batch --output data/pulse-batch --hours 168
\`\`\`

Cette commande crée un plan local, sans accès réseau. L'ancre UTC est fixée
au moment de la création : il faut démarrer rapidement car la conservation
des minutes est **glissante sur sept jours**. Pour recommencer à une
autre date, utiliser un nouveau dossier ; ne pas tenter de remplacer
les fichiers archivés.

### Lancer explicitement

\`\`\`powershell
.\.venv\Scripts\python.exe -m scripts.collect_pulse_replay_batch --output data/pulse-batch --hours 168 --run --interval-seconds 60
\`\`\`

Après la vérification de session, les réponses sont validées avant
enregistrement dans \`data/pulse-batch\`, puis suivies dans
\`pulse_batch_manifest.json\` avec empreintes SHA-256. Relancer exactement
la même commande dans le même dossier vérifie les fichiers présents et
reprend les fenêtres encore manquantes.

Le collecteur s'arrête sans recommencer automatiquement si le serveur
refuse l'accès (401/403), limite le débit (429) ou signale une autre erreur.
Il s'arrête également sur JSON invalide et sur données sorties de la plage
de rétention. Les données correctement téléchargées sont conservées.

### Reconstruire et auditer avant P5

\`\`\`powershell
.\.venv\Scripts\python.exe -m scripts.reconstruct_pulse_replay --output data/pulse-audit data/pulse-batch/replay-at-*.json
\`\`\`

Le reconstructeur retire les stations signalées supprimées par un changement
compact \`m=e=d=o=0\`, sans prolonger artificiellement leur présence.
L'export affiche la provenance, la couverture, les trous et les anomalies ;
**il n'entraîne pas P5 et ne modifie pas les observations P3**.
