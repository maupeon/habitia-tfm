"""Arranca HTTP real con UN worker y comprueba el artefacto sin promoverlo.

Ejecutar con servicio/requirements.txt en un entorno aislado, sin sklearn,
pyarrow ni dependencias de entrenamiento. Requiere casos reales producidos por
prepare_runtime_cases.py. Mantiene las fuentes y los artefactos sin cambios.

El resultado caracteriza este sistema operativo; no sustituye una prueba Linux
con límite real de 512 MiB. Si falla alguna comprobación, el proceso termina en
error y no genera un informe con estado aprobado.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request(base, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    return status, json.loads(body), (time.perf_counter() - start) * 1000


def verify(artifacts: Path, cases_file: Path, output: Path, default_artifact_path: bool = False):
    if output.exists():
        raise FileExistsError("Informe ya existente; use otro --output para conservar la evidencia anterior.")
    if default_artifact_path and artifacts.resolve() != (ROOT / "servicio").resolve():
        raise ValueError("La ruta predeterminada debe ser el directorio servicio/ del proyecto.")
    cases = json.loads(cases_file.read_text(encoding="utf-8"))["casos"]
    if not cases:
        raise ValueError("No hay casos de evaluación reales para verificar.")
    manifest = json.loads((artifacts / "manifiesto.json").read_text())
    expected_files = [artifacts / f for f in ["manifiesto.json", "pipeline.json", "modelo_precio.txt", "modelo_q_lo.txt", "modelo_q_hi.txt"]]
    sources = [ROOT / f for f in ["src/model_pipeline.py", "src/valorador.py", "servicio/api.py"]]
    before = {str(p.resolve()): sha(p) for p in expected_files + sources}
    env = os.environ.copy()
    token = "runtime-local-validation-only"
    env.update(VALORACION_TOKEN=token, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               VALORACION_PREDICT_THREADS="1", MAX_LOTE="60", PYTHONDONTWRITEBYTECODE="1")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    checks, samples = {}, []
    stop = threading.Event()
    with tempfile.TemporaryDirectory(prefix="habitia-http-") as tmp:
        bootstrap = Path(tmp) / "server.py"
        override = ("" if default_artifact_path else
                    "_real_valorador = api.Valorador\n"
                    f"api.Valorador = lambda: _real_valorador(Path({str(artifacts.resolve())!r}))\n")
        bootstrap.write_text(
            "import sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from servicio import api\nimport uvicorn\n"
            f"{override}"
            f"uvicorn.run(api.app, host='127.0.0.1', port={port}, workers=1, log_level='warning')\n")
        log_path = output.with_suffix(".server.log")
        output.parent.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        with log_path.open("w") as log:
            proc = subprocess.Popen([sys.executable, str(bootstrap)], env=env, stdout=log, stderr=subprocess.STDOUT)
            def sample_memory():
                while not stop.is_set():
                    try:
                        value = subprocess.check_output(["ps", "-o", "rss=", "-p", str(proc.pid)], text=True).strip()
                        if value:
                            samples.append(int(value))
                    except (subprocess.CalledProcessError, ValueError):
                        pass
                    stop.wait(.1)
            sampler = threading.Thread(target=sample_memory, daemon=True)
            sampler.start()
            try:
                health = None
                for _ in range(300):
                    if proc.poll() is not None:
                        raise RuntimeError(f"El servidor terminó con {proc.returncode}; consultar {log_path}")
                    try:
                        status, health, _ = request(base, "/salud")
                        if status == 200 and health["ok"]:
                            break
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(.1)
                else:
                    raise TimeoutError("El servidor no alcanzó estado saludable en 30 segundos")
                checks["arranque_saludable_ms"] = round((time.perf_counter() - start) * 1000, 1)
                assert health["model_version"] == manifest["version"]
                assert health["variables"] == len(manifest["columnas"])
                assert health["precision_actual_validada"] is False
                checks["salud_y_version"] = health
                payloads = [c["anuncio"] for c in cases]
                status, body, elapsed = request(base, "/valorar", {"anuncios": payloads, "renivelar": False}, token)
                assert status == 200, (status, body)
                assert body["errores"] == [] and len(body["resultados"]) == len(cases)
                for result, reference in zip(body["resultados"], cases):
                    assert result["propertyCode"] == reference["anuncio"]["propertyCode"]
                    assert result["precio_justo"] == reference["precio_estimado_esperado"], (result, reference)
                    assert result["intervalo"] == reference["intervalo_esperado"], (result, reference)
                checks["paridad_con_evaluacion"] = {"casos": len(cases), "precio_e_intervalo_exactos_al_euro": True, "http_ms": round(elapsed, 1)}
                one = payloads[0]
                first = body["resultados"][0]
                status, changed, _ = request(base, "/valorar", {"anuncios": [{**one, "price": 1}, {**one, "price": 99999999}]}, token)
                assert status == 200
                assert changed["resultados"][0]["precio_justo"] == changed["resultados"][1]["precio_justo"] == first["precio_justo"]
                assert changed["resultados"][0]["intervalo"] == changed["resultados"][1]["intervalo"] == first["intervalo"]
                assert changed["resultados"][0]["oportunidad"] and changed["resultados"][1]["sobrevalorado"]
                checks["precio_solo_comparacion"] = True
                status, mixed, _ = request(base, "/valorar", {"anuncios": [one, {**one, "propertyType": "chalet"}, {**one, "size": None}]}, token)
                assert status == 200 and len(mixed["resultados"]) == 1 and len(mixed["errores"]) == 2
                assert {e["estado"] for e in mixed["errores"]} == {"fuera_ambito", "datos_insuficientes"}
                checks["lote_mixto"] = True
                assert request(base, "/valorar", {"anuncios": [{**one, "price": -1}]}, token)[0] == 422
                assert request(base, "/valorar", {"anuncios": [{**one, "municipality": "Barcelona"}]}, token)[0] == 422
                assert request(base, "/valorar", {"anuncios": [one] * 61}, token)[0] == 413
                assert request(base, "/valorar", {"anuncios": [one]})[0] == 401
                rental_status, rental, _ = request(base, "/valorar-alquiler", {"anuncios": [one]}, token)
                assert rental_status == 422 and rental["detail"]["estado"] == "referencia_no_verificada"
                checks["rechazos_y_auth"] = True
                status, explained, _ = request(base, "/valorar", {"anuncios": [one], "explicar": True, "renivelar": True}, token)
                assert status == 200
                result = explained["resultados"][0]
                explain = result["explicacion"]
                total = explain["base_log_euros"] + explain["suma_otras_contribuciones_log_euros"] + sum(f["contribucion_log_euros"] for f in explain["factores"])
                assert abs(total - explain["prediccion_log_euros"]) < 1e-8
                assert explain["no_causal"] and result["extrapolacion_temporal"] and not result["precision_actual_validada"]
                assert abs(result["precio_justo"] - first["precio_justo"] * manifest["renivelado"]["factor"]) <= 2
                checks["shap_aditivo_y_escenario_explicito"] = True
                timings = []
                for _ in range(12):
                    status, result, milliseconds = request(base, "/valorar", {"anuncios": [one]}, token)
                    assert status == 200
                    timings.append(milliseconds)
                batch60 = (payloads * (60 // len(payloads) + 1))[:60]
                status, result, batch_ms = request(base, "/valorar", {"anuncios": batch60}, token)
                assert status == 200 and len(result["resultados"]) == 60
                with ThreadPoolExecutor(max_workers=4) as pool:
                    concurrent = list(pool.map(lambda _: request(base, "/valorar", {"anuncios": batch60}, token), range(8)))
                assert all(s == 200 and len(b["resultados"]) == 60 for s, b, t in concurrent)
                checks["latencias"] = {"solicitudes_individuales": len(timings), "individual_mediana_ms": round(statistics.median(timings), 1),
                                       "individual_max_ms": round(max(timings), 1), "lote_60_ms": round(batch_ms, 1),
                                       "lotes_concurrentes": 8, "clientes_simultaneos": 4,
                                       "concurrencia_mediana_ms": round(statistics.median(t for s, b, t in concurrent), 1),
                                       "concurrencia_max_ms": round(max(t for s, b, t in concurrent), 1)}
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                stop.set()
                sampler.join(timeout=2)
    after = {str(p.resolve()): sha(p) for p in expected_files + sources}
    assert after == before, "Se modificaron archivos durante la validación"
    result = {"estado": "aprobado", "fecha": datetime.now(timezone.utc).isoformat(), "sistema": platform.platform(),
              "python": platform.python_version(), "un_worker": True, "bibliotecas": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
              "sin_sklearn": importlib.util.find_spec("sklearn") is None,
              "sin_pyarrow": importlib.util.find_spec("pyarrow") is None,
              "artefactos": str(artifacts.resolve()), "sha256": before,
              "ruta_artefactos_predeterminada": default_artifact_path,
              "casos_sha256": sha(cases_file), "checks": checks,
              "rss_maximo_observado_MiB": round(max(samples) / 1024, 1) if samples else None,
              "limites": ["Medición de RSS muestreada en este sistema, no memoria cgroup Linux",
                          "No valida Fly ni la configuración de 512 MiB en producción",
                          "Paridad funcional, no nueva validación externa de precisión"]}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"estado": result["estado"], "rss_maximo_observado_MiB": result["rss_maximo_observado_MiB"], "checks": checks}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--default-artifact-path", action="store_true", help="Arranca servicio.api directamente, sin sustituir la ruta del constructor")
    args = parser.parse_args()
    verify(args.artifacts, args.cases, args.output, args.default_artifact_path)
