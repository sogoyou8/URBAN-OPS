# P6 C2.6.1 — Clarté cartographique et historique compact

## Constat (recette desktop du 21 octobre 2026)

Sur l'écran Réseau d'Urban Ops, la carte affiche des regroupements tels que « 370 ». Ce nombre **représente le nombre de stations regroupées dans un cercle**, et **jamais** le nombre de vélos. Le compteur « résultats / sur carte / repères » exige une explication, car les trois nombres décrivent des choses différentes. Enfin, les textes des deux graphiques sont trop petits dans le mode Historique compact choisi en C2.6.

## Modifications

- La légende cartographique existante conserve les couleurs de disponibilité et ajoute discrètement un **cercle d'exemple numéroté** : « 12 = stations regroupées ».
- Un bouton **ⓘ** situé près des chiffres de la carte affiche, au clic ou au toucher, un court panneau expliquant : « Résultats » = stations correspondant aux filtres ; « Sur carte » = stations présentes dans la zone affichée ; « Repères » = cercles/points dessinés pouvant regrouper plusieurs stations. Il fonctionne au clavier, se ferme avec Échap ou en cliquant ailleurs et rend le focus au bouton après Échap.
- Au survol d'un véritable regroupement MapLibre, le titre précise son nombre de stations et l'action de zoom.
- Sur ordinateur en mode Historique compact, la taille et le contraste des graduations, heures, titres des mesures et légende sont améliorés. Le mode développé et la disposition sur mobile restent inchangés.

## Invariants

**Aucun chiffre de P3, statut de station, filtre, regroupement, coordonnées, comptage de vélos, calcul de couverture, contrôle de P5 ni période historique ne change.** Ces corrections portent uniquement sur la compréhension des composants et sur la typographie. Le cockpit conserve les deux états Compact/Développé et la logique mono-écran.

## Recette

Tests Chromium à 1440×900, 1024×768, 390×844 et 320×700 : vérification des libellés, ouverture/fermeture de l'aide, position du panneau sur mobile, absence de défilement horizontal et taille réelle des textes du graphique compact. Test du paquet P6.9 construit sur les archives officielles P3 vérifiées avec capture supplémentaire `map-counter-help-real-1440x900.png`, sans publication publique.
