"""Interface Streamlit de démonstration (consomme l'API)."""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("GD_API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("GD_API_KEY")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
ICONS = {"low": "🟢", "moderate": "🟠", "high": "🔴"}

st.set_page_config(page_title="Goutte d'eau — risque de pluie", page_icon="💧", layout="centered")


def api_get(path: str, **params):
    r = requests.get(f"{API_URL}{path}", params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300, show_spinner=False)
def cached_get(path: str, **params):
    return api_get(path, **params)


st.title("💧 Goutte d'eau")
st.write("Estimation du **risque de pluie** (au moins 1 mm sur la journée) pour une date, "
         "sur la région couverte par le MVP.")

try:
    health = cached_get("/health")
    model = cached_get("/v1/model")
except requests.RequestException:
    st.error("L'API n'est pas joignable. Lancez-la avec `python -m goutte_deau serve` puis rechargez la page.")
    st.stop()

if not model["representative"]:
    st.warning("**Mode démonstration** : le modèle est entraîné sur des données synthétiques. "
               "Les résultats illustrent le fonctionnement, pas la météo réelle.")

tab_pred, tab_hist, tab_model = st.tabs(["Prévision", "Historique", "Modèle et qualité"])

with tab_pred:
    chosen = st.date_input("Date à estimer", value=date.today() + timedelta(days=1),
                           min_value=date(2000, 1, 1), max_value=date.today() + timedelta(days=365),
                           help="Format JJ/MM/AAAA")
    if st.button("Estimer le risque de pluie", type="primary"):
        try:
            res = api_get("/v1/predict", date=chosen.isoformat())
        except requests.HTTPError as exc:
            st.error(f"Estimation impossible : {exc.response.json().get('detail', exc)}")
        else:
            pct = round(res["probability"] * 100)
            st.metric("Probabilité de pluie", f"{pct} %")
            st.progress(res["probability"], text=f"{ICONS[res['risk_level']]} {res['risk_label']}")
            if res["mode"] == "observations":
                st.caption("Basée sur la météo observée la veille (pression, humidité, pluie récente).")
            else:
                st.caption("Date éloignée des dernières observations : estimation saisonnière "
                           "(climatologie), moins précise.")
            if res["observed_rain_mm"] is not None:
                st.info(f"Cumul réellement observé ce jour-là : {res['observed_rain_mm']:.1f} mm.")
            st.caption(res["disclaimer"])

with tab_hist:
    days = st.slider("Nombre de jours affichés", 7, 120, 30)
    hist = pd.DataFrame(cached_get("/v1/history", days=days))
    if hist.empty:
        st.info("Aucune donnée disponible.")
    else:
        hist["day"] = pd.to_datetime(hist["day"])
        st.bar_chart(hist.set_index("day")["rain_mm"], y_label="Pluie (mm)", x_label="Jour")
        st.caption("Graphique : cumul quotidien de pluie moyen sur la région. "
                   "Le tableau ci-dessous contient les mêmes données.")
        st.dataframe(hist.rename(columns={
            "day": "Jour", "rain_mm": "Pluie (mm)", "rain_day": "Jour de pluie (1=oui)",
            "temp_mean_c": "Température moyenne (°C)", "pressure_mean_hpa": "Pression (hPa)"}),
            hide_index=True, use_container_width=True)

with tab_model:
    m = model["test_metrics"]
    sel, clim = m["selected_model"], m["climatology_baseline"]
    st.write(f"Modèle **{model['selected_model']}** — version `{model['model_version']}` — "
             f"données : **{model['data_source']}** ({model['data_period'][0]} → {model['data_period'][1]}).")
    table = pd.DataFrame({
        "Indicateur": ["ROC-AUC", "Score de Brier (plus bas = mieux)", "F1", "Exactitude"],
        "Modèle": [sel["roc_auc"], sel["brier"], sel["f1"], sel["accuracy"]],
        "Climatologie (référence)": [clim["roc_auc"], clim["brier"], clim["f1"], clim["accuracy"]],
    })
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.write(f"Gain de Brier vs climatologie : **{m['brier_skill_score_vs_climatology']}** "
             "(positif = le modèle fait mieux).")
    eco = model["eco"]
    st.caption(f"Éco-conception : entraînement en {eco['training_wall_s']} s, "
               f"≈ {eco['estimated_energy_wh']} Wh estimés, sans deep learning.")
    st.caption(f"API v{health['api_version']} — dernière observation : {health['last_observation_day']}.")
