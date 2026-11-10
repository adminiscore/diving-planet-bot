# Inventario del repo actual (11-nov-2026)

Hecho por un agente sobre `feature/simple-gadea` 3261d80f, para el plan de reconstrucción. Solo cifras y nombres de fichero; ningún
dato de clientes. Las rutas son relativas a la raíz del repo.

## 1. Datos del negocio (`data/knowledge_base/`)

| Fichero | Tamaño | Contenido |
|---|---|---|
| `services.json` | 121 KB | 38 servicios (17 cursos, 11 paquetes, 9 salidas, 1 privado); 18 son variantes `_already_on_island`. 28 con `booking_url`, 3 `contact_only`, 10 sin enlace de reserva |
| `pricing.json` | 24 KB | Tarifa 2026: 51 entradas (26 desde Cartagena, 25 desde las islas), COP y USD, normal y online |
| `policies.json` | 40 KB | 62 políticas, español e inglés. La referencian 15 módulos de `src` |
| `faqs.json` | 165 KB | 135 preguntas (juego antiguo) |
| `curada/faqs.json` | 199 KB | 112 preguntas curadas |
| `curada/preguntas.json` | 27 KB | 66 entradas de redacciones alternativas, solo para el buscador |
| `activities.json` | 29 KB | 18 actividades: servicios por origen, certificación, edades, horas antes de volar |
| `discounts.json` | 5 KB | Online 10 %; grupo 10 % desde 5 (no cursos PADI); equipo propio 5 % (no minicurso ni snorkel); no se suman |
| `decisiones.json` | 20 KB | 31 decisiones (ver §2) |
| `avisos.json` | 9 KB | 12 avisos que pega el código y 8 temas |
| `lugares.json` | 8 KB | 8 hoteles con recogida, 37 sitios de las islas, alias y 8 barrios de Cartagena |
| `valores.json` | 1 KB | 11 horas oficiales |
| `brand_tone.json` | 8 KB | Personalidad y estilo |
| `escalation_rules.json` | 5 KB | 8 categorías. **No la lee ningún código de `src`**, solo el juez. Desfasada |
| `availability.json` | 2 KB | Operación, temporadas, hora de corte |

**El mismo dato en más de un sitio:**
- **Precios:** `pricing.json` y, escritos a mano, en 44 líneas de `faqs.json`, 20 de `curada/faqs.json`, 4 de `policies.json`, 4 de
  `decisiones.json`, 3 de `avisos.json` y 2 de `discounts.json`. Hay tests que los mantienen alineados.
- **Horas (4:30, 16:30, 18 h):** `valores.json` y, a mano, 30 menciones en `faqs.json`, 15 en las curadas y 14 en políticas.
- **Regla del vuelo:** en una política, una FAQ y `activities.json`.
- **Escalado:** `escalation_rules.json` y otra copia distinta en `src/agents/escalation.py`.
- **5 % de equipo propio:** en `pricing.json` y en `discounts.json`.

**Enlaces de reserva:** `book.divingplanet.org/book/<slug>/<id>?language=es`, 28 ids distintos. El idioma se cambia en el parámetro.
**Islas y Cartagena:** ids de servicio separados, cada uno con su enlace y su tarifa.

## 2. Decisiones

`decisiones.json`: 31 decisiones, del 17-sep al 9-nov. 12 tienen `instruccion_es`/`instruccion_en`; 19, no. 23 tienen `en_el_bot`,
que apunta a piezas de código del bot actual. Las del 10-nov están en el Plan V1 v4.1 (`docs/plan/plan-v1.md`) y en la memoria del
equipo (rama `memoria`), aún no en `decisiones.json`.

## 3. Canal

- **Entrada:** `POST /webhooks/chatwoot`, **sin comprobar firma**, y además un sondeo cada segundo de las conversaciones activas.
- **Salida:** API de Chatwoot. Respuestas partidas en varias burbujas, botones `input_select`, formato de WhatsApp, notas de voz
  transcritas.
- **Chatwoot:** se usan notas privadas, el estado `pending` en el pase y el indicador de escritura. No se usan etiquetas, equipos ni
  la API de agent-bot.
- **El bot no mira el estado ni el asignado: sigue contestando después de un pase.**
- **Pase:** `pasar_a_persona` (`src/agents/lead_summary.py`), llamado desde 15 sitios en 9 ficheros. Antes corre un detector de
  palabras clave (emergencias e incidencias de pago o reserva).
- **Ráfagas:** no se juntan; cada mensaje es un turno. Un candado en memoria por conversación, en un solo proceso.
- **Estado:** Redis, un JSON de 81 campos por conversación, 30 días. Historial de 24 mensajes.
- **Duplicados:** clave en Redis por mensaje, 30 días.
- **Postgres:** solo se lee la base de conocimiento (`kb_v2.kb_documents`). Las tablas de análisis (conversaciones, mensajes) nunca
  se escriben.

## 4. Infraestructura

- **Entornos:** local y **solo PRE** (un servidor Hetzner con el bot, Chatwoot y sus bases). Producción está definido en el compose
  pero no desplegado. En la lista de prelanzamiento, producción y la API de WhatsApp Business figuran como pendientes. Los 75
  episodios reales son de clientes hablando con una persona, no con el bot.
- **Despliegue:** al subir a una rama `pre_*`, tras los tests. Entra por SSH como root, reconstruye el bot y **vuelve a indexar la base
  de conocimiento**. Gana el último que sube; no hay control de concurrencia.
- **Base de datos:** Postgres propio con pgvector. Supabase está configurado, pero ningún código lo usa.
- **Secretos:** ficheros `.env.*` fuera de git; en GitHub, la clave del servidor y las de Langfuse.
- **Observabilidad:** una línea `[TURN_METRICS]` por turno. Langfuse, en pausa. `GET /health`.
- **Copias de seguridad: ninguna en el repo.**
- **Modelos:** escritor gpt-6-luna (respaldo deepseek a los 3 s), Jev (OpenRouter), claude-haiku-5.5 (extractor y lector de grupo),
  deepseek (reescritura, resumen, idioma, notas, juez de grounding), gpt-5.4-mini (reserva), embeddings y transcripción. Juez de
  evaluación: Claude Code con claude-opus-5-5.

## 5. Conversaciones y pruebas

- **Exportaciones crudas de WhatsApp (`wasap/`):** no están en el repo (ignoradas por git).
- **En git, reales anonimizados:** `real-episodes.json` (75 episodios de 39 chats, con las respuestas del equipo), `hidden-exam.json`
  (13 chats apartados), `golden-dialogues.json` (116 diálogos, 73 sacados de episodios reales), 142 respuestas juzgadas.
- **Sintéticos:** exámenes g9 y g10 (72 diálogos cada uno), `panel-graves.json` y `panel-vara.json` (40 cada uno), unos 29 bancos,
  190 charlas de sparring.
- **Calibración existente:** 17 ítems, 9 etiquetas de Gadea, 71 de Claude, 27 de revisión humana.
- **`docs/robustness`:** 2.782 ficheros, 626 MB, todo en git.
- **Tests:** 296 ficheros, unas 2.330 funciones. **El CI ejecuta solo 19 ficheros con nombre.**

## 6. El prototipo V1 (`scripts/simple_v1.py`)

- gpt-6-luna directo por OpenAI, temperatura 0, salida JSON, 1 llamada por turno.
- **Base:** 253.910 caracteres más 1.880 de instrucciones; unos 67.300 tokens por llamada. Caché automática de OpenAI: 96-99,6 % de
  acierto. p90 de unos 4 s.
- **Resultado (10-nov, V1 frente al bot actual):** panel 7,5 y 7,5; ciegos 3,0 y 3,0; reales 5,0 y 5,5; pases 71/120 frente a 45/120
  (no cumple); importes fuera del catálogo 13/272 frente a 0/623 (no cumple); en mensajes reales, 182 caracteres y 75 % con pregunta
  frente a 597 y 96 %; p90 4,04 s frente a 5,76 s; 1 llamada frente a 3,76.
- **Límite conocido:** V1 lee la misma base que el juez.

## 7. Tamaño del sistema actual

- `src`: 96 ficheros, **27.261 líneas**. Los mayores: `jev_router` 1.412, `conversational_core` 1.384, `nucleo/extractor` 1.364,
  `intent_detector` 1.126, `rag_agent` 1.096.
- `src/agents`: 42 módulos. `src/prompts`: 53 constantes, y más texto de prompt repartido en otros ficheros.
- `scripts`: 124 ficheros, 17.828 líneas.

## 8. Herramientas del equipo

- **Coral** (`tools/coral`): el chat entre los Claudes, con su servidor, sus ganchos y la memoria compartida (rama `memoria`).
- `.claude/`: los ganchos de Coral y las órdenes `closework`, `runtests` y `startcontext`.
- `docs/project-history/` y `docs/HISTORY.md`: la historia del proyecto.
