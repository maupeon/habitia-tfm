"""Inferencia del paquete XGBoost entrenado para viviendas de Madrid.

Carga los seis artefactos instalados y calcula venta, renta mensual y calidad de
las entradas. La API utiliza RuntimePredictor para validar el contrato y los hashes.

Uso por lotes: python -m predictor_v3.predictor predecir anuncios.json -o predicciones.csv
El entrenamiento y la exportación originales se conservan en el paquete de Tomás.
"""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xgboost as xgb

from . import produccion as prod


RAIZ = Path(__file__).resolve().parents[1]
RUTA_PAQUETE = RAIZ / "servicio" / "artefactos_v3"
VERSION_PAQUETE = 3
COLUMNAS_API = ["propertyCode", "operation", "propertyType", "price", "size", "rooms", "bathrooms",
                "latitude", "longitude", "detailedType.subTypology"]
OBLIGATORIAS = {"CONSTRUCTEDAREA": "sin_superficie", "ROOMNUMBER": "sin_habitaciones", "BATHNUMBER": "sin_banos"}
COLUMNAS_SALIDA = ["propertyCode", "propertyType", "valido", "motivo_no_valido", "barrio_code", "distrito_code",
                   "precio_anunciado", "precio_estimado_base", "indice_venta", "precio_estimado",
                   "factor_renta_mensual", "renta_mensual_estimada", "anunciado_sobre_estimado", "fuera_de_rango",
                   "barrio_rescatado", "planta_imputada", "ascensor_desde_descripcion", "sin_descripcion",
                   "ano_base", "ano_precio", "ano_renta", "modelo"]


def leer_anuncios(anuncios) -> pd.DataFrame:
    """
    Acepta: ruta a un JSON, dict de caché del 08 (`anuncios`), respuesta cruda de la API
    (`elementList`), un único anuncio, lista de anuncios o DataFrame (anidado o ya aplanado).
    """
    if isinstance(anuncios, (str, Path)):
        anuncios = json.loads(Path(anuncios).read_text(encoding="utf-8"))
    if isinstance(anuncios, dict):
        anuncios = anuncios.get("anuncios", anuncios.get("elementList", [anuncios]))
    registros = anuncios.to_dict("records") if isinstance(anuncios, pd.DataFrame) else list(anuncios)
    df = pd.json_normalize(registros)
    for columna in COLUMNAS_API:
        if columna not in df.columns:
            df[columna] = np.nan
    return df.reset_index(drop=True)


class PredictorHabitia:
    """Carga el paquete una vez y predice lotes de anuncios."""

    def __init__(self, modelo, metadatos: dict, barrios: gpd.GeoDataFrame, pois: dict[str, pd.DataFrame],
                 tabla_barrio: pd.DataFrame, indices: pd.DataFrame):
        self.modelo = modelo
        self.metadatos = metadatos
        self.columnas = metadatos["columnas"]
        self.barrios = barrios
        self.pois = pois
        self.tabla_barrio = tabla_barrio
        self.indices = indices

    @classmethod
    def cargar(cls, carpeta: Path = RUTA_PAQUETE) -> "PredictorHabitia":
        carpeta = Path(carpeta)
        metadatos = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
        if metadatos.get("version_paquete") != VERSION_PAQUETE:
            raise ValueError(f"paquete de versión {metadatos.get('version_paquete')}, se esperaba {VERSION_PAQUETE}")
        modelo = xgb.XGBRegressor()
        modelo.load_model(carpeta / "modelo.json")
        pois = pd.read_parquet(carpeta / "pois.parquet")
        return cls(
            modelo=modelo,
            metadatos=metadatos,
            barrios=gpd.read_parquet(carpeta / "barrios.parquet"),
            pois={t: g[["Lon", "Lat"]].reset_index(drop=True) for t, g in pois.groupby("tipo")},
            tabla_barrio=pd.read_parquet(carpeta / "variables_barrio.parquet").set_index("barrio_code"),
            indices=pd.read_parquet(carpeta / "indices_distrito.parquet"),
        )

    def preparar(self, anuncios) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Matriz del modelo, contexto de construcción y anuncios aplanados."""
        df = leer_anuncios(anuncios)
        X, contexto = prod.construir_variables(df, self.columnas, self.tabla_barrio, self.pois, self.barrios,
                                               self.metadatos["mediana_planta_train"])
        return X, contexto, df

    def predecir(self, anuncios, incluir_variables: bool = False) -> pd.DataFrame:
        X, contexto, df = self.preparar(anuncios)
        if X.empty:
            return pd.DataFrame(columns=COLUMNAS_SALIDA + ([f"x_{c}" for c in self.columnas] if incluir_variables else []))
        lat = pd.to_numeric(df["latitude"], errors="coerce")
        lon = pd.to_numeric(df["longitude"], errors="coerce")
        sin_coordenadas = ~np.isfinite(lat) | ~np.isfinite(lon) | lat.abs().gt(90) | lon.abs().gt(180)

        problemas = pd.DataFrame({
            "operacion_no_admitida": ~df["operation"].isin(["sale", "rent"]),
            "sin_coordenadas": sin_coordenadas,
            "fuera_de_madrid": contexto["sin_barrio"] & ~sin_coordenadas,
            **{motivo: ~np.isfinite(X[columna]) | (X[columna] < 0) for columna, motivo in OBLIGATORIAS.items()},
        })
        problemas["sin_superficie"] |= X["CONSTRUCTEDAREA"].le(0)
        problemas = problemas.join(prod.motivos_fuera_de_dominio(df, X, self.metadatos["area_max_dominio"]))
        motivo = pd.Series([";".join(problemas.columns[fila]) for fila in problemas.to_numpy(dtype=bool)],
                           index=X.index, dtype=object)
        valido = motivo.eq("")

        fuera = prod.fuera_de_rango(X, self.metadatos["rangos_train"])
        base = np.full(len(X), np.nan)
        if valido.any():
            base[valido] = prod.predecir_precio_base(self.modelo, X.loc[valido], self.metadatos["smearing"])
        ajuste = prod.ajustar_precio(base, contexto["distrito_code"], self.indices)

        salida = pd.DataFrame({
            "propertyCode": contexto["propertyCode"],
            "propertyType": df["propertyType"],
            "valido": valido,
            "motivo_no_valido": motivo.mask(valido),
            "barrio_code": contexto["barrio_code"],
            "distrito_code": contexto["distrito_code"],
            "precio_anunciado": contexto["precio_anunciado"],
            "precio_estimado_base": base,
            "indice_venta": ajuste["indice_venta"],
            "precio_estimado": ajuste["precio_estimado_destino"],
            "factor_renta_mensual": ajuste["factor_renta_mensual"],
            "renta_mensual_estimada": ajuste["renta_mensual_estimada"],
        })
        # El modelo estima venta; para alquiler se compara la mensualidad con
        # la renta derivada por el paquete, nunca con el valor total de venta.
        referencia = salida["precio_estimado"].where(df["operation"].eq("sale"), salida["renta_mensual_estimada"])
        salida["anunciado_sobre_estimado"] = salida["precio_anunciado"] / referencia
        estimaciones = ["precio_estimado_base", "indice_venta", "precio_estimado", "factor_renta_mensual",
                        "renta_mensual_estimada", "anunciado_sobre_estimado"]
        salida.loc[~valido, estimaciones] = np.nan

        salida["fuera_de_rango"] = [";".join(fuera.columns[fila]) or None for fila in fuera.to_numpy(dtype=bool)]
        for marca in ["barrio_rescatado", "planta_imputada", "ascensor_desde_descripcion", "sin_descripcion"]:
            salida[marca] = contexto[marca].to_numpy()
        salida["ano_base"] = self.metadatos["ano_base"]
        salida["ano_precio"] = self.metadatos["ano_precio"]
        salida["ano_renta"] = self.metadatos["ano_renta"]
        salida["modelo"] = self.metadatos["nombre"]
        if incluir_variables:
            salida = pd.concat([salida, X.add_prefix("x_")], axis=1)
        return salida


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m predictor_v3.predictor", description=__doc__.split("\n\n")[0])
    ordenes = parser.add_subparsers(dest="orden", required=True)
    predecir = ordenes.add_parser("predecir", help="predice un JSON de anuncios")
    predecir.add_argument("entrada", type=Path)
    predecir.add_argument("-o", "--salida", type=Path, required=True, help=".csv o .parquet")
    predecir.add_argument("--paquete", type=Path, default=RUTA_PAQUETE)
    predecir.add_argument("--con-variables", action="store_true", help="añade la matriz del modelo (x_*)")
    args = parser.parse_args(argv)
    resultado = PredictorHabitia.cargar(args.paquete).predecir(args.entrada, incluir_variables=args.con_variables)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    if args.salida.suffix == ".parquet":
        resultado.to_parquet(args.salida, index=False)
    else:
        resultado.to_csv(args.salida, index=False)
    print(f"{len(resultado)} anuncios ({int(resultado['valido'].sum())} válidos) -> {args.salida}")


if __name__ == "__main__":
    main()
