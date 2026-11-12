"""Modèles de données de l'API (validation et documentation OpenAPI automatiques)."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class PredictionOut(BaseModel):
    target_day: dt.date = Field(description="Jour demandé (UTC).")
    probability: float = Field(ge=0, le=1, description="Probabilité de jour de pluie (>= 1 mm).")
    risk_level: Literal["low", "moderate", "high"]
    risk_label: str = Field(description="Libellé en français, lisible sans dépendre de la couleur.")
    mode: Literal["observations", "climatologie"] = Field(
        description="`observations` : s'appuie sur la météo de la veille ; "
                    "`climatologie` : saisonnalité seule (date lointaine).")
    model_version: str
    data_source: str = Field(description="`infoclimat`, `csv`, `synthetic` ou `mixed`.")
    last_observation_day: dt.date | None
    observed_rain_mm: float | None = Field(
        default=None, description="Cumul observé si la date est dans le passé et connue.")
    inputs: dict[str, float] = Field(default_factory=dict, description="Variables clés utilisées.")
    disclaimer: str = ("Estimation statistique indicative sur un périmètre régional ; "
                       "ne remplace pas une prévision opérationnelle.")


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    model_loaded: bool
    data_source: str | None = None
    last_observation_day: dt.date | None = None
    api_version: str


class DailyPoint(BaseModel):
    day: dt.date
    rain_mm: float | None
    rain_day: int | None
    temp_mean_c: float | None
    pressure_mean_hpa: float | None


class ModelInfoOut(BaseModel):
    model_version: str
    selected_model: str
    data_source: str
    representative: bool
    data_period: list[str]
    test_period: list[str]
    test_metrics: dict
    eco: dict
