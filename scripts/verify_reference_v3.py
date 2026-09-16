"""Compara la integración con el código y los artefactos del paquete recibido.

Uso: python scripts/verify_reference_v3.py ../nuevo_modelo --output servicio/paridad_v3.json
Los casos son sintéticos; esta prueba no evalúa precisión predictiva.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from predictor_v3.runtime import RuntimePredictor

BASE = dict(propertyCode="paridad", operation="sale", municipality="Madrid", propertyType="flat",
            size=80, rooms=2, bathrooms=1, latitude=40.4168, longitude=-3.7038, floor="2", hasLift=True,
            price=450000, description="Piso con terraza, aire acondicionado, armarios empotrados y trastero.",
            parkingSpace={"hasParkingSpace": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    runtime = RuntimePredictor()
    for folder, hashes in ((source / "src", runtime.manifest["source_code_sha256"]),
                           (source / "data/models/paquete_produccion", runtime.manifest["sha256"])):
        for name, expected in hashes.items():
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Referencia distinta del manifiesto: {name}")
    sys.path.insert(0, str(source))
    original = importlib.import_module("src.predictor").PredictorHabitia.cargar(
        source / "data/models/paquete_produccion")
    original.modelo.set_params(n_jobs=1)
    points = original.barrios.geometry.representative_point().to_crs(4326)
    records = [{**BASE, "propertyCode": f"barrio-{i}", "latitude": float(point.y),
                "longitude": float(point.x), "size": 40 + i % 21 * 5}
               for i, point in enumerate(points)]
    edge_cases = [
        {"description": "Vivienda a reformar."},
        {"description": "Necesita una reforma integral."},
        {"description": "Piso para actualizar."},
        {"description": "Piso sin necesidad de reformar."},
        {"description": "No requiere ninguna reforma."},
        {"description": "Vivienda ocupada. Sin posesión."},
        {"description": "Piso actualmente alquilado con contrato de alquiler vigente."},
        {"description": "Piso libre de inquilinos, desocupado."},
        {"description": "Agencia: nuda propiedad - valoración de viviendas."},
        {"description": "Vivienda en nuda propiedad."},
        {"description": "Piso a reformar y ocupado."},
        {"description": None},
        {"floor": None, "hasLift": None},
        {"newDevelopment": True},
        {"newDevelopment": False},
        {"size": 367}, {"size": 368}, {"size": 0},
        {"rooms": 0, "propertyType": "studio"},
        {"propertyType": "chalet"},
        {"latitude": 41.3851, "longitude": 2.1734},
    ]
    records.extend({**BASE, **changes, "propertyCode": f"edge-{i}"}
                   for i, changes in enumerate(edge_cases))
    expected = original.predecir(records, incluir_variables=True)
    actual = runtime.predictor.predecir(records, incluir_variables=True)
    # La integración reserva float64 para no enviar al modelo filas inválidas;
    # la referencia calcula todas en float32. Se exigen valores exactos.
    pd.testing.assert_frame_equal(actual, expected, check_exact=True, check_dtype=False)
    outputs, errors = runtime.valorar(records)
    assert len(outputs) == int(expected.valido.sum())
    assert len(errors) == int((~expected.valido).sum())
    by_code = {r["propertyCode"]: r for r in outputs}
    max_runtime_diff = 0.0
    fields = ["precio_estimado_base", "precio_estimado", "renta_mensual_estimada"]
    for row in expected[expected.valido].to_dict("records"):
        response = by_code[row["propertyCode"]]
        for key in fields:
            diff = abs(response[key] - row[key])
            max_runtime_diff = max(max_runtime_diff, diff)
            assert diff < 1e-8, (row["propertyCode"], key, diff)
        assert response["calidad"]["obra_nueva"] == row["obra_nueva"]
    result = {"model_version": runtime.health()["model_version"],
              "modelo_sha256": runtime.manifest["sha256"]["modelo.json"],
              "source_exported_at": runtime.meta["exportado"],
              "poligonos": len(points), "casos_limite": len(edge_cases), "total": len(records),
              "validos": len(outputs), "abstenciones": len(errors),
              "matriz_y_salida_nativa_identicas": True,
              "diferencia_maxima_nativa_eur": 0.0,
              "diferencia_maxima_runtime_eur": float(max_runtime_diff),
              "tolerancia_serializacion_runtime_eur": 1e-8,
              "precision_predictiva_evaluada": False}
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
