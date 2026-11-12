"""Inférence : charge les modèles et produit une probabilité de pluie pour une date."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import joblib
import pandas as pd

from goutte_deau import db
from goutte_deau.features import CALENDAR_FEATURES, OBS_FEATURES, calendar_features, features_for_day

MIN_DATE = date(1990, 1, 1)
MAX_HORIZON_DAYS = 366

RISK_LABELS_FR = {"low": "Risque faible", "moderate": "Risque modéré", "high": "Risque élevé"}


class ModelNotAvailable(RuntimeError):
    pass


@dataclass
class Prediction:
    target_day: date
    probability: float
    risk_level: str
    risk_label: str
    mode: str                      # "observations" | "climatologie"
    model_version: str
    data_source: str
    last_observation_day: date | None
    observed_rain_mm: float | None = None
    inputs: dict[str, float] = field(default_factory=dict)


def risk_level(p: float, thresholds: dict) -> str:
    if p < thresholds["low_below"]:
        return "low"
    if p >= thresholds["high_from"]:
        return "high"
    return "moderate"


class Predictor:
    def __init__(self, model_obs, model_clim, metadata: dict):
        self.model_obs, self.model_clim, self.metadata = model_obs, model_clim, metadata

    @classmethod
    def load(cls, model_dir: str | Path) -> "Predictor":
        model_dir = Path(model_dir)
        files = [model_dir / n for n in ("model_obs.joblib", "model_clim.joblib", "metadata.json")]
        if not all(f.exists() for f in files):
            raise ModelNotAvailable(f"Modèle introuvable dans {model_dir}. Lancez : "
                                    "python -m goutte_deau train")
        # joblib (pickle) : ne charger que des modèles produits par ce projet
        return cls(joblib.load(files[0]), joblib.load(files[1]),
                   json.loads(files[2].read_text(encoding="utf-8")))

    @property
    def version(self) -> str:
        return self.metadata["model_version"]

    def predict(self, conn, day: date) -> Prediction:
        if not (MIN_DATE <= day <= date.today() + timedelta(days=MAX_HORIZON_DAYS)):
            raise ValueError(f"Date hors plage ({MIN_DATE} → +{MAX_HORIZON_DAYS} jours).")
        daily = db.read_daily(conn)
        ts = pd.Timestamp(day)
        row, obs_ok = features_for_day(daily, ts)

        if obs_ok:
            X = pd.DataFrame([row[OBS_FEATURES].astype(float)])
            p = float(self.model_obs.predict_proba(X)[0, 1])
            mode = "observations"
            inputs = {k: round(float(row[k]), 2) for k in
                      ("pressure_l1", "pressure_delta_1", "humidity_l1", "rain_day_l1", "rain_freq_7")
                      if pd.notna(row[k])}
        else:
            X = calendar_features(pd.DatetimeIndex([ts]))[CALENDAR_FEATURES]
            p = float(self.model_clim.predict_proba(X)[0, 1])
            mode, inputs = "climatologie", {}

        observed = None
        if not daily.empty and ts in daily.index and pd.notna(daily.loc[ts, "rain_mm"]):
            observed = float(daily.loc[ts, "rain_mm"])
        lvl = risk_level(p, self.metadata["risk_thresholds"])
        return Prediction(
            target_day=day, probability=round(p, 4), risk_level=lvl, risk_label=RISK_LABELS_FR[lvl],
            mode=mode, model_version=self.version, data_source=self.metadata["data_source"],
            last_observation_day=None if daily.empty else daily.index.max().date(),
            observed_rain_mm=observed, inputs=inputs)
