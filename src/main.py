import asyncio

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.channels.chatwoot import poll_chatwoot_interactions
from src.channels.chatwoot import router as chatwoot_router
from src.config import settings

logger = structlog.get_logger()

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
  </style>
</head>
<body>
  <main class="card">
    <h1>Diving Planet Bot</h1>
    <p>Habla con nuestro asistente virtual para reservar actividades de buceo y snorkel.</p>
    <p>Haz clic en la burbuja de chat en la esquina inferior derecha.</p>
    <span class="pill">Diving Planet · Cartagena de Indias</span>
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
