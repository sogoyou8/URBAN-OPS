# C3 — Publication d'Urban Ops, préparation sans activation

**État : contrôles de publication automatisés, hébergement public à autoriser séparément.**

## Ce qui peut être terminé pendant les sept jours P3

1. Vérifier les données **réelles** : captures P3 archivées en GitHub Releases, replay SHA-256, qualité station, dates et provenance. Le script `scripts/package_p6_public.py` doit accepter l'archive et l'interface; une capture récente mais sans stations utilisables demeure un relevé archivé **inexploitable**, pas un réseau vide.
2. Contrôler les quatre sections Réseau, Territoires, Fiabilité et Prévisions sur le paquet statique final, desktop/mobile et clavier. Maintenir le graphique des stations mesurées et la distinction entre captures partielles et totalement inutilisables. La validation visuelle humaine sur Windows reste distincte de Chromium CI.
3. Refuser **toute prévision P5** tant que les seuils, le backtest chronologique, le test indépendant et les métriques du modèle final ne sont pas réellement validés. Les essais précoces `P5_EXPLORATORY_ONLY.json` ne sont **jamais** des résultats publiables.
4. Construire le bundle public immuable avec JavaScript/CSS cartographiques auto-hébergés, politique CSP, `manifest.json` SHA-256, `provenance.json`, assets strictement autorisés et limite d'âge de l'archive vérifiée au build.
5. Exécuter `python -m scripts.c3_preflight --bundle dist/p6-public` et lire le rapport `data/c3-preflight.json` : il doit dire `technical_preflight_passed_human_checks_pending`, `deployment_performed: false`, `requires_explicit_manual_approval: true`.
6. Inspecter le rapport P3.5 de fraîcheur/couverture : l'archivage via GitHub Actions est **best effort**, non garanti chaque cinq minutes.

## Ce qui reste soumis à un accord de publication

- Valider visuellement le paquet exact sur Windows et son rendu mobile.
- Confirmer la destination publique (GitHub Pages sur dépôt public, sauf autre choix explicite) et autoriser l'activation dans **Settings → Pages → GitHub Actions**.
- **Seulement après cet accord**, configurer le premier déploiement, vérifier l'URL réelle, les chemins sous `/URBAN-OPS/`, la carte OpenFreeMap et son fallback, les polices, l'accessibilité et l'absence de secrets.
- Autoriser et configurer la cadence éventuelle de republication **au plus une fois par heure**, après un nouveau replay P3 réel validé. Si les archives sont périmées ou le build échoue, conserver le bundle public précédent affichant son horodatage : aucune mise à jour synthétique.

Le site peut être publié **sans attendre la fin de P5** tant que l'écran Prévisions indique explicitement la préparation et ne montre ni score ni valeur prédite. **La collecte P3 continue indépendamment**; sept jours calendaires sont un minimum de données, pas une durée pendant laquelle tout développement doit s'arrêter.

## Arrêt fonctionnel et gel

- **Observatoire V1 figé :** C3 publié, source/qualité/historique corrects, automatisation de mise à jour validée ou fréquence limitée et documentée, navigation et modules vérifiés. Les seuls changements ultérieurs sont des corrections de panne, qualité, sécurité ou conformité.
- **Projet complet V2 figé :** conditions de V1 remplies, P5 entraîné et évalué sur des captures réelles avec les règles publiées (≥7 jours, ≥900 captures, ≥40 % de créneaux distincts, paires réelles, évaluation train/validation/holdout sans fuite), puis ajout au site uniquement si la comparaison à la persistance est positive aux seuils fixés.
- Si P5 ne bat pas sa baseline, le bon résultat est **« modèle non validé »** ; ne pas inventer de performance ni allonger indéfiniment le projet pour satisfaire un chiffre.

## Artefacts et liens techniques

- `.github/workflows/p6-cockpit.yml` : `urban-ops-p69-publication-ready`, `urban-ops-c3-preflight-not-deployed`, `urban-ops-p5-exploratory-only`, captures Chromium.
- `.github/workflows/p5-forecasting.yml` : pipeline de **validation finale** P5, déclenché séparément quand l'inventaire est admissible.
- `docs/P69_PUBLICATION_READINESS.md` : contraintes d'intégrité, provenance, licence, CSP, sécurité et hébergement.

**Cette étape ne configure ni Pages, ni DNS, ni hébergement payant, ni facturation.**
