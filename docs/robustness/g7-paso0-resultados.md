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
