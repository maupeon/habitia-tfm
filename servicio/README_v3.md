# Servicio XGBoost v3

El servicio expone el modelo XGBoost de HabitIA para compra y alquiler en Madrid capital. `predictor_v3/` reconstruye las variables y ejecuta la inferencia. `manifiesto_v3.json` identifica los seis artefactos mediante SHA-256 y conserva la procedencia técnica de la implementación de referencia.

Requiere Python >=3.12 y las dependencias fijadas en `requirements_v3.txt`, incluido scikit-learn para `XGBRegressor`. La API carga el modelo una sola vez mediante el [ciclo de vida de FastAPI](https://fastapi.tiangolo.com/advanced/events/). El [formato nativo de XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html) permite cargarlo sin pickle.

```bash
python3.12 -m venv .venv-v3
source .venv-v3/bin/activate
python -m pip install -r servicio/requirements_v3.txt
curl -fL -o habitia-modelo-v3.3.zip https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-16-r2/habitia-modelo-v3.3.zip
python scripts/install_predictor_v3.py habitia-modelo-v3.3.zip
python scripts/install_predictor_v3.py --check
export VALORACION_TOKEN=un-token-local-propio
python -m uvicorn servicio.api_v3:app --host 127.0.0.1 --port 8000 --workers 1
```

El ZIP se descarga de la [release pública del 16 de septiembre](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-16-r2), sin iniciar sesión en GitHub. También está en `04_modelo/` dentro de la entrega completa. Se puede instalar la carpeta recibida con `python scripts/install_predictor_v3.py ../habitia_predictor`; también se acepta la carpeta que contiene directamente los seis artefactos. El instalador verifica todos los hashes antes de reemplazar archivos existentes. Los archivos se instalan en `servicio/artefactos_v3`; `VALORACION_ARTIFACTS_V3` permite cambiar la carpeta. En producción utiliza un token privado. La inferencia local se ejecuta con los artefactos instalados, sin consultar Idealista.

## Petición y respuesta

GET `/salud` devuelve disponibilidad, versión HTTP `3.3.0`, hash, 410 árboles, 21 variables, fechas de entrenamiento/exportación, versión del paquete 3, base 2018, venta y renta proyectadas a 2026. Las métricas se identifican como declaradas por el paquete.

POST `/valorar`, con `Authorization: Bearer <token>`:

```json
{
  "anuncios": [{
    "propertyCode": "sintetico-1", "operation": "sale", "municipality": "Madrid",
    "propertyType": "flat", "newDevelopment": false, "size": 80, "rooms": 2, "bathrooms": 1,
    "latitude": 40.4168, "longitude": -3.7038, "floor": "2", "hasLift": true,
    "price": 450000, "description": "Piso con terraza y trastero.",
    "parkingSpace": { "hasParkingSpace": true }
  }],
  "ano_ajuste": 2026,
  "renivelar": true,
  "explicar": false
}
```

`ano_ajuste` es opcional y vale 2026 por defecto; se acepta 2026 explícitamente y otro año devuelve 422. El paquete contiene las tablas ya fijadas a 2026 y no se reexporta durante las peticiones.

Máximo 24 anuncios, con tipos estrictos. Se aceptan operaciones `sale` y `rent`, incluso en el mismo lote. Para alquiler, `price` es la mensualidad en euros. Se aceptan flat, penthouse, duplex y studio, además de homes con detailedType.typology=flat. Se excluyen subtipos de casa, otros municipios, coordenadas inválidas y superficies superiores a 367 m². El barrio se asigna con la capa incluida y permite rescate hasta 500 m, identificado con una advertencia.

Las descripciones que indican una vivienda a reformar/actualizar (`a_reformar`) u ocupada, alquilada o sin posesión (`ocupada`) generan abstención `fuera_ambito`, respetando los patrones, negaciones y excepciones del nuevo paquete. La adaptación aplica las mismas reglas al escenario derivado de alquiler. El detalle incluye los motivos separados por punto y coma. Son detecciones textuales; no verifican el estado jurídico ni físico.

`newDevelopment` es booleano opcional; ausente o null se interpreta como false. Se expone en `calidad.obra_nueva` junto a una advertencia de dependencia entre viviendas de una promoción. No es una variable adicional ni modifica el precio. El resto de marcas de calidad mantiene su significado.

Cada fila se valida antes del cálculo geográfico. El precio anunciado no entra en las variables y puede omitirse; en ese caso la brecha es null. La respuesta identifica `habitIA-xgboost-2018-v3`, versión `3.3.0`, periodos, códigos territoriales y advertencias, junto con `precio_estimado`, `precio_estimado_base`, `factor_escenario`, `precio_anunciado` y `brecha_pct`.

`operation` conserva la operación observada. `precio_estimado` siempre contiene el valor de venta indexado; `precio_comparacion` toma ese valor para venta (`unidad_comparacion=EUR`) y `renta_mensual_estimada` para alquiler (`unidad_comparacion=EUR/mes`). `brecha_pct` compara el anuncio con la magnitud correspondiente. Estos campos se conservan desde el contrato 3.1, y las abstenciones por descripción y `calidad.obra_nueva` desde 3.2. El contrato 3.3 sustituye las tablas por la exportación proyectada a 2026 y añade la identidad del paquete y procedencia temporal.

`intervalo` y `banda` son null, `oportunidad` y `sobrevalorado` son false y no hay SHAP exportado. `explicar=true` añade una advertencia. La renta usa `metodo_renta=ratio_distrital_proyectado_2026` y `alquiler_validado=false`. No se vuelve a aplicar el factor de indexación de v2 ni se utiliza la renta automáticamente en la calculadora.

Un lote válido como petición devuelve 200 con `resultados` y `errores`, incluso si todas las filas se abstienen. Los errores incluyen índice, código, estado y detalle. La estructura inválida devuelve 422, la autenticación incorrecta 401 y un fallo de ejecución 503.

## Pruebas y despliegue

Fly utiliza una máquina compartida de 1 GB y 60 segundos de margen para el arranque. La configuración reserva memoria para cargar el modelo y las tablas geográficas.

```bash
python -m pip install httpx
python -m unittest discover -s tests_v3 -v
docker build -f servicio/Dockerfile.v3 -t habitia-valoracion:v3 .
docker run --rm -p 8000:8000 -e VALORACION_TOKEN habitia-valoracion:v3
```

El [README del repositorio](../README.md#verificación) documenta la igualdad de resultados entre la implementación de referencia y el servicio ejecutados en el mismo entorno, en 131 anuncios sintéticos de los polígonos y 21 casos límite (152 en total). Las pruebas verifican autenticación, lotes mixtos de venta y alquiler, comparación de mensualidades, errores, dominios y ausencia del precio anunciado entre los predictores. Las 13 pruebas también verifican obra nueva, nuevas abstenciones, negaciones e integridad de instalación. No recalculan métricas de test.

Los cálculos float32 pueden variar en sus últimos bits entre CPU y bibliotecas de distintas plataformas. Solo las dos aserciones contra importes guardados usan tolerancia relativa `2e-7`; una verificación multiplataforma previa detectó una diferencia de un ULP del precio base, propagado por los factores del paquete. La paridad exacta con la referencia se verifica dentro del mismo proceso/entorno, y las comprobaciones aritméticas de compra y alquiler se mantienen sin relajar.

GitHub Actions descarga el paquete de la release y verifica sus hashes antes de ejecutar las 13 pruebas. La memoria y los anexos describen las variables, la metodología de verificación y el alcance de la evaluación.

## Procedencia de la integración 3.3

Se integró el paquete `habitia_predictor`, exportado `2026-09-16T11:57:54`: XGBoost de 410 árboles, MdAPE histórico declarado 9,299045 % y RMSE log 0,185610. El modelo sigue siendo el entrenado el `2026-09-15T20:10:09`, y tanto sus pesos como sus métricas son idénticos a la exportación anterior. Cambian las tablas de índices y variables de barrio y los metadatos. Los seis artefactos conservan exactamente los bytes recibidos y sus hashes se comprueban antes de cargar el modelo. `source_code_sha256` identifica los cinco módulos originales, incluido `rutas.py`.

Los atributos de los Parquet fijan los últimos años observados en 2025 (venta) y 2024 (alquiler), con tendencia desde 2018. La proyección a 2026 se aplica a los índices de venta, ratios distritales de alquiler y alquiler de barrio. La API expone `ano_precio=2026`, `ano_renta=2026`, `ano_ajuste=2026`, `ultimo_ano_venta=2025`, `ultimo_ano_alquiler=2024`, `ano_inicio_tendencia=2018` y `ajuste_proyectado=true` en salud y resultados. Mantiene `precision_actual_validada=false` y `alquiler_validado=false`; las proyecciones no constituyen validación actual.

`paquete_sha256` identifica el conjunto de seis artefactos: SHA-256 del JSON del mapa `sha256` del manifiesto, con claves ordenadas y separadores `(',', ':')`. Su valor es `043304773c081968a67703429bbe028b3f397b1ccc49f2856fa0df91e7a079fc`. Los consumidores deben invalidar las cachés de 3.2 y validar la versión y este hash, porque el hash del modelo es el mismo aunque cambien los importes.

La integración conserva únicamente las funciones necesarias para inferencia: adapta rutas e importaciones, excluye exportación/entrenamiento y consultas a fuentes crudas, valida tipos/coordenadas antes del cálculo, evita predecir filas inválidas y mantiene la extensión de alquiler con comparación mensual. Los patrones de abstención usan grupos sin captura para evitar advertencias de pandas sin cambiar su detección; las 21 variables, la corrección de smearing y los cálculos de precio coinciden con la referencia. El script de paridad verifica además que `ANO_PRODUCCION`, los argumentos por defecto de `exportar_paquete` y la carga sin argumentos del paquete original apuntan a 2026.

La release `tfm-2026-09-16-r2` utiliza el archivo `habitia-modelo-v3.3.zip`; la release y el artefacto de 3.2 permanecen disponibles para reproducir esa versión anterior.
