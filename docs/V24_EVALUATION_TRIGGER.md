# Déclencheur réservé pour la vérification V2.4 du 4 novembre 2026

**NE PAS utiliser cette page comme un résultat de validation.**

Ce fichier est suivi par `.github/workflows/v24-evaluate.yml`.
Toute modification ultérieure sur la branche `research/v2-4-future-holdout`
relance le **précontrôle**. Avant le **4 novembre 2026 à 04:00 UTC
(05:00 à Paris)**, ce précontrôle doit répondre
`awaiting_future_data` et la tâche de score doit rester ignorée.

Après cette date, une nouvelle modification volontaire de ce fichier
pourra relancer l'évaluation, à condition que les archives et labels
qualifiés couvrent bien la semaine du 28/10 au 04/11 UTC.

Lancer les analyses de cette branche **n'entraîne jamais de publication
sur Vercel**. La PR #40 reste un brouillon.

## Trace

- Préenregistrement : 27 octobre 2026.
- Test futur prévu : 28 octobre 00:00 UTC — 4 novembre 00:00 UTC.
- Premier lancement possible : 4 novembre 04:00 UTC.
- Modèle épinglé : GitHub Actions #40495787979.
- Référence principale : la persistance du nombre de vélos.
- Aucun candidat V2.3.1 n'a passé la validation historique.

**Intervention manuelle future nécessaire :** déclencher le workflow
sur cette branche ou modifier une seule ligne de ce fichier après la date.
Le cron GitHub n'exécute pas les workflows de branches non par défaut.
