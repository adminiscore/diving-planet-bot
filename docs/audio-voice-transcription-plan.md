# Plan: reconocimiento de audio (notas de voz del cliente → texto → respuesta)

> Estado: **Fase 1 en implementación** (2026-07-08). Este documento es el hilo para que
> cualquiera del equipo pueda continuar sin depender de nadie más. Marca las casillas a
> medida que avances.

## Contexto y por qué

Hoy, cuando un cliente manda una **nota de voz**, el bot la ignora: en
`src/channels/chatwoot.py`, `extract_incoming_content()` devuelve `payload.get("content", "")`,
que para un audio viene **vacío**, y el adjunto (`attachments[].data_url`, `file_type: "audio"`)
no se mira en ninguna parte. El cliente manda voz y el bot responde con el fallback genérico
(o nada útil).

No es hipotético: en las conversaciones reales de WhatsApp de la KB (`conversations.json`) hay
**29 audios** (`<adjunto: ...-AUDIO-...opus>`). En WhatsApp la gente manda notas de voz sin
parar. Cuando se conecte WhatsApp Business API (pendiente en `session-handoff.md`), sin esto se
pierde una fracción real de clientes en el primer mensaje.

## Idea central (por qué es barato y de bajo riesgo)

Transcribimos el audio a texto **en el borde de la ingesta**. El transcript entra en el pipeline
**como si el cliente lo hubiera escrito**, así que **nada aguas abajo cambia**: detección de
intención, orquestador, RAG, árbol de decisión, memoria, escalado, PII — todo funciona igual. El
audio se convierte en texto en la puerta de entrada y el resto del bot ni se entera.

Ventajas que ya teníamos servidas:
- **OpenAI ya está cableado** (`AsyncOpenAI` en `rag_agent.py`/`orchestrator.py`, key en settings).
  La transcripción es el mismo SDK, la misma key, la misma facturación. Cero proveedores nuevos.
- **`httpx` ya se usa** para todo Chatwoot → descargar el `data_url` es trivial.
- El transcript pasa por el `detect_pii`/`redact_pii` existente → privacidad cubierta.

## El detalle NO obvio (no te lo saltes)

Hay **dos rutas de ingesta**, no una:
1. El **webhook**: `handle_message()` → `extract_incoming_content(payload)`.
2. El **poller de 1s**: `poll_active_conversations_once()`, que lee `chatwoot_message.get("content")`
   **directamente**, sin pasar por `extract_incoming_content`.

Si solo parcheas una, el audio funciona por un camino y no por el otro. **Ambas deben pasar por el
mismo helper compartido** (`_resolve_incoming_message`, ver Fase 1c).

## Decisiones de diseño ya tomadas

- **Modelo**: `gpt-4o-mini-transcribe` (más barato y mejor que `whisper-1`; SDK 2.31.0 lo soporta).
  Configurable vía `settings.openai_transcription_model`.
- **Idioma**: auto-detección de Whisper (no forzamos es/en — el centro es bilingüe). El modelo lo
  detecta solo.
- **Latencia/coste**: ~1-3s y fracciones de céntimo por audio. Consistente con lo que ya tarda un
  turno (route_message ya llama a gpt-4o de forma bloqueante). No se nota.
- **Responder CON audio (TTS): NO** (fuera de alcance, y desaconsejado). El bot vive de botones y
  quick replies (actividad/cantidad/isla) que no funcionan en audio. Recibir audio: sí. Responder
  en audio: no.
- **Fallback obligatorio**: si la transcripción falla / viene vacía / es ruido → mensaje amable
  ("no pude entender el audio, ¿me lo escribes?"), NUNCA romperse ni tragarse el turno en silencio.
- **NO desplegar a PRE hasta validar en dev.** El widget web actual probablemente no graba notas de
  voz (eso es nativo de WhatsApp), así que la función queda latente hasta WhatsApp — no hay prisa
  por desplegar, pero sí conviene dejarla lista y testeada.

---

## Fase 1 — MVP (recibir audio → transcribir → responder)

- [ ] **1a. Módulo `src/channels/audio.py`** (aislado y testeable):
  - `first_audio_attachment(message: dict) -> dict | None` — primer adjunto con `file_type == "audio"`.
  - `async def transcribe_audio_url(data_url: str, lang_hint: str | None = None) -> str | None`
    — descarga el audio con `httpx` y lo transcribe con OpenAI; devuelve el texto o `None` ante
    cualquier fallo (red, API, vacío). Nunca lanza.
  - `AUDIO_FALLBACK: dict[str, str]` — mensajes es/en para cuando la transcripción falla.
- [ ] **1b. Setting** `openai_transcription_model: str = "gpt-4o-mini-transcribe"` en `config.py`.
- [ ] **1c. Integrar en las 2 rutas** vía un helper compartido en `chatwoot.py`:
  - `async def _resolve_incoming_message(msg: dict) -> tuple[str | None, bool]` → `(text, audio_failed)`.
    - Si hay `content` de texto → `(content, False)`.
    - Si `content` vacío y hay adjunto de audio → transcribe: `(transcript, False)` o, si falla,
      `(None, True)`.
    - Si no hay ni texto ni audio (imagen, evento del sistema...) → `(None, False)` (skip, como hoy).
  - En `handle_message` y en `poll_active_conversations_once`: usar este helper. Si `audio_failed`
    → mandar `AUDIO_FALLBACK[state.language]`, marcar el mensaje como procesado (para que el poller
    no reintente) y `return`. Si `text is None` → skip. Si hay texto → `route_message(state, text)`
    igual que ahora.
  - **Dedup**: la clave sigue siendo `{conversation_id}:{message_id}:incoming` (por message_id, no
    por contenido), así que la transcripción no se repite. Marca la clave también en el caso de
    fallo de audio.
- [ ] **1d. Tests** (`tests/test_audio_transcription.py`), con la llamada a OpenAI y la descarga
  `httpx` **mockeadas** (ni un céntimo en CI):
  - audio OK → el transcript llega a `route_message`.
  - audio que falla la transcripción → se manda el fallback, no se rompe, se marca procesado.
  - mensaje de texto normal → intacto (no toca el audio path).
  - mensaje sin texto ni audio → skip silencioso (comportamiento actual).
  - `first_audio_attachment`: detecta audio, ignora imágenes, lista vacía.
- [ ] **Suite completa verde** + `compileall`.
- [ ] **Closework**: entrada en `docs/HISTORY.md`, actualizar `session-handoff.md`, commit + push a
  `feature/dev_alvaro`. **NO** actualizar `feature/pre_alvaro` (no desplegar a PRE) hasta que se
  valide con un audio real y el equipo lo apruebe.

## Fase 2 — pulido (después de validar Fase 1)

- [ ] **Eco de confirmación / nota privada**: mostrar "Entendí: _'...'_" al cliente (o al menos
  dejar el transcript como **nota privada** para el asesor). Importante por la sensibilidad a
  alucinaciones: una transcripción errónea de "somos 2" → "somos 12" cambiaría la reserva. Ver el
  texto y poder corregir da confianza.
- [ ] Manejo de audios muy largos (>~5 min) y de audios sin voz (ruido) con mensajes específicos.
- [ ] Métricas: contar audios recibidos / transcritos / fallidos (para saber si merece la pena).

## Fase 3 — (opcional, probablemente NO) responder con voz (TTS)

Desaconsejado por ahora (ver "Decisiones de diseño"). Documentado solo para cerrar el tema.

## Cómo probarlo AHORA (sin WhatsApp) — página `/audio-test`

El widget web de Chatwoot no tiene botón de micrófono (grabar voz es nativo de WhatsApp). Para
poder probar la función igualmente, se añadió una **herramienta de test** (v0.20.1):

- **`GET /audio-test`** (p.ej. `https://pre.is-core.dev/audio-test`): página con un botón
  "🎤 Mantén pulsado para grabar". Graba con el micro del navegador (MediaRecorder), envía el audio
  y muestra en pantalla **qué transcribió el bot** y **qué respondería** (con sus botones). Mantiene
  contexto entre grabaciones (memoria por conversación) y tiene "🔄 Nueva conversación".
- **`POST /audio-test`**: recibe el blob de audio crudo en el body, lo transcribe con
  `transcribe_audio_bytes` y lo pasa por el `route_message` real. Devuelve `{transcript, response, buttons}`.
- **Deshabilitado en producción** (`app_env == "production"` → 404). Estado en memoria, aislado de
  las conversaciones reales (NO usa Redis ni Chatwoot).

Requisitos: micrófono permitido en el navegador y HTTPS (PRE ya es https). Esto valida lo valioso:
que el audio real se transcribe bien y que el bot responde con sentido. Cuando WhatsApp esté
conectado, el camino de producción (webhook → `_resolve_voice_note` → pipeline) ya está listo y
probado por separado con los tests unitarios.

## Pruebas manuales del camino de producción (cuando WhatsApp esté vivo)

1. Mandar una nota de voz real por WhatsApp y confirmar que el bot responde al contenido.
2. Mandar un audio ininteligible y confirmar que dispara el fallback ("no pude entender el audio…").

## Referencias de código

- Ingesta webhook: `src/channels/chatwoot.py` → `handle_message`, `extract_incoming_content`.
- Ingesta poller: `src/channels/chatwoot.py` → `poll_active_conversations_once` (lee `content`
  directamente — ¡acuérdate de esta ruta!).
- Envío de mensajes / notas: `send_chatwoot_message`, `send_chatwoot_note`.
- OpenAI ya en uso: `src/agents/rag_agent.py` (patrón `AsyncOpenAI`).
- Config/keys: `src/config.py`.
