# Urban Ops P3.5 — Strict 0 €: Cloudflare Free Cron → GitHub

## Décision : pas d'abonnement R2

Cette option utilise **Cloudflare Workers Free**, puis **GitHub Actions sur le dépôt public**
et les archives **GitHub Releases déjà opérationnelles**. Il n'y a **ni R2, ni D1,
ni KV, ni carte bancaire à enregistrer** pour ce chemin. Il faut rester sur
Workers Free et ne jamais sélectionner Workers Paid. Le code R2 précédent
reste expérimental, non déployé, et n'est pas utilisé ici.

Le déclencheur ne contacte ni les flux Vélib' ni un stockage payant : il lance
uniquement `.github/workflows/collect.yml` via l'API GitHub
`workflow_dispatch`. GitHub réalise la collecte réelle et publie les mêmes
archives Bronze chiffrées SHA-256 dans la Release UTC du jour.

Le cron `*/5 * * * *` représente 288 **tentatives de lancement** par jour.
Le déclencheur peut être retardé et GitHub met aussi ses jobs en file d'attente.
**Aucune cadence stricte garantie à cinq minutes**. L'audit P3.5 existant doit
mesurer le nombre d'archives réellement publiées.

### Coût : pourquoi cette voie ?

- Cloudflare Workers Free : limite 100 000 requêtes/jour ; chaque appel
  `scheduled` déclenche une seule requête HTTPS vers l'API GitHub.
  CPU limité à 10 ms ; notre déclencheur ne fait ni compression ni traitement JSON volumineux.
- GitHub Actions runners standard (`ubuntu-latest`) : gratuits et non
  décomptés en minutes payantes sur les dépôts **publics**, confirmé pour `sogoyou8/URBAN-OPS`.
- GitHub Releases : stockage des archives existant, pas de bucket R2.
  Les limites GitHub, les politiques d'utilisation et la fréquence de requêtes
  continuent de s'appliquer. Ne pas basculer le dépôt en privé sans réévaluer
  la facturation GitHub Actions.

Sources :
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/workers/platform/limits/
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event

## Préparation sans aucun déploiement

Depuis le **dossier UNIQUE** UrbanOps Windows, après synchronisation Git :

```powershell
cd .\cloudflare\free-trigger
node --test .\test\dispatcher.test.mjs
```

Les tests sont exécutés également sur GitHub CI à chaque mise à jour du module.
Ils ne déclenchent AUCUN workflow réel et n'utilisent pas de jeton.

## Activation future : uniquement sur offre Workers Free

1. Ouvrir Cloudflare : **Build / Calcul → Workers & Pages**.
   Si Cloudflare demande une carte ou un passage en Workers Paid, **arrêter**.
2. Générer **personnellement** un jeton GitHub finement limité :
   GitHub → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens. Limiter à **sogoyou8/URBAN-OPS** et
   **Repository permissions → Actions: Read and write**. Durée limitée
   conseillée (p. ex. 30 ou 90 jours), avec renouvellement avant expiration.
   Ne jamais publier ou envoyer ce jeton par chat, commit, capture ou terminal partagé.
3. Connecter le Worker à Cloudflare en étant sur le plan Free ;
   enregistrer `GITHUB_DISPATCH_TOKEN` comme **secret chiffré** de ce Worker.
   L'interface Cloudflare permet de gérer Secrets et Variables.
   Attention : `wrangler secret put` peut créer un déploiement immédiatement.
4. **Seulement une fois le secret enregistré** et le plan Free confirmé,
   activer le Worker / Cron `*/5 * * * *` avec
   `cloudflare/free-trigger/wrangler.toml`. Ce fichier **ne contient aucun
   binding R2** et n'a pas de route HTTP publique.
5. Consulter **Cloudflare → Workers → Observability** et **GitHub → Actions →
   P3 best-effort Velib collector → workflow_dispatch**. Valider un lancement
   Cloudflare réel et l'existence d'une nouvelle archive Release, puis surveiller
   la régularité pendant 24 h.
6. Lorsque Cloudflare a démontré une meilleure continuité que le
   `schedule` GitHub, désactiver le **cron GitHub natif** pour réduire
   les collectes doubles, tout en conservant `workflow_dispatch`.
   Ne pas désactiver prématurément le workflow entier.

**Il n'y a pas encore de déploiement Cloudflare ni de jeton dans le dépôt.**
Aucun utilisateur ne doit communiquer son jeton à l'assistant.

## Limites connues

- Un dispatch HTTP 204 signifie que GitHub a accepté la requête, **pas**
  que le workflow a réussi ou qu'une capture est persistée.
- Le GitHub PAT doit être renouvelé ; à expiration, le déclencheur échoue
  et l'audit des archives doit détecter l'absence de nouvelles données.
- `concurrency` du workflow GitHub peut regrouper/supprimer des runs en attente
  lorsque la charge excède la capacité des runners.
- GitHub reste un fournisseur tiers ; sa politique et ses limites peuvent
  changer. Cette solution est un pilote **sans abonnement payant**, pas un
  engagement contractuel de collecte 24/7.
