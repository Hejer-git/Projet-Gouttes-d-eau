"""Données synthétiques (tests et démonstration uniquement ; ne reflètent aucune mesure)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from goutte_deau.cleaning import CANON_COLUMNS


def generate(start: str = "2018-01-01", end: str = "2024-12-31",
             stations: tuple[str, ...] = ("07156",), seed: int = 42,
             inject_defects: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    n = len(days)
    doy = days.day_of_year.to_numpy()
    season = np.cos(2 * np.pi * (doy - 15) / 365.25)  # +1 en hiver, -1 en été

    # pression et humidité de régime : processus autorégressifs
    a = np.zeros(n)
    w = np.zeros(n)
    for t in range(1, n):
        a[t] = 0.75 * a[t - 1] + rng.normal(0, 6.0)
        w[t] = 0.6 * w[t - 1] + rng.normal(0, 1.0)
    da = np.diff(a, prepend=a[0])

    logit = -1.0 + 0.35 * season - 1.2 * (a / 9.0) - 0.45 * (da / 6.0) + 0.55 * w
    p_rain = 1 / (1 + np.exp(-logit))
    rain_day = rng.random(n) < p_rain
    amount = np.where(rain_day, 1.0 + rng.gamma(0.9, 4.0, n), 0.0)
    drizzle = (~rain_day) & (rng.random(n) < 0.15)
    amount = np.where(drizzle, rng.uniform(0.1, 0.8, n), amount)

    pressure = 1015.0 + a
    humidity = np.clip(76 - 0.45 * a + 9 * rain_day + 4 * season + rng.normal(0, 5, n), 35, 100)
    temp = 11.5 - 8.5 * np.cos(2 * np.pi * (doy - 20) / 365.25) + 0.12 * a + rng.normal(0, 2.2, n)
    wind = np.clip(14 - 0.25 * a + 5 * rain_day + rng.normal(0, 3.5, n), 0, None)

    rows = []
    hours = np.arange(0, 24, 3)
    for k, sid in enumerate(stations):
        st_off_t = rng.normal(0, 0.4)
        st_rain = rng.lognormal(0, 0.2, n)
        slots_all = np.zeros((n, 8))  # fenêtre k : 3 h se terminant à 3*(k+1) h (la 8e finit à 24 h)
        for i in range(n):
            total = amount[i] * st_rain[i]
            if total > 0:
                m = rng.integers(1, 5)
                idx = rng.choice(8, size=m, replace=False)
                slots_all[i, idx] = rng.dirichlet(np.ones(m)) * total
        for i, day in enumerate(days):
            for j, h in enumerate(hours):
                # le relevé de 00 h porte sur les 3 h de la veille
                rain_val = slots_all[i - 1, 7] if (j == 0 and i > 0) else (0.0 if j == 0 else slots_all[i, j - 1])
                diur = np.sin(2 * np.pi * (h - 9) / 24)
                rows.append((
                    sid,
                    (day + pd.Timedelta(hours=int(h))).strftime("%Y-%m-%d %H:%M:%S"),
                    round(temp[i] + st_off_t + 3.0 * diur + rng.normal(0, 0.5), 1),
                    round(pressure[i] + rng.normal(0, 0.8) + 0.4 * k, 1),
                    round(float(np.clip(humidity[i] - 8 * diur + rng.normal(0, 3), 20, 100)), 0),
                    round(max(0.0, wind[i] + rng.normal(0, 2.0)), 1),
                    round(float(rain_val), 1),
                ))
    df = pd.DataFrame(rows, columns=CANON_COLUMNS)

    if inject_defects:  # pour exercer les règles de nettoyage
        m = rng.random(len(df))
        for col in ["temperature_c", "pressure_hpa", "humidity_pct", "wind_kmh", "rain_3h_mm"]:
            df.loc[rng.random(len(df)) < 0.015, col] = np.nan
        df.loc[m < 0.0008, "pressure_hpa"] = 9999.0
        df.loc[(m > 0.5) & (m < 0.5008), "temperature_c"] = -99.0
        dup = df.sample(frac=0.002, random_state=seed)
        df = pd.concat([df, dup], ignore_index=True)
    return df
