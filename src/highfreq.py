"""Stations à pas de 10 min : reconstruction des relevés tri-horaires, pluie issue du cumul `pluie_cumul_0h`."""
from __future__ import annotations

import numpy as np
import pandas as pd

from goutte_deau.cleaning import CANON_COLUMNS, normalize_raw

CUMUL_COL = "pluie_cumul_0h"
MIN_ROWS_PER_WINDOW = 9          # sur ~18 relevés de 10 min dans 3 h
MAX_GAP = pd.Timedelta("30min")  # au-delà, le cumul ne dit pas QUAND la pluie est tombée
MAX_INCREMENT_MM = 30.0          # incrément aberrant entre deux relevés consécutifs
TOLERANCE = pd.Timedelta("10min")
INSTANT = {"temperature": "temperature_c", "pression": "pressure_hpa",
           "humidite": "humidity_pct", "vent_moyen": "wind_kmh"}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _time_col(df: pd.DataFrame) -> str:
    return "dh_utc" if "dh_utc" in df.columns else "obs_utc"


def is_high_frequency(g: pd.DataFrame) -> bool:
    t = pd.to_datetime(g[_time_col(g)], utc=True, errors="coerce").dropna().sort_values()
    return len(t) > 2 and t.diff().median() < pd.Timedelta("30min")


def rain_increments(cumul: pd.Series) -> pd.Series:
    """Cumul (index temporel) -> pluie tombée depuis le relevé valide précédent."""
    c = cumul.dropna()
    inc = c.diff()
    reset = inc < 0
    inc[reset] = c[reset]
    inc[c.index.to_series().diff() > MAX_GAP] = np.nan
    inc[inc > MAX_INCREMENT_MM] = np.nan
    return inc


def to_three_hourly(g: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(g[_time_col(g)], utc=True, errors="coerce")
    df = (g.assign(_t=t).dropna(subset=["_t"]).sort_values("_t")
          .drop_duplicates("_t", keep="last").set_index("_t"))
    grid = pd.date_range(df.index.min().ceil("3h"), df.index.max().floor("3h"), freq="3h")
    out = pd.DataFrame(index=grid)
    for raw_col, canon in INSTANT.items():
        s = _num(df[raw_col]).dropna() if raw_col in df.columns else pd.Series(dtype=float)
        out[canon] = (s.reindex(grid, method="nearest", tolerance=TOLERANCE)
                      if not s.empty else np.nan)
    inc = rain_increments(_num(df[CUMUL_COL]))
    agg = inc.resample("3h", closed="right", label="right").agg(["sum", "count"]).reindex(grid)
    out["rain_3h_mm"] = agg["sum"].where(agg["count"] >= MIN_ROWS_PER_WINDOW)
    out["station_id"] = str(g["station_id"].iloc[0])
    out["obs_utc"] = grid
    return out[CANON_COLUMNS].reset_index(drop=True)


def standardize(raw: pd.DataFrame) -> pd.DataFrame:
    """Brut (API JSON, export CSV ou déjà canonique) -> tableau canonique tri-horaire."""
    if raw.empty:
        return normalize_raw(raw)
    raw = raw.rename(columns={"id_station": "station_id"})
    parts = []
    for _, g in raw.groupby("station_id", sort=False):
        if is_high_frequency(g) and CUMUL_COL in g.columns and _num(g[CUMUL_COL]).notna().any():
            parts.append(to_three_hourly(g))
        else:
            parts.append(normalize_raw(g))
    return pd.concat(parts, ignore_index=True)[CANON_COLUMNS]
