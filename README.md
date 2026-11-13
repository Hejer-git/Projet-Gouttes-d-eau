# Goutte d'eau — MVP de prévision du risque de pluie à Paris

MVP de l'étude de cas Goutte d'eau (Mastère Management de la Transformation digitale en IA, Bloc 2) :
collecte de mesures météo, nettoyage, stockage en base, modèle de machine learning, **API** qui estime le
risque de pluie pour une date et **interface graphique** de démonstration.

## Ce que contient le dépôt

| Exigence de l'énoncé | Où |
|---|---|
| Collecte des données et enregistrement en base | `src/goutte_deau/collector.py`, `cleaning.py`, `highfreq.py`, `daily.py`, `db.py` |
| Données utilisées | `data/000EW_2022-2026_fusion.csv.gz` : station 000EW (Paris 20e), exports Infoclimat de 2022 à 2026 |
| Modèle et entraînement | `features.py`, `train.py` (régression logistique, forêt aléatoire, gradient boosting) |
| Évaluation du modèle | `evaluate.py`, résultats dans `reports/` |
| API (FastAPI) | `api.py`, `schemas.py`, `predictor.py` |
| Interface graphique | `app/streamlit_app.py` |
| Indicateurs qualité | `quality.py`, `docs/qualite.md` |
| Architecture (diagrammes) | `docs/architecture.md`, `docs/img/` |
| Planning et budget | `docs/planning_budget_goutte_deau.xlsx`, `docs/img/gantt.png` |
| Accessibilité | `docs/accessibilite.md` |
| Dictionnaire de données | `docs/data_dictionary.md` |

## Installation (Python 3.11 ou plus)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          
pip install -r requirements-dev.txt
pip install -e .
pytest
```

## Utilisation

```bash
python -m goutte_deau collect --csv data/000EW_2022-2026_fusion.csv.gz   # nettoyage, base SQLite, table journalière
python -m goutte_deau quality                                           # indicateurs de qualité des données
python -m goutte_deau train                                             # entraînement, évaluation, rapports
python -m goutte_deau serve                                             # API : http://127.0.0.1:8000/docs
streamlit run app/streamlit_app.py                                      # interface (dans un second terminal)
```

Exemple d'appel de l'API :

```bash
curl "http://127.0.0.1:8000/v1/predict?date=2026-10-21"
```

La réponse contient la probabilité de pluie, un niveau de risque, le mode de calcul (`observations` si la
météo de la veille est connue, sinon `climatologie`), la version du modèle et la source des données.

Pour collecter depuis l'API Infoclimat, définir `INFOCLIMAT_TOKEN` (clé liée à l'adresse IP de la machine,
voir `.env.example`) puis : `python -m goutte_deau collect --infoclimat --start 2025-01-01 --end 2025-12-31`.

## Résultats

Cible : « jour de pluie » (cumul d'au moins 1 mm sur 24 h). Test chronologique sur 312 jours
(14/12/2025 au 23/10/2026), modèle retenu : forêt aléatoire réduite.

| | ROC-AUC | Score de Brier |
|---|---|---|
| Modèle | 0,79 | 0,139 |
| Climatologie (référence) | 0,67 | 0,165 |
| Persistance (référence) | 0,63 | 0,244 |

Avec le seuil d'alerte de 0,26 (choisi par validation croisée), 78 % des jours de pluie sont détectés pour
44 % de précision. Détails dans `reports/evaluation.md`.

## Limites

- Une seule station amateur, non comparée à une station officielle ; 2022 présente des données manquantes.
- Risque « jour de pluie » oui/non : pas de quantité de pluie ni d'événements extrêmes.
- Estimation statistique indicative, qui ne remplace pas une prévision opérationnelle.
- Le prototype Streamlit n'est pas conforme au RGAA (voir `docs/accessibilite.md`).

## Sécurité

Requêtes SQL paramétrées, jeton Infoclimat jamais journalisé, clé d'API optionnelle (`GD_API_KEY`,
en-tête `X-API-Key`). Les modèles sont sérialisés avec `joblib` (pickle) : ne charger que ceux produits
par ce dépôt.

## Licence

MIT. Données : Licence Ouverte (source Infoclimat).
