# Urban Ops — P6 C2.6 : finition du cockpit

## Objectif
Reprendre **uniquement** les points observés à la recette visuelle Windows après C2.5, sans refaire la direction esthétique choisie (concept n°5).

### 1. Carte moins chargée, sans effacer des stations
- À l'échelle métropolitaine (zoom inférieur à 12,6), les stations proches sont regroupées sur une grille d'écran plus large : **50 px desktop / 52 px tablette / 62 px smartphone**.
- Entre zoom 12,6 et 13,2, les groupes se resserrent. Aux zooms de rue, la granularité fine de C2.5 est conservée.
- Les cercles regroupés sont plus discrets (rayon plafonné à 13,5 px, contre 17 px) ; leur nombre affiche toujours le nombre d'identifiants de stations correspondants.
- Une station déjà sélectionnée reste individualisée, même à faible zoom. Le clic sur un groupe continue de zoomer ou d'ouvrir la liste selon le niveau de zoom. **Aucune station n'est supprimée, dédoublonnée ni modifiée dans la donnée.**
- Le compteur de la carte distingue : **résultats** des filtres, stations **sur carte**, et **repères** effectivement dessinés. Les chiffres restent calculés sur les données P3 réelles, à la position courante.

### 2. Carte prioritaire et historique développé à la demande
- Sur ordinateur, C / Historique démarre en mode **Compact** afin de laisser plus de place à la carte et à la liste de stations. **Développer** agrandit seulement le composant C2.5 ; **Réduire** restaure l'espace cartographique.
- La carte conserve sa position/son zoom, ses filtres et la station consultée. La capture actuellement sélectionnée conserve sa date et ses valeurs lors du changement de taille.
- Les deux tailles desktop préservent l'absence de défilement global et le panneau droit à défilement interne.
- Sur téléphone, les graphiques sont déjà empilés pleine largeur ; l'interrupteur de hauteur n'est pas proposé. Pas de régression sur le fallback sans tuiles.

### 3. Termes et lecture de C2.5
- **Intervalle max.** reste le terme correct lorsqu'un espacement de cinq minutes est normal.
- Un point orange hors de la plage détaillée n'est ni supprimé ni remplacé : l'indication devient, par exemple, **« 1 capture hors échelle · sélectionnez le point orange pour voir le chiffre exact. »** avec accord au pluriel et description au survol.
- Les échelles visibles, les valeurs mesurées, le seuil visuel de qualité de C2.3 et les ruptures de courbe sont inchangés.

### 4. Recette
- Tests JS : nombre de repères décroissant à faible zoom, conservation exacte de tous les identifiants de station, granularité au zoom de rue et station sélectionnée.
- Tests Chromium : mode compact par défaut, hauteur de carte avant/après, contrôle clavier, absence de scroll desktop, sélection de capture préservée, historique et fallback mobile.
- Build P6.9 réel : archives P3 vérifiées par SHA-256 et reconstruites sans modification, captures des deux tailles desktop et de la vue mobile, aucune mise en ligne.

La grande croix flottante visible dans une précédente capture Windows ne peut pas être attribuée avec certitude au code de l'application à partir de la seule image. Aucun élément de fermeture n'est supprimé sans preuve.
