"""Reconstrucción de variables y ajuste de precios durante la inferencia.

Las geometrías, puntos de interés, variables de barrio e índices se leen del
paquete instalado. Los cálculos incluyen distancias, asignación de barrio,
atributos del anuncio, venta indexada y renta mensual.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from .amenidades_descripcion import AMENIDADES_API_NO_DEVUELVE
from .amenidades_descripcion import aplicar as aplicar_amenidades


CRS_UTM = 25830
RADIO_TIERRA_KM = 6371.0088
PLANTAS_TEXTO = {"bj": 0, "en": 0, "ss": -1, "st": -1}
VARIABLES_BARRIO = ["alq_mediana_eur_m2_barrio", "delitos_per_10k_barrio", "indice_vulnerabilidad"]
TIPOS_CASA = {"chalet", "countryHouse"}
SUBTIPOS_CASA = {"independantHouse", "semidetachedHouse", "terracedHouse"}


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(a))


def _distancia_minima(lat: np.ndarray, lon: np.ndarray, puntos: pd.DataFrame, bloque: int = 2000) -> np.ndarray:
    plat, plon = puntos["Lat"].to_numpy()[None, :], puntos["Lon"].to_numpy()[None, :]
    salida = np.empty(len(lat))
    for i in range(0, len(lat), bloque):
        tramo = slice(i, i + bloque)
        salida[tramo] = haversine_km(lat[tramo, None], lon[tramo, None], plat, plon).min(axis=1)
    return salida


def calcular_distancias(lat, lon, pois: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    centro = pois["City_Center"]
    return pd.DataFrame({
        "DISTANCE_TO_CITY_CENTER": haversine_km(lat, lon, centro["Lat"].iloc[0], centro["Lon"].iloc[0]),
        "DISTANCE_TO_METRO": _distancia_minima(lat, lon, pois["Metro"]),
        "DISTANCE_TO_CASTELLANA": _distancia_minima(lat, lon, pois["Castellana"]),
    })


def asignar_barrio(lat, lon, barrios: gpd.GeoDataFrame, max_rescate_m: float = 500) -> pd.DataFrame:
    """Barrio y distrito por punto; `barrio_rescatado` marca los asignados por cercanía."""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    validas = np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
    if not validas.all():
        resultado = pd.DataFrame({"barrio_code": pd.Series([None] * len(lat), dtype=object),
                                  "distrito_code": pd.Series([None] * len(lat), dtype=object),
                                  "barrio_rescatado": False})
        if validas.any():
            resultado.loc[validas, :] = asignar_barrio(lat[validas], lon[validas], barrios, max_rescate_m).to_numpy()
        return resultado
    puntos = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)), crs=4326,
    ).to_crs(CRS_UTM)
    capa = barrios[["barrio_code", "geometry"]]
    dentro = gpd.sjoin(puntos, capa, how="left", predicate="within")
    barrio = dentro[~dentro.index.duplicated()]["barrio_code"].reindex(puntos.index)
    fuera = barrio.isna()
    if fuera.any():
        cercano = gpd.sjoin_nearest(puntos.loc[fuera], capa, how="left", max_distance=max_rescate_m)
        barrio.loc[fuera] = cercano[~cercano.index.duplicated()]["barrio_code"]
    return pd.DataFrame({
        "barrio_code": barrio.to_numpy(),
        "distrito_code": barrio.str[:2].to_numpy(),
        "barrio_rescatado": (fuera & barrio.notna()).to_numpy(),
    })


def _columna(df: pd.DataFrame, nombre: str, defecto=np.nan) -> pd.Series:
    return df[nombre] if nombre in df.columns else pd.Series(defecto, index=df.index, dtype=object)


def parsear_planta(planta) -> float:
    """Código de planta de idealista a número; NaN si no se puede interpretar."""
    if not isinstance(planta, str):
        return np.nan
    texto = planta.strip().lower()
    if texto in PLANTAS_TEXTO:
        return float(PLANTAS_TEXTO[texto])
    try:
        return float(int(texto))
    except ValueError:
        return np.nan


def construir_variables(anuncios: pd.DataFrame, columnas_modelo: list[str], tabla_barrio: pd.DataFrame,
                        pois: dict[str, pd.DataFrame], barrios: gpd.GeoDataFrame,
                        mediana_planta: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    `anuncios`: respuesta de la API aplanada con `pd.json_normalize`.
    Devuelve la matriz con las columnas y el orden del modelo, y un `contexto` por anuncio
    (identificación, precio anunciado, barrio y marcas de cómo se construyó cada fila).
    """
    df = anuncios.reset_index(drop=True)
    X = pd.DataFrame(index=df.index)
    X["CONSTRUCTEDAREA"] = pd.to_numeric(_columna(df, "size"), errors="coerce")
    X["ROOMNUMBER"] = pd.to_numeric(_columna(df, "rooms"), errors="coerce")
    X["BATHNUMBER"] = pd.to_numeric(_columna(df, "bathrooms"), errors="coerce")

    amenidades = aplicar_amenidades(pd.DataFrame({"description": _columna(df, "description", None)}))
    for amenidad in AMENIDADES_API_NO_DEVUELVE:
        X[amenidad] = amenidades[amenidad].astype(int)

    ascensor_api = _columna(df, "hasLift")
    X["HASLIFT"] = ascensor_api.where(ascensor_api.notna(), amenidades["HASLIFT"]).astype(bool).astype(int)
    garaje_api = _columna(df, "parkingSpace.hasParkingSpace")
    X["HASPARKINGSPACE"] = garaje_api.where(garaje_api.notna(), False).astype(bool).astype(int)

    subtipo = _columna(df, "detailedType.subTypology", "")
    tipo = _columna(df, "propertyType", "")
    X["ISDUPLEX"] = (subtipo.eq("duplex") | tipo.eq("duplex")).astype(int)
    X["ISSTUDIO"] = (subtipo.eq("studio") | tipo.eq("studio")).astype(int)

    planta = _columna(df, "floor", None).map(parsear_planta)
    X["FLOORCLEAN"] = planta.fillna(mediana_planta)

    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    distancias = calcular_distancias(lat, lon, pois)
    for columna in distancias.columns:
        X[columna] = distancias[columna].to_numpy()

    barrio = asignar_barrio(lat, lon, barrios)
    valores = tabla_barrio.reindex(barrio["barrio_code"])[VARIABLES_BARRIO]
    for columna in VARIABLES_BARRIO:
        X[columna] = valores[columna].to_numpy()

    faltan = set(columnas_modelo) - set(X.columns)
    if faltan:
        raise ValueError(f"variables del modelo sin construir: {sorted(faltan)}")

    contexto = pd.DataFrame({
        "propertyCode": _columna(df, "propertyCode"),
        "precio_anunciado": pd.to_numeric(_columna(df, "price"), errors="coerce"),
        "barrio_code": barrio["barrio_code"],
        "distrito_code": barrio["distrito_code"],
        "barrio_rescatado": barrio["barrio_rescatado"],
        "sin_barrio": barrio["barrio_code"].isna(),
        "planta_imputada": planta.isna(),
        "ascensor_desde_descripcion": ascensor_api.isna(),
        "sin_descripcion": amenidades["sin_descripcion"],
    })
    return X[list(columnas_modelo)], contexto


def motivos_fuera_de_dominio(anuncios: pd.DataFrame, X: pd.DataFrame, area_max: float) -> pd.DataFrame:
    """
    Por anuncio, las razones para no valorarlo aunque tenga todos los datos:
    `tipologia_casa` (chalet o casa: el modelo no ve la parcela) y `superficie_fuera_de_dominio`
    (superficie por encima de `area_max`, el percentil 99 de train: sin soporte y los árboles
    no extrapolan).
    """
    df = anuncios.reset_index(drop=True)
    casa = (_columna(df, "propertyType", "").isin(TIPOS_CASA)
            | _columna(df, "detailedType.subTypology", "").isin(SUBTIPOS_CASA))
    return pd.DataFrame({
        "tipologia_casa": casa.to_numpy(dtype=bool),
        "superficie_fuera_de_dominio": (X["CONSTRUCTEDAREA"] > area_max).to_numpy(dtype=bool),
    }, index=X.index)


def fuera_de_rango(X: pd.DataFrame, rangos_train: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Por variable, si el valor queda fuera del [mínimo, máximo] visto en train."""
    return pd.DataFrame({
        c: (X[c] < rangos_train[c]["min"]) | (X[c] > rangos_train[c]["max"])
        for c in X.columns if c in rangos_train
    })


def predecir_precio_base(modelo, X: pd.DataFrame, smearing: float) -> np.ndarray:
    """Precio en euros al nivel de los datos de entrenamiento (2018), con la corrección de Duan."""
    return np.exp(modelo.predict(X)) * smearing


def ajustar_precio(precio_base, distrito_code, indices: pd.DataFrame) -> pd.DataFrame:
    """Precio en el año de destino (índice de venta del distrito) y renta mensual estimada."""
    tabla = indices.set_index("distrito_code")
    distrito = pd.Series(np.asarray(distrito_code, dtype=object))
    indice = distrito.map(tabla["indice_venta"]).to_numpy(dtype=float)
    factor = distrito.map(tabla["factor_renta_mensual"]).to_numpy(dtype=float)
    precio_destino = np.asarray(precio_base, dtype=float) * indice
    return pd.DataFrame({
        "indice_venta": indice,
        "precio_estimado_destino": precio_destino,
        "factor_renta_mensual": factor,
        "renta_mensual_estimada": precio_destino * factor,
    })
