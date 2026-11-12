"""Ligne de commande : python -m goutte_deau <commande>."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

from goutte_deau import db, pipeline, quality, train as train_mod
from goutte_deau.config import get_settings
from goutte_deau.predictor import ModelNotAvailable, Predictor


def _date(s: str) -> date:
    return date.fromisoformat(s)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="goutte_deau", description="Projet Goutte d'eau - MVP")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Crée le schéma SQLite")

    c = sub.add_parser("collect", help="Collecte + nettoyage + stockage + agrégation")
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--infoclimat", action="store_true", help="API Infoclimat (token requis)")
    src.add_argument("--csv", nargs="+", metavar="FICHIER", help="Export(s) CSV Infoclimat (.csv ou .csv.gz)")
    src.add_argument("--synthetic", action="store_true", help="Données synthétiques (tests, démonstration)")
    c.add_argument("--start", type=_date, default=date.today() - timedelta(days=365 * 5))
    c.add_argument("--end", type=_date, default=date.today() - timedelta(days=1))

    t = sub.add_parser("train", help="Entraîne, évalue et enregistre le modèle")
    t.add_argument("--seed", type=int, default=42)

    pr = sub.add_parser("predict", help="Prévision en ligne de commande")
    pr.add_argument("--date", type=_date, default=date.today() + timedelta(days=1))

    sub.add_parser("quality", help="Indicateurs de qualité des données")

    s = sub.add_parser("serve", help="Lance l'API FastAPI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    st = get_settings()

    if args.cmd == "init-db":
        with db.connect(st.db_path) as conn:
            db.init_db(conn)
        print(f"Base initialisée : {st.db_path}")
    elif args.cmd == "collect":
        if args.infoclimat:
            out = pipeline.collect_infoclimat(st, args.start, args.end)
        elif args.csv:
            out = pipeline.collect_csv(st, args.csv)
        else:
            out = pipeline.collect_synthetic(st, args.start.isoformat(), args.end.isoformat())
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif args.cmd == "train":
        meta = train_mod.train(st.db_path, st.model_dir, st.report_dir, seed=args.seed)
        print(json.dumps(meta["test_metrics"], indent=2))
    elif args.cmd == "predict":
        try:
            pred = Predictor.load(st.model_dir)
        except ModelNotAvailable as exc:
            print(exc, file=sys.stderr)
            return 2
        with db.connect(st.db_path) as conn:
            r = pred.predict(conn, args.date)
        print(f"{r.target_day} : {r.probability:.0%} de risque de pluie "
              f"({r.risk_label}, mode {r.mode}, données {r.data_source})")
    elif args.cmd == "quality":
        with db.connect(st.db_path) as conn:
            print(json.dumps(quality.write_data_quality(conn, st.stations, st.report_dir), indent=2))
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("goutte_deau.api:app", host=args.host, port=args.port)
    return 0
