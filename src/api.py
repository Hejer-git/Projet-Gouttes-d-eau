"""API FastAPI : estimation du risque de pluie pour une date."""
from __future__ import annotations

import datetime as dt
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from goutte_deau import __version__, db
from goutte_deau.config import get_settings
from goutte_deau.predictor import ModelNotAvailable, Predictor
from goutte_deau.schemas import DailyPoint, HealthOut, ModelInfoOut, PredictionOut

LOG = logging.getLogger("goutte_deau.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        app.state.predictor = Predictor.load(settings.model_dir)
        LOG.info("Modèle chargé : %s", app.state.predictor.version)
    except ModelNotAvailable as exc:
        app.state.predictor = None
        LOG.error("%s", exc)
    yield


app = FastAPI(
    title="Goutte d'eau — API de risque de pluie (MVP)",
    version=__version__,
    description="Estimation de la probabilité de pluie (>= 1 mm) pour une date, sur une région.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_methods=["GET"],
    allow_headers=["X-API-Key"],
)


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().api_key
    if expected is None:  # mode ouvert (développement)
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Clé d'API invalide ou absente.")


def _predictor(request: Request) -> Predictor:
    predictor = request.app.state.predictor
    if predictor is None:
        raise HTTPException(status_code=503, detail="Modèle indisponible : lancez l'entraînement.")
    return predictor


@app.get("/health", response_model=HealthOut, tags=["Supervision"])
def health(request: Request) -> HealthOut:
    predictor = request.app.state.predictor
    last = None
    try:
        with db.connect(get_settings().db_path) as conn:
            daily = db.read_daily(conn)
            last = None if daily.empty else daily.index.max().date()
    except Exception:  # supervision : ne jamais lever
        LOG.exception("Lecture de la base impossible")
    ok = predictor is not None and last is not None
    return HealthOut(status="ok" if ok else "degraded", model_loaded=predictor is not None,
                     data_source=predictor.metadata["data_source"] if predictor else None,
                     last_observation_day=last, api_version=__version__)


@app.get("/v1/predict", response_model=PredictionOut, tags=["Prévision"],
         dependencies=[Depends(require_api_key)])
def predict(request: Request,
            date: Annotated[dt.date, Query(description="Date au format AAAA-MM-JJ")]) -> PredictionOut:
    predictor = _predictor(request)
    settings = get_settings()
    try:
        with db.connect(settings.db_path) as conn:
            result = predictor.predict(conn, date)
            if settings.log_predictions:
                db.log_prediction(conn, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                  date.isoformat(), result.probability, result.mode,
                                  result.model_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PredictionOut(**result.__dict__)


@app.get("/v1/history", response_model=list[DailyPoint], tags=["Données"],
         dependencies=[Depends(require_api_key)])
def history(days: Annotated[int, Query(ge=1, le=366, description="Nombre de jours")] = 30
            ) -> list[DailyPoint]:
    with db.connect(get_settings().db_path) as conn:
        daily = db.read_daily(conn).tail(days)
    return [DailyPoint(day=i.date(), rain_mm=_f(r.rain_mm), rain_day=_i(r.rain_day),
                       temp_mean_c=_f(r.temp_mean_c), pressure_mean_hpa=_f(r.pressure_mean_hpa))
            for i, r in daily.iterrows()]


@app.get("/v1/model", response_model=ModelInfoOut, tags=["Modèle"],
         dependencies=[Depends(require_api_key)])
def model_info(request: Request) -> ModelInfoOut:
    m = _predictor(request).metadata
    return ModelInfoOut(**{k: m[k] for k in ModelInfoOut.model_fields})


def _f(v):
    return None if v != v else float(v)  # NaN -> None


def _i(v):
    return None if v != v else int(v)
