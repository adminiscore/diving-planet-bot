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


# --------------------------------------------------------------------------- #
# Shared "underwater" brand design system for the public pages (/chat,
# /audio-test). Plain strings (NOT f-strings) so CSS/JS braces stay literal;
# the few dynamic values are injected with .replace() at request time.
# --------------------------------------------------------------------------- #

_BRAND_HEAD = """  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#062b43" />
  <title>__TITLE__</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root{
      --ink:#eaf6ff; --muted:rgba(234,246,255,.72);
      --ocean-950:#04141f; --ocean-900:#062b43; --ocean-700:#0b5c7a; --ocean-500:#1690bd;
      --coral:#ff5a3c; --gold:#ffc72c; --flag:#e11d2a;
      --glass:rgba(255,255,255,.08); --glass-brd:rgba(255,255,255,.16);
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0; color:var(--ink); min-height:100dvh;
      font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
      background:
        radial-gradient(1100px 720px at 72% -12%, rgba(60,190,225,.30), transparent 58%),
        radial-gradient(900px 620px at 8% 112%, rgba(255,90,60,.13), transparent 55%),
        linear-gradient(165deg,#073650 0%,#062b43 38%,#04141f 100%);
      display:flex; justify-content:center; align-items:flex-start;
      position:relative; overflow-x:hidden;
    }
    .ocean{position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden}
    .ocean .rays{position:absolute; inset:-25% -12% auto -12%; height:130%;
      background:repeating-linear-gradient(74deg, rgba(255,255,255,.05) 0 2px, transparent 2px 48px);
      filter:blur(2px); transform-origin:top center;
      animation:sway 15s ease-in-out infinite alternate; opacity:.5}
    @keyframes sway{from{transform:rotate(-3deg) translateX(-2%)} to{transform:rotate(3deg) translateX(2%)}}
    .bubbles span{position:absolute; bottom:-40px; border-radius:50%;
      background:radial-gradient(circle at 30% 30%, rgba(255,255,255,.6), rgba(255,255,255,.05) 60%, transparent);
      border:1px solid rgba(255,255,255,.14); animation:rise linear infinite}
    @keyframes rise{0%{transform:translateY(0) scale(.8); opacity:0}
      12%{opacity:.7} 100%{transform:translateY(-112vh) scale(1.1); opacity:0}}
    .wrap{position:relative; z-index:1; width:min(600px, calc(100vw - 28px)); margin:min(9vh,72px) 14px 40px}
    .card{background:var(--glass); backdrop-filter:blur(18px) saturate(140%);
      -webkit-backdrop-filter:blur(18px) saturate(140%);
      border:1px solid var(--glass-brd); border-radius:26px; padding:clamp(24px,5vw,40px);
      box-shadow:0 34px 90px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.14)}
    .emblem{width:76px; height:76px; display:block; filter:drop-shadow(0 8px 18px rgba(0,0,0,.4))}
    .eyebrow{margin:18px 0 8px; font-family:'Outfit',sans-serif; font-weight:700; letter-spacing:.16em;
      text-transform:uppercase; font-size:12px; color:var(--gold)}
    h1{margin:0; font-family:'Outfit',sans-serif; font-weight:800; letter-spacing:-.02em;
      font-size:clamp(28px,6vw,42px); line-height:1.06}
    h1 .accent{background:linear-gradient(100deg,var(--coral),var(--gold));
      -webkit-background-clip:text; background-clip:text; color:transparent}
    .tagline{margin:14px 0 0; color:var(--muted); font-size:clamp(15px,2.4vw,17px); line-height:1.55}
    .chips{display:flex; flex-wrap:wrap; gap:8px; margin:22px 0 2px}
    .chip{display:inline-flex; align-items:center; gap:6px; padding:7px 12px; border-radius:999px;
      background:rgba(255,255,255,.08); border:1px solid var(--glass-brd); font-size:13px; font-weight:500}
    .chip b{color:var(--gold); font-weight:700}
    .actions{display:flex; flex-wrap:wrap; gap:12px; margin-top:26px}
    .btn{appearance:none; border:0; cursor:pointer; font-family:'Outfit',sans-serif; font-weight:700;
      font-size:15px; padding:14px 20px; border-radius:14px; display:inline-flex; align-items:center; gap:9px;
      transition:transform .12s ease, box-shadow .2s ease, background .2s ease; text-decoration:none; color:var(--ink)}
    .btn:active{transform:translateY(1px)}
    .btn-primary{color:#08222f; background:linear-gradient(135deg,var(--coral),var(--gold));
      box-shadow:0 12px 26px rgba(255,120,60,.35)}
    .btn-primary:hover{box-shadow:0 16px 34px rgba(255,120,60,.5); transform:translateY(-1px)}
    .btn-ghost{background:rgba(255,255,255,.10); border:1px solid var(--glass-brd)}
    .btn-ghost:hover{background:rgba(255,255,255,.18)}
    .foot{margin-top:22px; font-size:12.5px; color:rgba(234,246,255,.5)}
    .mic-zone{display:flex; flex-direction:column; align-items:center; gap:12px; margin:28px 0 6px}
    .mic{width:132px; height:132px; border-radius:50%; border:0; cursor:pointer; color:#fff; font-size:40px;
      background:radial-gradient(circle at 35% 30%, #2bb4e6, var(--ocean-700));
      box-shadow:0 18px 40px rgba(0,0,0,.45), inset 0 2px 6px rgba(255,255,255,.3);
      display:grid; place-items:center; position:relative; transition:transform .12s ease;
      -webkit-user-select:none; user-select:none; touch-action:none}
    .mic:active{transform:scale(.96)}
    .mic.recording{background:radial-gradient(circle at 35% 30%, #ff7a5c, var(--flag))}
    .mic.recording::before,.mic.recording::after{content:""; position:absolute; inset:0; border-radius:50%;
      border:2px solid rgba(255,120,90,.55); animation:ring 1.6s ease-out infinite}
    .mic.recording::after{animation-delay:.8s}
    @keyframes ring{0%{transform:scale(1); opacity:.7} 100%{transform:scale(1.9); opacity:0}}
    .hint{font-family:'Outfit',sans-serif; font-weight:600; font-size:14px; color:var(--muted)}
    .status{min-height:18px; font-size:13.5px; color:rgba(234,246,255,.7); text-align:center}
    .msg{padding:14px 16px; border-radius:16px; margin-top:12px; white-space:pre-wrap; line-height:1.5; font-size:15px}
    .msg .who{font-family:'Outfit',sans-serif; font-size:11px; letter-spacing:.08em;
      text-transform:uppercase; opacity:.65; margin-bottom:6px}
    .msg.you{background:linear-gradient(135deg, rgba(255,90,60,.24), rgba(255,199,44,.16));
      border:1px solid rgba(255,150,90,.28)}
    .msg.bot{background:rgba(255,255,255,.09); border:1px solid var(--glass-brd)}
    .msg .btns{margin-top:10px; display:flex; flex-wrap:wrap; gap:6px}
    .msg .btns .b{font-size:12px; padding:5px 10px; border-radius:999px;
      background:rgba(255,255,255,.10); border:1px solid var(--glass-brd)}
    .muted{color:rgba(234,246,255,.5)}
  </style>"""

_OCEAN_BG = """  <div class="ocean" aria-hidden="true">
    <div class="rays"></div>
    <div class="bubbles">
      <span style="left:8%;width:10px;height:10px;animation-duration:16s;animation-delay:0s"></span>
      <span style="left:20%;width:6px;height:6px;animation-duration:12s;animation-delay:3s"></span>
      <span style="left:33%;width:14px;height:14px;animation-duration:19s;animation-delay:1s"></span>
      <span style="left:48%;width:8px;height:8px;animation-duration:14s;animation-delay:5s"></span>
      <span style="left:62%;width:5px;height:5px;animation-duration:11s;animation-delay:2s"></span>
      <span style="left:74%;width:12px;height:12px;animation-duration:18s;animation-delay:4s"></span>
      <span style="left:86%;width:7px;height:7px;animation-duration:13s;animation-delay:6s"></span>
      <span style="left:94%;width:9px;height:9px;animation-duration:15s;animation-delay:1.5s"></span>
    </div>
  </div>"""

_EMBLEM = """<svg class="emblem" viewBox="0 0 100 100" role="img" aria-label="Diving Planet">
    <defs><radialGradient id="oc" cx="35%" cy="30%" r="75%">
      <stop offset="0" stop-color="#38b6e6"/><stop offset="1" stop-color="#0b5c7a"/></radialGradient></defs>
    <circle cx="50" cy="50" r="46" fill="url(#oc)" stroke="rgba(255,255,255,.42)" stroke-width="2.5"/>
    <path d="M30 52 l-12 -10 l3.5 10 l-3.5 10 z" fill="#ffc72c"/>
    <ellipse cx="54" cy="52" rx="21" ry="13.5" fill="#ff5a3c"/>
    <path d="M50 52 q7 -6 15 0 q-7 6 -15 0z" fill="#e5442b" opacity=".5"/>
    <circle cx="64" cy="49" r="3" fill="#08222f"/><circle cx="65.2" cy="47.9" r="1" fill="#fff"/>
    <g fill="#ffc72c">
      <path d="M75 29 l1.5 4.2 l4.2 1.5 l-4.2 1.5 l-1.5 4.2 l-1.5 -4.2 l-4.2 -1.5 l4.2 -1.5z"/>
      <path d="M31 27 l1 2.8 l2.8 1 l-2.8 1 l-1 2.8 l-1 -2.8 l-2.8 -1 l2.8 -1z"/>
    </g>
  </svg>"""

_CHAT_PAGE = (
    "<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n"
    + _BRAND_HEAD.replace("__TITLE__", "Diving Planet · Buceo en Cartagena")
    + "\n</head>\n<body>\n"
    + _OCEAN_BG
    + """
  <div class="wrap"><main class="card">
    """ + _EMBLEM + """
    <div class="eyebrow">Desde 1995 · 30 años bajo el mar</div>
    <h1>Diving Planet <span class="accent">Cartagena</span></h1>
    <p class="tagline">Reserva buceo, cursos PADI y snorkel en las Islas del Rosario con nuestro asistente virtual. Pregúntale lo que quieras — te responde al instante. 🐠</p>
    <div class="chips">
      <span class="chip">⭐ <b>PADI</b> 5 Star</span>
      <span class="chip">🐠 Islas del Rosario</span>
      <span class="chip">🤿 <b>30</b> años de experiencia</span>
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="#" onclick="if(window.$chatwoot){window.$chatwoot.toggle('open');}return false;">💬 Abrir el chat</a>
      <button class="btn btn-ghost" onclick="if(window.$chatwoot){window.$chatwoot.reset();} setTimeout(function(){location.reload();},300);">🔄 Nueva conversación</button>
    </div>
    <p class="foot">También puedes tocar la burbuja de chat abajo a la derecha. · Cartagena de Indias 🇨🇴</p>
  </main></div>
  <script>
    (function(d,t){
      var BASE_URL='__CHATWOOT_URL__';
      var g=d.createElement(t),s=d.getElementsByTagName(t)[0];
      g.src=BASE_URL+'/packs/js/sdk.js'; g.defer=true; g.async=true;
      s.parentNode.insertBefore(g,s);
      g.onload=function(){ window.chatwootSDK.run({ websiteToken:'__WEBSITE_TOKEN__', baseUrl:BASE_URL, locale:'es', position:'right' }); };
    })(document,'script');
  </script>
</body>
</html>"""
)


@app.get("/chat", response_class=HTMLResponse)
async def chat_widget():
    """Serve the Chatwoot widget landing/test page for external testers."""
    chatwoot_url = settings.chatwoot_base_url.rstrip("/")
    html = _CHAT_PAGE.replace("__CHATWOOT_URL__", chatwoot_url).replace(
        "__WEBSITE_TOKEN__", settings.chatwoot_website_token
    )
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

_AUDIO_TEST_PAGE = (
    "<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n"
    + _BRAND_HEAD.replace("__TITLE__", "Diving Planet · Prueba de voz")
    + "\n</head>\n<body>\n"
    + _OCEAN_BG
    + """
  <div class="wrap"><main class="card">
    """ + _EMBLEM + """
    <div class="eyebrow">Prueba de voz</div>
    <h1>Habla con el <span class="accent">bot</span></h1>
    <p class="tagline">Graba un mensaje con tu voz, como una nota de WhatsApp. El bot lo transcribe y te muestra qué entendió y cómo respondería. 🎙️</p>
    <div class="mic-zone">
      <button id="rec" class="mic" aria-label="Mantén pulsado para grabar">🎤</button>
      <div class="hint" id="hint">Mantén pulsado para hablar</div>
      <div class="status" id="status"></div>
    </div>
    <div id="out"></div>
    <div class="actions" style="margin-top:10px">
      <button class="btn btn-ghost" id="reset">🔄 Nueva conversación</button>
    </div>
    <p class="foot">Permite el micrófono cuando el navegador lo pida. Herramienta solo para pruebas internas.</p>
  </main></div>
  <script>
    var convId = 'audiotest-' + Math.random().toString(36).slice(2);
    var mediaRecorder = null, chunks = [];
    var recBtn = document.getElementById('rec');
    var hintEl = document.getElementById('hint');
    var statusEl = document.getElementById('status');
    var outEl = document.getElementById('out');

    function extFor(mime){
      if (mime.indexOf('mp4') > -1 || mime.indexOf('m4a') > -1) return 'mp4';
      if (mime.indexOf('ogg') > -1) return 'ogg';
      if (mime.indexOf('wav') > -1) return 'wav';
      return 'webm';
    }
    async function startRec(){
      try{
        var stream = await navigator.mediaDevices.getUserMedia({ audio:true });
        mediaRecorder = new MediaRecorder(stream);
        chunks = [];
        mediaRecorder.ondataavailable = function(e){ if (e.data.size) chunks.push(e.data); };
        mediaRecorder.onstop = async function(){
          stream.getTracks().forEach(function(t){ t.stop(); });
          var mime = mediaRecorder.mimeType || 'audio/webm';
          var blob = new Blob(chunks, { type:mime });
          if (!blob.size){ statusEl.textContent = 'No se grabó audio.'; return; }
          statusEl.textContent = 'Transcribiendo y consultando al bot…';
          try{
            var res = await fetch('/audio-test?conversation_id=' + convId + '&ext=' + extFor(mime), {
              method:'POST', headers:{ 'Content-Type':mime }, body:blob
            });
            var data = await res.json();
            render(data);
            statusEl.textContent = 'Graba otra vez para continuar la conversación.';
          }catch(err){ statusEl.textContent = 'Error enviando el audio: ' + err; }
        };
        mediaRecorder.start();
        recBtn.classList.add('recording');
        hintEl.textContent = '● Grabando… suelta para enviar';
        statusEl.textContent = '';
      }catch(err){ statusEl.textContent = 'No se pudo acceder al micrófono: ' + err; }
    }
    function stopRec(){
      if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
      recBtn.classList.remove('recording');
      hintEl.textContent = 'Mantén pulsado para hablar';
    }
    function render(data){
      var you = '<div class="msg you"><div class="who">🎙️ Tú (audio)</div>' +
        (data.transcript ? escapeHtml(data.transcript) : '<span class="muted">— no se entendió el audio —</span>') + '</div>';
      var btns = (data.buttons && data.buttons.length)
        ? '<div class="btns">' + data.buttons.map(function(b){ return '<span class="b">' + escapeHtml(b) + '</span>'; }).join('') + '</div>'
        : '';
      var bot = '<div class="msg bot"><div class="who">🐠 Diving Planet Bot</div>' + escapeHtml(data.response || '') + btns + '</div>';
      outEl.innerHTML = you + bot + outEl.innerHTML;
    }
    function escapeHtml(s){ var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }

    recBtn.addEventListener('mousedown', startRec);
    recBtn.addEventListener('mouseup', stopRec);
    recBtn.addEventListener('mouseleave', stopRec);
    recBtn.addEventListener('touchstart', function(e){ e.preventDefault(); startRec(); });
    recBtn.addEventListener('touchend', function(e){ e.preventDefault(); stopRec(); });
    document.getElementById('reset').addEventListener('click', function(){
      convId = 'audiotest-' + Math.random().toString(36).slice(2);
      outEl.innerHTML = '';
      statusEl.textContent = 'Conversación nueva. Listo.';
    });
  </script>
</body>
</html>"""
)


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
