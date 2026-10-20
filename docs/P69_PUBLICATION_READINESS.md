# P6.9 — Préparation de publication d’Urban Ops (sans déployer)

**État attendu :** bundle statique autonome **prêt à vérifier**, stocké temporairement comme artefact GitHub Actions ; **aucun hébergement, Pages ni déploiement n'est activé**.

## A — Construction à partir des données réelles

Le workflow `.github/workflows/p6-cockpit.yml` :

1. Télécharge les archives P3 `capture-*.tar.gz` déjà publiées en Releases ; **les données de test ne sont pas acceptées**.
2. Rejoue les archives via `scripts.replay_capture`. Chaque archive est décompactée et ses empreintes SHA-256 contrôlées par `scripts.archive_capture.unpack` avant le traitement.
3. Produit `web/data/network.json` avec `scripts.export_p6` : dernière capture observée, qualité, historique non interpolé et seuils P5 *non validés*. La date de capture n’est pas la date de visite du lecteur.
4. `scripts.package_p6_public` construit une copie **à liste blanche** dans `dist/p6-public/`, remplace les JS/CSS MapLibre servis par le CDN par une copie locale de la version **exacte 4.7.1** téléchargée pendant la CI, vérifie la fraîcheur au moment du build (`<= 24 h`), le `run_id` du replay et les métriques de P3.
5. Crée `provenance.json` (provenance et méthode de vérification), `manifest.json` (SHA-256 de chaque fichier), `.nojekyll`, et inspecte l’intégrité du bundle. Rien de Git, des fichiers `.env`, des tokens ou de la fixture Chromium n'est empaqueté.
6. Publie **uniquement un artefact Actions téléchargeable**, `urban-ops-p69-publication-ready`, **pas** un site.

La chaîne d’archivage, le replay et les contrôles de CI constituent la preuve de provenance. Le manifeste est un contrôle d'intégrité du **paquet construit**, **pas une signature cryptographique d'un tiers de confiance**. Une archive P3 corrompue fait échouer le replay ; une donnée trop ancienne bloque ce paquet de publication.

## B — Hébergement futur choisi : GitHub Pages

- GitHub Pages convient à ce cockpit statique dans un **dépôt public** GitHub Free : pas de base de données, pas de serveur, pas de R2, pas d’abonnement de déploiement.
- **Pas de workflow Pages actif**, pas de `actions/deploy-pages`, pas de changement de Settings → Pages, pas de domaine réservé à cette étape.
- **Après autorisation explicite de l'utilisateur seulement** : configurer *Settings → Pages → Build and deployment → GitHub Actions*, ajouter une étape manuelle de déploiement du bundle **validé** (artefact de build du même commit), puis vérifier l'URL réelle et la mention archive.
- **Cadence proposée seulement, non activée** : publication au maximum **une fois par heure** (ou 1 fois/jour selon trafic/quotas), après succès des archives P3 et contrôles P6. Pas de collecte au navigateur ; pas de rafraîchissement public tous les cinq minutes. Chaque génération remplace atomiquement le JSON + l'interface ; l'observation reste datée dans le produit.
- Si le jeu de données est absent, périmé, non vérifiable ou si le build échoue, **ne pas déployer** ; conserver la version précédemment publiée avec sa date d'observation visible. Ne jamais injecter de données synthétiques pour combler un trou.
- **P5 reste non validé** et ne doit jamais générer de score ou de prévision dans P6 avant réussite de son évaluation chronologique indépendante.

## C — Contrôles techniques avant publication

- Bundle en **chemins relatifs** : fonctionne à la racine du domaine ou sous `/URBAN-OPS/`.
- JS/CSS de **MapLibre auto-hébergés** dans `vendor/`. Les styles OpenFreeMap et les tuiles, ainsi que Google Fonts, restent des services externes : les contrôler à la recette publique. Mode de secours cartographique actif en leur absence.
- Politique CSP (meta HTML) restrictive sur les scripts (auto-hébergés uniquement) et les connexions cartographiques; aucune autorisation générale de scripts tiers. **Une CSP meta ne permet pas `frame-ancestors`, HSTS ou X-Frame-Options :** ajouter les en-têtes HTTP correspondants uniquement si l'hébergement futur les permet.
- L'interface comporte une navigation clavier, un accès direct au contenu, l'indication du mode archivé, un message explicite si `network.json` est inaccessible, et respecte `prefers-reduced-motion`.
- Rejet des données de test, des secrets, de prévisions non validées, des fichiers supplémentaires, des incohérences d'horodatage et des sommes de contrôle divergentes.
- Budget technique de build : JSON `<= 3 Mo` non compressés et bundle de fichiers listés `<= 12 Mo` ; tests Node/Python + Chromium à 1440 × 900 et 390 × 844 sur le **paquet complet contenant les données réellement rejouées**.
- L'action NPM d'empaquetage est exécutée en CI uniquement ; auditer régulièrement les dépendances (MapLibre 4.7.1 actuellement conservée pour compatibilité avec les captures utilisateur). Les rapports npm de sécurité sont à réévaluer avant déploiement définitif.

## D — Critères de feu vert avant ordre de déploiement

- [ ] Tests Python/JS + Chromium réussis sur `main`.
- [ ] Job `real-export` et job `publication-package` réussis à partir des captures P3 authentiques.
- [ ] Artefact `urban-ops-p69-publication-ready` téléchargeable, `manifest.json` et `provenance.json` présents, somme SHA-256 vérifiée par `--verify-only`.
- [ ] Le JavaScript principal, la bibliothèque cartographique et les données sont accessibles sous un sous-chemin HTTP relatif ; navigateur sans erreur bloquante.
- [ ] Aucune page publique créée, aucune activation de facturation, aucune modification de domaine/DNS.
- [ ] **Recette finale du bundle sur le PC de l'utilisateur et accord explicite pour le futur déploiement.**

L'étape P6.9 **s'arrête ici** : aucun hébergement n'est déployé ni configuré automatiquement.