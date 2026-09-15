# HabitIA

Aplicación de búsqueda y comparación de viviendas de **compra y alquiler en Madrid capital**, desarrollada como TFM del Máster de Big Data, Data Science e Inteligencia Artificial de la Universidad Complutense de Madrid, curso 2025–2026, clase 2.

**Equipo:** Mauricio Peón García · João Paulo Nogueira Cunha · Manuel Macedo Púlido · Aldo Mauricio Ress Vilet · Tomás Perales Lara. **Tutores:** Carlos Ortega y Santiago Mota.

Este repositorio contiene el predictor XGBoost integrado, la API Python, su instalación, pruebas y configuración de despliegue.

## Entrega

La [entrega esencial del 15 de septiembre de 2026](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-15-r2) contiene:

- Memoria en PDF y Word: 21 páginas totales, 19 de contenido incluida la bibliografía, con portada UCM.
- Anexos en PDF y Word: 15 páginas con datos del modelo, contrato y reproducción de la inferencia.
- `03_codigo/`: copias de los repositorios de la aplicación y del predictor integrado.
- `04_modelo/habitia-modelo-v3.zip`: los seis artefactos necesarios para ejecutar el modelo.
- Instrucciones, versiones y sumas SHA-256.

**[Descargar el ZIP completo](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-15-r2/HabitIA_TFM_2026-09-14.zip)** · [Memoria PDF](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-15-r2/01_HabitIA_memoria.pdf) · [Anexos PDF](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-15-r2/02_HabitIA_anexos.pdf)

Los repositorios y las releases son privados. El ZIP permite revisar el código sin acceso a GitHub. `VERSIONES.json` identifica los commits incluidos y `SHA256SUMS.txt` verifica los archivos. El nombre del ZIP conserva la fecha de la primera versión documental; la revisión vigente se identifica en VERSIONES.json.

[Aplicación](https://habitiaucm.vercel.app) · [Presentación web](https://habitiaucm.vercel.app/presentacion) · [Repositorio web](https://github.com/maupeon/agente-inmobiliario)

## Estructura del repositorio

| Carpeta | Función | Uso |
| --- | --- | --- |
| `predictor_v3/` | Carga el modelo, reconstruye variables y calcula venta y alquiler | Ejecución |
| `servicio/` | API HTTP, dependencias, manifiesto y contenedor | Ejecución y despliegue |
| `scripts/` | Instalación de los seis artefactos con verificación SHA-256 | Instalación |
| `tests_v3/` | Pruebas de autenticación, dominio y operaciones | Verificación |

La carpeta `.github/` contiene la automatización de las pruebas y la construcción del contenedor. Los nombres de los módulos conservan la versión del contrato de integración.

## Ejecutar el modelo

Requisitos: Python 3.12 o superior y `libomp` en macOS o `libgomp1` en Linux. Extraer `03_codigo/habitia-tfm.zip` y abrir una terminal en la carpeta `habitia-tfm`. El instalador recibe la ruta al ZIP de `04_modelo/`.

```bash
python3.12 -m venv .venv-v3
source .venv-v3/bin/activate
python -m pip install -r servicio/requirements_v3.txt
python scripts/install_predictor_v3.py /ruta/a/habitia-modelo-v3.zip
python scripts/install_predictor_v3.py --check
export VALORACION_TOKEN=un-token-local-propio
python -m uvicorn servicio.api_v3:app --host 127.0.0.1 --port 8000 --workers 1
```

También se puede descargar el modelo con GitHub CLI autenticado:

```bash
gh release download tfm-2026-09-15-r2 --repo maupeon/habitia-tfm --pattern habitia-modelo-v3.zip
```

`GET /salud` comprueba la carga del modelo. Para conectar la web, configurar `VALORACION_URL=http://127.0.0.1:8000` y el mismo `VALORACION_TOKEN` en el servidor Next.js. Utilizar una credencial privada al publicar el servicio. [Contrato de la API, ejemplo de petición y despliegue](servicio/README_v3.md).

Para lotes locales: `python -m predictor_v3.predictor predecir anuncios.json -o predicciones.csv`. La inferencia utiliza únicamente el código y los seis artefactos instalados.

## Verificación

Después de instalar los artefactos:

```bash
python -m pip install httpx
python -m unittest discover -s tests_v3 -v
python scripts/install_predictor_v3.py --check
```

Las siete pruebas verifican autenticación, compra y alquiler, comparación mensual y errores de entrada y dominio. GitHub Actions instala y verifica los pesos, ejecuta las pruebas y construye el contenedor. La verificación de integración del 14 de septiembre comparó la implementación de referencia y el servicio con los mismos pesos y tablas:

| Comprobación registrada | Resultado |
| --- | --- |
| Anuncios sintéticos y resultados válidos | 131 de 131 |
| Estados coincidentes | Sí |
| Diferencia máxima en venta base, venta indexada y renta | 0 € |
| SHA-256 del modelo | `5d29cd26889cc0777196f592aa9828b18cc7d71ccd1a05ee61a95f0a44741a04` |

Esta comprobación describe paridad funcional en casos sintéticos; no mide precisión predictiva. Las siete pruebas incluidas permiten verificar la inferencia y el contrato localmente.

## Modelo y datos

`habitIA-xgboost-2018-v3` contiene 401 árboles y 21 variables. El contrato HTTP es `3.1.0`. Estima venta de 2018 indexada a 2025 y deriva el alquiler mensual mediante ratios distritales de 2024. El dominio de la aplicación es Madrid capital, con viviendas admitidas de hasta 367 m².

El MdAPE histórico del 9,29 % procede de los metadatos del entrenamiento y se presenta como resultado registrado. El alquiler no tiene entrenamiento ni validación independiente. No se ofrecen intervalos calibrados, SHAP ni una clasificación validada de oportunidad.

El histórico enriquecido documentado es `habitia_madrid_2018.parquet`: 94.852 filas, 62 columnas y 75.804 `ASSETID` distintos. Contiene `PRICE` y 18 de las 21 entradas del modelo. Faltan las columnas exactas `alq_mediana_eur_m2_barrio`, `delitos_per_10k_barrio` e `indice_vulnerabilidad`. SHA-256: `7c20dce686fb415430660167f092eb3e0ab44dae2e1221bc3db61fd94d3600ca`.

La reproducción completa del entrenamiento requiere la matriz final de modelado, las particiones, las predicciones de test y el código de ajuste. Estos elementos no forman parte de los artefactos de inferencia. La procedencia técnica y los hashes se registran en [el manifiesto](servicio/manifiesto_v3.json). La memoria y los anexos distinguen los resultados históricos, la verificación de software y las limitaciones de evaluación.
