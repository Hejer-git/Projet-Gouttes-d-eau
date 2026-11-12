from datetime import date

import pandas as pd
import pytest
import requests

from goutte_deau import collector, db


def test_iter_periods_covers_range_without_overlap():
    periods = list(collector.iter_periods(date(2024, 1, 1), date(2024, 3, 15), chunk_days=30))
    assert periods[0][0] == date(2024, 1, 1) and periods[-1][1] == date(2024, 3, 15)
    for (_, e1), (s2, _) in zip(periods, periods[1:]):
        assert (s2 - e1).days == 1
    assert all((e - s).days < 30 for s, e in periods)


def test_iter_periods_rejects_inverted_range():
    with pytest.raises(ValueError):
        list(collector.iter_periods(date(2024, 2, 1), date(2024, 1, 1)))


def test_fetch_range_requires_token():
    with pytest.raises(collector.CollectorError, match="INFOCLIMAT_TOKEN"):
        collector.fetch_range(["07015"], date(2024, 1, 1), date(2024, 1, 2), token=None)


class _FailingSession:
    def get(self, *a, **k):
        raise requests.ConnectionError("boom https://x?token=SECRET123")


def test_token_never_leaks_in_errors(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda s: None)
    with pytest.raises(collector.CollectorError) as exc:
        collector.fetch_period(_FailingSession(), ["07015"], date(2024, 1, 1), date(2024, 1, 2),
                               token="SECRET123", retries=2)
    assert "SECRET123" not in str(exc.value)


def test_upsert_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    db.init_db(conn)
    df = pd.DataFrame([{"station_id": "07015", "obs_utc": "2024-01-01 00:00:00", "temperature_c": 5.0,
                        "pressure_hpa": 1010.0, "humidity_pct": 80.0, "wind_kmh": 10.0,
                        "rain_3h_mm": 0.0}])
    db.upsert_observations(conn, df, "csv")
    df["temperature_c"] = 6.0
    db.upsert_observations(conn, df, "csv")
    rows = conn.execute("SELECT temperature_c FROM observation").fetchall()
    assert len(rows) == 1 and rows[0][0] == 6.0
    conn.close()


class _Response:
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _TextSession:
    calls = 0

    def get(self, *args, **kwargs):
        _TextSession.calls += 1
        return _Response("Wrong ip address")


def test_auth_error_is_explicit_and_not_retried():
    with pytest.raises(collector.CollectorError, match="adresse IP"):
        collector.fetch_period(_TextSession(), ["07015"], date(2024, 1, 1), date(2024, 1, 2),
                               token="SECRET123", retries=3)
    assert _TextSession.calls == 1


def test_load_real_infoclimat_csv_export():
    """Fixture = extrait d'un vrai export Infoclimat (stations 000BV / 000EW, pas de 10 min)."""
    import pathlib
    from goutte_deau.cleaning import clean_observations, normalize_raw
    raw = collector.load_csv(pathlib.Path(__file__).parent / "data" / "export_infoclimat_sample.csv")
    assert len(raw) == 60 and "YYYY-MM-DD hh:mm:ss" not in set(raw["dh_utc"])
    canon = normalize_raw(raw)
    assert set(canon["station_id"]) == {"000BV", "000EW"}
    assert canon["temperature_c"].notna().all()
    clean, rep = clean_observations(canon)
    assert rep.dropped_off_grid > 0          # pas de 10 min : seuls les relevés « pile » 3 h sont gardés
    assert (pd.to_datetime(clean["obs_utc"]).dt.hour % 3 == 0).all()


def test_unknown_station_is_registered_not_rejected(tmp_path):
    conn = db.connect(tmp_path / "y.db")
    db.init_db(conn)
    df = pd.DataFrame([{"station_id": "000BV", "obs_utc": "2026-11-10 00:00:00", "temperature_c": 7.6,
                        "pressure_hpa": 1009.4, "humidity_pct": 93.0, "wind_kmh": 3.2, "rain_3h_mm": None}])
    assert db.upsert_observations(conn, df, "csv") == 1
    assert conn.execute("SELECT region FROM station WHERE id='000BV'").fetchone()[0] == "non renseignée"
    conn.close()


class _CsvSession:
    def __init__(self, text):
        self.text, self.params = text, None

    def get(self, url, params=None, timeout=None):
        self.params = params
        return _Response(self.text)


def test_fetch_period_requests_csv_v2_and_parses():
    import pathlib
    text = (pathlib.Path(__file__).parent / "data" / "export_infoclimat_sample.csv").read_text(encoding="utf-8")
    sess = _CsvSession(text)
    df = collector.fetch_period(sess, ["000BV"], date(2025, 1, 1), date(2025, 1, 7), token="SECRET123")
    p = dict((k, v) for k, v in sess.params)
    assert p["version"] == "2" and p["format"] == "csv" and p["stations[]"] == "000BV"
    assert len(df) == 60 and "station_id" in df.columns


def test_load_gzipped_csv(tmp_path):
    import gzip
    import pathlib
    src = pathlib.Path(__file__).parent / "data" / "export_infoclimat_sample.csv"
    gz = tmp_path / "export.csv.gz"
    gz.write_bytes(gzip.compress(src.read_bytes()))
    assert len(collector.load_csv(gz)) == len(collector.load_csv(src)) == 60
