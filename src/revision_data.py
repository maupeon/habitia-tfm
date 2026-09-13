"""Carga trazable para la revisión de 2026-09-08, sin parámetros aprendidos.

Conserva observaciones distintas del mismo ASSETID. Los campos catastrales
originales se mantienen para auditoría, pero su disponibilidad en 2018 no está
verificada: el entrenador debe excluirlos de su protocolo temporal principal.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "habitia_madrid_2018.parquet"

ORIGINAL_COLUMNS = [
    "ASSETID", "PERIOD", "PRICE", "UNITPRICE", "CONSTRUCTEDAREA", "ROOMNUMBER",
    "BATHNUMBER", "HASTERRACE", "HASLIFT", "HASAIRCONDITIONING", "AMENITYID",
    "HASPARKINGSPACE", "ISPARKINGSPACEINCLUDEDINPRICE", "PARKINGSPACEPRICE",
    "HASNORTHORIENTATION", "HASSOUTHORIENTATION", "HASEASTORIENTATION",
    "HASWESTORIENTATION", "HASBOXROOM", "HASWARDROBE", "HASSWIMMINGPOOL",
    "HASDOORMAN", "HASGARDEN", "ISDUPLEX", "ISSTUDIO", "ISINTOPFLOOR",
    "CONSTRUCTIONYEAR", "FLOORCLEAN", "FLATLOCATIONID", "CADCONSTRUCTIONYEAR",
    "CADMAXBUILDINGFLOOR", "CADDWELLINGCOUNT", "CADASTRALQUALITYID",
    "BUILTTYPEID_1", "BUILTTYPEID_2", "BUILTTYPEID_3", "DISTANCE_TO_CITY_CENTER",
    "DISTANCE_TO_METRO", "DISTANCE_TO_CASTELLANA", "LONGITUDE", "LATITUDE",
]

# Únicamente para agrupar o diagnosticar; no se exige adscripción territorial.
TERRITORIAL_COLUMNS = [
    "codigo_censal", "barrio", "distrito", "seccion_rescatada", "sec_dist_borde_m",
    "sec_dudosa",
]
CADASTRAL_COLUMNS = [
    "CADCONSTRUCTIONYEAR", "CADMAXBUILDINGFLOOR", "CADDWELLINGCOUNT",
    "CADASTRALQUALITYID",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _summary(frame: pd.DataFrame) -> dict:
    groups = frame.groupby("ASSETID", observed=True, dropna=False)
    sizes = groups.size()
    return {
        "rows": int(len(frame)),
        "assets": int(frame.ASSETID.nunique(dropna=True)),
        "assets_with_multiple_rows": int((sizes > 1).sum()),
        "assets_in_multiple_periods": int((groups.PERIOD.nunique(dropna=False) > 1).sum()),
        "period_counts": {
            str(period): int(count)
            for period, count in frame.PERIOD.value_counts(dropna=False).sort_index().items()
        },
    }


def _valid_numeric(series: pd.Series, low: float | None = None,
                   high: float | None = None, *, allow_missing: bool = False,
                   strictly_positive: bool = False) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid = pd.Series(np.isfinite(values.to_numpy(dtype=float, na_value=np.nan)),
                      index=series.index)
    if low is not None:
        valid &= values.ge(low).fillna(False)
    if high is not None:
        valid &= values.le(high).fillna(False)
    if strictly_positive:
        valid &= values.gt(0).fillna(False)
    if allow_missing:
        valid |= series.isna()  # Un texto mal formado no se transforma en nulo admisible.
    return valid.fillna(False)


def load_revision_data(path: str | Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Lee el parquet, elimina duplicaciones de enriquecimiento y valida dominio.

    Los límites son fijos y no dependen del precio de entrenamiento o test.
    `source_row_id` es la posición (base cero) en el parquet original. Para dos
    filas idénticas sobre las 41 originales, conservar la primera no decide entre
    precios distintos: son iguales. Todo conflicto de extras se registra, y los
    extras conflictivos se anulan si fueran campos territoriales conservados.
    Los alquileres y sus derivados no se devuelven.
    """
    source = Path(path) if path is not None else DEFAULT_DATA
    raw = pd.read_parquet(source)
    missing = [column for column in ORIGINAL_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(f"Faltan columnas originales requeridas: {', '.join(missing)}")
    if not raw.columns.is_unique:
        raise ValueError("El parquet contiene nombres de columna duplicados")
    if "source_row_id" in raw.columns:
        raise ValueError("source_row_id está reservado para la posición del parquet original")

    raw = raw.reset_index(drop=True)
    input_columns = list(raw.columns)
    raw["source_row_id"] = np.arange(len(raw), dtype=np.int64)
    extras = [column for column in input_columns if column not in ORIGINAL_COLUMNS]
    returned = ORIGINAL_COLUMNS + [c for c in TERRITORIAL_COLUMNS if c in raw.columns]
    duplicate_mask = raw.duplicated(ORIGINAL_COLUMNS, keep=False)
    merged_rows = []
    conflict_counts: dict[str, int] = {}
    territorial_conflicts: list[tuple[int, str]] = []
    for _, group in raw.loc[duplicate_mask].groupby(
            ORIGINAL_COLUMNS, observed=True, dropna=False, sort=False):
        row_ids = group.source_row_id.astype(int).tolist()
        conflicts = [c for c in extras if group[c].nunique(dropna=False) > 1]
        for column in conflicts:
            conflict_counts[column] = conflict_counts.get(column, 0) + 1
            if column in TERRITORIAL_COLUMNS:
                territorial_conflicts.append((row_ids[0], column))
        merged_rows.append({
            "kept_source_row_id": row_ids[0],
            "removed_source_row_ids": row_ids[1:],
            "conflicting_extra_columns": conflicts,
        })
    frame = raw.drop_duplicates(ORIGINAL_COLUMNS, keep="first")[returned + ["source_row_id"]].copy()
    for row_id, column in territorial_conflicts:
        frame.loc[row_id, column] = pd.NA

    dedup_summary = _summary(frame)
    audit = {
        "schema_version": "revision_data/1.0",
        "dataset": {
            "path": str(source.resolve()), "sha256": _sha256(source),
            "bytes": source.stat().st_size, "rows_input": len(raw),
            "columns_input": input_columns, "original_columns": list(ORIGINAL_COLUMNS),
            "returned_columns": list(frame.columns),
            "excluded_extra_columns": [c for c in extras if c not in TERRITORIAL_COLUMNS],
        },
        "deduplication": {
            "key_columns": list(ORIGINAL_COLUMNS),
            "groups_merged": len(merged_rows),
            "rows_removed": int(len(raw) - len(frame)),
            "merged_rows": merged_rows,
            "conflicting_extra_columns": conflict_counts,
            "territorial_conflict_policy": "set_missing_and_audit",
        },
        "after_deduplication": dedup_summary,
        "exclusions": [],
        "temporal_provenance": {
            "PERIOD": "trimestre de extracción del anuncio; no fecha exacta ni transacción",
            "rental_reference_date": "unverified; rental columns excluded",
            "cadastral_as_of_2018": "unverified; exclude from principal temporal model",
            "cadastral_columns": list(CADASTRAL_COLUMNS),
            "territorial_layer_date": "unverified; retained for diagnostics",
            "coordinates": "masked; source preserves neighborhood, not census section",
            "property_type": "not recorded; ISINTOPFLOOR is top-floor flag, not penthouse type",
        },
        "target_policy": "finite PRICE > 0; no price quantiles or target-dependent trimming",
        "missing_policy": "no imputation; rooms, bathrooms and floor may be missing",
    }

    def retain(reason: str, valid: pd.Series) -> None:
        nonlocal frame
        rejected = frame.loc[~valid.fillna(False), "source_row_id"].astype(int).tolist()
        frame = frame.loc[valid.fillna(False)].copy()
        audit["exclusions"].append({
            "reason": reason, "rows_removed": len(rejected),
            "source_row_ids": rejected, "rows_remaining": len(frame),
        })

    ids = frame.ASSETID.astype("string")
    retain("invalid_assetid", ids.notna() & ids.str.strip().ne(""))
    retain("invalid_price", _valid_numeric(frame.PRICE, strictly_positive=True))
    retain("area_outside_20_1000", _valid_numeric(frame.CONSTRUCTEDAREA, 20, 1000))
    retain("coordinates_outside_madrid_bbox",
           _valid_numeric(frame.LATITUDE, 40.30, 40.55)
           & _valid_numeric(frame.LONGITUDE, -3.90, -3.50))
    retain("rooms_outside_0_12", _valid_numeric(frame.ROOMNUMBER, 0, 12, allow_missing=True))
    retain("bathrooms_outside_0_10", _valid_numeric(frame.BATHNUMBER, 0, 10, allow_missing=True))
    retain("floor_outside_minus2_40", _valid_numeric(frame.FLOORCLEAN, -2, 40, allow_missing=True))
    frame["ASSETID"] = frame.ASSETID.astype(str)
    frame = frame.reset_index(drop=True)
    audit["output"] = _summary(frame)
    audit["rows_excluded_by_validation"] = int(dedup_summary["rows"] - len(frame))
    return frame, audit


def asset_weights(frame: pd.DataFrame) -> np.ndarray:
    """Pesos de media 1; cada ASSETID suma n_filas/n_activos.

    Se calculan sobre la partición recibida, no antes del split. No convierten
    filas repetidas en observaciones independientes para calibración conformal.
    """
    if frame.empty:
        return np.empty(0, dtype=float)
    if "ASSETID" not in frame:
        raise ValueError("Se requiere ASSETID para ponderar por activo")
    ids = frame.ASSETID.astype("string")
    if ids.isna().any() or ids.str.strip().eq("").any():
        raise ValueError("ASSETID debe estar informado para ponderar por activo")
    sizes = frame.groupby("ASSETID", observed=True)["ASSETID"].transform("size").to_numpy(dtype=float)
    return len(frame) / (frame.ASSETID.nunique() * sizes)
