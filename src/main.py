import asyncio

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.channels.audio import AUDIO_FALLBACK, transcribe_audio_bytes
from src.channels.chatwoot import poll_chatwoot_interactions
from src.channels.chatwoot import router as chatwoot_router
from src.config import settings
from src.flows.decision_tree import MESSAGE_SPLIT, ConversationState

logger = structlog.get_logger()

# In-memory conversation state for the /audio-test tool only (keyed by a
# client-generated id). Deliberately NOT Redis — keeps the test tool working
# anywhere and isolated from real conversations.
_audio_test_states: dict[str, ConversationState] = {}

app = FastAPI(
    title="Diving Planet Bot",
    description="AI-powered customer service chatbot for Diving Planet Cartagena",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else [settings.chatwoot_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatwoot_router, prefix="/webhooks", tags=["webhooks"])


@app.on_event("startup")
async def start_chatwoot_interaction_polling():
    app.state.chatwoot_polling_task = asyncio.create_task(poll_chatwoot_interactions())


@app.on_event("shutdown")
async def stop_chatwoot_interaction_polling():
    task = getattr(app.state, "chatwoot_polling_task", None)
    if task:
        task.cancel()


@app.get("/chat", response_class=HTMLResponse)
async def chat_widget():
    """Serve the Chatwoot widget test page for external testers."""
    chatwoot_url = settings.chatwoot_base_url.rstrip("/")
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Diving Planet Bot</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: linear-gradient(135deg, #062b43, #0b5c7a);
      color: #fff;
      min-height: 100vh;
      display: grid;
      place-items: center;
    }}
    .card {{
      width: min(680px, calc(100vw - 32px));
      background: rgba(255,255,255,0.08);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255,255,255,0.16);
      border-radius: 18px;
      padding: 28px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ margin: 0 0 10px; line-height: 1.5; color: rgba(255,255,255,0.9); }}
    .pill {{
      display: inline-block;
      margin-top: 12px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.14);
      font-size: 14px;
    }}
    .reset-btn {{
      display: block;
      margin-top: 20px;
      padding: 10px 16px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.25);
      background: rgba(255,255,255,0.12);
      color: #fff;
      font-size: 14px;
      cursor: pointer;
    }}
    .reset-btn:hover {{ background: rgba(255,255,255,0.22); }}
  </style>
</head>
<body>
  <main class="card">
    <h1>Diving Planet Bot</h1>
    <p>Habla con nuestro asistente virtual para reservar actividades de buceo y snorkel.</p>
    <p>Haz clic en la burbuja de chat en la esquina inferior derecha.</p>
    <span class="pill">Diving Planet · Cartagena de Indias</span>
    <button class="reset-btn" onclick="if(window.$chatwoot){{window.$chatwoot.reset();}} setTimeout(function(){{location.reload();}}, 300);">
      🔄 Nueva conversación
    </button>
  </main>
  <script>
    (function(d,t){{
      var BASE_URL='{chatwoot_url}';
      var g=d.createElement(t),s=d.getElementsByTagName(t)[0];
      g.src=BASE_URL+'/packs/js/sdk.js';
      g.defer=true; g.async=true;
      s.parentNode.insertBefore(g,s);
      g.onload=function(){{
        window.chatwootSDK.run({{
          websiteToken:'{settings.chatwoot_website_token}',
          baseUrl:BASE_URL,
          locale:'es',
          position:'right'
        }});
      }};
    }})(document,'script');
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


# --------------------------------------------------------------------------- #
# Voice-note test tool (/audio-test)
#
# The Chatwoot web widget has no mic/record button (voice notes are a WhatsApp-
# native thing), so this standalone page lets a tester record with the browser
# microphone and see (a) what the bot transcribed and (b) how it would answer —
# exercising the real transcription + route_message pipeline. Disabled in
# production. State is in-memory and isolated from real conversations.
# --------------------------------------------------------------------------- #

_AUDIO_TEST_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Diving Planet Bot — Prueba de audio</title>
  <style>
    body { margin:0; font-family:Arial,sans-serif; background:linear-gradient(135deg,#062b43,#0b5c7a); color:#fff; min-height:100vh; display:flex; justify-content:center; }
    .card { width:min(680px,calc(100vw - 24px)); margin:24px 12px; }
    h1 { font-size:24px; margin:0 0 6px; }
    p.sub { color:rgba(255,255,255,0.8); margin:0 0 20px; font-size:14px; }
    button { font-size:16px; padding:14px 20px; border-radius:12px; border:1px solid rgba(255,255,255,0.25); background:rgba(255,255,255,0.12); color:#fff; cursor:pointer; }
    button:hover { background:rgba(255,255,255,0.22); }
    #rec.recording { background:#e5484d; border-color:#e5484d; }
    .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
    .status { margin:14px 0; font-size:14px; color:rgba(255,255,255,0.85); min-height:20px; }
    .bubble { margin-top:14px; padding:14px 16px; border-radius:14px; background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.16); white-space:pre-wrap; line-height:1.5; }
    .bubble .label { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:rgba(255,255,255,0.6); margin-bottom:6px; }
    .btns { margin-top:8px; font-size:13px; color:rgba(255,255,255,0.7); }
    .muted { color:rgba(255,255,255,0.55); font-size:13px; }
  </style>
</head>
<body>
  <main class="card">
    <h1>🎤 Prueba de audio del bot</h1>
    <p class="sub">Graba un mensaje con tu voz (como una nota de voz de WhatsApp) y mira qué entiende el bot y cómo respondería.</p>
    <div class="row">
      <button id="rec">🎤 Mantén pulsado para grabar</button>
      <button id="reset" title="Empezar una conversación nueva">🔄 Nueva conversación</button>
    </div>
    <div class="status" id="status">Listo.</div>
    <div id="out"></div>
    <p class="muted">Requiere permitir el micrófono. Herramienta solo para pruebas.</p>
  </main>
  <script>
    let convId = 'audiotest-' + Math.random().toString(36).slice(2);
    let mediaRecorder = null, chunks = [];
    const recBtn = document.getElementById('rec');
    const statusEl = document.getElementById('status');
    const outEl = document.getElementById('out');

    function extFor(mime) {
      if (mime.includes('mp4') || mime.includes('m4a')) return 'mp4';
      if (mime.includes('ogg')) return 'ogg';
      if (mime.includes('wav')) return 'wav';
      return 'webm';
    }

    async function startRec() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        chunks = [];
        mediaRecorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
        mediaRecorder.onstop = async () => {
          stream.getTracks().forEach(t => t.stop());
          const mime = mediaRecorder.mimeType || 'audio/webm';
          const blob = new Blob(chunks, { type: mime });
          if (!blob.size) { statusEl.textContent = 'No se grabó audio.'; return; }
          statusEl.textContent = 'Transcribiendo y consultando al bot…';
          try {
            const res = await fetch('/audio-test?conversation_id=' + convId + '&ext=' + extFor(mime), {
              method: 'POST', headers: { 'Content-Type': mime }, body: blob
            });
            const data = await res.json();
            render(data);
            statusEl.textContent = 'Listo. Graba otra vez para continuar la conversación.';
          } catch (err) {
            statusEl.textContent = 'Error enviando el audio: ' + err;
          }
        };
        mediaRecorder.start();
        recBtn.classList.add('recording');
        recBtn.textContent = '● Grabando… suelta para enviar';
        statusEl.textContent = 'Grabando…';
      } catch (err) {
        statusEl.textContent = 'No se pudo acceder al micrófono: ' + err;
      }
    }
    function stopRec() {
      if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
      recBtn.classList.remove('recording');
      recBtn.textContent = '🎤 Mantén pulsado para grabar';
    }
    function render(data) {
      let html = '';
      html += '<div class="bubble"><div class="label">Entendí (transcripción)</div>' +
              (data.transcript ? escapeHtml(data.transcript) : '<span class="muted">— no se entendió el audio —</span>') + '</div>';
      html += '<div class="bubble"><div class="label">Respuesta del bot</div>' + escapeHtml(data.response || '') +
              (data.buttons && data.buttons.length ? '<div class="btns">Botones: ' + data.buttons.map(escapeHtml).join(' · ') + '</div>' : '') +
              '</div>';
      outEl.innerHTML = html + outEl.innerHTML;
    }
    function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    // Hold-to-talk (mouse + touch)
    recBtn.addEventListener('mousedown', startRec);
    recBtn.addEventListener('mouseup', stopRec);
    recBtn.addEventListener('mouseleave', stopRec);
    recBtn.addEventListener('touchstart', e => { e.preventDefault(); startRec(); });
    recBtn.addEventListener('touchend', e => { e.preventDefault(); stopRec(); });
    document.getElementById('reset').addEventListener('click', () => {
      convId = 'audiotest-' + Math.random().toString(36).slice(2);
      outEl.innerHTML = '';
      statusEl.textContent = 'Conversación nueva. Listo.';
    });
  </script>
</body>
</html>"""


@app.get("/audio-test", response_class=HTMLResponse)
async def audio_test_page():
    if settings.app_env == "production":
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(content=_AUDIO_TEST_PAGE)


@app.post("/audio-test")
async def audio_test_run(request: Request, conversation_id: str = "audio-test", ext: str = "webm"):
    """Transcribe an uploaded browser recording and run it through the real bot
    pipeline. Test tool only — disabled in production."""
    if settings.app_env == "production":
        return JSONResponse({"error": "disabled in production"}, status_code=404)

    audio_bytes = await request.body()
    transcript = await transcribe_audio_bytes(audio_bytes, f"audio.{ext}")
    if not transcript:
        return JSONResponse({"transcript": None, "response": AUDIO_FALLBACK["es"], "buttons": []})

    state = _audio_test_states.get(conversation_id)
    if state is None:
        state = ConversationState(conversation_id=conversation_id, language=settings.default_language)
        _audio_test_states[conversation_id] = state

    from src.agents.supervisor import route_message

    response = await route_message(state, transcript)
    response_text = (response or "").replace(MESSAGE_SPLIT, "\n\n")
    buttons = [qr.get("title", "") for qr in (state.quick_replies or [])]
    return JSONResponse({"transcript": transcript, "response": response_text, "buttons": buttons})


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "diving-planet-bot",
        "environment": settings.app_env,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.is_dev,
    )
