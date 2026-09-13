# Método y límites

1. Entrada enriquecida: 94.852 filas. Identidad en 41 columnas originales: 94.815; límites estáticos: 94.778; contrato compartido: 94.026 observaciones y 75.225 activos.
2. Tres folds exteriores por `ASSETID`. Cada desarrollo separa ajuste, selección interna y calibración; ninguna fila del mismo activo cruza esas partes. Los pesos hacen que cada activo tenga igual peso al ajustar.
3. Referencia territorial, hedónico Ridge y LightGBM se comparan sobre las mismas observaciones admitidas. Las transformaciones se aprenden solo con el ajuste correspondiente. No entran precios, rentabilidad, Catastro ni alquiler como predictores del modelo principal.
4. LightGBM estima log precio. Dos cuantiles y una calibración CQR basada en el peor residual de cada activo producen el intervalo. Su nivel nominal no garantiza cobertura por vivienda ni en 2026.
5. La reserva fija evalúa exactamente el artefacto que se sirve. Quedan 18.782 filas evaluadas y 16 abstenciones. La paridad al euro se verifica sobre toda esa evaluación; es una comprobación de implementación, no otra prueba independiente de precisión.
6. El diagnóstico temporal desarrolla con Q1–Q3 y evalúa Q4 de 2018. Q4 había sido explorado antes; se declara esa limitación.

La geografía se aproxima con centroides aprendidos, soporte máximo de 1 km y municipio declarado: no constituye un polígono municipal exacto. El alquiler carece de referencia verificada. Las explicaciones SHAP representan asociaciones en log euros, no efectos causales. El score del producto es una regla de preferencia, no un modelo entrenado de satisfacción del usuario. Fair y Lifestyle pueden puntuar con evidencia; Opportunity y Zone permanecen no disponibles.

Fuente numérica: [resultados_revision.json](../revision_2026-09-08/experimento/resultados_revision.json). Las cifras del antiguo modelo de 8,20 % no corresponden a este contrato y no deben usarse para presentar su precisión.
