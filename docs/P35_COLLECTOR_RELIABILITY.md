# URBAN OPS — P3.5 : fiabilisation mesurable de la collecte

## Diagnostic vérifié

Le collector GitHub Actions a bien réalisé une collecte lors d'un push le 19 octobre 2026 (21:30 UTC), puis au moins une exécution planifiée le 20 octobre (00:33 UTC ; archive 00:34 UTC). Il y a donc **plusieurs heures de trou**, même si les deux exécutions aboutissent et sont archivées. Ce n'est pas une panne du pipeline Python ; c'est une cadence GitHub Actions non garantie.

La source exacte du trou ne peut pas être établie uniquement à partir des runs présents : l'absence de certains événements `schedule` ne prouve pas un bug applicatif. Un déclenchement manqué ne peut **pas** être rattrapé en réinterrogeant plus tard un flux temps réel.

## Contrôles automatiques

- `.github/workflows/collect.yml` reste un **pilote best effort** de cadence cible cinq minutes, sur `main`.
- `.github/workflows/collector-health.yml` audite les **assets réellement persistés**, pas les jobs démarrés ou un compteur théorique de captures.
- `scripts/audit_collector.py` relève les captures uniques, le dernier instant, l'âge de l'archive, les écarts entre captures, l'estimation de couverture depuis la première capture présente dans la fenêtre 24 h.
- **Une seule archive ne vaut jamais 100 % de couverture**. Le calcul indique si la fenêtre de 24 h est complète.
- La pagination des assets de Releases évite de s'arrêter arbitrairement au centième fichier.
- Le contrôle passe en erreur quand la dernière archive a plus de **90 minutes** ; une couverture dégradée émet un avertissement. La notification dépend des réglages GitHub de l'utilisateur.
- Aucun faux remplissage des périodes sans données, aucun déploiement Vercel, Railway ou service payant.

## Limite fondamentale

L'audit n'ajoute **aucune garantie de déclenchement**. Les deux workflows utilisent GitHub Actions et peuvent tous deux être retardés. Pour une cadence de 5 minutes réellement garantie, il faut un déclencheur indépendant doté de garanties contractuelles ou un service supervisé, dont le coût et l'accès devront être approuvés avant activation.

## Contrôle et décision

1. Vérifier `Actions > P3 best-effort Velib collector` et `Releases` : chaque capture archivée doit avoir un timestamp réel.
2. Consulter `Actions > P3.5 collector coverage and freshness audit` : télécharger le rapport JSON si nécessaire.
3. Après plusieurs heures d'observation, considérer la cadence comme **dégradée** si les manques persistent ; ne pas annoncer « toutes les 5 minutes » comme acquis.
4. **P5** : on peut préparer la baseline et les caractéristiques temporelles, mais on n'entraîne/évalue aucune prévision sérieuse tant que les données mesurées ne couvrent pas suffisamment de situations.
5. Si l'utilisateur demande une vraie continuité de collecte, comparer ensuite les hébergements persistants/cron externes, et demander l'accord avant tout frais ou connexion supplémentaire.

Le rapport est basé uniquement sur les archives retrouvées, sans estimation de trajets ni d'activité d'usagers.
