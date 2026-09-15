# Servicio XGBoost v3

El servicio expone el modelo XGBoost de HabitIA para compra y alquiler en Madrid capital. `predictor_v3/` reconstruye las variables y ejecuta la inferencia. `manifiesto_v3.json` identifica los seis artefactos mediante SHA-256 y conserva la procedencia técnica de la implementación de referencia.

Requiere Python >=3.12 y las dependencias fijadas en `requirements_v3.txt`, incluido scikit-learn para `XGBRegressor`. La API carga el modelo una sola vez mediante el [ciclo de vida de FastAPI](https://fastapi.tiangolo.com/advanced/events/). El [formato nativo de XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html) permite cargarlo sin pickle.

```bash
python3.12 -m venv .venv-v3
source .venv-v3/bin/activate
python -m pip install -r servicio/requirements_v3.txt
gh release download tfm-2026-09-15-r2 --repo maupeon/habitia-tfm --pattern habitia-modelo-v3.zip
python scripts/install_predictor_v3.py habitia-modelo-v3.zip
python scripts/install_predictor_v3.py --check
export VALORACION_TOKEN=un-token-local-propio
python -m uvicorn servicio.api_v3:app --host 127.0.0.1 --port 8000 --workers 1
```

El ZIP se descarga de la [release vigente del 15 de septiembre](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-15-r2), con GitHub CLI autenticado y acceso al repositorio privado. También está en `04_modelo/` dentro de la entrega completa. Los archivos se instalan en `servicio/artefactos_v3`; `VALORACION_ARTIFACTS_V3` permite cambiar la carpeta. En producción utiliza un token privado. La inferencia local se ejecuta con los artefactos instalados, sin consultar Idealista.

## Petición y respuesta

GET `/salud` devuelve disponibilidad, versión, hash, 21 variables, base 2018, venta 2025 y renta 2024. Las métricas se identifican como declaradas por el paquete.

POST `/valorar`, con `Authorization: Bearer <token>`:

```json
{
  "anuncios": [{
    "propertyCode": "sintetico-1", "operation": "sale", "municipality": "Madrid",
    "propertyType": "flat", "size": 80, "rooms": 2, "bathrooms": 1,
    "latitude": 40.4168, "longitude": -3.7038, "floor": "2", "hasLift": true,
    "price": 450000, "description": "Piso con terraza y trastero.",
    "parkingSpace": { "hasParkingSpace": true }
  }],
  "renivelar": true,
  "explicar": false
}
```

Máximo 24 anuncios, con tipos estrictos. Se aceptan operaciones `sale` y `rent`, incluso en el mismo lote. Para alquiler, `price` es la mensualidad en euros. Se aceptan flat, penthouse, duplex y studio, además de homes con detailedType.typology=flat. Se excluyen subtipos de casa, otros municipios, coordenadas inválidas y superficies superiores a 367 m². El barrio se asigna con la capa incluida y permite rescate hasta 500 m, identificado con una advertencia.

Cada fila se valida antes del cálculo geográfico. El precio anunciado no entra en las variables y puede omitirse; en ese caso la brecha es null. La respuesta identifica `habitIA-xgboost-2018-v3`, versión `3.1.0`, periodos, códigos territoriales y advertencias, junto con `precio_estimado`, `precio_estimado_base`, `factor_escenario`, `precio_anunciado` y `brecha_pct`.

`operation` conserva la operación observada. `precio_estimado` siempre contiene el valor de venta indexado; `precio_comparacion` toma ese valor para venta (`unidad_comparacion=EUR`) y `renta_mensual_estimada` para alquiler (`unidad_comparacion=EUR/mes`). `brecha_pct` compara el anuncio con la magnitud correspondiente. El contrato 3.1 añade estos campos sin cambiar los pesos.

`intervalo` y `banda` son null, `oportunidad` y `sobrevalorado` son false y no hay SHAP exportado. `explicar=true` añade una advertencia. La renta usa `metodo_renta=ratio_distrital_2024` y `alquiler_validado=false`. No se vuelve a aplicar el factor de indexación de v2 ni se utiliza la renta automáticamente en la calculadora.

Un lote válido como petición devuelve 200 con `resultados` y `errores`, incluso si todas las filas se abstienen. Los errores incluyen índice, código, estado y detalle. La estructura inválida devuelve 422, la autenticación incorrecta 401 y un fallo de ejecución 503.

## Pruebas y despliegue

Fly utiliza una máquina compartida de 1 GB y 60 segundos de margen para el arranque. La configuración reserva memoria para cargar el modelo y las tablas geográficas.

```bash
python -m pip install httpx
python -m unittest discover -s tests_v3 -v
docker build -f servicio/Dockerfile.v3 -t habitia-valoracion:v3 .
docker run --rm -p 8000:8000 -e VALORACION_TOKEN habitia-valoracion:v3
```

El [README del repositorio](../README.md#verificación) documenta la igualdad de resultados entre la implementación de referencia y el servicio en 131 anuncios sintéticos. Las pruebas verifican autenticación, lotes mixtos de venta y alquiler, comparación de mensualidades, errores, dominios y ausencia del precio anunciado entre los predictores. No recalculan métricas de test.

GitHub Actions descarga el paquete de la release y verifica sus hashes antes de ejecutar las siete pruebas. La memoria y los anexos describen las variables, la metodología de verificación y el alcance de la evaluación.
