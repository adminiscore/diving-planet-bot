# Plan próximos pasos árbol de decisiones

Este plan organiza los siguientes pasos para probar sistemáticamente el árbol de decisiones en ES, pulir UX/copys, cerrar huecos de lógica y alinear RAG/FAQs.

## 1. Pasada sistemática del árbol ES (testing manual)

- Listar los recorridos principales a revisar (al menos):
  - Tours certificados: 2/5/7/9 buceos + privado.
  - Principiantes/snorkel: minicurso, snorkel, privado.
  - Grupo mixto (certificados + principiantes/snorkel/acompañantes).
  - "Ya estoy en las islas": variantes para certificados, principiantes, snorkel.
  - Menús de precios, reservas/pagos y logística.
  - Cursos PADI (Open Water, avanzado, rescue, divemaster) y paths especiales.
- Probar cada recorrido en Chatwoot/widget (o en consola) y anotar:
  - Textos raros o duplicados.
  - Mensajes demasiado largos o confusos.
  - Casos donde el usuario podría perderse (ej. demasiados saltos).
- Volcar los hallazgos en una checklist (por ejemplo, en TODO.md bajo cada sección).

## 2. Mejora de UX y copys del flujo actual

- A partir de los hallazgos del paso 1, priorizar ajustes que no cambian la lógica:
  - Ajustar copys de menús (títulos de botones, explicaciones cortas).
  - Revisar resúmenes finales: orden, claridad, separación visual, emojis.
  - Completar el copy de almuerzo/comida en los resúmenes y en la parte logística.
  - Afinar la forma de explicar reglas de vuelo y referencias a la web.
- Validar en voz alta que cada flujo cuenta una "historia" clara y consistente para el usuario.

## 3. Cerrar gaps de lógica del árbol

- Tomar la lista de gaps ya identificados (en TODO.md) y elegir 2–3 para esta iteración, por ejemplo:
  - Disponibilidad de última hora y corte de reserva online.
  - Personalización de paquetes 5/7/9 buceos (por ejemplo, quitar nocturna) con escalado a humano.
  - Estándar para formularios de exoneración y datos que se piden tras reservar.
- Para cada gap elegido:
  - Diseñar el mini-flujo o mensaje estándar (1–2 pasos máximo) para no complicar demasiado el árbol.
  - Revisar impacto en `DecisionTree` y en `docs/arbol_opciones_es.md`.
  - Añadir/actualizar tests en `tests/test_decision_tree.py` que cubran el nuevo comportamiento.
- Dejar los gaps más complejos (p.ej. edades mínimas detalladas o lógica avanzada de grupos grandes) para una iteración posterior.

## 4. Alinear RAG/FAQs con lo que no entra en el árbol

- Revisar `data/knowledge_base/faqs.json`, `services.json`, `policies.json` y `conversations.json` con foco en:
  - Fotos y vídeos (no incluidos, cómo se piden).
  - Detalles finos de alojamiento y noches extra.
  - Políticas de cancelación, reembolsos y cambios de fecha.
  - Preguntas sobre profundidad máxima, sitios de buceo, logbook.
- Crear o ajustar FAQs para que el RAG tenga respuestas claras en esos temas sin inflar el árbol.
- (Opcional) Marcar en TODO.md qué temas han pasado a estar "principalmente cubiertos por RAG" para evitar duplicar lógica en el árbol.

## 5. Revisión final y priorización de siguiente ronda

- Tras aplicar los cambios de copys y lógica seleccionados:
  - Repetir una mini pasada de testing sobre los flujos más tocados (por ejemplo, 2 buceos, minicurso, grupo mixto, un menú de logística).
  - Actualizar TODO.md marcando lo que ya esté hecho y ordenando nuevos hallazgos.
- Decidir si la siguiente iteración se centra más en:
  - Extender el árbol (por ejemplo, edades, tamaños de grupo), o
  - Afinar aún más RAG/FAQs y preparación para entorno de PRE/PRO.
