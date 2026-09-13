"""Contrasta TODAS las predicciones reservadas con el valorador exportado.

No reentrena, no modifica el artefacto y no utiliza servicios externos. Las
únicas diferencias permitidas son el redondeo final de la API a euros enteros.
"""
from pathlib import Path
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import sklearn  # noqa: F401; orden de carga de OpenMP en macOS
import numpy as np
import pandas as pd
from revision_data import load_revision_data
from model_pipeline import historical_to_payloads
from valorador import Valorador


def run():
    start = time.time()
    experiment = ROOT / "revision_2026-09-08" / "experimento"
    expected = pd.read_parquet(experiment / "predicciones_artefacto.parquet")
    data, _ = load_revision_data()
    raw = data.set_index("source_row_id").loc[expected.source_row_id].reset_index()
    assert raw.source_row_id.tolist() == expected.source_row_id.tolist()
    assert np.array_equal(raw.PRICE.to_numpy(), expected.PRICE.to_numpy())
    model = Valorador(experiment / "artefacto")
    # La comparación usa exactamente el adaptador que consume el contrato público.
    payloads = historical_to_payloads(raw, include_price=True)
    actual = []
    for begin in range(0, len(payloads), 512):
        actual.extend(model.valorar(payloads[begin:begin + 512]))
    checks = {}
    for field, column in [("precio_estimado", "pred_lgb"),
                          ("limite_inferior", "limite_inferior"),
                          ("limite_superior", "limite_superior")]:
        values = np.array([r["precio_estimado"] if field == "precio_estimado"
                           else r["intervalo"][0 if field == "limite_inferior" else 1]
                           for r in actual])
        difference = np.abs(values - expected[column].to_numpy())
        assert difference.max() <= 0.500001, (field, difference.max())
        checks[field] = {"n": len(values), "max_diferencia_eur": float(difference.max()),
                         "igual_a_redondeo": bool(np.array_equal(values, np.rint(expected[column])))}
        assert checks[field]["igual_a_redondeo"]
    assert all(r["nivel_precios"] == "2018" and not r["extrapolacion_temporal"]
               and not r["precision_actual_validada"] for r in actual)
    assert all(r["intervalo"][0] <= r["precio_estimado"] <= r["intervalo"][1]
               for r in actual)
    fit = pd.read_csv(experiment / "artefacto" / "fit_ids.csv")
    cal = pd.read_csv(experiment / "artefacto" / "calibracion_ids.csv")
    groups = [set(fit.ASSETID), set(cal.ASSETID), set(expected.ASSETID)]
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    result = {"estado": "aprobado", "observaciones": len(actual),
              "activos_evaluados": len(groups[2]), "comparaciones": checks,
              "separacion_activos_fit_cal_evaluacion": True,
              "salida_por_defecto_2018": True, "puntos_dentro_intervalo": True,
              "duracion_segundos": round(time.time() - start, 3),
              "sha256_valorador": hashlib.sha256((ROOT / "src/valorador.py").read_bytes()).hexdigest(),
              "sha256_manifiesto": hashlib.sha256((experiment / "artefacto/manifiesto.json").read_bytes()).hexdigest()}
    target = ROOT / "revision_2026-09-08" / "paridad_toda_evaluacion.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run()
