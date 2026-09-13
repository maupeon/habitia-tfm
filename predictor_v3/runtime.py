"""Contrato v3: pesos recibidos sin reentrenar, entradas estrictas y salidas trazables."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .predictor import PredictorHabitia, RUTA_PAQUETE

MODEL_ID = "habitIA-xgboost-2018-v3"
MODEL_VERSION = "3.0.0"
MANIFEST = Path(__file__).resolve().parents[1] / "servicio" / "manifiesto_v3.json"
WARNINGS = [
    "Estimación de precio anunciado con datos de 2018, indexada a 2025. Precisión actual no validada.",
    "El paquete no incluye intervalos calibrados ni clasificación validada de barato o caro.",
    "No observa estado de conservación, condición de ático, vistas ni parcela.",
    "La renta es un escenario derivado del precio de venta y ratios distritales de 2024; no un modelo de alquiler validado.",
]


class StrictRecord(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="ignore")


class DetailedType(StrictRecord):
    typology: str | None = Field(default=None, max_length=80)
    subTypology: str | None = Field(default=None, max_length=80)


class ParkingSpace(StrictRecord):
    hasParkingSpace: bool | None = None


class Anuncio(StrictRecord):
    propertyCode: str = Field(min_length=1, max_length=80)
    operation: Literal["sale", "rent"]
    municipality: str = Field(max_length=120)
    propertyType: str = Field(max_length=80)
    price: float | None = Field(default=None, gt=0)
    size: float | None = None
    rooms: int | None = None
    bathrooms: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    floor: str | None = Field(default=None, max_length=20)
    hasLift: bool | None = None
    description: str | None = Field(default=None, max_length=12000)
    detailedType: DetailedType | None = None
    parkingSpace: ParkingSpace | None = None


class RuntimePredictor:
    def __init__(self, directory: Path | None = None):
        directory = directory or Path(os.getenv("VALORACION_ARTIFACTS_V3", str(RUTA_PAQUETE)))
        self.manifest = json.loads(MANIFEST.read_text())
        for name, expected in self.manifest["sha256"].items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Artefacto v3 alterado: {name}")
        self.predictor = PredictorHabitia.cargar(directory)
        self.predictor.modelo.set_params(n_jobs=1)
        self.meta = self.predictor.metadatos
        if (self.meta["ano_base"], self.meta["ano_precio"], self.meta["ano_renta"]) != (2018, 2025, 2024):
            raise ValueError("Periodos incompatibles con el contrato v3")
        if self.predictor.modelo.get_booster().feature_names != self.predictor.columnas:
            raise ValueError("Variables distintas entre modelo y metadatos")

    def health(self):
        return {"ok": True, "model_id": MODEL_ID, "model_version": MODEL_VERSION,
                "variables": len(self.predictor.columnas), "nivel_precios": "2025",
                "ano_base": 2018, "ano_precio": 2025, "ano_renta": 2024,
                "objetivo": "precio_anunciado", "precision_actual_validada": False,
                "intervalos_disponibles": False, "alquiler_validado": False,
                "modelo_sha256": self.manifest["sha256"]["modelo.json"],
                "metricas_test_declaradas": self.meta["metricas_test"]}

    @staticmethod
    def validate(raw: Any):
        try:
            a = Anuncio.model_validate(raw)
        except ValidationError as error:
            fields = sorted({str(e["loc"][0]) for e in error.errors() if e["loc"]})
            return None, ("datos_insuficientes", "Revisa los campos requeridos y sus tipos: " + ", ".join(fields))
        subtype = a.detailedType.subTypology if a.detailedType else None
        typology = a.detailedType.typology if a.detailedType else None
        if a.operation != "sale" or a.municipality.strip().casefold() != "madrid":
            return None, ("fuera_ambito", "El modelo estima viviendas de venta en Madrid capital.")
        if (a.propertyType not in {"flat", "penthouse", "duplex", "studio"}
                and not (a.propertyType == "homes" and typology == "flat")) or subtype in {
                    "independantHouse", "semidetachedHouse", "terracedHouse"}:
            return None, ("fuera_ambito", "Tipología no admitida: el modelo no valora casas, oficinas ni parcelas.")
        if a.size is not None and a.size > 367:
            return None, ("fuera_ambito", "Superficie superior al límite de 367 m² del paquete recibido.")
        if (a.latitude is None or a.longitude is None or not -90 <= a.latitude <= 90
                or not -180 <= a.longitude <= 180):
            return None, ("datos_insuficientes", "Se requieren coordenadas finitas y válidas del anuncio.")
        if a.size is None or a.size <= 0 or a.rooms is None or a.rooms < 0 or a.bathrooms is None or a.bathrooms < 0:
            return None, ("datos_insuficientes", "Se requieren superficie positiva, habitaciones y baños observados.")
        return a.model_dump(exclude_none=True), None

    def valorar(self, anuncios: list[Any], explicar: bool = False):
        errors, valid = [], []
        codes = [row.get("propertyCode") if isinstance(row, dict) else None for row in anuncios]
        for i, raw in enumerate(anuncios):
            data, error = self.validate(raw)
            if data and codes.count(data["propertyCode"]) != 1:
                error = ("datos_insuficientes", "propertyCode duplicado en el lote.")
            if error:
                errors.append({"indice": i, "propertyCode": codes[i] if isinstance(codes[i], str) else None,
                               "estado": error[0], "detalle": error[1]})
            else:
                valid.append((i, data))
        results = []
        if not valid:
            return results, errors
        rows = json.loads(self.predictor.predecir([a for _, a in valid]).to_json(orient="records"))
        for (i, data), row in zip(valid, rows, strict=True):
            price = row["precio_estimado"]
            if not row["valido"] or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                reason = row["motivo_no_valido"] or "No se pudo obtener una estimación finita."
                errors.append({"indice": i, "propertyCode": data["propertyCode"],
                               "estado": "fuera_ambito" if "fuera" in reason or "tipologia" in reason else "datos_insuficientes",
                               "detalle": reason})
                continue
            warnings = list(WARNINGS)
            marks = {
                "sin_descripcion": "Sin descripción: los atributos extraídos del texto se tratan como ausentes.",
                "planta_imputada": "Planta desconocida: imputada con la mediana del entrenamiento (2).",
                "ascensor_desde_descripcion": "Ascensor inferido de la descripción al faltar el campo estructurado.",
                "barrio_rescatado": "Barrio asignado por cercanía, hasta 500 m del polígono disponible.",
            }
            warnings += [text for key, text in marks.items() if row[key]]
            if row["fuera_de_rango"]:
                warnings.append("Valores fuera del rango de entrenamiento: " + row["fuera_de_rango"])
            if not data.get("parkingSpace") or "hasParkingSpace" not in data["parkingSpace"]:
                warnings.append("Garaje no informado: el predictor lo trata como ausente.")
            if explicar:
                warnings.append("Este paquete no exporta explicaciones SHAP por anuncio.")
            announced = data.get("price")
            results.append({
                "propertyCode": data["propertyCode"], "estado": "ok", "model_id": MODEL_ID,
                "model_version": MODEL_VERSION, "modelo": self.meta["nombre"],
                "modelo_sha256": self.manifest["sha256"]["modelo.json"],
                "objetivo": "precio_anunciado", "periodo_entrenamiento": "2018",
                "extrapolacion_temporal": True, "precision_actual_validada": False,
                "clasificacion_validada": False, "nivel_precios": "2025",
                "ano_base": 2018, "ano_precio": 2025, "ano_renta": 2024,
                "factor_escenario": row["indice_venta"], "precio_estimado_base": row["precio_estimado_base"],
                "precio_estimado": price, "precio_anunciado": announced,
                "brecha_pct": (announced / price - 1) * 100 if announced else None,
                "intervalo": None, "banda": None, "oportunidad": False, "sobrevalorado": False,
                "barrio_code": row["barrio_code"], "distrito_code": row["distrito_code"],
                "renta_mensual_estimada": row["renta_mensual_estimada"],
                "factor_renta_mensual": row["factor_renta_mensual"],
                "alquiler_validado": False, "metodo_renta": "ratio_distrital_2024",
                "advertencias": warnings,
                "calidad": {key: row[key] for key in (*marks, "fuera_de_rango")},
            })
        return results, errors
