"""Orchestration : collecte -> nettoyage -> stockage -> agrégation journalière."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from goutte_deau import collector, db, synthetic
from goutte_deau.cleaning import clean_observations
from goutte_deau.config import Settings
from goutte_deau.daily import aggregate_daily
from goutte_deau.highfreq import standardize

LOG = logging.getLogger(__name__)


def ingest(settings: Settings, raw: pd.DataFrame, source: str, period: tuple[str, str] | None = None) -> dict:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    canon = standardize(raw)
    clean, report = clean_observations(canon)
    with db.connect(settings.db_path) as conn:
        db.init_db(conn)
        db.upsert_observations(conn, clean, source=source)
        daily = aggregate_daily(db.read_observations(conn), settings.rain_threshold_mm)
        n_days = db.replace_daily(conn, daily)
        db.log_collection_run(
            conn, started_utc=started, source=source, stations=",".join(settings.stations),
            period_start=period[0] if period else None, period_end=period[1] if period else None,
            rows_fetched=report.rows_in, rows_kept=report.rows_out,
            rows_rejected=report.rows_rejected, status="ok")
    summary = {**report.as_dict(), "daily_rows": n_days, "source": source}
    LOG.info("Ingestion terminée : %s", summary)
    return summary


def collect_infoclimat(settings: Settings, start: date, end: date) -> dict:
    raw = collector.fetch_range(list(settings.stations), start, end, settings.infoclimat_token)
    return ingest(settings, raw, "infoclimat", (start.isoformat(), end.isoformat()))


def collect_csv(settings: Settings, paths) -> dict:
    """Un ou plusieurs exports CSV Infoclimat (fusionnés ; doublons aux jonctions éliminés)."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    frames = [f for f in (collector.load_csv(p) for p in paths) if not f.empty]
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return ingest(settings, raw, "csv")


def collect_synthetic(settings: Settings, start: str, end: str, seed: int = 42) -> dict:
    raw = synthetic.generate(start, end, tuple(settings.stations), seed)
    return ingest(settings, raw, "synthetic", (start, end))
