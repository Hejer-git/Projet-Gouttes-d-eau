"""Métriques d'évaluation d'un classifieur de probabilité de pluie."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss, f1_score,
                             log_loss, precision_score, recall_score, roc_auc_score)


def classification_metrics(y_true, proba, threshold: float = 0.5) -> dict:
    y = np.asarray(y_true).astype(int)
    p = np.clip(np.asarray(proba, dtype=float), 1e-6, 1 - 1e-6)
    pred = (p >= threshold).astype(int)
    both = len(np.unique(y)) == 2
    return {
        "n": int(len(y)),
        "base_rate": round(float(y.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4) if both else None,
        "pr_auc": round(float(average_precision_score(y, p)), 4) if both else None,
        "brier": round(float(brier_score_loss(y, p)), 4),
        "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 4),
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "threshold": threshold,
    }


def reliability_table(y_true, proba, bins: int = 10) -> list[dict]:
    """Courbe de fiabilité : probabilité prédite moyenne vs fréquence observée par classe."""
    y = np.asarray(y_true).astype(int)
    p = np.asarray(proba, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        out.append({"bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}", "n": int(m.sum()),
                    "mean_predicted": round(float(p[m].mean()), 3),
                    "observed_frequency": round(float(y[m].mean()), 3)})
    return out


def brier_skill_score(brier_model: float, brier_reference: float) -> float:
    """> 0 : le modèle bat la référence (ici la climatologie)."""
    return round(1.0 - brier_model / brier_reference, 4)


def plot_evaluation(y_true, proba, path, title: str) -> bool:
    """Courbes ROC et de fiabilité (matplotlib optionnel). Renvoie False si indisponible."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import roc_curve
    except ImportError:
        return False
    y = np.asarray(y_true).astype(int)
    p = np.asarray(proba, dtype=float)
    fig, ax = plt.subplots(1, 2, figsize=(9, 4))
    fpr, tpr, _ = roc_curve(y, p)
    ax[0].plot(fpr, tpr, color="#1f5f99", lw=2, label="Modèle")
    ax[0].plot([0, 1], [0, 1], "--", color="#555555", label="Hasard")
    ax[0].set(xlabel="Taux de faux positifs", ylabel="Taux de vrais positifs", title="Courbe ROC")
    ax[0].legend(loc="lower right")
    rel = reliability_table(y, p)
    ax[1].plot([0, 1], [0, 1], "--", color="#555555", label="Calibration parfaite")
    ax[1].plot([r["mean_predicted"] for r in rel], [r["observed_frequency"] for r in rel],
               "o-", color="#b34700", lw=2, label="Modèle")
    ax[1].set(xlabel="Probabilité prédite", ylabel="Fréquence observée", title="Fiabilité")
    ax[1].legend(loc="upper left")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True
