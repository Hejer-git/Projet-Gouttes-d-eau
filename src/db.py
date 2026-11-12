"""Base SQLite : schéma, écriture idempotente, lectures."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pandas as pd

from goutte_deau.config import STATION_CATALOG

SCHEMA = """
CREATE TABLE IF NOT EXISTS station (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    region    TEXT NOT NULL,
    latitude  REAL,
    longitude REAL
);

-- Observations tri-horaires nettoyées (aucune donnée brute inutilisée n'est conservée).
CREATE TABLE IF NOT EXISTS observation (
    station_id    TEXT NOT NULL REFERENCES station(id),
    obs_utc       TEXT NOT NULL,                 -- 'YYYY-MM-DD HH:MM:SS' (UTC)
    temperature_c REAL,
    pressure_hpa  REAL,
    humidity_pct  REAL,
    wind_kmh      REAL,
    rain_3h_mm    REAL,
    source        TEXT NOT NULL DEFAULT 'infoclimat'
                  CHECK (source IN ('infoclimat', 'csv', 'synthetic')),
    PRIMARY KEY (station_id, obs_utc)
) WITHOUT ROWID;

-- Agrégat journalier régional (1 ligne par jour UTC) : table d'entraînement et d'inférence.
CREATE TABLE IF NOT EXISTS daily_weather (
    day               TEXT PRIMARY KEY,          -- 'YYYY-MM-DD'
    n_stations        INTEGER NOT NULL,
    temp_mean_c       REAL,
    temp_min_c        REAL,
    temp_max_c        REAL,
    pressure_mean_hpa REAL,
    humidity_mean_pct REAL,
    wind_mean_kmh     REAL,
    rain_mm           REAL,
    rain_day          INTEGER CHECK (rain_day IN (0, 1))
);

-- Traçabilité des collectes (indicateurs de qualité des données).
CREATE TABLE IF NOT EXISTS collection_run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_utc     TEXT NOT NULL,
    source          TEXT NOT NULL,
    stations        TEXT NOT NULL,
    period_start    TEXT,
    period_end      TEXT,
    rows_fetched    INTEGER NOT NULL,
    rows_kept       INTEGER NOT NULL,
    rows_rejected   INTEGER NOT NULL,
    status          TEXT NOT NULL
);

-- Journal des prévisions servies (audit, suivi de dérive). Aucune donnée personnelle.
CREATE TABLE IF NOT EXISTS prediction_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_utc TEXT NOT NULL,
    target_day    TEXT NOT NULL,
    probability   REAL NOT NULL,
    mode          TEXT NOT NULL,
    model_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observation_time ON observation(obs_utc);
CREATE INDEX IF NOT EXISTS idx_prediction_target ON prediction_log(target_day);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO station (id, name, region, latitude, longitude) VALUES (?,?,?,?,?)",
        [(s.id, s.name, s.region, s.latitude, s.longitude) for s in STATION_CATALOG.values()],
    )
    conn.commit()


def _clean_value(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


def upsert_observations(conn: sqlite3.Connection, df: pd.DataFrame, source: str) -> int:
    """Insère ou met à jour les observations (idempotent : rejouer une collecte est sûr)."""
    if df.empty:
        return 0
    cols = ["station_id", "obs_utc", "temperature_c", "pressure_hpa",
            "humidity_pct", "wind_kmh", "rain_3h_mm"]
    rows = [tuple(_clean_value(v) for v in rec) + (source,)
            for rec in df[cols].itertuples(index=False, name=None)]
    # station inconnue du catalogue : enregistrée avec un libellé neutre (clé étrangère)
    conn.executemany(
        "INSERT OR IGNORE INTO station (id, name, region) VALUES (?, ?, 'non renseignée')",
        [(sid, sid) for sid in sorted(df["station_id"].astype(str).unique())],
    )
    conn.executemany(
        """
        INSERT INTO observation (station_id, obs_utc, temperature_c, pressure_hpa,
                                 humidity_pct, wind_kmh, rain_3h_mm, source)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(station_id, obs_utc) DO UPDATE SET
            temperature_c = excluded.temperature_c,
            pressure_hpa  = excluded.pressure_hpa,
            humidity_pct  = excluded.humidity_pct,
            wind_kmh      = excluded.wind_kmh,
            rain_3h_mm    = excluded.rain_3h_mm,
            source        = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def read_observations(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT station_id, obs_utc, temperature_c, pressure_hpa, humidity_pct, wind_kmh, "
        "rain_3h_mm, source FROM observation ORDER BY obs_utc, station_id",
        conn,
    )


def replace_daily(conn: sqlite3.Connection, daily: pd.DataFrame) -> int:
    """Remplace la table journalière (elle est entièrement dérivée des observations)."""
    cols = ["day", "n_stations", "temp_mean_c", "temp_min_c", "temp_max_c",
            "pressure_mean_hpa", "humidity_mean_pct", "wind_mean_kmh", "rain_mm", "rain_day"]
    out = daily.reset_index().copy()
    out["day"] = pd.to_datetime(out["day"]).dt.strftime("%Y-%m-%d")
    rows = [tuple(_clean_value(v) for v in rec)
            for rec in out[cols].itertuples(index=False, name=None)]
    with conn:
        conn.execute("DELETE FROM daily_weather")
        conn.executemany(
            f"INSERT INTO daily_weather ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            rows,
        )
    return len(rows)


def read_daily(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM daily_weather ORDER BY day", conn)
    if df.empty:
        return df.set_index(pd.DatetimeIndex([], name="day"))
    df["day"] = pd.to_datetime(df["day"])
    return df.set_index("day")


def log_collection_run(conn: sqlite3.Connection, **fields) -> None:
    keys = ["started_utc", "source", "stations", "period_start", "period_end",
            "rows_fetched", "rows_kept", "rows_rejected", "status"]
    with conn:
        conn.execute(
            f"INSERT INTO collection_run ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            [fields.get(k) for k in keys],
        )


def log_prediction(conn: sqlite3.Connection, requested_utc: str, target_day: str,
                   probability: float, mode: str, model_version: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO prediction_log (requested_utc, target_day, probability, mode, model_version)"
            " VALUES (?,?,?,?,?)",
            (requested_utc, target_day, probability, mode, model_version),
        )


def data_sources(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT source FROM observation ORDER BY 1")]
