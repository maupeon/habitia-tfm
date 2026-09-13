# Procedencia y decisiones de carga · revisión 8 de septiembre de 2026

El fichero de entrada es `data/habitia_madrid_2018.parquet`. Esta revisión no lo
modifica. SHA-256:

```text
7c20dce686fb415430660167f092eb3e0ab44dae2e1221bc3db61fd94d3600ca
```

El cargador `src/revision_data.py` devuelve datos y un registro JSON serializable
con el hash, esquema, filas originales fusionadas, exclusiones secuenciales,
conteos por periodo y advertencias de procedencia. `source_row_id` es la posición
de la fila en el parquet original, empezando en cero; no es una identidad del
inmueble. Las 41 columnas originales están enumeradas en `ORIGINAL_COLUMNS`.

## Fuente histórica

La fuente declarada es Idealista18, descrita por Rey-Blanco, Arbués, López y Páez
(2024), *A geo-referenced micro-data set of real estate listings for Spain’s three
largest cities*, Environment and Planning B, 51(6), 1369–1379.
[Artículo y DOI](https://doi.org/10.1177/23998083241242844),
[paquete oficial](https://paezha.github.io/idealista18/),
[diccionario](https://paezha.github.io/idealista18/reference/Madrid_Sale.html),
[licencia ODbL 1.0](https://paezha.github.io/idealista18/LICENSE.html).

La publicación declara 94.815 observaciones de Madrid y 42 campos incluyendo
geometría. `PRICE` es precio de oferta, no precio escriturado. `PERIOD` indica el
trimestre de extracción. Los precios publicados incorporan ruido de ±2,5 % y
redondeo a 1.000 euros; las coordenadas están desplazadas preservando el barrio.
La sección censal real no queda garantizada por esa anonimización. La publicación
atribuye el enriquecimiento catastral a una fuente de 2021, sin acreditar su
disponibilidad histórica en cada fecha de anuncio. El diccionario describe
`ISINTOPFLOOR` como vivienda en última planta: no identifica por sí solo la
tipología comercial de ático.

La cabecera del diccionario contiene dimensiones antiguas incompatibles con su
propia descripción final. Para los conteos usamos el fichero examinado y la
tabla trimestral de la publicación. La referencia de versiones anteriores a
“Rey-Juan-Carlos et al. (2021)” no identifica correctamente esta fuente.

## Observaciones verificadas en el fichero local

| Etapa | Filas | ASSETID únicos |
| --- | ---: | ---: |
| Parquet enriquecido recibido | 94.852 | 75.804 |
| Identidad sobre las 41 columnas originales | 94.815 | 75.804 |
| Dominio estático admitido por el cargador revisado | 94.778 | 75.771 |

Las 37 filas adicionales forman 37 pares idénticos en las 41 variables originales.
Todos corresponden a la sección `2807902018`. Solo cambian tres campos del
enriquecimiento: `n_viviendas_alquiler` (nulo/153), `alq_nivel_imputacion`
(`codigo_censal`/`original`) y `alq_imputado` (verdadero/falso). Conservar la primera
fila de cada par no selecciona entre observaciones originales diferentes.
Los campos de alquiler se excluyen de los datos devueltos; sus conflictos y los
identificadores de las filas fusionadas quedan registrados. Si apareciera un
conflicto entre campos territoriales conservados, el cargador dejaría ese valor
ausente y lo registraría en vez de escoger una adscripción arbitraria.

Antes de las restricciones de dominio, 13.829 ASSETID tienen varias filas.
Entre ellos, 13.539 difieren en precio, 974 en superficie y 13.825 en coordenadas.
Ningún ASSETID aparece en más de un trimestre en este fichero. Esta última
observación limita la interpretación de seguimiento longitudinal: no demuestra
que inmuebles físicos no se repitan con otra identificación. Tampoco puede
afirmarse que las coordenadas distintas prueben colisiones de identificadores.
No hay fecha dentro del trimestre que permita elegir el anuncio “más reciente”.

## Reglas del cargador

Las restricciones son fijas: precio finito y positivo, superficie de 20 a 1.000
m², latitud entre 40,30 y 40,55 y longitud entre −3,90 y −3,50, dormitorios entre
0 y 12, baños entre 0 y 10 y planta entre −2 y 40. Dormitorios, baños y planta
pueden estar ausentes; ASSETID debe estar informado. Estos límites definen el
dominio de estudio y no significan que todas las viviendas fuera de él sean
imposibles. El rectángulo geográfico tampoco sustituye al límite municipal.

En orden secuencial se excluyen 1 fila por coordenadas, 22 por dormitorios y 14
por baños. No hay recorte por cuantiles de precio, imputaciones ni parámetros
estimados sobre el conjunto completo. Barrio y sección faltantes se conservan.
La carga no descarta observaciones originales distintas del mismo ASSETID.

Los pesos de `asset_weights(particion)` tienen media uno y hacen que cada activo
sume el mismo peso dentro de la partición. Los splits deben mantener cada ASSETID
en un único bloque. Deben publicarse tanto métricas por observación como métricas
por activo y explicitar si el ajuste utiliza esos pesos. La ponderación no hace
independientes las repeticiones para la calibración conformal: esa etapa necesita
una regla por activo o un método conformal para grupos.

## Enriquecimientos y límites no resueltos

En el árbol local TFM examinado no se encontraron el fichero original previo al
enriquecimiento, las capas censales y de alquiler descargadas, ni el programa que
realizó ese cruce. El metadato GeoParquet solo informa de CRS y librería creadora
(geopandas 1.1.1); no acredita fechas de publicación o disponibilidad de las capas.
`CONSTRUCTIONYEAR` y `CADCONSTRUCTIONYEAR` son años de construcción, no metadatos
de fecha de consulta.

El modelo temporal principal debe excluir alquiler y Catastro hasta acreditar
su disponibilidad en la fecha pertinente. El cargador conserva las cuatro
variables CAD originales para auditoría y experimentos separados; ello no es una
autorización para incluirlas en el principal. Los campos territoriales derivados
pueden servir para diagnóstico, con su procedencia pendiente explícita.

El parquet no contiene una tipología general `propertyType`. Estudios y dúplex
sí tienen indicadores; asumir que cualquier otra vivienda es un piso debe
declararse como supuesto del adaptador, no como etiqueta observada. Las
predicciones históricas no validan automáticamente anuncios de 2026, precios de
transacción, alquileres ni ahorro o rentabilidad de una operación futura.

## Verificación

`tests/test_revision_data.py` contiene seis pruebas focalizadas: duplicación del
enriquecimiento, conservación de precios extremos positivos, restricciones
secuenciales, nulos opcionales, conflictos territoriales, pesos por activo y
esquema requerido. Ejecutadas con éxito con:

```bash
python -m unittest discover -s tests -p test_revision_data.py -v
```

También se cargó el parquet real y se comprobó que el registro se serializa a
JSON, que se recuperan las 94.815 observaciones originales y que los pesos tienen
media uno. No se reentrena ningún modelo al importar o ejecutar el cargador.
