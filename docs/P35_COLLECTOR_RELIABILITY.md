# URBAN OPS — P3.5 : fiabilisation mesurable de la collecte

## Diagnostic vérifié

Le collector GitHub Actions a bien réalisé une collecte lors d'un push le 19 octobre 2026 (21:30 UTC), puis au moins une exécution planifiée le 20 octobre (00:33 UTC ; archive 00:34 UTC). Il y a donc **plusieurs heures de trou**, même si les deux exécutions aboutissent et sont archivées. Ce n'est pas une panne du pipeline Python ; c'est une cadence GitHub Actions non garantie.

La source exacte du trou ne peut pas être établie uniquement à partir des runs présents : l'absence de certains événements `schedule` ne prouve pas un bug applicatif. Un déclenchement manqué ne peut **pas** être rattrapé en réinterrogeant plus tard un flux temps réel.

## Contrôles automatiques

- `.github/workflows/collect.yml` reste un **pilote best effort** de cadence cible cinq minutes, sur `main`.
- `.github/workflows/collector-health.yml` audite les **assets réellement persistés**, pas les jobs démarrés ou un compteur théorique de captures.
- `scripts/audit_collector.py` relève les captures uniques, le dernier instant, l'âge de l'archive, les écarts entre captures et **les créneaux UTC distincts de cinq minutes**. Plusieurs archives dans un même créneau ne font pas artificiellement monter la couverture.
- **Une seule archive ne vaut jamais 100 % de couverture**. Le rapport distingue la couverture sur la période observée de celle des **24 h intégrales** et signale précisément le plus grand trou.
- La pagination des assets de Releases évite de s'arrêter arbitrairement au centième fichier.
- Le contrôle passe en erreur quand la dernière archive a plus de **90 minutes** **ou** quand la couverture observée tombe sous 80 % **ou** quand un écart entre captures dépasse 15 minutes. Ces seuils pilotent uniquement l'alerte, **pas** l'acceptation des données par P5. L'alerte est visible dans GitHub Actions ; la notification dépend des réglages GitHub de l'utilisateur.
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

## Diagnostic des captures du 20 octobre 2026

Sur les archives persistées dans GitHub Releases (pas sur une simulation), nous avons observé **261 fichiers** pour le 20 octobre, contre **288 créneaux de cinq minutes possibles**. Le principal trou court de **00:34:04 à 02:41:11 UTC**, soit environ **127 minutes** entre deux captures persistées. Une interruption plus courte d'environ 10 minutes est visible vers 18:51–19:01 UTC. L'archive seule ne prouve pas la cause : retard/absence de déclenchement GitHub, échec de collecte ou de publication seraient à distinguer dans les logs des exécutions.

**Ne jamais reconstruire les valeurs manquantes à partir du dernier état courant**. Ce correctif améliore seulement l'observabilité et les alertes ; il n'ajoute pas de scheduler secondaire, de stockage ou de coût.

Dans GitHub, consulter [l'audit P3.5](https://github.com/sogoyou8/URBAN-OPS/actions/workflows/collector-health.yml). Les échecs du job `audit` signalent soit une archive trop ancienne, soit une discontinuité ou couverture dégradée. Examiner aussi les `collect.yml` et la Release du jour pour rechercher la cause, sans confondre une exécution manquée avec une panne du pipeline.
