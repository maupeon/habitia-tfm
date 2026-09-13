# Verificación de la distribución · 13 de septiembre de 2026

Se instaló un entorno nuevo con Python 3.12.12 y los dos ficheros de dependencias fijadas. Se ejecutaron **25 pruebas unitarias**, todas correctas. La biblioteca Starlette emite un aviso de deprecación de su integración de pruebas con httpx; no impidió las comprobaciones. Se conserva el entorno de la versión para no introducir una actualización ajena al estudio.

En una copia de trabajo, restaurada desde el paquete privado:

- El instalador comprobó el manifiesto y los cuatro hashes del pipeline y los modelos. También rechazó un manifiesto distinto antes de escribir archivos.
- El verificador de particiones comprobó separación de activos, evaluación única de cada observación y 93.944 predicciones más 82 abstenciones.
- Las **18.782 observaciones** de la reserva del artefacto reprodujeron exactamente el precio y ambos límites tras redondear al euro.
- La API real local pasó autenticación, estados de error, lotes mixtos, paridad, SHAP, escenario temporal, límite de lote y concurrencia del verificador HTTP.
- El notebook terminó su reejecución en modo de reutilización del experimento guardado y exportó HTML sin errores. No se volvió a entrenar el estudio; las salidas publicadas conservan la ejecución histórica.

Los cuatro módulos científicos se mantienen byte a byte respecto de la fuente local. Los resultados numéricos se conservan. El manifiesto de procedencia registra los archivos cuyo formato o rutas se han normalizado para publicar.

La memoria y los anexos se revisaron en PDF, página a página; ambos tienen 14 páginas. La presentación académica reemplaza las cifras antiguas del PowerPoint histórico y mantiene 12 diapositivas, con tablas y gráfico editables. El paquete conserva PDF y formatos editables.

La web corresponde al commit `b909fb9ba735f7dc325f85ede25d3bb353da6cb2` de su repositorio: instalación limpia, pruebas, TypeScript, lint, build y CI correctos en la revisión previa de esta sesión. Esta entrega del modelo no modifica el funcionamiento de la aplicación.

Límites: no se realizó una nueva recogida de datos, no se reentrenó, no se comprobó carga de producción ni se ensayó en el ordenador del tribunal. Las verificaciones científicas no eliminan la falta de validación de mercado en 2026. El acceso al dataset enriquecido requiere el paquete privado del equipo; los repositorios privados necesitan permisos para abrirse desde otra cuenta.
