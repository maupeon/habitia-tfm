# -*- coding: utf-8 -*-
"""Inferencia de la versión 2: precio anunciado histórico y escenario indexado.

Los artefactos y ModelPipeline se exportan juntos desde el entrenamiento. El
precio que trae el anuncio solo se compara DESPUÉS de calcular la predicción.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import sys
from pathlib import Path

# En macOS, cargar sklearn antes que LightGBM evita conflictos de libomp al
# importar ambos en el mismo proceso. El servicio no necesita sklearn si no está.
try:
    import sklearn  # noqa: F401
except ImportError:
    pass
import lightgbm as lgb
import numpy as np
import pandas as pd

from model_pipeline import (InputDataError, ModelPipeline, OutOfDomainError,
                            haversine_km, parsea_planta)

RAIZ = Path(__file__).resolve().parents[1] / "servicio"
DISTRITO_OK = {"Chamberi": "Chamberí", "Chamartin": "Chamartín", "Tetuan": "Tetuán",
              "San Blas . Canillejas": "San Blas-Canillejas", "Vicalvaro": "Vicálvaro",
              "Villa De Vallecas": "Villa de Vallecas", "Puente De Vallecas": "Puente de Vallecas"}


def _f(value, por_defecto=np.nan):
    try:
        x = float(value)
        return x if math.isfinite(x) else por_defecto
    except (ValueError, TypeError):
        return por_defecto


def precio_comparacion(a: dict) -> float | None:
    """Un precio ausente no impide predecir; un precio inválido sí se rechaza."""
    raw = a.get("price")
    if raw is None:
        return None
    price = _f(raw)
    if not math.isfinite(price) or price <= 0 or isinstance(raw, bool):
        raise InputDataError("price debe ser positivo y finito, o null para no comparar.")
    return price


def conformal_log_interval(point, raw_lo, raw_hi, correction: float):
    """Misma regla anterior a calibrar y a servir: ordenar e incluir el punto.

    La corrección conformal no puede contraer la banda. El entrenamiento debe
    calcular sus scores de calibración sobre EXACTAMENTE estos bordes con Q=0.
    """
    q = float(correction)
    if not math.isfinite(q) or q < 0:
        raise ValueError("conformal_Q debe ser finito y no negativo.")
    return np.minimum(np.minimum(raw_lo, raw_hi), point) - q, np.maximum(np.maximum(raw_lo, raw_hi), point) + q


class Valorador:
    def __init__(self, raiz: Path = RAIZ, portable: bool = False):
        self.raiz = Path(raiz)
        self.man = json.loads((self.raiz / "manifiesto.json").read_text(encoding="utf-8"))
        if not str(self.man.get("version", "")).startswith("2."):
            raise ValueError("El servicio v2 requiere artefactos v2; ejecute el entrenamiento reproducible.")
        for filename, expected in self.man.get("sha256", {}).items():
            if Path(filename).name != filename:
                raise ValueError("El manifiesto solo puede verificar archivos de su propio directorio.")
            actual = hashlib.sha256((self.raiz / filename).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Integridad SHA-256 incorrecta para {filename}; vuelva a exportar el conjunto de artefactos.")
        self.pipeline = ModelPipeline.load(self.raiz / self.man.get("pipeline", "pipeline.json"))
        self.cols, self.cat = self.pipeline.columns, self.pipeline.categoricals
        if self.man.get("columnas") != self.cols:
            raise ValueError("Columnas distintas entre manifiesto y pipeline; no se inicia el servicio.")
        archivo = self.man.get("modelo_precio", "modelo_precio.txt")
        if portable:
            archivo = self.man.get("modelo_portable", {}).get("archivo", archivo)
        self.modelo = lgb.Booster(model_file=str(self.raiz / archivo))
        self.q = {key: lgb.Booster(model_file=str(self.raiz / f"modelo_q_{key}.txt")) for key in ("lo", "hi")}
        for booster in [self.modelo, *self.q.values()]:
            if booster.feature_name() != self.cols:
                raise ValueError("Las variables del booster no coinciden con el pipeline exportado.")
        self.smearing = float(self.man.get("smearing", 1.0))
        if not math.isfinite(self.smearing) or self.smearing <= 0:
            raise ValueError("smearing debe ser positivo.")
        self.Q = float(self.man["conformal_Q"])
        conformal_log_interval(np.asarray([0.]), np.asarray([0.]), np.asarray([0.]), self.Q)
        self.alpha = float(self.man.get("alpha", self.man.get("alfa", .1)))
        if not 0 < self.alpha < 1:
            raise ValueError("alpha/alfa debe estar entre 0 y 1.")
        self.factor = float(self.man.get("renivelado", {}).get("factor", 1.0))
        if not math.isfinite(self.factor) or self.factor <= 0:
            raise ValueError("Factor del escenario temporal no válido.")
        self.threads = max(1, int(os.getenv("VALORACION_PREDICT_THREADS", "1")))

    def fila(self, a: dict) -> dict:
        """Compatibilidad de inspección; la matriz siempre la prepara el pipeline."""
        precio_comparacion(a)
        row = self.pipeline.transform(a).iloc[0].to_dict()
        meta = self.pipeline.metadata(a)[0]
        return {**row, **meta, "_seccion": meta["seccion_censal"]}

    def _matriz(self, filas: list[dict]) -> pd.DataFrame:
        """Solo para herramientas de inspección que ya hayan llamado a fila()."""
        x = pd.DataFrame(filas)[self.cols].copy()
        for col, categories in self.cat.items():
            x[col] = pd.Categorical(x[col], categories=categories)
        return x

    def seccion(self, lat: float, lon: float) -> pd.Series:
        if not (math.isfinite(lat) and math.isfinite(lon)):
            raise InputDataError("Coordenadas finitas necesarias.")
        inds, distances = self.pipeline.nearest(np.asarray([lat]), np.asarray([lon]))
        if distances[0] > self.pipeline.max_support_distance_km:
            raise OutOfDomainError("Coordenadas fuera del soporte espacial de entrenamiento.")
        sec = self.pipeline.sections[inds[0]]
        return pd.Series(sec, name=sec["codigo_censal"])

    def valorar(self, anuncios: dict | list[dict], renivelar: bool = False, explicar: bool = False):
        uno = isinstance(anuncios, dict)
        lista = [anuncios] if uno else list(anuncios)
        if not lista:
            return []
        precios = [precio_comparacion(a) for a in lista]
        x = self.pipeline.transform(lista)
        metadata = self.pipeline.metadata(lista)
        point_log = self.modelo.predict(x, num_threads=self.threads) + math.log(self.smearing)
        raw_lo = self.q["lo"].predict(x, num_threads=self.threads)
        raw_hi = self.q["hi"].predict(x, num_threads=self.threads)
        low_log, high_log = conformal_log_interval(point_log, raw_lo, raw_hi, self.Q)
        k = self.factor if renivelar else 1.0
        point, low, high = np.exp(point_log) * k, np.exp(low_log) * k, np.exp(high_log) * k
        if not all(np.isfinite(values).all() for values in (point, low, high)):
            raise RuntimeError("El modelo produjo una predicción no finita.")
        contributions = self.modelo.predict(x, pred_contrib=True, num_threads=self.threads) if explicar else None
        output = []
        for index, (a, price, p, lo, hi, meta) in enumerate(zip(lista, precios, point, low, high, metadata)):
            gap = (price - p) / p * 100 if price is not None else None
            warnings = ["Estimación de precio anunciado, no precio de compraventa ni tasación oficial.",
                        "Evaluación histórica de 2018; no se ha medido precisión con anuncios actuales.",
                        "La sección y el barrio se aproximan por el centroide de entrenamiento más cercano."]
            if renivelar:
                warnings.append("Escenario indexado: el factor agregado no valida cambios de cada vivienda o barrio.")
            if meta["campos_ausentes"]:
                warnings.append("Datos ausentes imputados con estadísticas de entrenamiento: " + ", ".join(meta["campos_ausentes"]) + ".")
            output.append({
                "propertyCode": a.get("propertyCode"), "estado": "ok",
                "precio_justo": round(float(p)), "precio_estimado": round(float(p)),
                "intervalo": [round(float(lo)), round(float(hi))],
                "precio_anunciado": round(price) if price is not None else None,
                "brecha_pct": round(gap, 1) if gap is not None else None,
                "banda": self._banda(gap),
                "oportunidad": bool(price is not None and price < lo),
                "sobrevalorado": bool(price is not None and price > hi),
                **meta,
                "distrito": DISTRITO_OK.get(meta["distrito"], meta["distrito"]),
                "nivel_precios": self.man.get("renivelado", {}).get("periodo", "escenario") if renivelar else "2018",
                "model_version": self.man["version"], "objetivo": "precio_anunciado",
                "model_id": self.man.get("model_id", self.man["version"]),
                "periodo_entrenamiento": "2018", "extrapolacion_temporal": bool(renivelar),
                "factor_escenario": k, "precision_actual_validada": False,
                "clasificacion_validada": False,
                "regla_banda": "Umbrales descriptivos de brecha porcentual; no clasificador entrenado.",
                "nivel_intervalo_nominal": 1 - self.alpha,
                "advertencias": warnings,
            })
            if contributions is not None:
                values = contributions[index, :-1]
                top = np.argsort(-np.abs(values), kind="stable")[:3]
                factors = []
                for j in top:
                    value = x.iloc[index, j]
                    if isinstance(value, np.generic):
                        value = value.item()
                    factors.append({"variable": self.cols[j], "valor": value,
                                    "contribucion_log_euros": float(values[j]),
                                    "sentido": "aumenta" if values[j] >= 0 else "disminuye"})
                output[-1]["explicacion"] = {
                    "metodo": "TreeSHAP nativo de LightGBM", "escala": "log_euros_2018",
                    "base_log_euros": float(contributions[index, -1] + math.log(self.smearing)),
                    "prediccion_log_euros": float(point_log[index]), "factores": factors,
                    "suma_otras_contribuciones_log_euros": float(values.sum() - values[top].sum()),
                    "no_causal": True,
                    "advertencia": "Explica asociaciones aprendidas del modelo respecto a su referencia; no estima el efecto causal de reformar ni cambiar una característica.",
                }
        return output[0] if uno else output

    def valorar_alquiler(self, anuncios, renivelar: bool = False):
        """No recicla el modelo de venta ni fechas no verificadas como alquiler."""
        raise InputDataError("Referencia de alquiler no habilitada en v2: falta verificar la fecha y procedencia de la tabla territorial. El modelo predice precios anunciados de venta.")

    @staticmethod
    def _banda(brecha):
        # Regla descriptiva heredada para compatibilidad; no clasificador evaluado.
        if brecha is None:
            return None
        if brecha <= -12:
            return "barato"
        if brecha <= -4:
            return "ajustado"
        if brecha < 8:
            return "en_linea"
        if brecha < 20:
            return "caro"
        return "muy_caro"


_singleton: Valorador | None = None


def valorador() -> Valorador:
    global _singleton
    if _singleton is None:
        _singleton = Valorador()
    return _singleton


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Estima precio anunciado de 2018 con el pipeline v2.")
    parser.add_argument("--json", required=True, help="JSON del anuncio, o '-' para stdin")
    parser.add_argument("--renivelar", action="store_true", help="Escenario temporal agregado explícito")
    parser.add_argument("--sin-renivelar", action="store_true", help="Compatibilidad: 2018 ya es el valor por defecto")
    args = parser.parse_args()
    datos = json.loads(sys.stdin.read() if args.json == "-" else args.json)
    print(json.dumps(valorador().valorar(datos, renivelar=args.renivelar and not args.sin_renivelar), indent=2, ensure_ascii=False))
