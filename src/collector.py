"""Collecte des observations Infoclimat : API open data (CSV, version 2) ou export CSV du site."""
from __future__ import annotations

import gzip
import io
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

LOG = logging.getLogger(__name__)
API_URL = "https://www.infoclimat.fr/opendata/"
API_VERSION = "2"
CHUNK_DAYS = 7          # l'API limite la durée d'une requête
PAUSE_S = 1.0           # pause entre deux requêtes


class CollectorError(RuntimeError):
    pass


def _mask(text: str, token: str | None) -> str:
    return text.replace(token, "***") if token else text


def iter_periods(start: date, end: date, chunk_days: int = CHUNK_DAYS):
    """Découpe [start, end] en fenêtres de `chunk_days` jours maximum."""
    if end < start:
        raise ValueError("La date de fin précède la date de début.")
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=chunk_days - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def parse_csv_text(text: str) -> pd.DataFrame:
    """Lit un export Infoclimat : lignes « # » ignorées, séparateur « ; », ligne d'unités supprimée."""
    lines = [ln for ln in text.splitlines(keepends=True) if not ln.startswith("#")]
    if not lines:
        return pd.DataFrame()
    sep = ";" if ";" in lines[0] else ","
    df = pd.read_csv(io.StringIO("".join(lines)), sep=sep, dtype=str)
    if "dh_utc" in df.columns:
        df = df[df["dh_utc"] != "YYYY-MM-DD hh:mm:ss"].reset_index(drop=True)
    return df


def load_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return parse_csv_text(f.read())


def fetch_period(session: requests.Session, stations: list[str], start: date, end: date,
                 token: str, retries: int = 3, timeout: float = 30.0) -> pd.DataFrame:
    params = [("version", API_VERSION), ("method", "get"), ("format", "csv")]
    params += [("stations[]", s) for s in stations]
    params += [("start", start.isoformat()), ("end", end.isoformat()), ("token", token)]
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = session.get(API_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            if "dh_utc" not in resp.text[:5000]:
                # erreur d'authentification : texte brut, HTTP 200 (ex. « Wrong ip address »)
                body = _mask(resp.text.strip()[:120], token)
                raise CollectorError(
                    f"Réponse inattendue de l'API : « {body} ». Vérifiez le jeton et que l'adresse IP "
                    "de cette machine est bien celle associée au jeton.")
            return parse_csv_text(resp.text)
        except CollectorError as exc:
            raise CollectorError(_mask(str(exc), token)) from None
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            LOG.warning("Échec collecte %s->%s (essai %d/%d) : %s",
                        start, end, attempt + 1, retries, _mask(str(exc), token))
            time.sleep(2 ** attempt)
    raise CollectorError(_mask(f"Collecte impossible {start}->{end} : {last_exc}", token))


def fetch_range(stations: list[str], start: date, end: date, token: str | None,
                chunk_days: int = CHUNK_DAYS, session: requests.Session | None = None) -> pd.DataFrame:
    if not token:
        raise CollectorError("INFOCLIMAT_TOKEN absent : définissez-le ou utilisez --csv avec un export.")
    session = session or requests.Session()
    frames = []
    for p_start, p_end in iter_periods(start, end, chunk_days):
        LOG.info("Collecte %s -> %s", p_start, p_end)
        frames.append(fetch_period(session, stations, p_start, p_end, token))
        time.sleep(PAUSE_S)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
