# HabitIA · modelo XGBoost y entrega académica del TFM

HabitIA busca y compara viviendas de **compra y alquiler en Madrid capital**. Este repositorio contiene la integración Python del modelo entrenado por Tomás Perales Lara, su API y las pruebas de inferencia.

La **[entrega vigente del 14 de septiembre de 2026](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-14)** reúne la memoria ampliada con la portada original de la UCM, los anexos, las copias de código y los seis artefactos del modelo. La memoria tiene 21 páginas totales y 19 de contenido, incluida bibliografía.

Trabajo Fin de Máster de Big Data, Data Science e Inteligencia Artificial, Universidad Complutense de Madrid, curso 2025–2026, clase 2.

**Equipo:** Mauricio Peón García · João Paulo Nogueira Cunha · Manuel Macedo Púlido · Aldo Mauricio Ress Vilet · Tomás Perales Lara. **Tutores:** Carlos Ortega y Santiago Mota.

## 1. Empezar por aquí

- **Descargar la entrega completa:** [HabitIA_TFM_2026-09-14.zip](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-14/HabitIA_TFM_2026-09-14.zip).
- **Leer la memoria:** [PDF](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-14/01_HabitIA_memoria.pdf) · [Word editable](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-14/01_HabitIA_memoria.docx).
- **Consultar los anexos:** [PDF](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-14/02_HabitIA_anexos.pdf) · [Word editable](https://github.com/maupeon/habitia-tfm/releases/download/tfm-2026-09-14/02_HabitIA_anexos.docx).
- **Ejecutar el modelo:** apartado 4 y [contrato de la API XGBoost](servicio/README_v3.md).
- **Probar la aplicación:** [HabitIA](https://habitiaucm.vercel.app) · [presentación interactiva](https://habitiaucm.vercel.app/presentacion) · [código web](https://github.com/maupeon/agente-inmobiliario).

Los repositorios y sus releases son privados. Los enlaces de GitHub requieren una cuenta con acceso. El ZIP incluye copias del código para revisar la entrega sin conexión a GitHub. `VERSIONES.json` identifica los commits incluidos y `SHA256SUMS.txt` permite comprobar su integridad.

## 2. Modelo vigente y alcance

| Elemento | Estado |
| --- | --- |
| Modelo | `habitIA-xgboost-2018-v3`, entrenado y exportado el 13 de septiembre |
| Estructura | 401 árboles y 21 variables |
| Contrato HTTP | Versión `3.1.0`, API `servicio.api_v3:app` |
| Venta | Precio de oferta base de 2018, indexado a 2025 por distrito |
| Alquiler | Mensualidad derivada de la venta estimada y ratios distritales de 2024 |
| Cobertura de la app | Madrid capital; viviendas admitidas por el contrato, hasta 367 m² |
| Test histórico | MdAPE 9,29 %, registrado en los metadatos del paquete |
| Comprobaciones de integración | 131 casos sintéticos con diferencia máxima de 0 € respecto al predictor original y 7 pruebas del servicio |

Las métricas de test proceden de los metadatos recibidos: todavía no se han reproducido con las particiones originales. El alquiler no tiene un entrenamiento ni una validación independiente. No se ofrecen intervalos calibrados, SHAP ni una clasificación validada de oportunidad. La referencia estima precios de oferta; no acredita precios de operaciones cerradas ni precisión actual.

Los pesos recibidos se conservan. La adaptación valida las entradas, reconstruye las variables y mantiene las unidades de cada operación. [Contrato, ejemplo de petición y límites](servicio/README_v3.md).

## 3. Estructura y contenido de la entrega

```text
habitia-tfm/
├── README.md
├── predictor_v3/                  # Inferencia del XGBoost recibido
├── servicio/
│   ├── api_v3.py                 # API vigente
│   ├── README_v3.md              # Instalación, contrato y despliegue
│   ├── requirements_v3.txt       # Dependencias del servicio vigente
│   └── Dockerfile.v3
├── scripts/install_predictor_v3.py
├── tests_v3/                     # Pruebas de API, operaciones y dominio
├── docs/                         # Contratos, paridad y documentación histórica
└── data/README.md                # Datos custodiados fuera de Git
```

El ZIP de entrega añade memoria y anexos en PDF y Word, copias de ambos repositorios y del paquete original de Tomás, `habitia-modelo-v3.zip`, una guía de defensa y la carpeta `09_revision/` con la auditoría, la descripción reproducible del parquet, diagramas y capturas sintéticas. La portada reproduce la referencia facilitada por el equipo, con fecha del 17 de septiembre de 2026.

La presentación web se mantiene como pieza independiente. Esta entrega documental no incorpora el notebook de entrenamiento original de XGBoost ni una presentación estática final.

## 4. Arrancar la API sin el dataset

Requisitos: Python 3.12 o superior, `libomp` en macOS o `libgomp1` en Linux y GitHub CLI autenticado con acceso al repositorio. También se puede extraer `06_modelo/habitia-modelo-v3.zip` de la entrega completa.

```bash
git clone https://github.com/maupeon/habitia-tfm.git
cd habitia-tfm
python3.12 -m venv .venv-v3
source .venv-v3/bin/activate
python -m pip install -r servicio/requirements_v3.txt

gh release download tfm-2026-09-14 --repo maupeon/habitia-tfm --pattern habitia-modelo-v3.zip
python scripts/install_predictor_v3.py habitia-modelo-v3.zip
python scripts/install_predictor_v3.py --check

export VALORACION_TOKEN=un-token-local-propio
python -m uvicorn servicio.api_v3:app --host 127.0.0.1 --port 8000 --workers 1
```

En otra terminal: `curl http://127.0.0.1:8000/salud`. El token del ejemplo se debe sustituir por una credencial privada al publicar el servicio. No hacen falta el dataset de entrenamiento ni credenciales de Idealista para ejecutar inferencia local.

Para conectar la web, configurar `VALORACION_URL=http://127.0.0.1:8000` y el mismo `VALORACION_TOKEN` en el servidor Next.js. [Petición de ejemplo y manejo de errores](servicio/README_v3.md).

## 5. Comprobaciones

```bash
python -m pip install httpx
python -m unittest discover -s tests_v3 -v
python scripts/install_predictor_v3.py --check
```

Las pruebas verifican autenticación, lotes mixtos de venta y alquiler, comparación mensual, errores de entrada y dominios admitidos. [Paridad registrada](docs/verificacion-paridad-v3.json). La carpeta `09_revision/` del ZIP incluye el script de auditoría y sus resultados; estas comprobaciones no reentrenan el modelo ni recalculan su precisión de test.

## 6. Datos disponibles y materiales pendientes

El histórico enriquecido `habitia_madrid_2018.parquet` está disponible fuera de Git: 94.852 filas, 62 columnas y 75.804 `ASSETID` distintos. Incluye `PRICE` y 18 de las 21 entradas del XGBoost. Faltan las tres columnas territoriales exactas del paquete: `alq_mediana_eur_m2_barrio`, `delitos_per_10k_barrio` e `indice_vulnerabilidad`.

El histórico no identifica por sí solo la matriz final ni las particiones de entrenamiento y test de Tomás. Quedan pendientes sus notebooks y la confirmación de esas particiones para reproducir las métricas. Los seis artefactos de producción sí permiten ejecutar las predicciones. El parquet completo no se incluye en la release ni en el ZIP ordinario de entrega.

## 7. Material histórico

La [release del 13 de septiembre](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-13), el [notebook ejecutado](TFM_HabitIA_entrenamiento.ipynb), el [cuaderno de Colab](colab/HabitIA_Colab.ipynb), `src/`, `tests/` y `revision_2026-09-08/` conservan el estudio anterior de LightGBM. Sus instrucciones y resultados corresponden a ese experimento y no al entrenamiento de XGBoost.

La [guía de reproducción histórica](docs/reproduccion.md), la [metodología anterior](docs/metodologia.md) y el [contrato v2](servicio/README.md) permanecen disponibles para consultar esa evidencia. La entrada para ejecutar el producto vigente es `servicio.api_v3:app`.
