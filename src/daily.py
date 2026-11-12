"""Agrégation journalière régionale à partir des observations tri-horaires."""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_OBS_PER_DAY = 6  # sur 8 observations tri-horaires possibles


def aggregate_daily(obs: pd.DataFrame, rain_threshold_mm: float = 1.0,
                    min_obs_per_day: int = MIN_OBS_PER_DAY) -> pd.DataFrame:
    """Table journalière régionale ; jour de pluie = cumul moyen des stations >= seuil."""
    cols = ["n_stations", "temp_mean_c", "temp_min_c", "temp_max_c", "pressure_mean_hpa",
            "humidity_mean_pct", "wind_mean_kmh", "rain_mm", "rain_day"]
    if obs.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="day"))

    df = obs.copy()
    ts = pd.to_datetime(df["obs_utc"], utc=True)
    df["day"] = ts.dt.normalize().dt.tz_localize(None)
    # le cumul 3 h porte sur les 3 heures précédentes : le relevé de 00 h UTC compte pour la veille
    df["rain_day_key"] = (ts - pd.Timedelta(minutes=1)).dt.normalize().dt.tz_localize(None)

    g = df.groupby(["station_id", "day"])
    inst = pd.DataFrame({
        "temp_mean_c": g["temperature_c"].mean(),
        "temp_min_c": g["temperature_c"].min(),
        "temp_max_c": g["temperature_c"].max(),
        "pressure_mean_hpa": g["pressure_hpa"].mean(),
        "humidity_mean_pct": g["humidity_pct"].mean(),
        "wind_mean_kmh": g["wind_kmh"].mean(),
    })
    gr = df.groupby(["station_id", "rain_day_key"])["rain_3h_mm"]
    rain = pd.DataFrame({"rain_sum": gr.sum(min_count=1), "rain_cnt": gr.count()})
    rain.index = rain.index.set_names(["station_id", "day"])
    per_station = inst.join(rain, how="outer")
    per_station["rain_cnt"] = per_station["rain_cnt"].fillna(0)
    per_station.loc[per_station["rain_cnt"] < min_obs_per_day, "rain_sum"] = np.nan

    r = per_station.groupby("day")
    daily = pd.DataFrame({
        "n_stations": r["rain_sum"].count(),
        "temp_mean_c": r["temp_mean_c"].mean(),
        "temp_min_c": r["temp_min_c"].mean(),
        "temp_max_c": r["temp_max_c"].mean(),
        "pressure_mean_hpa": r["pressure_mean_hpa"].mean(),
        "humidity_mean_pct": r["humidity_mean_pct"].mean(),
        "wind_mean_kmh": r["wind_mean_kmh"].mean(),
        "rain_mm": r["rain_sum"].mean(),
    })
    daily["rain_day"] = np.where(daily["rain_mm"].isna(), np.nan,
                                 (daily["rain_mm"] >= rain_threshold_mm).astype(float))
    daily["n_stations"] = daily["n_stations"].astype(int)
    daily.index.name = "day"
    return daily[cols].round(3)
