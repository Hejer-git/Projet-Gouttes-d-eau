"""Normalisation et nettoyage des observations (5 variables, pas tri-horaire)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

# Colonnes Infoclimat -> noms du projet
RAW_TO_CANON = {
    "id_station": "station_id",  # JSON ; l'export CSV utilise déjà `station_id`
    "dh_utc": "obs_utc",
    "temperature": "temperature_c",
    "pression": "pressure_hpa",
    "humidite": "humidity_pct",
    "vent_moyen": "wind_kmh",
    "pluie_3h": "rain_3h_mm",
}
MEASURES = ["temperature_c", "pressure_hpa", "humidity_pct", "wind_kmh", "rain_3h_mm"]
CANON_COLUMNS = ["station_id", "obs_utc", *MEASURES]

# plages plausibles ; hors plage -> valeur manquante
VALID_RANGES = {
    "temperature_c": (-40.0, 50.0),
    "pressure_hpa": (900.0, 1080.0),
    "humidity_pct": (0.0, 100.0),
    "wind_kmh": (0.0, 250.0),
    "rain_3h_mm": (0.0, 200.0),
}


@dataclass
class CleaningReport:
    rows_in: int = 0
    rows_out: int = 0
    dropped_bad_timestamp: int = 0
    dropped_off_grid: int = 0
    dropped_duplicates: int = 0
    dropped_all_missing: int = 0
    out_of_range: dict[str, int] = field(default_factory=dict)

    @property
    def rows_rejected(self) -> int:
        return self.rows_in - self.rows_out

    def as_dict(self) -> dict:
        d = asdict(self)
        d["rows_rejected"] = self.rows_rejected
        return d


def normalize_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Renomme les colonnes brutes et force les types. Colonnes manquantes -> NaN."""
    df = raw.rename(columns=RAW_TO_CANON)
    for col in CANON_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    df = df[CANON_COLUMNS].copy()
    df["station_id"] = df["station_id"].astype("string").str.strip()
    for col in MEASURES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clean_observations(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Applique les règles de qualité et renvoie (données propres, rapport)."""
    report = CleaningReport(rows_in=len(df))
    out = df.copy()

    ts = pd.to_datetime(out["obs_utc"], utc=True, errors="coerce")
    bad = ts.isna() | out["station_id"].isna()
    report.dropped_bad_timestamp = int(bad.sum())
    out = out.loc[~bad].copy()
    out["obs_utc"] = ts.loc[~bad]

    # pas tri-horaire uniquement (00, 03, ..., 21 h UTC)
    on_grid = (out["obs_utc"].dt.hour % 3 == 0) & (out["obs_utc"].dt.minute == 0)
    report.dropped_off_grid = int((~on_grid).sum())
    out = out.loc[on_grid].copy()

    # pluie négative (trace) ramenée à 0
    out.loc[out["rain_3h_mm"] < 0, "rain_3h_mm"] = 0.0
    for col, (lo, hi) in VALID_RANGES.items():
        invalid = out[col].notna() & ~out[col].between(lo, hi)
        if invalid.any():
            report.out_of_range[col] = int(invalid.sum())
            out.loc[invalid, col] = np.nan

    empty = out[MEASURES].isna().all(axis=1)
    report.dropped_all_missing = int(empty.sum())
    out = out.loc[~empty].copy()

    before = len(out)
    out = out.drop_duplicates(subset=["station_id", "obs_utc"], keep="last")
    report.dropped_duplicates = before - len(out)

    out["obs_utc"] = out["obs_utc"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out["station_id"] = out["station_id"].astype(str)
    out = out.sort_values(["obs_utc", "station_id"]).reset_index(drop=True)
    report.rows_out = len(out)
    return out, report
