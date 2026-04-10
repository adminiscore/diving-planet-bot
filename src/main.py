import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.channels.chatwoot import router as chatwoot_router

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
