# Urban Ops — Diagnostic des captures P3 sans mesures exploitables

## Anomalie observée (21 octobre 2026)

Un écran Windows affiche un relevé du 21 octobre 2026 à **11 h 06 (Paris, 09 h 06 UTC)** : 1 515 stations référencées, **0 station exploitable**, affichées jusqu'ici à tort comme « 0 vélo disponible ». Le journal des archives publiques contient un objet `capture-20261021T090616Z-523362e7.tar.gz` de 82 098 octets, contre 96 421 octets à 09:01 UTC et 96 369 à 09:11 UTC. **La différence de taille ne prouve pas à elle seule la cause des rejets.**

### Origine précise du faux zéro

1. Dans P3, une ingestion marquée `success` veut dire que les fichiers ont été obtenus et archivés et que le traitement SQL a abouti. Ce n'est **pas une promesse que des mesures sont exploitables**.
2. La qualification `is_usable` exige les drapeaux opérationnels, des comptes cohérents et un horodatage acceptable. Les valeurs peuvent être rejetées sans que l'archive cesse d'exister.
3. P6 exportait `SUM(CASE WHEN is_usable=1 ... ELSE 0 END)`, et remplaçait un total SQL nul par `0` même pour **0 station exploitable**.
4. Le cockpit annonçait alors « 0 vélo », ce qui confondait **absence de mesure** et **mesure de zéro vélo**.

### Corrections

- L'export conserve la capture réelle mais inscrit `metrics.bikes`, `docks` et `empty` à `null` si `metrics.usable==0`. Même règle pour les totaux historiques. Les vrais zéros, quand une station est **effectivement exploitable**, restent des nombres zéro.
- Un champ `capture_quality.status` indique `no_usable_stations` ou `usable`, sans inventer de correction.
- Les chiffres « vélos disponibles » et « stations sans vélo » affichent **—**, pas zéro, lorsqu'il n'existe aucune station mesurée ; le bandeau indique **Capture inexploitable**, même si l'archive a été créée récemment.
- L'historique garde les dates et le nombre de stations de la capture (zéro station mesurée), mais marque **Données indisponibles** au lieu d'une chute à zéro vélo. Aucun segment relie cette capture à ses voisines.
- `scripts/diagnose_p3_capture.py` examine **toutes les captures ayant 0 station exploitable dans le rejeu P3 vérifié**, compare chaque capture à ses voisines, ventile les drapeaux, anomalies de comptes, décalages temporels et motifs enregistrés en SQL. **Les motifs peuvent se chevaucher** ; le rapport ne décrète pas une cause unique.
- Le workflow P6 conserve un artefact `urban-ops-p3-zero-usable-diagnostic` et affiche un résumé agrégé dans le journal. Aucune donnée brute ou station nominative n'est envoyée à un service supplémentaire.

## Test et périmètre

Tester un vrai zéro vélo sur station exploitable, une capture de 0 station utilisable, des captures voisines normales et une période avec une interruption. Le paquet produit reste vérifié SHA-256, construit uniquement sur les archives officielles P3, **sans changer leurs contenus**. Le diagnostic peut identifier un facteur dominant, mais toute correction de qualification doit être décidée séparément et justifiée par les sources brutes. Aucun déploiement public C3.


## Diagnostic vérifié sur 48 captures archivées (workflow du 21/10/2026)

Le rapport forensique [GitHub Actions #39578382533](https://github.com/sogoyou8/URBAN-OPS/actions/runs/39578382533), issu du rejeu SQL P3 et de captures SHA-256 vérifiées, relève pour **21/10/2026 09:06:16 UTC (11 h 06 Paris)** :

| Contrôle | Résultat |
| --- | ---: |
| Stations sources information / statut | 1 517 / 1 517 |
| Statuts normalisés et présents | 1 515 |
| Stations exploitables | 0 |
| Vélos totaux absents après normalisation | 0 |
| Bornes totales absentes après normalisation | 0 |
| **Répartition mécaniques absente après normalisation** | **1 515** |
| **Répartition électriques absente après normalisation** | **1 515** |
| Signalements `invalid_counts` | **1 515** |
| Statuts dépassant 3 600 s de retard | 12 |
| Statuts avec date légèrement future | 74 |
| Stations sans location / retour | 16 / 16 |
| Capture précédente (09:01 UTC) : stations utilisables | 1 284 |
| Capture suivante (09:11 UTC) : stations utilisables | 1 485 |

**Conclusion démontrée** : le rejet généralisé est causé immédiatement par l'absence de décomposition mécanique/électrique exploitable dans les champs P3 normalisés. Les totaux de vélos et de bornes sont conservés dans les faits SQL, mais ne suffisent pas aux contrôles P3, qui exigent les quatre quantités cohérentes. L'absence de valeurs mécaniques et électriques peut venir d'un champ absent ou d'une structure invalide dans le JSON source : **le seul diagnostic SQL ne permet pas de trancher ces deux explications**. Aucune donnée n'a été remplacée ni supposée. La vérification du fichier Bronze brut serait nécessaire pour attribuer l'origine exacte à une modification ponctuelle du flux amont.

**Décision produit** : garder les contrôles P3 inchangés et afficher **« Données indisponibles »** pour cette capture, plutôt que « 0 vélo » ; aucune affirmation sur une disparition des vélos et aucune interpolation vers les captures voisines.

Rapport téléchargeable sous **urban-ops-p3-zero-usable-diagnostic** dans le workflow lié.
