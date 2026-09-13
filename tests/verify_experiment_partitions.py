"""Verifica la separación real y los denominadores guardados del experimento."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "revision_2026-09-08" / "experimento"


def run():
    assignments = pd.read_parquet(BASE / "particiones_exteriores.parquet")
    predictions = pd.read_parquet(BASE / "predicciones_exteriores.parquet")
    rejected = pd.read_csv(BASE / "abstenciones_exteriores.csv")
    assert assignments.groupby(["fold", "ASSETID"]).parte.nunique().max() == 1
    evaluation = assignments[assignments.parte == "evaluacion"]
    assert not evaluation.source_row_id.duplicated().any()
    assert evaluation.groupby("ASSETID").fold.nunique().max() == 1
    assert not predictions.source_row_id.duplicated().any()
    assert not rejected.source_row_id.duplicated().any()
    assert not set(predictions.source_row_id) & set(rejected.source_row_id)
    assert set(predictions.source_row_id) | set(rejected.source_row_id) == set(evaluation.source_row_id)
    assert predictions.groupby("ASSETID").fold.nunique().max() == 1
    metric_checks = []
    for fold, group in predictions.groupby("fold"):
        index = int(str(fold).rsplit("_", 1)[1])
        declared = json.loads((BASE / f"fold_{index}.json").read_text())
        for name, column in [("Referencia territorial", "pred_baseline"),
                             ("Hedónico Ridge", "pred_ridge"), ("LightGBM", "pred_lgb")]:
            y, p = group.PRICE.to_numpy(), group[column].to_numpy()
            observed = {"n": len(group), "MdAPE_pct": float(np.median(np.abs(p-y)/y)*100),
                        "MAE_eur": float(np.mean(np.abs(p-y)))}
            for key, value in observed.items():
                assert np.isclose(value, declared["metricas"][name][key], atol=1e-9, rtol=1e-12)
            metric_checks.append({"fold": index, "modelo": name, **observed})
    result = {"estado": "aprobado", "activos_sin_solapamiento_entre_partes": True,
              "cada_observacion_evaluada_una_vez": True, "abstenciones_completas_y_disjuntas": True,
              "observaciones_elegibles": len(evaluation), "activos_elegibles": int(evaluation.ASSETID.nunique()),
              "observaciones_evaluadas": len(predictions), "abstenciones": len(rejected),
              "metricas_recalculadas": metric_checks}
    target = ROOT / "revision_2026-09-08" / "verificacion_particiones.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
