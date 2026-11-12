"""Configuration lue dans les variables d'environnement."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Station:
    """Station OMM (réseau RESO40, observations tri-horaires) utilisée par le MVP."""

    id: str
    name: str
    region: str
    latitude: float | None  # valeurs approximatives, à des fins de cartographie uniquement
    longitude: float | None


# Pilote : département 75 (Paris). 000EW = station amateur retenue ; 07156 = station officielle de référence.
STATION_CATALOG: dict[str, Station] = {
    "000EW": Station("000EW", "Paris 20e - Porte de Vincennes (station amateur Infoclimat)", "Paris (75)", None, None),
    "07156": Station("07156", "Paris-Montsouris", "Paris (75)", 48.82, 2.34),
    "ME098": Station("ME098", "ESPE Paris (station amateur)", "Paris (75)", None, None),
}


@dataclass(frozen=True)
class Settings:
    db_path: Path
    model_dir: Path
    report_dir: Path
    infoclimat_token: str | None
    stations: tuple[str, ...]
    rain_threshold_mm: float
    api_key: str | None
    cors_origins: tuple[str, ...]
    log_predictions: bool


def _split(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",") if v.strip())


def get_settings() -> Settings:
    """Relit l'environnement à chaque appel (pratique pour les tests)."""
    return Settings(
        db_path=Path(os.environ.get("GD_DB_PATH", ROOT / "data" / "goutte_deau.db")),
        model_dir=Path(os.environ.get("GD_MODEL_DIR", ROOT / "models")),
        report_dir=Path(os.environ.get("GD_REPORT_DIR", ROOT / "reports")),
        infoclimat_token=os.environ.get("INFOCLIMAT_TOKEN") or None,
        stations=_split(os.environ.get("GD_STATIONS", "000EW")),
        rain_threshold_mm=float(os.environ.get("GD_RAIN_THRESHOLD_MM", "1.0")),
        api_key=os.environ.get("GD_API_KEY") or None,
        cors_origins=_split(os.environ.get("GD_CORS_ORIGINS", "http://localhost:8501")),
        log_predictions=os.environ.get("GD_LOG_PREDICTIONS", "1") == "1",
    )
