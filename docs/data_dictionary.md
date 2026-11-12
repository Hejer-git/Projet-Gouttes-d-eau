# Dictionnaire de données

## Table `observation` (pas tri-horaire OMM, UTC)
| Colonne | Type | Unité | Règle de qualité |
|---|---|---|---|
| station_id | TEXT | — | identifiant de la station (ex. 000EW) |
| obs_utc | TEXT | UTC | heure ronde multiple de 3 ; unique par station |
| temperature_c | REAL | °C | −40 à 50, sinon manquant |
| pressure_hpa | REAL | hPa | 900 à 1080, sinon manquant |
| humidity_pct | REAL | % | 0 à 100, sinon manquant |
| wind_kmh | REAL | km/h | 0 à 250, sinon manquant |
| rain_3h_mm | REAL | mm | cumul des 3 h **précédant** le relevé ; 0 à 200 ; valeur négative (trace) ramenée à 0 |
| source | TEXT | — | `infoclimat`, `csv` ou `synthetic` |

## Table `daily_weather` (1 ligne par jour UTC, moyenne des stations)
| Colonne | Description |
|---|---|
| day | jour UTC |
| n_stations | stations ayant un cumul de pluie valide (≥ 6 relevés sur 8) |
| temp_mean_c / temp_min_c / temp_max_c | températures (min/max sur relevés tri-horaires) |
| pressure_mean_hpa, humidity_mean_pct, wind_mean_kmh | moyennes journalières |
| rain_mm | cumul régional moyen sur 24 h se terminant à 00 h UTC |
| rain_day | 1 si rain_mm ≥ seuil (1 mm par défaut), 0 sinon, vide si cumul invalide |

## Variables du modèle (jour cible D, informations ≤ D−1)
`doy_sin`, `doy_cos` (saisonnalité) ; `temp_mean_l1`, `temp_range_l1`, `pressure_l1`, `pressure_delta_1`,
`pressure_delta_3`, `humidity_l1`, `humidity_mean_3`, `wind_l1`, `rain_log_l1`, `rain_day_l1`, `rain_freq_7`,
`rain_mean_7`.

## Variables écartées (sobriété)
Nébulosité, visibilité, point de rosée, rafales, neige au sol, temps présent : redondantes avec les variables
retenues ou trop lacunaires sur les stations du périmètre ; elles ne sont ni téléchargées ni stockées.
