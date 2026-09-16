# HabitIA

Aplicación de búsqueda y comparación de viviendas de **compra y alquiler en Madrid capital**, desarrollada como TFM del Máster de Big Data, Data Science e Inteligencia Artificial de la Universidad Complutense de Madrid, curso 2025–2026, clase 2.

**Equipo:** Mauricio Peón García · João Paulo Nogueira Cunha · Manuel Macedo Púlido · Aldo Mauricio Ress Vilet · Tomás Perales Lara. **Tutores:** Carlos Ortega y Santiago Mota.

Este repositorio contiene el predictor XGBoost integrado, la API Python, su instalación, pruebas y configuración de despliegue.

## Entrega

La [entrega actualizada del 16 de septiembre de 2026](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-16) contiene:

- Memoria en PDF y Word, con portada UCM y resultados del nuevo modelo.
- Anexos en PDF y Word con datos del modelo, contrato y reproducción de la inferencia.
- `03_codigo/`: copias de los repositorios de la aplicación y del predictor integrado.
- `04_modelo/habitia-modelo-v3.zip`: los seis artefactos necesarios para ejecutar el modelo.
- Instrucciones, versiones y sumas SHA-256.

**[Descargar el ZIP completo](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-16/HabitIA_TFM_2026-09-16.zip)** · [Memoria PDF](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-16/01_HabitIA_memoria.pdf) · [Anexos PDF](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-16/02_HabitIA_anexos.pdf)

Los repositorios y la release de entrega son públicos y se pueden consultar sin iniciar sesión en GitHub. El ZIP permite descargar el código y los artefactos para revisarlos localmente. `VERSIONES.json` identifica los commits incluidos y `SHA256SUMS.txt` verifica los archivos. La revisión vigente se identifica en VERSIONES.json.

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

Requisitos: Python 3.12 o superior y `libomp` en macOS o `libgomp1` en Linux. Extraer `03_codigo/habitia-tfm.zip` y abrir una terminal en la carpeta `habitia-tfm`. El instalador recibe la ruta al ZIP de `04_modelo/`; también admite directamente la carpeta recibida `nuevo_modelo` o una carpeta con los seis artefactos.

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
gh release download tfm-2026-09-16 --repo maupeon/habitia-tfm --pattern habitia-modelo-v3.zip
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

Las 13 pruebas verifican autenticación, compra y alquiler, comparación mensual, errores de entrada, nuevas abstenciones de dominio, obra nueva e instalación desde carpeta o ZIP. GitHub Actions instala y verifica los pesos de la release `tfm-2026-09-16`, ejecuta las pruebas y construye el contenedor.

La comprobación del 16 de septiembre utiliza el código y los seis artefactos originales de `nuevo_modelo`, exportados el 15 de septiembre a las 22:56:50. Su informe está en [paridad_v3.json](servicio/paridad_v3.json) y se reproduce, conservando esa carpeta, con:

```bash
python scripts/verify_reference_v3.py ../nuevo_modelo --output servicio/paridad_v3.json
```

| Comprobación registrada | Resultado |
| --- | --- |
| Anuncios sintéticos en los 131 polígonos | 131 válidos de 131 |
| Casos límite adicionales | 21; 10 válidos y 11 abstenciones |
| Valores de las 21 variables, estados y salidas nativas | Iguales a la referencia en el mismo entorno |
| Diferencia máxima nativa en venta base, venta indexada y renta, mismo entorno | 0 € |
| Diferencia máxima tras serializar la respuesta | 5,82 × 10⁻¹¹ € (tolerancia 10⁻⁸ €) |
| SHA-256 del modelo | `e5526aca6001741f24eb976dbd9607df131b3822b5b5a01b66c6c92af2a9d748` |

Esta comprobación describe paridad funcional en casos sintéticos; no mide precisión predictiva. Los ejemplos y el barrido de superficie de la memoria están en [evidencia_modelo_v3.json](servicio/evidencia_modelo_v3.json).

La igualdad exacta compara referencia e integración ejecutadas juntas en el mismo entorno. Entre macOS/ARM y Linux pueden variar los últimos bits de los cálculos float32 según CPU y bibliotecas numéricas. El ejemplo de 80 m² produjo 482.507,295671 € en macOS y 482.507,249227 € en Linux: 0,046444 € de diferencia, equivalente a un ULP del precio base (0,03125 €) multiplicado por el índice de venta. En renta la diferencia fue 0,000131 €/mes. Las dos pruebas contra valores guardados admiten error relativo de `2e-7` (aproximadamente dos ULP); las comprobaciones de independencia del precio anunciado y de comparación mensual conservan sus igualdades y verificaciones aritméticas. Esto no cambia los pesos, las fórmulas ni la versión del servicio.

## Modelo y datos

`habitIA-xgboost-2018-v3` contiene 410 árboles y 21 variables. El contrato HTTP es `3.2.0`. Estima venta de 2018 indexada a 2025 y deriva el alquiler mensual mediante ratios distritales de 2024. El dominio de la aplicación es Madrid capital, con viviendas admitidas de hasta 367 m². La exportación vigente es `2026-09-15T22:56:50`; el cambio sustituye los pesos, metadatos y tablas por los seis archivos del nuevo paquete, sin recalcular los índices. El nuevo paquete sigue usando precios de 2025 y ratios de alquiler de 2024, no índices de 2026.

Se añade abstención cuando la descripción indica vivienda a reformar/actualizar (`a_reformar`) u ocupada/alquilada/sin posesión (`ocupada`), con las negaciones y excepciones del paquete. Estas reglas se aplican también al escenario de alquiler. `newDevelopment` se devuelve como `calidad.obra_nueva` y añade una advertencia: varias viviendas de la misma promoción no son observaciones independientes. El flag no cambia el precio.

El MdAPE histórico del 9,30 % procede de los metadatos del entrenamiento y se presenta como resultado registrado. El alquiler no tiene entrenamiento ni validación independiente. No se ofrecen intervalos calibrados, SHAP ni una clasificación validada de oportunidad.

El histórico enriquecido documentado es `habitia_madrid_2018.parquet`: 94.852 filas, 62 columnas y 75.804 `ASSETID` distintos. Contiene `PRICE` y 18 de las 21 entradas del modelo. Faltan las columnas exactas `alq_mediana_eur_m2_barrio`, `delitos_per_10k_barrio` e `indice_vulnerabilidad`. SHA-256: `7c20dce686fb415430660167f092eb3e0ab44dae2e1221bc3db61fd94d3600ca`.

La reproducción completa del entrenamiento requiere la matriz final de modelado, las particiones, las predicciones de test y el código de ajuste. Estos elementos no forman parte de los artefactos de inferencia. La procedencia técnica y los hashes se registran en [el manifiesto](servicio/manifiesto_v3.json). La memoria y los anexos distinguen los resultados históricos, la verificación de software y las limitaciones de evaluación.
