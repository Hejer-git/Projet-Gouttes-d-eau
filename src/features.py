"""Variables explicatives : le jour D n'utilise que des observations antérieures ou égales à D-1."""
from __future__ import annotations

import numpy as np
import pandas as pd

CALENDAR_FEATURES = ["doy_sin", "doy_cos"]
OBS_FEATURES = [
    *CALENDAR_FEATURES,
    "temp_mean_l1", "temp_range_l1", "pressure_l1", "pressure_delta_1", "pressure_delta_3",
    "humidity_l1", "humidity_mean_3", "wind_l1", "rain_log_l1", "rain_day_l1",
    "rain_freq_7", "rain_mean_7",
]
CORE_OBS = ["pressure_l1", "rain_day_l1"]  # indispensables pour le mode « observations »
TARGET = "rain_day"


def calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    angle = 2 * np.pi * (index.day_of_year.to_numpy() - 1) / 365.25
    return pd.DataFrame({"doy_sin": np.sin(angle), "doy_cos": np.cos(angle)}, index=index)


def build_feature_table(daily: pd.DataFrame, until: pd.Timestamp | None = None) -> pd.DataFrame:
    """Table de variables indexée par jour cible D (calendrier continu, jusqu'à `until`)."""
    if daily.empty:
        return pd.DataFrame(columns=[*OBS_FEATURES, TARGET])
    last = max(daily.index.max(), until) if until is not None else daily.index.max()
    cal = pd.date_range(daily.index.min(), last, freq="D", name="day")
    d = daily.reindex(cal)

    f = calendar_features(cal)
    f["temp_mean_l1"] = d["temp_mean_c"].shift(1)
    f["temp_range_l1"] = (d["temp_max_c"] - d["temp_min_c"]).shift(1)
    f["pressure_l1"] = d["pressure_mean_hpa"].shift(1)
    f["pressure_delta_1"] = d["pressure_mean_hpa"].shift(1) - d["pressure_mean_hpa"].shift(2)
    f["pressure_delta_3"] = d["pressure_mean_hpa"].shift(1) - d["pressure_mean_hpa"].shift(4)
    f["humidity_l1"] = d["humidity_mean_pct"].shift(1)
    f["humidity_mean_3"] = d["humidity_mean_pct"].shift(1).rolling(3, min_periods=2).mean()
    f["wind_l1"] = d["wind_mean_kmh"].shift(1)
    f["rain_log_l1"] = np.log1p(d["rain_mm"].shift(1))
    f["rain_day_l1"] = d["rain_day"].shift(1)
    f["rain_freq_7"] = d["rain_day"].shift(1).rolling(7, min_periods=4).mean()
    f["rain_mean_7"] = d["rain_mm"].shift(1).rolling(7, min_periods=4).mean()
    f[TARGET] = d["rain_day"]
    return f


def training_frames(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Renvoie (jeu « observations », jeu « climatologie »), cible non manquante."""
    f = build_feature_table(daily)
    f = f[f[TARGET].notna()]
    obs = f.dropna(subset=CORE_OBS)
    return obs[[*OBS_FEATURES, TARGET]], f[[*CALENDAR_FEATURES, TARGET]]


def features_for_day(daily: pd.DataFrame, day: pd.Timestamp) -> tuple[pd.Series, bool]:
    """Variables pour un jour cible ; bool = True si le mode « observations » est possible."""
    f = build_feature_table(daily, until=day)
    if day not in f.index:  # date antérieure aux données
        row = calendar_features(pd.DatetimeIndex([day]))
        return row.iloc[0], False
    row = f.loc[day, OBS_FEATURES]
    return row, bool(row[CORE_OBS].notna().all())
