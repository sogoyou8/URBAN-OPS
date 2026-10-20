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
