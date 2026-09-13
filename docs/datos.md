# Datos, procedencia y custodia

La fuente declarada es [Idealista18](https://paezha.github.io/idealista18/), descrita por Rey-Blanco, Arbués, López y Páez (2024), [DOI](https://doi.org/10.1177/23998083241242844), [ODbL 1.0](https://paezha.github.io/idealista18/LICENSE.html). No es un conjunto de compraventas: contiene ofertas de 2018 con precios perturbados y coordenadas desplazadas.

El fichero recibido está enriquecido. Se conservan su hash y las decisiones de limpieza en [la auditoría de procedencia](../revision_2026-09-08/procedencia_datos.md). No se han localizado las capas ni el programa del enriquecimiento original; descargar Idealista18 no garantiza reconstruir exactamente este parquet. No se publica una licencia propia que sustituya la de la fuente.

| Material | Ubicación y uso |
| --- | --- |
| Código, notebook con salidas y resultados JSON | Este repositorio, acceso privado |
| Pipeline y modelos v2 | `habitia-modelo-v2.zip` en la release privada y entrega local |
| Dataset enriquecido, particiones, predicciones y modelos del experimento | `habitia-reproduccion-privada.zip`, custodia local del equipo |
| Borradores y resultados anteriores | Archivo privado, fuera de la entrega vigente |

El paquete privado permite reproducir localmente el experimento, pero no se adjunta a GitHub ni al ZIP de entrega por defecto. Para el tribunal, el equipo debe facilitar su acceso por el canal acordado y explicar la procedencia pendiente del enriquecimiento. La atribución y las condiciones de la fuente deben acompañar cualquier redistribución. No se afirma que el estudio sea reproducible únicamente con el repositorio.

Los JSON y las salidas del notebook publicados normalizan las rutas del ordenador. Se mantienen los números, salidas e identificadores de la evidencia histórica; la copia original permanece en el archivo privado. Los módulos científicos se copian byte a byte y conservan sus hashes.
