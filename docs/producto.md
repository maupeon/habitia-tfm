# Producto y relación con la web

La [aplicación Next.js](https://github.com/maupeon/agente-inmobiliario) se mantiene en otro repositorio. Vercel sirve la web; las rutas de servidor coordinan anuncios, herramientas del asistente, Supabase y esta API Python. El modelo v2 fue desplegado en Fly el 11 de septiembre de 2026 según el registro operativo del equipo. Las pruebas locales de esta entrega no equivalen a una prueba de carga de producción.

- Búsqueda conversacional y con filtros, mapa, valoración por anuncio, explicación y contexto con fuentes y periodos.
- Historial y favoritos **compartidos por todos los visitantes** de la demo, guardados en Supabase mediante rutas de servidor. No hay cuentas individuales.
- Perfil y última búsqueda en el navegador. La bandeja de selección diaria usa una identidad privada por navegador mediante cookie HttpOnly; prepara hasta **cinco** anuncios y puede devolver menos.
- Score con pesos Fair, Opportunity, Zone y Lifestyle que suman 100. Un componente ausente aporta cero y no redistribuye su peso; se informa cobertura. Fair utiliza una estimación individual válida y Lifestyle el tiempo de trayecto al trabajo. Opportunity (revalorización relativa) y Zone (calidad de vida) están pendientes de series e indicadores verificables y no puntúan. Presupuesto e imprescindibles se aplican como filtros.
- Calculadora de compra frente a alquiler con costes, hipoteca, inversión alternativa y horizonte común. Los resultados dependen de los supuestos; el crecimiento salarial solo afecta a avisos personales.
- Fuentes oficiales con fecha y procedencia. Los índices manuales de seguridad y las cifras sin respaldo no se incluyen en el ranking como hechos verificados.

La notificación implementada es una bandeja persistida, con aviso opcional del navegador cuando la aplicación está abierta y hay permiso. No se ofrece correo ni Web Push con el navegador cerrado. Los pesos del score y los cambios del producto no alteran las métricas históricas del modelo.

La búsqueda real, mapas, asistente y persistencia requieren sus servicios y credenciales. El modo demo utiliza anuncios identificados y no sustituye todas las dependencias. Las instrucciones operativas vigentes están en los documentos de [arquitectura](https://github.com/maupeon/agente-inmobiliario/blob/main/docs/arquitectura.md), [configuración](https://github.com/maupeon/agente-inmobiliario/blob/main/docs/configuracion.md) y [notificaciones](https://github.com/maupeon/agente-inmobiliario/blob/main/docs/notificaciones.md) de la web.
