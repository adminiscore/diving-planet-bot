# rag-2 · Paso 1: inventario y decisiones

Inventario automático: `python -m scripts.kb_inventario` → `inventario.json`. Lo revisé a mano y aquí queda lo real.

## La base de hoy (718 fragmentos)

| Fuente | Fragmentos | Qué pasa |
|---|---|---|
| Servicios | 352 (36 × 5 trozos × 2 idiomas) | el mismo servicio en 5 trozos; cada servicio existe dos veces (Cartagena / "ya en las islas") |
| FAQs | 270 (135 × 2) | 25 describen un servicio entero ("¿cómo es el plan X…?") → duplican `services.json` y son los clones que llenaban el top-8; ~40 son cultura de buceo (bien); 7 llevan listas de precios que ya están en el catálogo; 1 es una instrucción para el bot (FAQ 87) |
| Políticas | 68 (34 × 2) | cortas y sin preguntas → no se encuentran |
| Precios | 28 | listas de precios que duplican el catálogo; el cargador escribe **"Descuento equipo propio: $0 COP por día"** (lee una clave que no existe) |

Marcas: **50 fragmentos con el teléfono**, 45 con el tono "escríbenos / te paso con un asesor", 124 con precios metidos en el texto.

Paridad ES/EN: sin huecos de datos importantes (solo detalles: falta el enlace de exoneración en inglés, "Bautizo").

## Decisiones de negocio (Gadea)

| # | Tema | Qué dicen las fuentes | Propuesta |
|---|---|---|---|
| D1 | **Quién paga en COP** | política: nacido en Colombia (viva donde viva) o extranjero con cédula de extranjería · FAQs 14 y 116, `discounts.json`, catálogo y prompt: "colombianos y residentes" | la regla precisa de la política en todas partes |
| D2 | **Refresh tras más de 2 años** | requisitos de los servicios: "debes hacer refresh" · FAQ 17: "te recomendamos" · política: "normalmente debes" · todos: "escríbenos por WhatsApp antes de reservar" | "normalmente se requiere; los buzos muy experimentados (500+ inmersiones, Dive Master) los revisa un asesor", sin teléfono |
| D3 | **Teléfono en la base** | 50 fragmentos lo dan; el prompt prohíbe darlo; s4-14: si el cliente lo pide, se da el WhatsApp oficial (eso ya lo hace el código) | quitarlo de la base; el WhatsApp solo por el camino de s4-14 |
| D4 | **Descuento de segundo día (10 %)** | está en `discounts.json` y `pricing.json`; no en el catálogo ni en la web de reservas que conocemos | ¿sigue vigente? ¿a qué aplica? Si no, se quita |
| D5 | **Almuerzo** | FAQ 11: "todos los tours incluyen almuerzo" · "ya en las islas": no incluido · paquetes y cursos de varios días: solo el día 1 (el catálogo dice "almuerzo incluido" sin más) | desde Cartagena solo el día 1; desde las islas, no; el catálogo lo dirá así |
| D6 | **Hora de llegada a Cartagena** | 4:15 p. m. en la mayoría · 4:00 p. m. en Open Water, 9 buceos, Mindful y especialidades | ¿diferencia real o se unifica a 4:15? |
| D7 | **Cómo pagan los extranjeros** | FAQ 114-115: 100 % en línea con tarjeta **o presencial con tarjeta/efectivo**; colombianos, anticipo del 50 % · política: extranjeros pagan con tarjeta en la web | ¿se mantiene el pago presencial y el anticipo del 50 %? |
| D8 | **5 % por equipo propio** | `discounts.json`: buceo recreativo y cursos · el catálogo no dice a qué aplica (el bot lo ofreció para snorkel) | solo buceo recreativo y cursos, no snorkel ni minicurso |

## Decisiones de estructura (las tomo yo, salvo que digas lo contrario)

- **Una ficha por servicio y origen**, autocontenida (qué es, para quién, duración y noches, qué incluye y qué no,
  itinerario, requisitos, precio, enlace), con el origen en el título. Sustituye a los 5 trozos y a las 25 FAQs de
  servicio. Los 2 datos que solo estaban en esas FAQs (edad mínima 6 del snorkel; formato del seguro en el plan de 2
  inmersiones) pasan a `services.json`.
- **FAQs y políticas neutras**: sin teléfono, sin "escríbenos", sin listas de precios (los precios viven en la ficha y
  en el catálogo). Cada política lleva 2-3 formas de preguntarla para que la búsqueda la encuentre.
- **Fuera de la base**: las listas de precios (FAQs 120-121 y los 28 trozos de `pricing`) y la FAQ 87 (instrucción
  para el bot; si hace falta, va al prompt en rag-4). Se arregla el "$0 COP".
- **Una regla, un sitio**: moneda, refresh, almuerzo, recogida y descuentos se escriben una vez (política) y el resto
  no los repite.
- Todo en una tabla nueva (`kb_documents_v2`) detrás del flag `RAG_KB_V2`: la base de hoy no se toca.
