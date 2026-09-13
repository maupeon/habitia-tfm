# Reproducir el estudio

Para una prueba guiada en Google Colab, usar [el cuaderno y las instrucciones de Colab](colab.md). Esa copia verifica el experimento guardado sin iniciar entrenamientos por falta de archivos.

Todos los comandos se ejecutan desde la raíz de `habitia-tfm`, con Python 3.12. El entorno histórico registró Python 3.12.14; las dependencias directas están fijadas en `requirements_revision.txt`. La instalación de entrega se comprueba con Python 3.12.12. `entorno_revision.lock.txt` es el inventario histórico, con paquetes específicos de macOS, y no sustituye la receta portable.

## Preparación

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements_revision.txt -r servicio/requirements.txt
python -m ipykernel install --prefix .venv --name habitia --display-name 'HabitIA Python 3.12'
```

Linux requiere `libgomp1`; macOS, `libomp`. En macOS se importa sklearn antes de LightGBM por compatibilidad con OpenMP.

## Pruebas que no necesitan datos

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m unittest discover -s tests -v
python scripts/install_artifacts.py habitia-modelo-v2.zip
python scripts/install_artifacts.py --check
```

Las pruebas unitarias trabajan con ejemplos sintéticos. El instalador solo requiere el ZIP del modelo y verifica sus cinco archivos frente al manifiesto incluido en el repositorio.

## Recuperar la evidencia completa

Solicitar al equipo `habitia-reproduccion-privada.zip` y seguir [datos.md](datos.md). Extraerlo en **una copia de trabajo** del repositorio para conservar intactos los JSON normalizados de publicación. Incluye `data/habitia_madrid_2018.parquet` y `revision_2026-09-08/experimento/` con predicciones, particiones y artefacto. Comprobar el hash indicado en `data/README.md`.

```bash
python tests/verify_experiment_partitions.py
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python tests/verify_exported_evaluation.py
python tests/prepare_runtime_cases.py --experiment revision_2026-09-08/experimento --output auditoria_2026-09-08/casos_runtime.json
python tests/verify_runtime_http.py --artifacts servicio --cases auditoria_2026-09-08/casos_runtime.json --output auditoria_2026-09-08/runtime_http.json --default-artifact-path
```

Estas comprobaciones vuelven a calcular métricas, separación por activo, paridad y contrato HTTP sin entrenar. Los verificadores escriben informes; ejecutar en la copia de trabajo evita modificar los informes históricos conservados.

## Notebook y entrenamiento

El notebook entregado conserva las salidas históricas. El HTML de la release permite leerlas sin instalar Jupyter. La normalización de rutas está declarada en `docs/procedencia-publicacion.json`.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -u src/execute_revision_notebook.py
```

El ejecutor usa el kernel `habitia`, guarda salidas y exporta HTML. Con `REENTRENAR = False`, reutiliza el experimento guardado si está completo y la configuración coincide, y recalcula las tablas desde sus predicciones. Si falta la evidencia puede iniciar entrenamiento: restaurar primero el paquete privado para una simple comprobación.

Para volver a ajustar todo el estudio, poner `REENTRENAR = True` en una copia del notebook, o usar:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -u src/train_revision.py --output revision_2026-09-08/repeticion_manual
```

La salida debe ser nueva. No usar `--sin-temporal` para reproducir la entrega completa. Semilla 17, dos hilos; quedan posibles diferencias numéricas entre plataformas. El cuaderno debe abrirse desde la raíz del repositorio.

## Documentos

La memoria y los anexos de la release son copias editoriales actualizadas el 13 de septiembre. Sus métodos, tablas y figuras proceden de los resultados canónicos del 8 de septiembre. El código de entrenamiento se conserva sin modificaciones. Los generadores antiguos ligados a la carpeta de trabajo no forman parte de la receta entregada. Si se hace otro experimento, revisar explícitamente las cifras y referencias de todos los documentos antes de emitir una nueva versión.
