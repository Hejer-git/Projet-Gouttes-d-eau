"""Indicateurs de qualité des données calculés depuis la base (affichés dans l'interface)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from goutte_deau import db

EXPECTED_OBS_PER_DAY_PER_STATION = 8


def data_quality(conn, stations: tuple[str, ...], today: date | None = None) -> dict:
    today = today or date.today()
    obs = db.read_observations(conn)
    daily = db.read_daily(conn)
    if obs.empty or daily.empty:
        return {"status": "empty"}
    n_days = (daily.index.max() - daily.index.min()).days + 1
    expected = n_days * EXPECTED_OBS_PER_DAY_PER_STATION * len(stations)
    measures = ["temperature_c", "pressure_hpa", "humidity_pct", "wind_kmh", "rain_3h_mm"]
    runs = pd.read_sql_query("SELECT rows_fetched, rows_rejected FROM collection_run", conn)
    fetched, rejected = int(runs["rows_fetched"].sum()), int(runs["rows_rejected"].sum())
    last = daily.index.max().date()
    return {
        "status": "ok",
        "period": [str(daily.index.min().date()), str(last)],
        "completeness_obs_pct": round(100 * len(obs) / expected, 1),
        "missing_values_pct": {m: round(100 * float(obs[m].isna().mean()), 2) for m in measures},
        "valid_target_days_pct": round(100 * float(daily["rain_day"].notna().mean()), 1),
        "rejected_rows_pct": round(100 * rejected / fetched, 2) if fetched else None,
        "freshness_days": (today - last).days,
        "rain_day_rate": round(float(daily["rain_day"].mean()), 3),
        "sources": db.data_sources(conn),
    }


def write_data_quality(conn, stations, report_dir: str | Path) -> dict:
    q = data_quality(conn, stations)
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    (Path(report_dir) / "data_quality.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
    return q
