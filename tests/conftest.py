"""Fixtures partagées : un environnement complet (base + modèle) sur données synthétiques."""
import pytest

from goutte_deau import db, pipeline, train
from goutte_deau.config import get_settings


@pytest.fixture(scope="session")
def demo_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("gd")
    import os
    os.environ.update({"GD_DB_PATH": str(root / "t.db"), "GD_MODEL_DIR": str(root / "models"),
                       "GD_REPORT_DIR": str(root / "reports"), "GD_LOG_PREDICTIONS": "1"})
    os.environ.pop("GD_API_KEY", None)
    st = get_settings()
    pipeline.collect_synthetic(st, "2019-01-01", "2024-12-31", seed=7)
    meta = train.train(st.db_path, st.model_dir, st.report_dir, seed=7)
    return st, meta
