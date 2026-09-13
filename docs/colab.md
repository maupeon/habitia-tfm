# Probar el estudio en Google Colab

Usar [HabitIA_Colab.ipynb](../colab/HabitIA_Colab.ipynb) y el archivo **HabitIA_Colab_datos_y_codigo.zip** facilitado por el equipo. El ZIP contiene los datos y no se distribuye en GitHub. El notebook no contiene datos incrustados ni credenciales.

1. Abrir [Google Colab](https://colab.research.google.com/) y elegir **Subir notebook**. Seleccionar `HabitIA_Colab.ipynb`.
2. En **Entorno de ejecución → Cambiar tipo de entorno de ejecución**, seleccionar **CPU** y la versión **2026.07**, que incluye Python 3.12.13. El entorno más reciente observado en esta revisión utiliza Python 3.13.
3. Pulsar **Ejecutar todo** y cargar `HabitIA_Colab_datos_y_codigo.zip` cuando aparezca el selector. El cuaderno comprueba el hash del ZIP y de todos los archivos extraídos.
4. Si la instalación pide reiniciar porque NumPy ya estaba cargado, usar **Entorno de ejecución → Reiniciar la sesión y ejecutar todas las celdas**. El archivo cargado permanece en la máquina; no hace falta seleccionarlo de nuevo.
5. Esperar al mensaje **PRUEBA COMPLETA** al final. Las celdas quedan disponibles para explorar tablas, gráficos y respuestas del modelo.

La configuración usa las siete dependencias científicas fijadas en `requirements_revision.txt`. Conserva el kernel de Colab y solo instala las versiones científicas necesarias. La prueba comprueba las particiones y las 18.782 predicciones del artefacto, además de ejecutar las celdas del estudio. No llama a Idealista ni a la API publicada, y no requiere GPU.

## Qué conserva esta copia

El código de `src/` y el artefacto se conservan íntegros. De las 14 celdas de código del cuaderno canónico, 12 mantienen exactamente su código; las otras dos adaptan la ruta y obligan a cargar el experimento guardado. Se añaden preparación y verificaciones. No hay entrenamiento automático si falta evidencia, y las salidas se generan de nuevo al ejecutar. Para entrenar otro modelo, usar el cuaderno canónico y la [guía de reproducción](reproduccion.md).

La versión de entrega `tfm-2026-09-13` permanece intacta. Esta copia de Colab es un complemento para probarla.

## Datos y duración de la sesión

El ZIP se carga en la máquina temporal de Colab de la cuenta que ejecuta el notebook. No se monta Google Drive ni se cambian permisos. Cuando Colab elimina esa máquina, hay que volver a cargar los archivos. Compartir el enlace del notebook no comparte los archivos de la máquina; cada persona necesita el ZIP. El equipo debe acordar el acceso a los datos conforme a [datos.md](datos.md).

Las versiones históricas de Colab tienen disponibilidad limitada y su arranque puede tardar varios minutos. La primera celda comprueba Python antes de continuar. Si la versión 2026.07 deja de estar disponible, no basta con cambiar el número: se debe verificar la receta con el entorno elegido. [Documentación de Google sobre versiones](https://research.google.com/colaboratory/runtime-version-faq.html) y [archivos y sesiones](https://research.google.com/colaboratory/faq.html).

## Regenerar el par notebook + ZIP

Desde la raíz del repositorio, con el paquete privado de reproducción:

```bash
python scripts/build_colab.py RUTA/habitia-reproduccion-privada.zip ../prueba-colab
```

El directorio de salida debe quedar fuera del repositorio. Contiene el notebook, el ZIP privado y un LEEME. Distribuir siempre el notebook y el ZIP generados juntos: el cuaderno comprueba un hash específico. No subir el ZIP a GitHub ni sustituir el dato por otro fichero.
