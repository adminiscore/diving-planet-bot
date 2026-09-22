# g-7 · Paso 0 (análisis, sin tocar el bot) — resultados del 2026-09-22

Plan: [g7-retirar-conversations-plan.md](g7-retirar-conversations-plan.md). Todo se midió en una copia
LOCAL del RAG (Postgres + pgvector en Docker, `dp-g7-pg`, mismo índice de 807 documentos que PRE), con y
sin los 107 fragmentos de chats antiguos. PRE no se tocó.

## 1. Recuperación (`eval_retrieval`, 20 preguntas ES + 20 EN, top-4)
- Con chats: aparecen chats en el top-4 de **6/20 preguntas ES** (1 en primer lugar) y **1/20 EN**.
- Sin chats: esos huecos los rellenan **documentos oficiales** (FAQ/políticas); ninguna pregunta se
  queda sin contexto. Ej.: "¿Puedo pagar por transferencia o QR?" pasa de `chat, chat, faq, faq` a 4 FAQ.

## 2. Respuestas del RAG (`eval_rag_answers`, 39 casos)
| | contesta | "no lo tengo" | aclaración | modo esperado |
|---|---|---|---|---|
| Con chats | 35 | 0 | 4 | 39/39 |
| Sin chats | 33 | **2** | 4 | 39/39 |

- **Huecos reales (solo los cubrían chats):** "¿Cómo reservo?" y "¿Qué formulario tengo que llenar para
  bucear certificado?" → hay que taparlos en la KB oficial (paso 2).
- **Donde los chats hacen daño:** "¿Necesitan foto del carné?" — con chats: *"es necesario que nos envíes
  una foto"*; sin chats: *"no hace falta la foto, presenta el carné el día de la actividad"* (lo que dice
  la política oficial).

## 3. Inventario de hechos de los chats contra la KB (`g7_inventory.py` → `g7-inventory.json`)
404 hechos del lado del equipo en 50 chats: **327 ya están en la KB**, 13 **desfasados**, 12 no son de
negocio y **52 "ausentes"** (la mayoría ruido: saludos, "no se menciona…", cosas de un día).

**Desfasados (se descartan, no pasan a la KB):** "Marina Todo Mar" como punto de encuentro (3 veces),
precios viejos (snorkel 445.000 / 2 buceos 163 USD), "refresh sin costo" (la KB: se cobra como
minicurso), regreso "4:30" (KB: 4:15), foto del carné obligatoria.

## 4. Few-shot
- 196 de los 465 turnos del golden v7 llevarían bloque de ejemplos si fueran al RAG; de los 389 ejemplos
  elegidos, **113 (29 %) son la bienvenida automática** ("Hello! Welcome to Diving Planet…").
- El resto son resúmenes de contenido ("Todo el equipo obligatorio está incluido"), no de tono. El tono
  sale de `brand_tone.json` y de los prompts. **Apagarlo tiene riesgo bajo**; el paso 3 lo confirma.

## 5. Decisiones para Gadea (lista c: válido en los chats y AUSENTE de la KB)
Para cada punto: ¿es cierto hoy? ¿entra en la KB y con qué texto?
1. **Cómo reservar**: web con enlaces por actividad (10 % online); si es para mañana y ya pasó el cierre de
   las 4:30 PM, por WhatsApp / con un asesor. *(hueco real del RAG)*
2. **Formulario de exoneración para buzos certificados**: los chats dan un enlace de Jotform
   (`form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol`); la KB solo habla del formato del
   seguro que se envía en el correo de confirmación. ¿Cuál es el vigente? *(hueco real del RAG)*
3. **Foto del carné**: ¿hay que enviarla antes o basta con presentarlo el día? (la KB dice lo segundo).
4. **Minicurso**: ¿hay que crear cuenta PADI, cuestionario médico y la parte online (DSD,
   `learning.padi.com/dsd?store_number=17945`) antes de la actividad? ¿Da acceso a la primera parte del
   Open Water y certificado de participación?
5. **Pagar el día de la actividad** (curso / paquete en el centro): ¿se puede? La KB dice colombianos
   100 % online o 50/50, extranjeros 100 % online.
6. **Tarjeta extranjera**: ¿hay que pagar con pasaporte como identificación?
7. **Si falla el sistema de reservas**, ¿el equipo puede crear un link de pago manual? (hoy: pasar a asesor)
8. **Otros hoteles con acceso marítimo** que se recomiendan (Rosario de Mar, Ubuntu, Mulata, Eco Hotel Las
   Palmeras; los chats dicen que Secreto ya no opera). La KB solo nombra Pao Pao.
9. **Snorkel en otra lancha por seguridad** en grupos mixtos: ¿es así?
10. **Pastillas para el mareo** en la marina: ¿se menciona?

(Descartado sin preguntar: "máximo 7 por instructor" — Gadea dijo el 22-sep que no hay número oficial.)

### Respuestas de Gadea (22-sep) — se aplican en el paso 2
1. **Cómo reservar:** siempre por la web. Si ya pasó el cierre (4:30 PM del día anterior), también por la
   web, pero la reserva es para el día siguiente disponible.
2. **Formulario de exoneración:** valen los dos. El equipo pasa el formulario (Jotform) para rellenarlo y el
   correo de confirmación lo recuerda si aún no se hizo.
3. **Carné:** valen las dos opciones: enviar la foto antes o presentarlo el día de la actividad.
4. **Minicurso:** es un bautizo, una iniciación al buceo. **No certifica nada y no hace falta nada previo.**
   (Revisar en el paso 2 si la KB dice algo distinto, p. ej. "teoría online".)
5. **Pago:** los colombianos pueden pagar el 50 % allí (en persona); los demás, con tarjeta por la web.
6. **Tarjeta extranjera:** sí, el pasaporte sirve como identificación para pagar.
7. **Si falla el sistema de reservas:** el equipo manda un link para hacer transferencia.
8. **Hoteles:** Secreto **sí opera** (el chat antiguo que decía lo contrario está desfasado).
9. **Snorkel en grupos mixtos:** va a una zona distinta de la del buceo. Si hay poca gente van juntos en la
   lancha; si no, se dividen por actividad.
10. **Pastillas para el mareo:** no se menciona (no entra en la KB).

## Paso 1 (22-sep): hecho
Interruptores `rag_exclude_sources` / `rag_fewshot_enabled` (3fb025e). Verificado en local contra el indice
real (con los valores por defecto, mismos documentos y orden en las 40 preguntas; con el filtro, igual que la
copia sin chats) y en PRE con una ronda del core: 16/32 sin fallos frente a 14/32 en la v7 con el mismo codigo;
las diferencias son variabilidad del LLM (el juez de grounding del RAG a veces rechaza y da 'no lo tengo').
**El RAG no es determinista**: por eso el A/B del paso 3 va con 2 rondas por lado.

## Paso 2 (22-sep): huecos tapados en la KB oficial
- `policies.json`: how_to_book, waiver_form, minicourse_scope, foreign_card_payment, payment_fallback,
  mixed_group_boat, other_island_hotels; certification_required admite foto previa o carne el dia.
- `faqs.json`: nueva "¿Que formularios tengo que llenar antes de bucear?" (la politica sola no entraba en el
  top-8: el RAG pesa mas las FAQ en formularios, que antes cubrian los chats).
- **Decision de Gadea: se quita la via de WhatsApp para ultima hora** (politica de reservas y 2 FAQ): pasado el
  cierre de las 4:30 PM se reserva por la web para el siguiente dia disponible.
- Puerta en local (copia sin chats): `eval_rag_answers` 35 respuestas / **0 'no lo tengo'** / 39 de 39,
  igual que con chats; "como reservo", "formularios" y "foto del carne" bien. (En local solo funciona la
  busqueda vectorial: falta la columna de BM25; el A/B real es el del paso 3 en PRE.)
- Pendiente fuera del bot: la web del minicurso dice "30 % de deposito"; la regla es 50 % (Gadea: se deja).

## Paso 3 (22-sep): A/B en PRE el mismo dia — pasa, con un hueco tapado
Core (32 dialogos), 2 rondas por lado, juez gpt-5-mini:

| Ronda | Chats antiguos | Criterios | Sin fallos | 'no lo tengo' (dialogos/turnos) | Latencia p50 / p95 |
|---|---|---|---|---|---|
| A1 | si | 86,0 % | 17/32 | 3 / 4 | 4 s / 9 s |
| A2 | si | 89,8 % | 18/32 | 4 / 5 | 5 s / 10 s |
| B1 | no | 86,8 % | 17/32 | 4 / 5 | 5 s / 10 s |
| B2 | no | 86,5 % | 18/32 | 4 / 6 | 5 s / 11 s |

- Ningun dialogo empeora de forma consistente (sin fallos en las 2 A y con fallos en las 2 B); 1 mejora
  (cancelacion de una reserva existente). Punto de encuentro, pago y disponibilidad: sin empeoramientos.
- **1 criterio empeora en las 2 B:** "¿Y me recuerda los hoteles por favor?" -> 'no lo tengo'. Causa: las
  FAQ oficiales de hoteles salian con similitud 0,36-0,38, bajo el umbral del RAG (0,40); con chats respondia
  gracias a listas de hoteles de chats antiguos. **Tapado con una FAQ oficial** ("¿Que hoteles me
  recomiendan?"): en la copia local sin chats, 7 formulaciones ES/EN ("¿que hoteles hay?", "donde me puedo
  quedar a dormir en la isla", "which hotels do you recommend?"...) quedan entre 0,41 y 0,54 con la
  informacion oficial. Que la frase original quede en 0,41 (umbral 0,40) es el problema de fondo de l1-6.
- Decision: se mantienen los interruptores activos en PRE; paso 4 (borrar conversations.json) tras unos
  dias asi.
