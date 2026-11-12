# Indicateurs de qualité

| Domaine | Indicateur | Cible | Mesure |
|---|---|---|---|
| Données | Complétude des observations | ≥ 95 % | `python -m goutte_deau quality` |
| Données | Fraîcheur (jours depuis la dernière observation) | ≤ 2 j en exploitation | idem |
| Données | Lignes rejetées par le nettoyage | < 2 % | table `collection_run` |
| Modèle | ROC-AUC, score de Brier, F1 sur jeu de test chronologique | Brier < climatologie (BSS > 0) | `reports/metrics.json` |
| Modèle | Calibration (courbe de fiabilité) | écart < 0,05 par classe | `reports/evaluation.png` |
| API | Disponibilité / latence p95 | ≥ 99 % / < 300 ms | supervision de `/health` |
| API | Couverture de tests | ≥ 80 % | `pytest --cov=goutte_deau` |
| Code | Lint | 0 erreur | `ruff check src tests app` |
| UI | Score d'accessibilité automatisé | ≥ 90 (puis audit RGAA) | Lighthouse / axe |
| Éco | Énergie d'entraînement, poids des pages | suivi à chaque version | `metadata.json` (`eco`) |
