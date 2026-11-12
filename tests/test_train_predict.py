import json
from datetime import date, timedelta

from goutte_deau import db
from goutte_deau.predictor import Predictor, risk_level


def test_training_artifacts_and_metadata(demo_env):
    st, meta = demo_env
    for f in ("model_obs.joblib", "model_clim.joblib", "metadata.json"):
        assert (st.model_dir / f).exists()
    saved = json.loads((st.model_dir / "metadata.json").read_text(encoding="utf-8"))
    assert saved["data_source"] == "synthetic" and saved["representative"] is False
    assert saved["eco"]["deep_learning"] is False
    t = saved["test_metrics"]
    assert 0.0 <= t["selected_model"]["brier"] <= 0.5
    assert set(t) >= {"selected_model", "climatology_baseline", "persistence_baseline"}
    assert (st.report_dir / "evaluation.md").exists()


def test_chronological_split_no_overlap(demo_env):
    _, meta = demo_env
    assert meta["test_period"][0] > meta["data_period"][0]
    assert meta["test_period"][1] <= meta["data_period"][1]


def test_predict_modes_and_ranges(demo_env):
    st, _ = demo_env
    predictor = Predictor.load(st.model_dir)
    with db.connect(st.db_path) as conn:
        last = db.read_daily(conn).index.max().date()
        near = predictor.predict(conn, last + timedelta(days=1))
        far = predictor.predict(conn, last + timedelta(days=60))
        past = predictor.predict(conn, last - timedelta(days=10))
    assert near.mode == "observations" and far.mode == "climatologie"
    assert past.mode == "observations" and past.observed_rain_mm is not None
    for r in (near, far, past):
        assert 0.0 <= r.probability <= 1.0 and r.risk_level in {"low", "moderate", "high"}


def test_out_of_range_dates_rejected(demo_env):
    import pytest
    st, _ = demo_env
    predictor = Predictor.load(st.model_dir)
    with db.connect(st.db_path) as conn:
        with pytest.raises(ValueError):
            predictor.predict(conn, date(1980, 1, 1))
        with pytest.raises(ValueError):
            predictor.predict(conn, date.today() + timedelta(days=2000))


def test_risk_thresholds():
    th = {"low_below": 0.30, "high_from": 0.60}
    assert [risk_level(p, th) for p in (0.1, 0.3, 0.59, 0.6, 0.9)] == \
        ["low", "moderate", "moderate", "high", "high"]
