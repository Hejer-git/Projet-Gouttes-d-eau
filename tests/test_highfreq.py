import pathlib

import numpy as np
import pandas as pd

from goutte_deau import collector
from goutte_deau.daily import aggregate_daily
from goutte_deau.cleaning import clean_observations
from goutte_deau.highfreq import rain_increments, standardize


def _station(cumul, start="2025-06-01 00:00:00", freq="10min", sid="ME098"):
    t = pd.date_range(start, periods=len(cumul), freq=freq)
    return pd.DataFrame({"station_id": sid, "dh_utc": t.strftime("%Y-%m-%d %H:%M:%S"),
                         "temperature": 15.0, "pression": 1010.0, "humidite": 80.0, "vent_moyen": 5.0,
                         "pluie_cumul_0h": cumul})


def test_increments_handle_reset():
    idx = pd.date_range("2025-06-01", periods=6, freq="10min")
    c = pd.Series([0.0, 1.0, 3.0, 0.0, 0.5, 0.5], index=idx)   # remise à zéro entre le 3e et le 4e relevé
    inc = rain_increments(c)
    assert inc.iloc[1] == 1.0 and inc.iloc[2] == 2.0 and inc.iloc[3] == 0.0 and inc.iloc[4] == 0.5


def test_gap_does_not_create_phantom_rain():
    idx = pd.DatetimeIndex(["2025-06-01 00:00", "2025-06-01 00:10", "2025-06-01 05:00"])
    inc = rain_increments(pd.Series([0.0, 0.0, 20.0], index=idx))
    assert np.isnan(inc.iloc[2])      # 20 mm « apparus » pendant un trou de 5 h : non attribuables


def test_three_hourly_rain_is_sum_of_increments():
    # 37 relevés de 10 min (00h00 -> 06h00) ; 0,2 mm à chaque relevé -> 3,6 mm par fenêtre de 3 h
    cumul = np.round(np.arange(37) * 0.2, 1)
    out = standardize(_station(cumul))
    assert list(out.columns)[:2] == ["station_id", "obs_utc"] and len(out) == 3   # 00h, 03h, 06h
    assert out["rain_3h_mm"].iloc[1] == 3.6 and out["rain_3h_mm"].iloc[2] == 3.6
    assert np.isnan(out["rain_3h_mm"].iloc[0])        # pas de relevés avant 00h : fenêtre vide


def test_non_highfreq_station_untouched():
    raw = pd.DataFrame({"id_station": ["07156"] * 3,
                        "dh_utc": ["2025-06-01 00:00:00", "2025-06-01 03:00:00", "2025-06-01 06:00:00"],
                        "temperature": [10, 11, 12], "pluie_3h": [0.0, 1.2, 0.0]})
    out = standardize(raw)
    assert out["rain_3h_mm"].tolist() == [0.0, 1.2, 0.0]


def test_real_rainy_day_amateur_station():
    """Fixture réelle ME098 : ~26 mm le 25 juin 2025 (somme des incréments du cumul)."""
    raw = collector.load_csv(pathlib.Path(__file__).parent / "data" / "me098_rain_sample.csv")
    canon = standardize(raw)
    clean, _ = clean_observations(canon)
    d = aggregate_daily(clean, 1.0, min_obs_per_day=6)
    assert 24.0 <= d.loc["2025-06-25", "rain_mm"] <= 28.0 and d.loc["2025-06-25", "rain_day"] == 1
