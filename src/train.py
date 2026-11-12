"""Entraînement, sélection (validation croisée temporelle) et évaluation de trois modèles légers."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from goutte_deau import __version__, db
from goutte_deau.evaluate import (brier_skill_score, classification_metrics, plot_evaluation,
                                  reliability_table)
from goutte_deau.features import (CALENDAR_FEATURES, OBS_FEATURES, TARGET, calendar_features,
                                  training_frames)

LOG = logging.getLogger(__name__)

# hypothèses de l'estimation d'énergie (ordre de grandeur)
ASSUMED_CPU_POWER_W = 15.0          # portable, charge CPU mono-cœur à quelques cœurs
GRID_G_CO2_PER_KWH = 44.0           # mix électrique français (Ember 2024) ; 16 g/kWh selon Electricity Maps


def candidates(seed: int) -> dict:
    return {
        "logreg": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                LogisticRegression(C=1.0, max_iter=1000)),
        "random_forest": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(n_estimators=150, max_depth=6, min_samples_leaf=20,
                                   n_jobs=1, random_state=seed)),
        "hist_gb": HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=40,
            l2_regularization=1.0, random_state=seed),
    }


def _split_time(frame, test_fraction: float):
    cut = int(len(frame) * (1 - test_fraction))
    return frame.iloc[:cut], frame.iloc[cut:]


def _cv_scores(model, X, y, n_splits: int = 5) -> dict:
    briers, aucs = [], []
    for tr, va in TimeSeriesSplit(n_splits=n_splits).split(X):
        m = clone(model).fit(X.iloc[tr], y.iloc[tr])
        p = m.predict_proba(X.iloc[va])[:, 1]
        met = classification_metrics(y.iloc[va], p)
        briers.append(met["brier"])
        if met["roc_auc"] is not None:
            aucs.append(met["roc_auc"])
    return {"brier_mean": round(float(np.mean(briers)), 4),
            "roc_auc_mean": round(float(np.mean(aucs)), 4) if aucs else None}


def _alert_threshold(model, X, y, n_splits: int = 5) -> float:
    """Seuil maximisant le F1 sur les prévisions hors échantillon (jamais sur le jeu de test)."""
    ys, ps = [], []
    for tr, va in TimeSeriesSplit(n_splits=n_splits).split(X):
        m = clone(model).fit(X.iloc[tr], y.iloc[tr])
        ys.append(y.iloc[va].to_numpy())
        ps.append(m.predict_proba(X.iloc[va])[:, 1])
    y_all, p_all = np.concatenate(ys), np.concatenate(ps)
    grid = np.arange(0.10, 0.70, 0.02)
    f1s = [classification_metrics(y_all, p_all, float(t))["f1"] for t in grid]
    return round(float(grid[int(np.argmax(f1s))]), 2)


def train(db_path: str | Path, model_dir: str | Path, report_dir: str | Path,
          test_fraction: float = 0.2, seed: int = 42) -> dict:
    t0, cpu0 = time.perf_counter(), time.process_time()
    model_dir, report_dir = Path(model_dir), Path(report_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    with db.connect(db_path) as conn:
        daily = db.read_daily(conn)
        sources = db.data_sources(conn)
    if len(daily) < 300:
        raise ValueError(f"Pas assez de jours ({len(daily)}) : collectez au moins ~2 ans de données.")
    if len(daily) < 730:
        LOG.warning("⚠ Seulement %d jours : jeu de test très petit, métriques peu fiables "
                    "(visez 5 ans ou plus).", len(daily))
    data_source = sources[0] if len(sources) == 1 else "mixed"
    if "synthetic" in sources:
        LOG.warning("⚠ Entraînement sur données SYNTHÉTIQUES : métriques non représentatives.")

    obs_frame, clim_frame = training_frames(daily)
    X_all, y_all = obs_frame[OBS_FEATURES], obs_frame[TARGET].astype(int)

    # sélection par validation croisée temporelle (apprentissage uniquement)
    train_df, test_df = _split_time(obs_frame, test_fraction)
    Xtr, ytr = train_df[OBS_FEATURES], train_df[TARGET].astype(int)
    Xte, yte = test_df[OBS_FEATURES], test_df[TARGET].astype(int)
    cv = {name: _cv_scores(m, Xtr, ytr) for name, m in candidates(seed).items()}
    best_name = min(cv, key=lambda k: cv[k]["brier_mean"])
    LOG.info("Validation croisée temporelle : %s -> retenu : %s", cv, best_name)

    # évaluation sur la période la plus récente
    best = clone(candidates(seed)[best_name]).fit(Xtr, ytr)
    p_best = best.predict_proba(Xte)[:, 1]

    ctr = clim_frame[clim_frame.index <= train_df.index.max()]
    clim_eval = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(
        ctr[CALENDAR_FEATURES], ctr[TARGET].astype(int))
    p_clim = clim_eval.predict_proba(calendar_features(yte.index)[CALENDAR_FEATURES])[:, 1]
    y_clim = yte

    alert_thr = _alert_threshold(candidates(seed)[best_name], Xtr, ytr)
    m_best = classification_metrics(yte, p_best)
    m_alert = classification_metrics(yte, p_best, alert_thr)
    m_clim = classification_metrics(y_clim, p_clim)
    m_persist = classification_metrics(yte, Xte["rain_day_l1"].to_numpy())
    m_base = classification_metrics(yte, np.full(len(yte), float(ytr.mean())))
    bss = brier_skill_score(m_best["brier"], m_clim["brier"])

    # réentraînement final sur toutes les données
    final_obs = clone(candidates(seed)[best_name]).fit(X_all, y_all)
    final_clim = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(
        clim_frame[CALENDAR_FEATURES], clim_frame[TARGET].astype(int))

    wall, cpu = time.perf_counter() - t0, time.process_time() - cpu0
    energy_wh = ASSUMED_CPU_POWER_W * cpu / 3600.0
    trained_at = datetime.now(timezone.utc).replace(microsecond=0)
    fingerprint = hashlib.sha256(
        f"{daily.index.min()}|{daily.index.max()}|{len(daily)}|{best_name}|{seed}".encode()
    ).hexdigest()[:8]
    version = f"{trained_at:%Y%m%d}-{fingerprint}"

    meta = {
        "model_version": version,
        "code_version": __version__,
        "trained_at_utc": trained_at.isoformat(),
        "data_source": data_source,
        "representative": data_source != "synthetic",
        "data_period": [str(daily.index.min().date()), str(daily.index.max().date())],
        "n_days_total": int(len(daily)),
        "n_samples_obs_model": int(len(obs_frame)),
        "target": f"jour de pluie (cumul régional >= seuil), cible = `{TARGET}`",
        "obs_features": OBS_FEATURES,
        "calendar_features": CALENDAR_FEATURES,
        "selected_model": best_name,
        "cross_validation": cv,
        "test_period": [str(test_df.index.min().date()), str(test_df.index.max().date())],
        "test_metrics": {
            "selected_model": m_best, "selected_model_at_alert_threshold": m_alert,
            "alert_threshold": alert_thr, "climatology_baseline": m_clim,
            "persistence_baseline": m_persist, "base_rate_baseline": m_base,
            "brier_skill_score_vs_climatology": bss,
        },
        "reliability": reliability_table(yte, p_best),
        "risk_thresholds": {"low_below": 0.30, "high_from": 0.60},
        "eco": {"training_wall_s": round(wall, 2), "training_cpu_s": round(cpu, 2),
                "estimated_energy_wh": round(energy_wh, 4),
                "estimated_co2_g": round(energy_wh / 1000 * GRID_G_CO2_PER_KWH, 5),
                "assumptions": {"cpu_power_w": ASSUMED_CPU_POWER_W,
                                "grid_g_co2_per_kwh": GRID_G_CO2_PER_KWH},
                "deep_learning": False},
    }

    joblib.dump(final_obs, model_dir / "model_obs.joblib", compress=3)
    joblib.dump(final_clim, model_dir / "model_clim.joblib", compress=3)
    (model_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    (report_dir / "metrics.json").write_text(json.dumps(meta["test_metrics"], indent=2),
                                             encoding="utf-8")
    plotted = plot_evaluation(yte, p_best, report_dir / "evaluation.png",
                              f"{best_name} — jeu de test {meta['test_period'][0]} → "
                              f"{meta['test_period'][1]} (source : {data_source})")
    (report_dir / "evaluation.md").write_text(render_report(meta, plotted), encoding="utf-8")
    LOG.info("Modèle %s enregistré dans %s", version, model_dir)
    return meta


def render_report(meta: dict, with_figure: bool) -> str:
    t = meta["test_metrics"]
    rows = [("Modèle retenu (" + meta["selected_model"] + "), seuil 0,5", t["selected_model"]),
            (f"Modèle retenu, seuil d'alerte {t['alert_threshold']} (choisi par validation croisée)",
             t["selected_model_at_alert_threshold"]),
            ("Référence : climatologie", t["climatology_baseline"]),
            ("Référence : persistance", t["persistence_baseline"]),
            ("Référence : fréquence moyenne", t["base_rate_baseline"])]
    lines = [
        "# Évaluation du modèle", "",
        f"- Version : `{meta['model_version']}` — source des données : **{meta['data_source']}**",
        f"- Période de test : {meta['test_period'][0]} → {meta['test_period'][1]}",
    ]
    if not meta["representative"]:
        lines += ["", "> ⚠ **Données synthétiques** : ces chiffres valident le pipeline, "
                  "ils ne mesurent PAS la performance réelle."]
    lines += ["", "| Modèle | ROC-AUC | PR-AUC | Brier | Exactitude | Précision | Rappel | F1 |",
              "|---|---|---|---|---|---|---|---|"]
    for name, m in rows:
        lines.append(f"| {name} | {m['roc_auc']} | {m['pr_auc']} | {m['brier']} | {m['accuracy']} "
                     f"| {m['precision']} | {m['recall']} | {m['f1']} |")
    lines += ["", f"Score de Brier relatif à la climatologie (BSS) : "
              f"**{t['brier_skill_score_vs_climatology']}** (> 0 = le modèle bat la climatologie).", ""]
    if with_figure:
        lines += ["![Évaluation](evaluation.png)", ""]
    return "\n".join(lines)
