import numpy as np
import pandas as pd

from goutte_deau.cleaning import clean_observations, normalize_raw
from goutte_deau.daily import aggregate_daily
from goutte_deau.features import CORE_OBS, OBS_FEATURES, build_feature_table, features_for_day


def _obs(day, rain_per_slot, n_slots=8, station="07015"):
    rows = []
    for h in range(0, 24, 3)[:n_slots]:
        rows.append([station, f"{day} {h:02d}:00:00", 10.0, 1010.0, 80.0, 12.0, rain_per_slot])
    return rows


def _daily_from(rows):
    cols = ["id_station", "dh_utc", "temperature", "pression", "humidite", "vent_moyen", "pluie_3h"]
    clean, _ = clean_observations(normalize_raw(pd.DataFrame(rows, columns=cols)))
    return aggregate_daily(clean, rain_threshold_mm=1.0)


def test_rain_day_threshold():
    # 7 relevés (03..21 h) par jour : 7 x 0.2 = 1.4 mm (>= 1) et 7 x 0.05 = 0.35 mm (< 1)
    d = _daily_from(_obs("2024-01-01", 0.2) + _obs("2024-01-02", 0.05))
    assert d.loc["2024-01-01", "rain_day"] == 1 and d.loc["2024-01-02", "rain_day"] == 0


def test_midnight_observation_belongs_to_previous_day():
    # Le relevé de 00 h UTC cumule les 3 h précédentes : il compte pour la veille.
    rows = _obs("2024-01-01", 0.0) + [["07015", "2024-01-02 00:00:00", 10.0, 1010.0, 80.0, 12.0, 5.0]]
    d = _daily_from(rows)
    assert d.loc["2024-01-01", "rain_mm"] == 5.0


def test_incomplete_day_has_no_rain_target():
    d = _daily_from(_obs("2024-01-01", 1.0, n_slots=5))  # < 6 relevés
    assert np.isnan(d.loc["2024-01-01", "rain_day"])


def test_regional_mean_over_stations():
    d = _daily_from(_obs("2024-01-01", 0.5, station="07015") + _obs("2024-01-01", 0.0, station="07005"))
    assert d.loc["2024-01-01", "rain_mm"] == 1.75 and d.loc["2024-01-01", "n_stations"] == 2  # (3.5 + 0) / 2


def _long_daily(n=40, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", name="day")
    return pd.DataFrame({
        "n_stations": 2, "temp_mean_c": rng.normal(10, 3, n), "temp_min_c": 5.0, "temp_max_c": 15.0,
        "pressure_mean_hpa": rng.normal(1013, 6, n), "humidity_mean_pct": rng.normal(75, 8, n),
        "wind_mean_kmh": rng.normal(14, 3, n), "rain_mm": rng.gamma(1, 2, n),
        "rain_day": (rng.random(n) < 0.3).astype(float)}, index=idx)


def test_no_leakage_features_ignore_target_day():
    daily = _long_daily()
    day = pd.Timestamp("2024-02-05")
    before = build_feature_table(daily).loc[day, OBS_FEATURES]
    tampered = daily.copy()
    tampered.loc[day, ["pressure_mean_hpa", "humidity_mean_pct", "rain_mm", "rain_day",
                       "temp_mean_c", "wind_mean_kmh"]] = [900, 1, 500, 1, -30, 200]
    after = build_feature_table(tampered).loc[day, OBS_FEATURES]
    pd.testing.assert_series_equal(before, after)


def test_features_for_day_modes():
    daily = _long_daily()
    last = daily.index.max()
    _, ok_next = features_for_day(daily, last + pd.Timedelta(days=1))
    _, ok_far = features_for_day(daily, last + pd.Timedelta(days=10))
    _, ok_before = features_for_day(daily, pd.Timestamp("2010-06-01"))
    assert ok_next is True and ok_far is False and ok_before is False
    assert set(CORE_OBS) <= set(OBS_FEATURES)
