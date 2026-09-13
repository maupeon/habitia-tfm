# HabitIA · modelo y entrega académica del TFM

Evaluación retrospectiva de **precios anunciados de vivienda en Madrid (2018)**. Este repositorio reúne el código Python vigente, el cuaderno ejecutado, las pruebas y los resultados de la revisión del 8 de septiembre de 2026.

Trabajo Fin de Máster de Big Data, Data Science e Inteligencia Artificial, Universidad Complutense de Madrid, curso 2025–2026.

**Equipo:** Mauricio Peón García · João Paulo Nogueira Cunha · Manuel Macedo Púlido · Aldo Mauricio Ress Villets · Tomás Perales Lara. **Tutores:** Carlos Ortega y Santiago Mota.

## 1. Empezar por aquí

- **Leer el estudio:** memoria, anexos, presentación y HTML del notebook en la [entrega versionada](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-13).
- **Ver el código y las salidas:** [notebook ejecutado](TFM_HabitIA_entrenamiento.ipynb).
- **Arrancar el modelo:** seguir el apartado 4 y [el contrato HTTP](servicio/README.md).
- **Repetir el estudio:** [guía de reproducción](docs/reproduccion.md), con el fichero de entrada custodiado por el equipo.
- **Aplicación web:** [repositorio independiente](https://github.com/maupeon/agente-inmobiliario) · [demo](https://habitiaucm.vercel.app) · [presentación interactiva](https://habitiaucm.vercel.app/presentacion).

Los repositorios y sus releases son privados. Los enlaces de GitHub requieren una cuenta con acceso. La entrega local incluye copias del código para poder revisarlo sin depender de esos permisos.

## 2. Qué resultados se pueden citar

| Evaluación | MdAPE | Observaciones evaluadas |
| --- | ---: | ---: |
| Referencia territorial, exterior agrupada | 15,41 % | 93.944 |
| Hedónico Ridge, exterior agrupada | 13,13 % | 93.944 |
| LightGBM, exterior agrupada | **10,31 %** | 93.944 |
| LightGBM del artefacto exportado, reserva fija | **10,25 %** | 18.782 |
| LightGBM, diagnóstico Q1–Q3 → Q4 de 2018 | 11,22 % | 43.839 |

MdAPE es el error porcentual absoluto **mediano**. La cobertura del artefacto final es 90,93 % por observación y 90,21 % por activo; la anchura relativa mediana del intervalo es 61,48 %. Se publican conjuntamente error, cobertura, anchura y abstenciones. Fuente: [resultados canónicos](revision_2026-09-08/experimento/resultados_revision.json).

El modelo utiliza 25 variables y agrupa todas las observaciones de cada inmueble. Estos resultados son retrospectivos sobre un histórico previamente explorado. **No validan precios de compraventa ni precisión en 2026.** El factor ×1,5534 es un escenario temporal explícito, no una nueva estimación validada. [Método y límites](docs/metodologia.md).

## 3. Estructura

```text
habitia-tfm/
├── README.md
├── TFM_HabitIA_entrenamiento.ipynb  # Cuaderno con salidas conservadas
├── src/
│   ├── revision_data.py            # Carga y auditoría de identidad
│   ├── model_pipeline.py           # Misma transformación al entrenar y servir
│   ├── train_revision.py           # Selección, calibración y evaluación
│   ├── valorador.py                # Inferencia e integridad del modelo
│   └── execute_revision_notebook.py
├── servicio/                      # API FastAPI y contenedor
├── tests/                         # Unitarias, particiones, paridad y HTTP
├── scripts/                       # Instalación verificada del artefacto
├── docs/                          # Reproducción, datos, método y producto
├── data/README.md                 # Identidad del dato; parquet excluido de Git
├── revision_2026-09-08/            # Evidencia canónica de la revisión
├── requirements_revision.txt      # Entorno del estudio
└── entorno_revision.lock.txt      # Inventario del entorno histórico
```

El nombre fechado de la carpeta del experimento se conserva para mantener las rutas del código y del notebook. Se excluyen scripts antiguos, duplicados de documentos, cachés, entornos, credenciales y artefactos obsoletos. Los modelos vigentes se descargan como un único ZIP de la release.

## 4. Arrancar la API sin el dataset

Requisitos: Python 3.12, `libomp` en macOS o `libgomp1` en Linux; GitHub CLI autenticado con acceso al repositorio para descargar el modelo. También se puede usar el ZIP de la entrega local.

```bash
git clone https://github.com/maupeon/habitia-tfm.git
cd habitia-tfm
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r servicio/requirements.txt

gh release download tfm-2026-09-13 --repo maupeon/habitia-tfm --pattern habitia-modelo-v2.zip
python scripts/install_artifacts.py habitia-modelo-v2.zip

VALORACION_TOKEN=habitia-local-review OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1   python -m uvicorn servicio.api:app --host 127.0.0.1 --port 8000 --workers 1
```

En otra terminal: `curl http://127.0.0.1:8000/salud`. El token mostrado es solo un ejemplo local; el servicio publicado necesita una credencial propia. No hace falta un dataset ni una clave de Idealista para ejecutar inferencia local. El servidor escucha únicamente en el equipo local.

Para conectar la web: `VALORACION_URL=http://127.0.0.1:8000`, el mismo `VALORACION_TOKEN` y `VALORACION_TIMEOUT_MS=4000`, configurados en el servidor Next.js. [Ejemplo de petición y errores](servicio/README.md).

## 5. Comprobaciones

```bash
python -m pip install -r requirements_revision.txt
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m unittest discover -s tests -v
python scripts/install_artifacts.py --check
```

Las pruebas unitarias usan datos sintéticos. La comprobación de particiones, la paridad de las 18.782 observaciones y la reejecución del notebook requieren el paquete privado de reproducción. No se inicia entrenamiento al importar el código ni al ejecutar las pruebas unitarias. [Comandos completos](docs/reproduccion.md).

## 6. Datos y disponibilidad

El parquet enriquecido, particiones y predicciones por anuncio se conservan **fuera de Git**. La fuente declarada es Idealista18 (Rey-Blanco et al., 2024), ODbL 1.0; el enriquecimiento local no puede reconstruirse desde las fuentes disponibles. El repositorio por sí solo permite leer resultados y ejecutar la API con su artefacto, pero no repetir todo el entrenamiento sin ese fichero. [Procedencia, hash y acceso](docs/datos.md).

La documentación del producto corresponde al código web entregado el 13 de septiembre. [Arquitectura y alcance](docs/producto.md) · [comprobaciones de esta entrega](docs/verificacion-entrega.md). Las métricas y el código científico se conservan; la normalización de rutas del equipo está registrada en [el manifiesto de procedencia](docs/procedencia-publicacion.json).
