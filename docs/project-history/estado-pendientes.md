# Estado del bot: bugs arreglados y pendientes

> Documento vivo de estado. Última actualización: 2026-07-22 (v0.20.41, tras mergear la rama de Gadea).
> Consolidado a petición del owner. Para el detalle técnico de cada punto, ver
> `docs/HISTORY.md` (versión indicada) y `docs/project-history/session-handoff.md`.

## ✅ Bugs reportados y arreglados (esta racha, desplegados en PRE)

| Versión | Qué se arregló |
|---|---|
| v0.20.8 | Agujero de alucinación cerrado (respuesta desde conocimiento del mundo sin KB) + umbral RAG calibrado a 0.40 (medido, no a ojo) |
| v0.20.9 | El bot recogía datos personales en el chat para "tramitar la reserva" (PII) |
| v0.20.14 | "cojo/coja" no reconocido como movilidad reducida en DIVE TO HEAL |
| v0.20.15 | Acompañante sin actividad → recomienda minicurso; recap de contexto al "Volver" |
| v0.20.16 | Sub-flujo DIVE TO HEAL coherente (contexto persistente entre turnos) |
| v0.20.17-24 (Gadea) | **Memoria B/C/A**: resumen progresivo + notas abiertas + ventana configurable (24) |
| v0.20.18-25 (Gadea) | Bloqueo de botones en pasos sí/no; precisión de precio de buceo; falso positivo "planes"; fallback de certificación desconocida; **chunk de descuentos indexado en blanco desde hace años**; cálculo de precios derivados; preguntas bloqueadas en MIXED_LOCATION/ADD_QTY |
| v0.20.26 | **No ofrecer asesor por defecto** (solo sensible/necesario/pedido) + **nunca dar el WhatsApp** (guard determinista); botones asesor/menú fuera de respuestas normales; "Volver" en el resumen final ya no abandona el carrito; **reset de memoria por escenario nuevo** (saludo + auto-presentación con memoria previa) |
| v0.20.27 | **Certificado por texto libre → recomendar 2 inmersiones directo** (sin menú), acotado a la entrada libre y gateado por acompañante principiante (split y botón in-cart conservan menú); **snorkel a mitad de flujo ya no se ignora** (aterriza en ADD_QTY donde el split cert/actividad lo reconoce); **"Volver" fuera de todo el carrito** (`_CART_MENU_KEYS`) — cambios por lenguaje natural |
| v0.20.28 | **Inferir "1 persona" de auto-presentación singular** ("soy certificada" → group_size=1, se salta la pregunta de cantidad); conservador ante acompañante/número/plural/colectivo |
| v0.20.29 | **Switch multi-día por texto en cualquier paso cert** (antes caía a RAG y la reserva se quedaba en 2 inmersiones) + **acompañante snorkel a mitad de flujo ya no se pierde** (antes solo subía headcount; ahora hace split y acaba en el carrito) |

## 🟡 Pendientes abiertos (no bloqueantes)

1. **Coste/latencia de la ventana de memoria de 24** — la ventana 12→24 ~duplica los tokens de historial por llamada LLM (hay 3-4 por turno) + una llamada extra de resumen cada 24 mensajes. **Medir en vivo en PRE con conversaciones largas antes de PRO.** Palanca: `HISTORY_WINDOW_SIZE`.
2. **La generación del resumen se `await`ea antes de responder** (1 de cada 24 turnos añade ~1-2s). Evaluar fire-and-forget si la latencia molesta.
3. **Orquestador LLM no determinista** — un mensaje de reserva claro puede clasificarse distinto entre ejecuciones. Revisar si hay más combinaciones de `_should_*` sin su red de seguridad determinista (señalado por Gadea en v0.20.21).
4. **Validación de esquema en `load_embeddings.py`** — el bug del descuento en blanco (v0.20.22) pide un test general que detecte cualquier chunk que salga vacío, no solo el de descuentos.
5. **Bug hermano `MIXED_ASK_CERTIFICATION`** (v0.20.2) — "yo y mi pareja"/"2 y uno snorkel" entrando por ese paso cuenta mal. Sin arreglar.
6. **Gaps del acompañante** (v0.20.13, ver `TODO.md`): roles quién bucea/acompaña; familiares en el atajo de overview; decisión deny-list vs safe-list del atajo de precios.
7. **Hallazgos menores de baterías** (Gonzalo): nitrox "$10/tanque" (alucinación), "?" resetea a idioma, emoji/"..." → welcome en inglés.
8. **Números de teléfono embebidos en la KB** — la regla de prompt + el guard determinista los bloquean en la salida, pero siguen en los JSON. Limpieza opcional del KB (requiere reindex) si se quiere quitarlos de raíz.
9. ~~**Switch multi-día vago por texto**~~ **RESUELTO en v0.20.29**: el interceptor del supervisor detecta el switch multi-día (incl. frases vagas "más días"/"multi-día") en `MIXED_ADD_QTY`/`MIXED_CERT_LAST_DIVE`/`MIXED_ADD_PREVIEW` y cambia el plan (o muestra el menú multi-día) antes de la vía RAG. Igual que el acompañante snorkel a mitad de flujo.
10. **Extracción integral de información del mensaje por LLM (aspiración del owner, 2026-07-21) — LUZ VERDE DADA, plan completo en `docs/robustness/`**. El detector determinista (`intent_detector.py`) extrae por regex campos sueltos (actividad, cert, grupo, ubicación, conteos, edades, nacionalidad…) y se ha ido ampliando caso a caso (últimos: group_size=1 singular en v0.20.28; switch multi-día y acompañante en v0.20.29; typos "certfied"/"vucea" en v0.20.31). Tras una sesión de live-testing contra PRE que encontró 6 inconsistencias reales en total, se escribió `docs/archive/robustness-strategy-options.md` con 4 opciones; owner + Álvaro + Gonzalo decidieron empezar por la extracción LLM (Opción 2). **El diseño acordado es exactamente el propuesto aquí**: el LLM rellena huecos que el regex deja vacíos (gap-filler), nunca reemplaza de golpe. Plan de implementación completo, con fases y criterios de corte, en `docs/robustness/plan.md`; registro de progreso sesión-a-sesión en `docs/robustness/progress-log.md`. Empieza ahí, no aquí.

## 🐞 Bugs de UX del carrito reportados en vivo (Rocío, PRE, 2026-07-22) — SIN ARREGLAR

> Reportados por el owner probando en `pre.is-core.dev/chat` con el código ya
> mergeado de Gadea (v0.20.41). Guion: "hola soy rocio, tengo el open water y
> quiero hacer buceo" → ubicación Cartagena → "soy solo yo" → "No" (2 años) →
> resumen 2 inmersiones → "viene también uno que hace snorkel" → añadir snorkel.
> **No arreglados a propósito**: el owner va a proponer un refactor importante del
> carrito/árbol antes de tocarlos (ver nota al final). Análisis de fondo en
> `docs/archive/cart-vs-conversational-analysis.md`.

1. **"¡Genial!" duplicado.** Tras "hola soy rocio, tengo el open water y quiero hacer
   buceo", el bot responde "¡Genial! Veo que eres buzo certificado. 🤿" e
   inmediatamente "Genial 🤿 Para armarlo bien, dime desde dónde saldrías:". Dos copys
   pegados que ambos abren con "Genial". **Causa**: la confirmación de cert y el prompt
   de ubicación son plantillas separadas concatenadas. **Fix**: quitar el "Genial" de
   una de las dos.
2. **Botón "Volver" innecesario en la pregunta de ubicación → dead-end.** El paso
   "¿desde dónde saldrías? (Cartagena / islas)" muestra un botón "⬅️ Volver"; al pulsarlo
   lleva a la pantalla genérica "¡Genial! Vamos a armar tu reserva paso a paso [Añadir
   actividades]", perdiendo el contexto. **Causa**: ese paso de ubicación quedó FUERA del
   filtro `_CART_MENU_KEYS` de v0.20.27, así que conserva el `back`; y el `back` es un
   salto de estado, no una intención. **Fix**: quitar el `back` de ese paso (añadir su
   key a `_CART_MENU_KEYS`) y replantear el copy.
3-4. **Re-pregunta "¿han pasado 2 años?" tras añadir al acompañante snorkel.** El usuario
   ya respondió "No" a la pregunta de seguridad (última inmersión) para sí mismo; al
   decir luego "viene también uno que hace snorkel", el split cert+acompañante vuelve a
   preguntar "¿Han pasado más de 2 años desde tu última inmersión?". **Causa**:
   `_start_cert_companion_split` (fix de v0.20.29) re-entra en `MIXED_CERT_LAST_DIVE` sin
   comprobar que esa respuesta ya se dio para el subgrupo certificado. **Fix**: no
   re-preguntar `last_dive` si ya está respondida para el mismo subgrupo cert.
5. **Al añadir una actividad no pregunta cuántas personas.** "Añadir otra actividad" →
   elegir "Snorkel" → va directo al resumen "Tour de Snorkeling" sin preguntar la
   cantidad (asume 1). **Causa**: el paso de menú "añadir actividad" no ata la cantidad
   antes del preview. **Fix**: pasar por `MIXED_ADD_QTY` (o extraer la cantidad de la
   frase) antes del preview.

> **Nota (2026-07-22)**: el owner considera que el carrito de botones "no es tan buena
> idea" y quiere un bot que INTERPRETE (como la entrada del principio). Estudio riguroso
> en `docs/archive/cart-vs-conversational-analysis.md`. **Plan de implementación acordado y
> detallado en `docs/archive/conversational-refactor-plan.md`** (núcleo conversacional de
> slot-filling, carrito como estado interno, quick-replies mínimos, OpenAI + structured
> outputs, migración incremental por vertical detrás de flag). **Los 5 bugs de arriba se
> resuelven POR DISEÑO en la Fase 1 de ese plan** (el slot-filling no repite/olvida/
> re-pregunta por construcción); no arreglarlos por separado — se cierran con el refactor,
> que lo implementará el equipo. El plan incluye persona/estilo, guardarraíles anti-
> manipulación (OWASP) y re-engagement con timing como feature opcional.

## 🧪 Robustez / extracción por LLM (Gadea) — qué quedaba pendiente

> Trabajo de Gadea mergeado a `dev_alvaro` el 2026-07-21 (v0.20.30→v0.20.41,
> fast-forward). Plan completo en `docs/robustness/plan.md`, progreso en
> `docs/robustness/progress-log.md`, review en `docs/robustness/review-2026-07-21.md`.
> Fases 0-4 y 8 (dominios cert/grupo/ubicación/logística) **completas** y verificadas en
> vivo, detrás de flags de cutover por dominio. **Pendiente**:

- **Fase 6 — Bucle de datos reales** (`[~]`, prioridad alta): tooling hecho
  (`scripts/harvest_cutover_logs.py` + batería de 32 casos `docs/robustness/
  live-test-battery-fase6.md` + tests). **Falta**: correr el harvester contra los logs
  reales de `dp-pre-bot` (`[EXTRACT][CUTOVER]`/`[EXTRACT][SHADOW]`, requiere SSH a la
  VPS) y curar los candidatos hacia el eval-set (validar `expected` antes de fijarlo).
  Aviso apuntado: los mensajes de prueba a veces no llegan a `docker logs` — asegurar que
  el tráfico de prueba queda registrado.
- **Fase 5 — Limpieza y consolidación** (`[ ]`): **bloqueada por Fase 6** — sin datos
  reales no se sabe qué regex está muerto y se puede retirar.
- **Fase 7 — Override selectivo por campo** (`[ ]`, nueva): override medido por campo
  donde el LLM sea más fiable que el regex aunque el regex "resuelva" (bug documentado
  `me plus 3 friends` → group_size). Ver `review-2026-07-21.md` H6.
- **Fase 8 Parte 2 — cablear entry-points (H4/H5), DEFERIDA con razón**: cablear el
  cutover en los short-circuits pre-dispatch (`_apply_group_recomposition`,
  `_maybe_answer_age_eligibility`) duplicaría la llamada LLM en fall-through. El fix
  correcto es **un cutover único temprano en `_route_message_inner`** — un refactor de
  dispatch, documentado como trabajo futuro. (Nota: esto se solapa con la Opción B del
  análisis carrito↔conversacional — el "punto único de comprensión temprano".)

## 🔴 Bloqueado / dependencias externas

- **Matriz hotel→recogida** (`Dudas_V2.docx`): esperando que el equipo confirme cuáles de los 8 hoteles "posibles obsoletos" (incl. Pao Pao) siguen vivos antes de montar `hoteles.json`.
- **Booking Agent** (integración Roverd): sigue siendo un stub.
- **WhatsApp Business API**: reloj externo — pedir cuanto antes.
- **Dominio**: migrar de `pre.is-core.dev` a `pre.divingplanet.org` (acceso a HostGator).
