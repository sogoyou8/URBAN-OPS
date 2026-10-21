# C2.5 — Historique interactif (concept 5 retenu)

## Périmètre

Seul le composant **C / Historique** du cockpit P6 est refait : carte, navigation, fiche station, calculs de P3, préparation P5 et publication restent inchangés.

La présentation retenue a **deux mesures synchronisées** sur les mêmes instants : courbe verte « Vélos comptés » et histogramme bleu « Stations mesurées ». Le panneau conserve les totaux, le nombre de captures orange et la date réelle de début/fin ; « Plus grande pause » est remplacé par **« Intervalle max. »** car un intervalle d'environ cinq minutes est normal et ne doit pas être décrit comme une panne.

### Vérité des données

- Source : `history[].at`, `bikes`, `usable`, `connected_to_previous`, `gap_minutes` de l'export P6 construit à partir des véritables archives P3.
- **Aucune interpolation.** Les traits verts relient uniquement des valeurs consécutives considérées comparables. Les mesures à couverture réduite restent visibles sous forme de points orange. Les barres bleues sont le nombre exact de stations exploitables : **pas le total de stations**.
- Courbe du haut : **échelle détaillée explicitement titrée**. Elle se base uniquement sur les observations comparables pour ne pas aplatir la variation normale à cause des relevés incomplets. Si un point orange sort de l'échelle, il est **montré en limite avec chevron orange**, toujours consultable, et sa valeur réelle reste intacte dans le panneau d'inspection. Le panneau ne présente **pas** une échelle commençant à zéro pour les vélos.
- Histogramme du bas : échelle **commençant à zéro**, jusqu'au nombre de stations référencées (arrondi à la centaine supérieure), annotée avec ses bornes. Les données inconnues ne deviennent pas zéro.
- Durée et bornes temporelles : calculées uniquement sur les horodatages présents ; aucun bouton « 7 jours / 30 jours » fictif n'est ajouté.

### Interaction

- Cliquer sur un point ou une barre sélectionne une capture et synchronise un repère vertical.
- Le panneau de gauche détaille son heure, ses vélos comptés, ses stations mesurées rapportées aux stations du réseau, et un statut « Mesure comparable », « Capture incomplète » ou « Données insuffisantes ».
- Le curseur de sélection est utilisable au **clavier, au toucher et à la souris** ; il décrit la capture dans `aria-valuetext`. La sélection est conservée lors du changement de vue et de la redimension.
- Pas de nouvelle requête vers Vélib' ou Pulse, pas de cookies ni d'API supplémentaire.

### Recette

Tests unitaires sur l'échelle détaillée et les valeurs hors échelle ; tests Chromium sur la sélection, la navigation au clavier, les points orange, le mode mono-écran 1440×900 et 1024×768, les largeurs 390 et 320, et le fallback cartographique. Contrôle séparé sur le **paquet P6 construit à partir des archives P3 réelles** par le workflow existant, avec captures d'écran. La validation réelle d'OpenFreeMap sur Windows doit être maintenue avant publication publique.
