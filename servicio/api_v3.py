"""Servicio HTTP del predictor XGBoost para compra y alquiler en Madrid."""
from __future__ import annotations
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from predictor_v3.runtime import MODEL_ID, MODEL_VERSION, RuntimePredictor

V: RuntimePredictor | None = None
LOCK = Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global V
    V = RuntimePredictor()
    yield
    V = None

app = FastAPI(title="HabitIA XGBoost · precio anunciado", version=MODEL_VERSION, lifespan=lifespan)

class Peticion(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)
    anuncios: list[Any] = Field(min_length=1, max_length=24)
    renivelar: Literal[True] = True
    explicar: bool = False

@app.get("/salud")
def salud(response: Response):
    if V is None:
        response.status_code = 503
        return {"ok": False, "model_id": MODEL_ID, "model_version": MODEL_VERSION}
    return V.health()

@app.post("/valorar")
def valorar(p: Peticion, authorization: str | None = Header(default=None)):
    token = os.getenv("VALORACION_TOKEN")
    if token and not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Token inválido")
    if V is None:
        raise HTTPException(503, "Modelo no disponible")
    started = time.perf_counter()
    try:
        with LOCK:
            results, errors = V.valorar(p.anuncios, explicar=p.explicar)
    except Exception:
        logging.exception("Error de inferencia v3")
        raise HTTPException(503, "No se pudo completar la valoración") from None
    return {"resultados": results, "errores": errors, "ms": round((time.perf_counter() - started) * 1000, 1),
            "model_id": MODEL_ID, "model_version": MODEL_VERSION, "nivel_precios": "2025",
            "objetivo": "precio_anunciado", "extrapolacion_temporal": True, "precision_actual_validada": False}
