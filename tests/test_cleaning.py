import pandas as pd

from goutte_deau.cleaning import clean_observations, normalize_raw


def _raw(rows):
    cols = ["id_station", "dh_utc", "temperature", "pression", "humidite", "vent_moyen", "pluie_3h"]
    return pd.DataFrame(rows, columns=cols)


def test_normalize_renames_and_coerces():
    df = normalize_raw(_raw([["07015", "2024-01-01 00:00:00", "5.1", "1012.0", "80", "10", "0.0"]]))
    assert list(df.columns) == ["station_id", "obs_utc", "temperature_c", "pressure_hpa",
                                "humidity_pct", "wind_kmh", "rain_3h_mm"]
    assert df["temperature_c"].iloc[0] == 5.1


def test_missing_columns_become_nan():
    df = normalize_raw(pd.DataFrame({"id_station": ["07015"], "dh_utc": ["2024-01-01 00:00:00"],
                                     "temperature": [3.0]}))
    assert df["rain_3h_mm"].isna().all()


def test_out_of_range_set_to_nan_and_reported():
    df = normalize_raw(_raw([["07015", "2024-01-01 00:00:00", "99", "9999", "80", "10", "0"]]))
    clean, rep = clean_observations(df)
    assert pd.isna(clean["temperature_c"].iloc[0]) and pd.isna(clean["pressure_hpa"].iloc[0])
    assert rep.out_of_range == {"temperature_c": 1, "pressure_hpa": 1}


def test_off_grid_bad_timestamp_and_duplicates_dropped():
    df = normalize_raw(_raw([
        ["07015", "2024-01-01 00:00:00", 5, 1010, 80, 10, 0],
        ["07015", "2024-01-01 00:00:00", 6, 1011, 80, 10, 0],   # doublon -> garde le dernier
        ["07015", "2024-01-01 01:00:00", 5, 1010, 80, 10, 0],   # hors grille tri-horaire
        ["07015", "n'importe quoi", 5, 1010, 80, 10, 0],        # horodatage invalide
    ]))
    clean, rep = clean_observations(df)
    assert len(clean) == 1 and clean["temperature_c"].iloc[0] == 6
    assert (rep.dropped_duplicates, rep.dropped_off_grid, rep.dropped_bad_timestamp) == (1, 1, 1)
    assert rep.rows_rejected == 3


def test_negative_rain_is_trace_zero():
    df = normalize_raw(_raw([["07015", "2024-01-01 03:00:00", 5, 1010, 80, 10, -0.1]]))
    clean, _ = clean_observations(df)
    assert clean["rain_3h_mm"].iloc[0] == 0.0
