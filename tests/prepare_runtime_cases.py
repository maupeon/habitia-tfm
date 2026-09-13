"""Construye casos HTTP desde predicciones reales del artefacto final exportado.

Ejecutar con el entorno de entrenamiento (requiere pyarrow), nunca modifica los
artefactos. Los resultados esperados vienen del parquet evaluado, no del servidor.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model_pipeline import historical_to_payloads
from revision_data import load_revision_data


def prepare(experiment: Path, output: Path, count: int = 30):
    source = experiment / "predicciones_artefacto.parquet"
    predictions = pd.read_parquet(source)
    chosen = predictions.sample(min(count, len(predictions)), random_state=1709).reset_index(drop=True)
    historical, _ = load_revision_data()
    rows = historical.set_index("source_row_id").loc[chosen.source_row_id].reset_index()
    payloads = historical_to_payloads(rows, include_price=True)
    cases = [{"source_row_id": int(r.source_row_id), "anuncio": p,
              "precio_estimado_esperado": round(float(r.pred_lgb)),
              "intervalo_esperado": [round(float(r.limite_inferior)), round(float(r.limite_superior))]}
             for r, p in zip(chosen.itertuples(), payloads)]
    result = {"origen": str(source.resolve()), "sha256_predicciones": hashlib.sha256(source.read_bytes()).hexdigest(),
              "alcance": "paridad con predicciones exportadas; no nueva estimación de precisión", "casos": cases}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"Preparados {len(cases)} casos reales en {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--count", default=30, type=int)
    args = parser.parse_args()
    prepare(args.experiment, args.output, args.count)
