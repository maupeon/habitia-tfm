"""Contrato único de variables para entrenamiento y servicio (sin precios).

``fit`` aprende exclusivamente de las filas que recibe: centroides aproximados,
medianas y vocabularios. ``transform`` adapta primero el histórico al mismo JSON
observable que utiliza el servicio. Nunca consulta PRICE, UNITPRICE ni alquiler.

La comprobación espacial describe un área de aplicabilidad alrededor del soporte
de entrenamiento. NO es una operación punto-en-polígono ni prueba de pertenencia
administrativa: también se exige que el anuncio declare el municipio Madrid.
"""
from __future__ import annotations

import json
import math
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PIPELINE_VERSION = "2.0.0"
EARTH_KM = 6371.0088
SOL = (40.416944, -3.703333)
LIMITS = {"size": (20, 1000), "rooms": (0, 12), "bathrooms": (0, 10), "floor": (-2, 40)}
BBOX = {"lat": (40.30, 40.55), "lon": (-3.90, -3.50)}
MAX_CITY_RADIUS_KM = 25.0  # filtro de geocodificaciones; no límite municipal
MAX_SUPPORT_DISTANCE_KM = 1.0
MISSING = "__sin_dato__"
DIRECT_NUMERIC = ["CONSTRUCTEDAREA", "ROOMNUMBER", "BATHNUMBER", "FLOORCLEAN", "HASLIFT",
                  "LATITUDE", "LONGITUDE", "ISSTUDIO", "ISDUPLEX"]
MISSING_FEATURES = ["ROOMNUMBER_ausente", "BATHNUMBER_ausente", "FLOORCLEAN_ausente",
                    "HASLIFT_ausente", "exterior_ausente", "subtipo_ausente"]
DERIVED = ["m2_por_habitacion", "banos_por_habitacion", "es_bajo", "x_km", "y_km",
           "DISTANCE_TO_CITY_CENTER", "log_dist_centro"]
CATEGORICAL = ["FLATLOCATIONID_cat", "barrio", "distrito"]
FEATURES = DIRECT_NUMERIC + MISSING_FEATURES + DERIVED + CATEGORICAL


class InputDataError(ValueError):
    """Falta una entrada necesaria o su representación no es válida."""


class OutOfDomainError(ValueError):
    """Entrada válida en forma pero fuera del dominio de aplicación."""


def _normal(value: Any) -> str:
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).strip().lower())
                   if not unicodedata.combining(c))


def _number(value: Any) -> float:
    try:
        if isinstance(value, (bool, np.bool_)):
            return float(value)
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def parsea_planta(value: Any) -> float:
    """Conserva el desconocido; no convierte ``top`` en una planta inventada."""
    s = _normal(value)
    return {"bj": 0.0, "bajo": 0.0, "en": 0.0, "entreplanta": 0.0,
            "st": -1.0, "ss": -1.0, "sotano": -1.0}.get(s, _number(value))


def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia geodésica aproximada, escalar o vectorial, siempre kilómetros."""
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def historical_to_payloads(frame: pd.DataFrame, include_price: bool = False) -> list[dict]:
    """Adaptador auditable del conjunto de pisos de Madrid de 2018.

    Los indicadores históricos pueden solaparse; el JSON de búsqueda admite un
    subtipo principal. Se fija la prioridad estudio, dúplex, piso tanto en
    entrenamiento como en evaluación, sin usar variables que no tendrá la API.
    ISINTOPFLOOR no se utiliza: última planta no demuestra que sea un ático.
    El conjunto no trae tipología bruta; esta reconstrucción es una asunción
    de compatibilidad con la API, no una etiqueta histórica comprobada.
    ``include_price`` sirve únicamente para evaluación/comparación, nunca features.
    """
    result = []
    for a in frame.to_dict("records"):
        sub = ("studio" if _number(a.get("ISSTUDIO")) == 1 else
               "duplex" if _number(a.get("ISDUPLEX")) == 1 else
               "flat")
        code = str(a.get("codigo_censal", ""))
        floor = _number(a.get("FLOORCLEAN"))
        lift, exterior = _number(a.get("HASLIFT")), _number(a.get("FLATLOCATIONID"))
        p = {
            "propertyCode": str(a.get("ASSETID", "")),
            "size": _number(a.get("CONSTRUCTEDAREA")),
            "rooms": None if pd.isna(a.get("ROOMNUMBER")) else _number(a.get("ROOMNUMBER")),
            "bathrooms": None if pd.isna(a.get("BATHNUMBER")) else _number(a.get("BATHNUMBER")),
            "floor": str(floor) if math.isfinite(floor) else None,
            "hasLift": bool(lift) if math.isfinite(lift) else None,
            "exterior": True if exterior == 1 else (False if exterior == 2 else None),
            "latitude": _number(a.get("LATITUDE")), "longitude": _number(a.get("LONGITUDE")),
            "municipality": "Madrid" if code.startswith("28079") else None,
            "propertyType": sub, "detailedType": {"typology": "flat", "subTypology": sub},
        }
        if include_price:
            p["price"] = _number(a.get("PRICE"))
        result.append(p)
    return result


def validate_payload(a: dict) -> dict:
    """Comprueba campos observables sin consultar precio ni estado del fit."""
    if _normal(a.get("municipality")) != "madrid":
        raise OutOfDomainError("Solo se admiten anuncios que indiquen municipality='Madrid' (capital).")
    detail = a.get("detailedType") or {}
    if not isinstance(detail, dict):
        raise InputDataError("detailedType debe ser un objeto o null.")
    typ, detail_typ = _normal(a.get("propertyType")), _normal(detail.get("typology"))
    sub = _normal(detail.get("subTypology"))
    allowed = {"flat", "studio", "duplex", "penthouse", "piso", "estudio", "atico"}
    if typ not in allowed and not (typ in {"", "homes"} and detail_typ in allowed):
        raise OutOfDomainError("El modelo solo admite pisos, estudios, dúplex y áticos; no casas/chalets.")
    if detail_typ and detail_typ not in allowed:
        raise OutOfDomainError("La tipología detallada contradice el dominio de pisos del modelo.")
    if sub and sub not in allowed:
        raise OutOfDomainError(f"Subtipología no admitida: {sub}.")
    subtype = sub or (typ if typ not in {"", "homes", "flat", "piso"} else "")
    lat, lon = _number(a.get("latitude")), _number(a.get("longitude"))
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise InputDataError("El anuncio necesita latitude y longitude finitas.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise OutOfDomainError("Coordenadas fuera de los rangos geográficos válidos.")
    if not (BBOX["lat"][0] <= lat <= BBOX["lat"][1] and BBOX["lon"][0] <= lon <= BBOX["lon"][1]):
        raise OutOfDomainError("Geocodificación fuera del recorte amplio de estudio; no es un polígono municipal.")
    if haversine_km(lat, lon, *SOL) > MAX_CITY_RADIUS_KM:
        raise OutOfDomainError("Geocodificación alejada del ámbito de estudio de Madrid.")
    vals = {"size": _number(a.get("size")), "rooms": _number(a.get("rooms")),
            "bathrooms": _number(a.get("bathrooms")), "floor": parsea_planta(a.get("floor"))}
    if not math.isfinite(vals["size"]):
        raise InputDataError("El anuncio necesita size (superficie construida) finita.")
    for field, x in vals.items():
        raw_value = a.get(field)
        if field in {"rooms", "bathrooms"} and raw_value is not None and not math.isfinite(x):
            raise InputDataError(f"{field} debe ser un número entero finito o null.")
        if math.isfinite(x) and not LIMITS[field][0] <= x <= LIMITS[field][1]:
            raise OutOfDomainError(f"{field} fuera del dominio {LIMITS[field][0]}–{LIMITS[field][1]}.")
        if field in {"rooms", "bathrooms"} and math.isfinite(x) and x != int(x):
            raise InputDataError(f"{field} debe ser un número entero o null.")
    return {**vals, "latitude": lat, "longitude": lon, "subtype": subtype}


def historical_eligibility(frame: pd.DataFrame) -> tuple[np.ndarray, dict[str, int]]:
    """Filtro fijo previo al split. No calcula cuantiles ni consulta etiquetas."""
    mask, counts = [], {}
    for raw, p in zip(frame.to_dict("records"), historical_to_payloads(frame)):
        try:
            validate_payload(p)
            if not raw.get("barrio") or pd.isna(raw.get("barrio")) or pd.isna(raw.get("distrito")):
                raise InputDataError("Sin adscripción territorial histórica.")
            valid = True
        except ValueError as e:
            counts[str(e)] = counts.get(str(e), 0) + 1
            valid = False
        mask.append(valid)
    return np.asarray(mask, dtype=bool), counts


class ModelPipeline:
    """Preprocesador serializable en JSON, sin pickle ni datos de precios."""

    def __init__(self, max_support_distance_km: float = MAX_SUPPORT_DISTANCE_KM):
        self.max_support_distance_km = float(max_support_distance_km)
        self.columns = list(FEATURES)
        self.categoricals: dict[str, list] = {}
        self.medians: dict[str, float] = {}
        self.sections: list[dict] = []

    @staticmethod
    def _payloads(data) -> list[dict]:
        if isinstance(data, pd.DataFrame):
            return historical_to_payloads(data)
        return [data] if isinstance(data, dict) else list(data)

    def fit(self, historical_train: pd.DataFrame):
        """Ninguna fila de selección, calibración o evaluación debe entrar aquí."""
        valid, reasons = historical_eligibility(historical_train)
        if not valid.all() or len(historical_train) == 0:
            raise InputDataError(f"fit requiere filas históricas elegibles; exclusiones: {reasons}")
        raw = historical_train.copy()
        raw["codigo_censal"] = raw["codigo_censal"].astype(str)
        sections = []
        for code, g in raw.groupby("codigo_censal", sort=True, observed=True):
            sections.append({"codigo_censal": code,
                             "lat": float(g.LATITUDE.mean()), "lon": float(g.LONGITUDE.mean()),
                             "barrio": str(g.barrio.mode().iloc[0]),
                             "distrito": str(g.distrito.mode().iloc[0]), "n": int(len(g))})
        self.sections = sections
        self._refresh()
        rows, _ = self._raw_rows(self._payloads(historical_train), enforce_support=False)
        for col in DIRECT_NUMERIC:
            observed = pd.to_numeric(rows[col], errors="coerce").dropna()
            self.medians[col] = float(observed.median()) if len(observed) else 0.0
        for col in CATEGORICAL:
            self.categoricals[col] = sorted(set(rows[col].astype(str)) | {MISSING})
        return self

    def _refresh(self):
        self._lat = np.asarray([s["lat"] for s in self.sections], dtype=float)
        self._lon = np.asarray([s["lon"] for s in self.sections], dtype=float)

    def nearest(self, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self.sections:
            raise RuntimeError("Pipeline no ajustado: faltan secciones aprendidas de train.")
        inds, distances = [], []
        for start in range(0, len(lat), 512):
            d = haversine_km(np.asarray(lat[start:start+512])[:, None],
                             np.asarray(lon[start:start+512])[:, None], self._lat, self._lon)
            ix = np.argmin(d, axis=1)
            inds.extend(ix.tolist())
            distances.extend(d[np.arange(len(ix)), ix].tolist())
        return np.asarray(inds, dtype=int), np.asarray(distances)

    def _raw_rows(self, payloads: list[dict], enforce_support: bool = True):
        validated = [validate_payload(a) for a in payloads]
        inds, distances = self.nearest(np.asarray([v["latitude"] for v in validated]),
                                      np.asarray([v["longitude"] for v in validated]))
        rows, meta = [], []
        for a, v, ix, distance in zip(payloads, validated, inds, distances):
            if enforce_support and distance > self.max_support_distance_km:
                raise OutOfDomainError(f"A {distance:.2f} km del centroide de entrenamiento más cercano; "
                                       f"máximo {self.max_support_distance_km:g} km. No es un límite municipal.")
            sec = self.sections[ix]
            lift = a.get("hasLift")
            exterior = a.get("exterior")
            if lift is not None and not isinstance(lift, (bool, np.bool_)):
                raise InputDataError("hasLift debe ser booleano o null.")
            if exterior is not None and not isinstance(exterior, (bool, np.bool_)):
                raise InputDataError("exterior debe ser booleano o null.")
            f = {"CONSTRUCTEDAREA": v["size"], "ROOMNUMBER": v["rooms"],
                 "BATHNUMBER": v["bathrooms"], "FLOORCLEAN": v["floor"],
                 "LATITUDE": v["latitude"], "LONGITUDE": v["longitude"],
                 "HASLIFT": float(lift) if lift is not None else np.nan,
                 "ISSTUDIO": float(v["subtype"] in {"studio", "estudio"}) if v["subtype"] else np.nan,
                 "ISDUPLEX": float(v["subtype"] == "duplex") if v["subtype"] else np.nan,
                 "FLATLOCATIONID_cat": ("1" if bool(exterior) else "2") if exterior is not None else MISSING,
                 "barrio": sec["barrio"], "distrito": sec["distrito"]}
            for col in ["ROOMNUMBER", "BATHNUMBER", "FLOORCLEAN", "HASLIFT"]:
                f[col + "_ausente"] = float(not math.isfinite(f[col]))
            f["exterior_ausente"] = float(exterior is None)
            f["subtipo_ausente"] = float(not v["subtype"])
            rows.append(f)
            meta.append({"seccion_censal": sec["codigo_censal"], "barrio": sec["barrio"],
                         "distrito": sec["distrito"], "distancia_soporte_km": float(distance),
                         "asignacion_territorial": "centroide aproximado aprendido solo de train",
                         "campos_ausentes": [c.removesuffix("_ausente") for c in MISSING_FEATURES if f[c] == 1]})
        return pd.DataFrame(rows), meta

    def transform(self, data, *, enforce_support: bool = True) -> pd.DataFrame:
        if not self.medians:
            raise RuntimeError("Debe ejecutar fit antes de transform.")
        payloads = self._payloads(data)
        if not payloads:
            return pd.DataFrame(columns=self.columns)
        x, _ = self._raw_rows(payloads, enforce_support=enforce_support)
        for col in DIRECT_NUMERIC:
            x[col] = x[col].fillna(self.medians[col]).astype(float)
        rooms = x.ROOMNUMBER.clip(lower=1)
        x["m2_por_habitacion"] = x.CONSTRUCTEDAREA / rooms
        x["banos_por_habitacion"] = x.BATHNUMBER / rooms
        x["es_bajo"] = (x.FLOORCLEAN <= 0).astype(float)
        x["x_km"] = (x.LONGITUDE + 3.70) * 111.32 * np.cos(np.radians(40.42))
        x["y_km"] = (x.LATITUDE - 40.42) * 110.57
        x["DISTANCE_TO_CITY_CENTER"] = haversine_km(x.LATITUDE, x.LONGITUDE, *SOL)
        x["log_dist_centro"] = np.log1p(x.DISTANCE_TO_CITY_CENTER)
        for col, categories in self.categoricals.items():
            x[col] = pd.Categorical(x[col].where(x[col].isin(categories), MISSING), categories=categories)
        return x[self.columns].copy()

    def metadata(self, data, *, enforce_support: bool = True) -> list[dict]:
        return self._raw_rows(self._payloads(data), enforce_support=enforce_support)[1]

    def fit_transform(self, historical_train: pd.DataFrame) -> pd.DataFrame:
        return self.fit(historical_train).transform(historical_train)

    def to_dict(self) -> dict:
        return {"version": PIPELINE_VERSION, "columnas": self.columns,
                "categoricas": self.categoricals, "medianas": self.medians,
                "secciones": self.sections, "max_support_distance_km": self.max_support_distance_km,
                "dominio": {"municipality": "Madrid", "tipos": ["flat", "studio", "duplex", "penthouse"],
                            "limites": LIMITS, "recorte_geocodificacion": BBOX, "radio_geocodificacion_km": MAX_CITY_RADIUS_KM,
                            "es_poligono_municipal": False},
                "estadisticas_aprendidas_de": "fit exclusivamente; sin PRICE ni alquiler"}

    def save(self, path: str | Path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path):
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        if state["version"] != PIPELINE_VERSION or state["columnas"] != FEATURES:
            raise ValueError("Versión o columnas del pipeline incompatibles; reentrene/exporte juntos.")
        obj = cls(state["max_support_distance_km"])
        obj.columns = state["columnas"]
        obj.categoricals = state["categoricas"]
        obj.medians = state["medianas"]
        obj.sections = state["secciones"]
        obj._refresh()
        return obj
