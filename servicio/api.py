# -*- coding: utf-8 -*-
"""HTTP v2. Mismo pipeline y artefactos que el entrenamiento reproducible."""
from __future__ import annotations

import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model_pipeline import InputDataError, OutOfDomainError  # noqa: E402
from valorador import Valorador  # noqa: E402

TOKEN = os.getenv("VALORACION_TOKEN")
MAX_LOTE = max(1, int(os.getenv("MAX_LOTE", "60")))
V: Valorador | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global V
    start = time.perf_counter()
    V = Valorador()
    print(f"[valoracion] modelo {V.man['version']} · {len(V.cols)} variables · "
          f"cargado en {time.perf_counter() - start:.1f} s")
    yield
    V = None


app = FastAPI(title="HabitIA · estimación de precio anunciado", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=[s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])


class Anuncio(BaseModel):
    # Los límites físicos/dominio se comprueban por fila en el pipeline para que
    # un chalet no anule un lote de pisos. JSON inválido o NaN sí rechaza el lote.
    model_config = ConfigDict(allow_inf_nan=False)
    propertyCode: str | None = None
    price: float | None = None
    size: float | None = None
    rooms: int | None = None
    bathrooms: int | None = None
    floor: str | float | None = None
    hasLift: bool | None = None
    exterior: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    municipality: str | None = None
    propertyType: str | None = None
    detailedType: dict[str, Any] | None = None


class Peticion(BaseModel):
    anuncios: list[Anuncio] = Field(..., min_length=1)
    renivelar: bool = False
    explicar: bool = False


def _auth(cabecera: str | None):
    if TOKEN and cabecera != f"Bearer {TOKEN}":
        raise HTTPException(401, "token inválido")


def _ready() -> Valorador:
    if V is None:
        raise HTTPException(503, "Modelo no disponible: aún no se han cargado artefactos v2 válidos.")
    return V


@app.get("/salud")
def salud(response: Response):
    if V is None:
        response.status_code = 503
    return {"ok": V is not None, "variables": len(V.cols) if V else 0,
            "alquiler": False, "nivel_precios": "2018" if V else None,
            "factor_renivelado": V.factor if V else None,
            "mdape_test_pct": V.man.get("metricas_test", {}).get("MdAPE_pct") if V else None,
            "model_version": V.man["version"] if V else None,
            "objetivo": "precio_anunciado", "precision_actual_validada": False,
            "renivelado_es_escenario": True}


@app.post("/valorar-alquiler")
def valorar_alquiler(p: Peticion, authorization: str | None = Header(default=None)):
    _auth(authorization)
    _ready()
    raise HTTPException(422, {"estado": "referencia_no_verificada",
                             "mensaje": "La referencia de alquiler está deshabilitada hasta verificar fecha y procedencia. El modelo v2 estima precios anunciados de venta."})


@app.post("/valorar")
def valorar(p: Peticion, authorization: str | None = Header(default=None)):
    _auth(authorization)
    v = _ready()
    if len(p.anuncios) > MAX_LOTE:
        raise HTTPException(413, f"máximo {MAX_LOTE} anuncios por petición")
    start = time.perf_counter()
    valid, errors = [], []
    for i, a in enumerate(p.anuncios):
        data = a.model_dump()
        try:
            v.fila(data)
            valid.append(data)
        except (InputDataError, OutOfDomainError) as error:
            errors.append({"indice": i, "propertyCode": a.propertyCode,
                           "estado": "fuera_ambito" if isinstance(error, OutOfDomainError) else "datos_insuficientes",
                           "detalle": str(error)})
    if not valid:
        raise HTTPException(422, {"mensaje": "Ningún anuncio cumple el contrato del modelo.", "errores": errors})
    results = v.valorar(valid, renivelar=p.renivelar, explicar=p.explicar)
    return {"resultados": results, "errores": errors,
            "ms": round((time.perf_counter() - start) * 1000, 1),
            "nivel_precios": results[0]["nivel_precios"], "model_version": v.man["version"],
            "objetivo": "precio_anunciado", "extrapolacion_temporal": p.renivelar,
            "precision_actual_validada": False}
