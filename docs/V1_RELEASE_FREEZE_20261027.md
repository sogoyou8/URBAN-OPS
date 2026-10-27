# Urban Ops V1 — Gel fonctionnel (27 octobre 2026)

## Statut public

**V1 publiée sur Vercel :** https://urban-ops.vercel.app/

Cette version est un **observatoire d'archives Vélib’ horodatées, et non un service temps réel**. Son cockpit comprend quatre espaces : Réseau, Territoires, Fiabilité et Prévisions (non disponibles tant que le modèle n'est pas validé).

## Périmètre figé

- **P3** : collecte Vélib’ réelle, archives GitHub Releases, contrôles de qualité et empreintes SHA-256.
- **P4** : rapport Power BI Desktop à quatre pages ; affichage et interactions vérifiés sur Windows le 27/10/2026. Le paquet de recette utilisé était un échantillon historique du 21/10/2026.
- **P5** : entraînement et validation chronologique exécutés après 7 jours de collecte. L'expérience est terminée mais le candidat n'a pas démontré de gain MAE : test MAE persistance **1,1549** vélo vs candidat **1,2203** vélo. Décision **baseline_wins_or_uncertain**. Aucune prévision issue de ce modèle n'est publiée.
- **P6** : quatre vues du cockpit, carte, recherche et inspection des stations, diagnostics de fiabilité, historique compact/étendu et aide contextuelle. Contrôles Chromium réels ordinateur et mobile (390 px) réussis.

## Fonctionnement de production

- Source GitHub : `sogoyou8/URBAN-OPS`, branche `main`.
- Publication sur **Vercel**, pas GitHub Pages.
- Les archives P3 sont rejouées au build à partir de 48 captures au plus.
- Le build refuse les données fictives, l'intégrité invalide, les sources périmées ou les captures sans observations exploitables.
- Le workflow `.github/workflows/vercel-v1-refresh.yml` recherche de nouvelles captures quatre fois par jour (créneaux en UTC). Si un nouvel instantané existe, un commit de métadonnées déclenche une reconstruction Vercel.
- Ces mises à jour périodiques **ne déploient pas de nouveaux modèles** et **ne prétendent pas fournir un flux en direct**. Le succès du premier déclenchement a été vérifié le 27/10/2026 ; les exécutions ultérieures restent à surveiller.

## Politique de gel

La **conception, les écrans et les fonctionnalités de V1 sont figés**. Le gel fonctionnel n'arrête pas la collecte ni la republication d'instantanés P3 vérifiés. Les corrections de sécurité, de qualité des données ou de production restent autorisées, documentées et testées.

**V2 est un chantier indépendant** pour la recherche et l'amélioration de la prévision à +30 minutes. Aucun modèle ne peut être intégré à V1 avant un backtest chronologique concluant contre la persistance et une nouvelle validation explicite.

## Portfolio

Fiche de présentation : Abyss Showcase → Projets → Urban Ops.
Démo : https://urban-ops.vercel.app/
Source : https://github.com/sogoyou8/URBAN-OPS
