# Auditoría MVP de la base de conocimiento

Esta auditoría compara la base de conocimiento actual con la información necesaria para un MVP robusto que informa, cualifica, recomienda y prepara la conversión con ayuda humana.

## Objetivo del documento

Usar este documento como checklist interno para completar la información que el bot puede usar de forma segura.

El bot no debe intentar cerrar reservas reales, confirmar cupos, procesar pagos ni resolver casos médicos. Para eso debe preparar el contexto y pasar la conversación a una persona.

## Archivos revisados

- `data/knowledge_base/services.json`
- `data/knowledge_base/pricing.json`
- `data/knowledge_base/availability.json`
- `data/knowledge_base/policies.json`
- `data/knowledge_base/faqs.json`
- `data/knowledge_base/discounts.json`
- `data/knowledge_base/brand_tone.json`
- `data/knowledge_base/escalation_rules.json`
- `data/knowledge_base/conversations.json`

## Estados

- **Cubierto:** suficiente para responder en el MVP.
- **Parcial:** existe información, pero está incompleta o dispersa.
- **Falta:** conviene añadirlo antes de que el bot lo use.
- **Requiere confirmación:** alguien del negocio debe validar la respuesta oficial antes de cargarla en la KB.

## Matriz de auditoría

| Tema | Estado | Qué hay ahora | Riesgo o hueco | Qué hay que completar |
|---|---|---|---|---|
| Servicios disponibles | Cubierto | `services.json` es la fuente principal y el árbol carga el catálogo desde ahí; `faqs.json` complementa preguntas frecuentes | Si se añaden servicios nuevos al JSON, aún hay que decidir si entran como opción guiada del árbol o solo como RAG/asesor | Mantener `services.json` como fuente de verdad y actualizar `docs/arbol_opciones_es.md` cuando cambie el recorrido visual |
| Precios actualizados | Requiere confirmación | `services.json` tiene precios para algunos tours/planes; `pricing.json` mantiene muchos `precio_a_definir` | El bot no puede inventar precios; puede responder incompleto | Confirmar precios oficiales por servicio, nacionalidad, salida desde Cartagena/islas, cursos y paquetes |
| Horarios y temporadas | Cubierto | `availability.json` y `faqs.json` | No hay disponibilidad real conectada | Mantener respuestas generales; escalar cuando pregunten por cupo real |
| Condiciones de reserva | Parcial | `policies.json` incluye cierre de ROVERD y link de términos | Falta anticipo, medios de pago, cuándo queda confirmada una reserva y qué datos se piden | Completar política de reserva en formato claro |
| Política de cancelación | Parcial | Link de términos y respuesta sobre cancelación por clima | Falta política normal: cancelación por cliente, no-show, enfermedad, cambio de fecha, reembolso parcial/total | Confirmar reglas oficiales y crear entradas específicas |
| Requisitos médicos | Parcial | `policies.json`, `faqs.json`, `escalation_rules.json` y escalado sensible | El bot no debe dar diagnóstico ni autorizar buceo por condiciones médicas | Añadir regla explícita: el bot nunca decide aptitud médica |
| Requisitos por curso | Parcial | `services.json` y el árbol ya cubren Open Water, Advanced, Rescue, Divemaster y especialidades PADI, incluyendo variantes para clientes ya en islas cuando existen | Aún falta confirmación de negocio para precios, materiales y políticas finas; Divemaster/privado no tienen link de pago directo | Confirmar/estandarizar duración, prerrequisitos, edad mínima, qué incluye, teoría, vuelos y certificación |
| Pernocta + regla de vuelo (Cartagena → Islas) | Cubierto | `services.json` (requirements_es/en) y `faqs.json` remarcan pernocta obligatoria (hotel no incluido) en planes multi-día y la regla de 18h sin volar | Si el contenido se dispersa entre FAQs y servicios puede perderse el mensaje | Mantener este requisito como “must say” al recomendar planes multi-día desde Cartagena |
| Diferencias entre bautismo, Open Water, Advanced y buceos guiados | Parcial | El árbol separa principiantes, certificados, cursos y especialidades; `services.json` aporta detalles de cada plan | Falta una comparación editorial corta que explique “qué me conviene” en una sola respuesta para RAG y humanos | Crear comparación simple para recomendar el plan correcto |
| Preguntas frecuentes | Cubierto | `faqs.json` cubre ubicación, horarios, grupos mixtos, edad, vuelos, recogidas, clima, etc. | Algunas respuestas mezclan varios temas | Separar FAQs importantes en respuestas más concretas con el tiempo |
| Tono comercial | Cubierto | `brand_tone.json` | Debe mantenerse consistente en árbol y RAG | Usarlo como referencia para toda nueva respuesta |
| Casos de escalado humano | Cubierto | `escalation_rules.json`, `src/agents/escalation.py` y supervisor | Las reglas de JSON y las de código pueden desalinearse | Mantener checklist de escalado y luego crear tests |
| Respuestas que el bot nunca debe dar | Parcial | `brand_tone.json` dice que no debe inventar; prompts de RAG también | No hay documento dedicado con prohibiciones claras | Crear política explícita de “nunca responder” |
| Comidas y alergias | Cubierto para MVP | `policies.json` y `faqs.json` ya cubren almuerzo, agua, dulces de coco, opción vegetariana/vegana/celíaca y aviso previo por alergias; además se define que el bot no pregunta proactivamente por alergias | Quedan matices finos: snacks/bebidas adicionales, si se puede llevar comida propia y hasta dónde se pueden prometer adaptaciones | Validar wording final con operación, pero no bloquea la demo |
| Fotos y videos | Cubierto para MVP | `policies.json` y `faqs.json` ya cubren que no están incluidos, no se ofrecen proactivamente, pueden hacerse voluntariamente, se entregan como máximo al día siguiente y no aplican a minicursos / primeras experiencias | Conviene validar si la política y la propina orientativa son estables antes de comunicarlo de forma más comercial | Mantener respuesta conservadora y validar wording final |
| Hoteles, recogidas y traslados | Parcial | `policies.json`, `faqs.json` y árbol mencionan recogida en islas/hoteles; el árbol incluye selector de isla/hotel para cualificar | Falta lista validada como KB estructurada y restricciones exactas por acceso marítimo | Crear documento de logística por isla/hotel y acceso marítimo |
| Descuentos | Parcial | `discounts.json`, `pricing.json` y `faqs.json` | Puede haber conflictos: web, directo, colombianos, grupo, segundo día, PARCEROS | Confirmar qué descuentos existen y si son acumulables |
| Disponibilidad y reservas de última hora | Cubierto para MVP | `policies.json` y `faqs.json` ya explican que ROVERD cierra a las 4:30 PM del día anterior y que después de esa hora hay que pasar a WhatsApp | No hay inventario/cupos conectados, así que el bot no puede confirmar disponibilidad real | Mantener el corte horario como respuesta FAQ y escalar siempre la disponibilidad en tiempo real |
| Pagos | Parcial | `services.json` ya contiene `booking_url` para la mayoría de servicios; `escalation_rules.json` menciona problemas de pago | Falta política: medios de pago, depósito, moneda, cuándo se confirma, tarjetas extranjeras, transferencias y qué hacer si falla un pago | Crear política de pagos antes de que el bot responda detalles. El flujo de pago para clientes colombianos (anticipo, medios, pasarela) **requiere confirmación con Andrés**; mientras tanto, el bot no debe exponer link de pasarela para colombianos y mostrará `PENDIENTE` como marcador interno. |
| Datos para cualificar leads | Falta | El estado de conversación guarda algunos datos, pero no hay esquema comercial | El humano puede recibir conversaciones sin fecha, número de personas, servicio o nivel | Definir resumen estándar para Chatwoot |
| Casos de evaluación | Parcial | Hay tests técnicos para árbol, botones Chatwoot y seguridad RAG; el árbol ya se valida contra servicios de islas y especialidades | Falta dataset de conversaciones comerciales reales/sintéticas para validar recomendación y escalado extremo a extremo | Crear dataset después de completar esta auditoría |

## Prioridades para completar la KB

### Prioridad 1: necesario antes de probar el MVP ampliamente

1. Precios oficiales y reglas de descuentos.
2. Condiciones de reserva y pagos.
3. Requisitos por curso, especialmente precios/materiales/políticas finas de cursos y especialidades.
4. Comparación entre servicios para recomendar bien.
5. Política de respuestas prohibidas.
6. Esquema de resumen para pasar leads a un humano.
7. Validación final de wording para comida/alergias y fotos/videos.

### Prioridad 2: puede escalarse a humano durante el MVP

- Cupos reales.
- Confirmación final de reserva.
- Pagos o errores de pago.
- Casos médicos o de seguridad.
- Excepciones de cancelación/reembolso.
- Recogidas complejas en hoteles o islas.
- Cotizaciones especiales para grupos, privados o casos mixtos.

## Información que necesitamos del equipo

### Precios y descuentos

- Precio oficial de cada tour, curso y paquete.
- Diferencia entre extranjeros, colombianos/locales y salidas desde islas.
- Descuentos vigentes.
- Si los descuentos son acumulables o no.
- Qué descuentos requieren verificación.

### Reserva y pago

- Qué datos se piden para reservar.
- Cuánto se paga para confirmar.
- Medios de pago aceptados.
- Monedas aceptadas.
- Qué pasa si falla un pago.
- Hora límite real para reservar.

### Cancelaciones y cambios

- Política por cancelación del cliente.
- Política por clima/capitanía.
- Cambios de fecha.
- No-show.
- Enfermedad o emergencia.
- Plazos de reembolso.

### Cursos

- Duración real de cada curso.
- Prerrequisitos.
- Edad mínima.
- Qué incluye.
- Qué no incluye.
- Materiales/teoría.
- Certificación final.
- Restricciones de vuelo.

### Logística

- Punto de encuentro.
- Horarios.
- Qué pasa si el cliente está en una isla.
- Hoteles donde sí se recoge.
- Hoteles donde no se recoge.
- Reglas de acceso marítimo.
- Transporte terrestre incluido o no.

### Comida, fotos y extras

- Validar si el almuerzo cambia según operación/proveedor o si puede comunicarse como menú estándar.
- Confirmar snacks/bebidas adicionales más allá de agua y dulces de coco.
- Confirmar si se puede llevar comida propia.
- Confirmar qué adaptaciones por alergias/restricciones se pueden prometer con seguridad.
- Validar si la política actual de fotos/videos puede comunicarse tal cual en demo.
- Confirmar si la propina orientativa y la entrega al día siguiente son regla estable.
- Confirmar si la exclusión en minicursos / primeras experiencias aplica siempre.

## Reglas MVP para el bot

- El bot puede informar y recomendar.
- El bot puede cualificar al cliente con preguntas simples.
- El bot puede compartir links oficiales.
- El bot no debe confirmar disponibilidad real.
- El bot no debe confirmar pagos.
- El bot no debe cerrar reservas por su cuenta.
- El bot no debe dar consejos médicos.
- El bot no debe inventar precios, descuentos, políticas ni excepciones.
- El bot debe pasar a humano cuando haya intención clara de reserva o un caso sensible.

## Próxima acción recomendada

El árbol y la documentación visual ya están alineados con el catálogo actual de `services.json`. El siguiente paso recomendado es completar primero las secciones de **precios/descuentos**, **reserva/pago** y **cancelaciones/cambios**, porque son las áreas con más impacto comercial y mayor riesgo si el bot responde mal.

Después, crear una comparación editorial corta entre **minicurso/bautismo**, **Open Water**, **Advanced**, **buceos guiados** y **snorkeling** para que el RAG pueda recomendar mejor sin depender de respuestas largas del catálogo. En paralelo, confirmar si existe link de pago/reserva directo para **Divemaster** y/o **Servicio privado**; si no existe, mantenerlos como derivación a asesor.
