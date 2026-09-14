# Histórico de anuncios

El equipo conserva `habitia_madrid_2018.parquet` fuera de Git y de la release ordinaria. No es necesario para arrancar la API: la inferencia utiliza los seis artefactos de `habitia-modelo-v3.zip`.

| Dato | Valor comprobado |
| --- | --- |
| Tamaño | 10.969.510 bytes |
| Filas y columnas | 94.852 × 62 |
| Inmuebles ASSETID distintos | 75.804 |
| Objetivo disponible | `PRICE` |
| Entradas del XGBoost presentes | 18 de 21 |
| SHA-256 | `7c20dce686fb415430660167f092eb3e0ab44dae2e1221bc3db61fd94d3600ca` |

Faltan las columnas territoriales exactas `alq_mediana_eur_m2_barrio`, `delitos_per_10k_barrio` e `indice_vulnerabilidad`. El parquet no identifica por sí solo la matriz final ni las particiones de entrenamiento y test de Tomás; sus notebooks originales siguen pendientes.

La fuente declarada es [Idealista18](https://paezha.github.io/idealista18/). La procedencia del enriquecimiento y el inventario del parquet se describen en la memoria y en `09_revision/` del [ZIP de entrega](https://github.com/maupeon/habitia-tfm/releases/tag/tfm-2026-09-14). Descargar la fuente pública no garantiza reconstruir este fichero enriquecido.
