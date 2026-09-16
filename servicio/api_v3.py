"""Servicio HTTP del predictor XGBoost para compra y alquiler en Madrid."""
from __future__ import annotations
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
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


@app.exception_handler(RequestValidationError)
async def peticion_invalida(request, error: RequestValidationError):
    # No reflejar la entrada: NaN/Infinity admitidos por el parser de JSON de
    # Python harían fallar la serialización de la respuesta de validación.
    details = [{key: item[key] for key in ("type", "loc", "msg")} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": details})


class Peticion(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="forbid")
    anuncios: list[Any] = Field(min_length=1, max_length=24)
    renivelar: Literal[True] = True
    explicar: bool = False
    ano_ajuste: Literal[2026] = 2026

    @field_validator("renivelar", mode="before")
    @classmethod
    def renivelar_booleano(cls, value):
        # Literal[True] acepta 1 por igualdad de Python incluso en modo strict.
        if type(value) is not bool:
            raise ValueError("renivelar debe ser un booleano")
        return value

    @field_validator("ano_ajuste", mode="before")
    @classmethod
    def ano_entero(cls, value):
        if type(value) is not int:
            raise ValueError("ano_ajuste debe ser un entero")
        return value


def autenticar(authorization: str | None = Header(default=None)):
    token = os.getenv("VALORACION_TOKEN", "")
    if not token.strip():
        # Una configuración incompleta nunca debe convertir la API privada en pública.
        raise HTTPException(503, "Autenticación del servicio no configurada")
    if not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Token inválido", headers={"WWW-Authenticate": "Bearer"})


@app.get("/salud")
def salud(response: Response):
    if V is None:
        response.status_code = 503
        return {"ok": False, "model_id": MODEL_ID, "model_version": MODEL_VERSION}
    return V.health()

@app.post("/valorar", dependencies=[Depends(autenticar)])
def valorar(p: Peticion):
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
            "model_id": MODEL_ID, "model_version": MODEL_VERSION, **V.temporalidad(),
            "objetivo": "precio_anunciado", "extrapolacion_temporal": True, "precision_actual_validada": False}
