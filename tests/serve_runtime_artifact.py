"""Servidor local de revisión de un artefacto exportado, sin promoverlo.

Ejemplo (el token es exclusivamente de pruebas locales):
    VALORACION_TOKEN=habitia-local-review python tests/serve_runtime_artifact.py \
        --artifacts revision_2026-09-08/experimento/artefacto --port 8018

La aplicación web debe usar VALORACION_URL=http://127.0.0.1:8018 y el mismo
VALORACION_TOKEN. Solo escucha en loopback. No modifica servicio/ ni artefactos.
El despliegue normal utiliza servicio.api:app y su directorio de producción.
"""
import argparse
import os
from pathlib import Path
import sys


def serve(artifacts: Path, port: int):
    if not (artifacts / "manifiesto.json").is_file():
        raise FileNotFoundError("No existe un manifiesto exportado en --artifacts")
    for variable in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VALORACION_PREDICT_THREADS"]:
        os.environ[variable] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from servicio import api
    import uvicorn
    real_constructor = api.Valorador
    api.Valorador = lambda: real_constructor(artifacts.resolve())
    print(f"Directorio de artefactos de revisión: {artifacts.resolve()}", flush=True)
    uvicorn.run(api.app, host="127.0.0.1", port=port, workers=1, log_level="info")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8018)
    args = parser.parse_args()
    serve(args.artifacts, args.port)
