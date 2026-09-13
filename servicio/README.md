# HabitIA: servicio del modelo de precio anunciado v2

Este servicio carga el mismo pipeline y los mismos tres modelos evaluados en el experimento reproducible. Estima precios anunciados de viviendas del histórico de Madrid de 2018. Su salida predeterminada está en ese nivel histórico; la indexación a 2026T1 es un escenario agregado explícito cuya precisión actual no se ha validado.

El modelo v2 fue publicado y verificado en Fly el 11 de septiembre de 2026, según el registro operativo del equipo. Esta distribución contiene su código y manifiesto; los modelos se instalan desde `habitia-modelo-v2.zip` mediante `python scripts/install_artifacts.py habitia-modelo-v2.zip`, desde la raíz del repositorio.

## Resultados del artefacto instalado

Fuente: `servicio/manifiesto.json`, campo `metricas_test`. Son resultados retrospectivos en datos de 2018 ya explorados; no constituyen una validación externa nueva.

| Medida | Resultado |
|---|---:|
| Variables del pipeline compartido | 25 |
| Observaciones evaluadas tras abstenciones | 18.782 |
| Activos distintos evaluados | 15.031 |
| Error porcentual absoluto mediano, MdAPE | 10,251 % |
| Error porcentual absoluto medio, MAPE | 14,549 % |
| Error absoluto mediano | 26.439 € |
| Predicciones dentro de ±10 % | 49,100 % |
| Predicciones dentro de ±20 % | 76,898 % |
| Cobertura del intervalo por observación | 90,933 % |
| Cobertura de todos los registros de cada activo | 90,214 % |
| Anchura relativa mediana del intervalo | 61,482 % |
| Predicciones puntuales fuera del intervalo | 0 |
| Intervalos invertidos | 0 |

La partición reservada contenía inicialmente 18.798 observaciones: 16 quedaron fuera del soporte espacial del modelo. El ajuste utilizó 60.166 observaciones de 48.144 activos; la calibración aceptó 15.049 observaciones de 12.029 activos. La corrección conformal se calculó sobre el máximo residual de cada activo, con nivel nominal del 90 % y `Q=0.049389109739086834` en escala logarítmica.

El servicio reprodujo **las 18.782 observaciones reservadas**, tanto precio como ambos límites, exactamente tras redondear al euro. Evidencia: `revision_2026-09-08/paridad_toda_evaluacion.json`. Esta paridad confirma que se sirve el modelo evaluado; no añade otra estimación independiente de precisión.

## Preparar y ejecutar en local

Desde la raíz de `habitia-tfm`, con Python 3.12:

```bash
python3.12 -m venv .venv-runtime
.venv-runtime/bin/python -m pip install -r servicio/requirements.txt

VALORACION_TOKEN=habitia-local-review \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
.venv-runtime/bin/python -m uvicorn servicio.api:app \
  --host 127.0.0.1 --port 8000 --workers 1
```

`habitia-local-review` es exclusivamente un token de pruebas locales. Para un servicio publicado se debe configurar una credencial propia en su entorno y la misma en el backend de Next.js. No se guarda una credencial real en este repositorio. Linux necesita `libgomp1`, instalado por el Dockerfile; en macOS se necesita el runtime OpenMP compatible con LightGBM.

En otra terminal:

```bash
curl http://127.0.0.1:8000/salud

curl http://127.0.0.1:8000/valorar \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer habitia-local-review' \
  --data '{"anuncios":[{"propertyCode":"demo","price":420000,"size":95,"rooms":3,"bathrooms":2,"floor":"3","hasLift":true,"exterior":true,"latitude":40.4378,"longitude":-3.7010,"municipality":"Madrid","propertyType":"flat","detailedType":{"typology":"flat","subTypology":"flat"}}],"renivelar":false,"explicar":true}'
```

La aplicación Next.js usa estas variables en su proceso servidor:

```dotenv
VALORACION_URL=http://127.0.0.1:8000
VALORACION_TOKEN=habitia-local-review
VALORACION_TIMEOUT_MS=4000
```

Para revisar un artefacto antes de instalarlo puede utilizarse `tests/serve_runtime_artifact.py --artifacts <directorio> --port 8018`. Ese servidor escucha únicamente en loopback; el despliegue normal usa directamente `servicio.api:app` y el directorio `servicio/`.

## Entradas, salidas y abstenciones

| Método | Ruta | Comportamiento |
|---|---|---|
| GET | `/salud` | Modelo cargado, versión, variables, MdAPE histórica y precisión actual no validada. Devuelve 503 si no está disponible. |
| POST | `/valorar` | Recibe `anuncios`, `renivelar` y `explicar`; devuelve `resultados` y `errores` por anuncio. |
| POST | `/valorar-alquiler` | Devuelve 422 con `referencia_no_verificada` hasta comprobar fecha y procedencia de la referencia territorial. |

`renivelar` y `explicar` valen `false` por defecto. El máximo es 60 anuncios (`MAX_LOTE`). Con `VALORACION_TOKEN` configurado se exige el encabezado `Authorization: Bearer ...`. El servicio no utiliza el precio anunciado como predictor: permite omitirlo y solo calcula la brecha cuando es positivo y finito.

El anuncio debe declarar municipio Madrid, coordenadas finitas, superficie construida y una tipología de la familia piso, estudio, dúplex o ático. `homes` sin una tipología detallada compatible es insuficiente. Se rechazan casas/chalets, contradicciones de tipología, superficies fuera de 20–1.000 m², habitaciones fuera de 0–12, baños fuera de 0–10 y plantas numéricas fuera de −2–40. Habitaciones, baños, ascensor, exterior y planta pueden ser desconocidos; se conserva esa ausencia y se informa la imputación.

La comprobación geográfica combina municipio declarado, un recorte amplio de geocodificación y un máximo de 1 km hasta el centroide de entrenamiento más cercano. **No es un polígono municipal.** Barrio y sección se aproximan por ese centroide. Fuera de ámbito, el servicio se abstiene en vez de asignar indiscriminadamente una sección madrileña.

Un lote mixto devuelve HTTP 200 con los anuncios admitidos y los motivos de rechazo del resto. Si todos son inválidos devuelve 422; lote excesivo, 413; credencial inválida, 401. La aplicación debe mostrar explícitamente indisponibilidad o una referencia alternativa identificada, sin atribuir al modelo un resultado que no devolvió.

La respuesta conserva `precio_justo` por compatibilidad y añade `precio_estimado`, `objetivo=precio_anunciado`, `model_id`, versión, período de entrenamiento, advertencias e indicadores de extrapolación. Las bandas de brecha son umbrales descriptivos: **no son un clasificador supervisado validado**. `oportunidad` indica únicamente que el precio anunciado está bajo el intervalo del escenario elegido; no demuestra una ganga real ni sustituye una tasación.

`renivelar=true` aplica el factor heredado ×1,5534 para el escenario 2026T1. Siempre mantiene `precision_actual_validada=false`; no se actualiza automáticamente ni demuestra la evolución de cada vivienda o barrio. Los precios históricos también fueron perturbados y las coordenadas desplazadas en la fuente.

`explicar=true` añade las tres contribuciones TreeSHAP principales, la referencia y la suma de las restantes, en log euros históricos. Su suma reproduce la predicción logarítmica. Explica asociaciones aprendidas por el modelo, sin causalidad ni promesas sobre el efecto de reformar una vivienda.

## Artefactos y reproducción

| Archivo instalado | Contenido |
|---|---|
| `pipeline.json` | Contrato de 25 variables, medianas, categorías y tabla territorial aprendidas exclusivamente en ajuste. |
| `modelo_precio.txt` | Modelo puntual LightGBM sobre log precio anunciado. |
| `modelo_q_lo.txt` | Cuantil inferior. |
| `modelo_q_hi.txt` | Cuantil superior. |
| `manifiesto.json` | Identificación, métricas, calibración, escenario temporal y hashes SHA-256. |

Los cinco archivos suman 13.409.720 bytes. Se exportan como un conjunto; no deben mezclarse piezas de entrenamientos distintos. El cargador verifica SHA-256 y orden de variables antes de iniciar. `modelo_precio_portable.txt` y `secciones.json` antiguos se excluyen de esta distribución y **no se cargan en el contenedor v2**.

El protocolo vigente es `src/train_revision.py`, explicado y ejecutado por el notebook de la revisión. No regenerar esta versión con los scripts históricos `src/10_servicio.py` o `src/13_adelgazar.py`: implementan otro protocolo. Tampoco usar `src/11_pruebas_servicio.py` como batería vigente: contiene supuestos y métricas antiguos.

Con las dependencias de entrenamiento de `requirements_revision.txt`:

```bash
python -m unittest discover -s tests -v
python src/train_revision.py --output revision_2026-09-08/otra_ejecucion
```

Para verificar HTTP sobre el directorio instalado, primero se preparan casos con el entorno de entrenamiento y después se prueba con el entorno de inferencia:

```bash
python tests/prepare_runtime_cases.py \
  --experiment revision_2026-09-08/experimento \
  --output auditoria_2026-09-08/casos_runtime_nueva_prueba.json

python tests/verify_runtime_http.py \
  --artifacts servicio \
  --cases auditoria_2026-09-08/casos_runtime_nueva_prueba.json \
  --output auditoria_2026-09-08/runtime_http_nueva_prueba.json \
  --default-artifact-path
```

La verificación HTTP conserva las fuentes y modelos, y no sobrescribe informes anteriores. Comprueba paridad al euro, estados de error, autenticación, SHAP, escenario temporal, lotes de 60 y cuatro clientes simultáneos.

## Contenedor y límites de la validación operativa

El Dockerfile utiliza Python 3.12.12 Bookworm con digest oficial fijo, 20 dependencias exactas, `libgomp1`, usuario sin privilegios, un proceso Uvicorn y un hilo de predicción por llamada. El contexto solo incorpora los archivos de inferencia, sin dataset, notebooks o secretos. No requiere volúmenes ni una base de datos propia.

Receta para ensayar localmente cuando esté activo Docker:

```bash
docker build -f servicio/Dockerfile -t habitia-valoracion:v2 .
docker run --rm --memory=512m --cpus=1 \
  -p 127.0.0.1:8000:8000 \
  -e VALORACION_TOKEN=habitia-local-review habitia-valoracion:v2
```

La construcción Linux y una prueba funcional en Fly con una máquina de 512 MB se registraron el 11 de septiembre de 2026. No equivalen a una prueba de carga. La entrega conserva pruebas de contrato, autenticación y paridad locales; la disponibilidad de producción depende del alojamiento y sus servicios. Antes de la defensa se debe ensayar en el equipo que se utilizará.
