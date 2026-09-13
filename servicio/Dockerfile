# Índice multi-arquitectura oficial comprobado el 2026-09-08.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY servicio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/model_pipeline.py      src/model_pipeline.py
COPY src/valorador.py           src/valorador.py
COPY servicio/api.py            servicio/api.py
COPY servicio/manifiesto.json   servicio/manifiesto.json
COPY servicio/pipeline.json     servicio/pipeline.json
COPY servicio/modelo_precio.txt servicio/modelo_precio.txt
COPY servicio/modelo_q_lo.txt   servicio/modelo_q_lo.txt
COPY servicio/modelo_q_hi.txt   servicio/modelo_q_hi.txt

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    VALORACION_PREDICT_THREADS=1
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=3)"
CMD ["uvicorn", "servicio.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
