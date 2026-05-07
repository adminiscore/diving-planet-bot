# TODO

## Infraestructura multi-entorno

### DEV (local — Windows)
- [ ] Instalar y dejar disponible **Python 3.11+** en el PATH (que funcione `python --version`).
- [ ] Instalar **Docker Desktop** y verificar que funciona (`docker compose version`).
- [ ] Copiar `.env.dev.example` a `.env` y configurar `OPENAI_API_KEY`.
- [ ] Levantar infra local: `docker compose up -d` (PostgreSQL + Redis).
- [ ] (Opcional) Levantar Chatwoot local: `docker compose --profile chatwoot up -d`.
- [ ] Instalar dependencias del proyecto: `pip install -e ".[dev]"`.
- [ ] Crear DB de Chatwoot si aplica: `docker exec dp-dev-postgres psql -U postgres -c "CREATE DATABASE chatwoot_dev;"`.
- [ ] Ejecutar carga de embeddings: `python -m scripts.load_embeddings`.
- [ ] Arrancar el bot: `python -m src.main` y verificar `http://localhost:8000/health`.

### PRE (staging — VPS)
- [ ] Provisionar VPS (Hetzner/DigitalOcean/OVH, mínimo 4GB RAM).
- [ ] Configurar DNS: `pre.divingplanet.org` → IP del VPS.
- [ ] Copiar repo al VPS (`git clone`).
- [ ] Copiar `.env.pre.example` a `.env.pre` y configurar API keys + contraseñas fuertes.
- [ ] Levantar VPS: `docker compose -f docker-compose.vps.yml up -d --build`.
- [ ] Crear DB de Chatwoot: `docker exec dp-pro-postgres psql -U postgres -c "CREATE DATABASE chatwoot_production;"`.
- [ ] Cargar embeddings en pre: `docker exec dp-pre-bot python -m scripts.load_embeddings`.
- [ ] Verificar: `curl https://pre.divingplanet.org/health`.

### PRO (producción — VPS, mismo servidor)
- [ ] Configurar DNS: `api.divingplanet.org` + `chatwoot.divingplanet.org` → IP del VPS.
- [ ] Copiar `.env.pro.example` a `.env.pro` y configurar API keys + contraseñas fuertes.
- [ ] Reiniciar con variables de producción: `docker compose -f docker-compose.vps.yml up -d --build`.
- [ ] Cargar embeddings en pro: `docker exec dp-pro-bot python -m scripts.load_embeddings`.
- [ ] Configurar Chatwoot: crear cuenta admin, inbox WhatsApp, generar API token.
- [ ] Configurar webhook en Chatwoot: `https://api.divingplanet.org/webhooks/chatwoot`.
- [ ] Conectar WhatsApp Business API en Chatwoot.
- [ ] Verificar: `curl https://api.divingplanet.org/health`.

## Funcionalidad pendiente (media prioridad)
- [ ] Validar que `data/knowledge_base/conversations.json` está siendo indexado correctamente en `kb_documents`.
- [ ] Ajustar/añadir reglas de privacidad para que el bot no pida ni repita datos sensibles (IDs, cuentas, comprobantes) y siempre derive a humano.
- [ ] Implementar **Booking Agent** (integración Roverd deep links).
- [ ] Migrar estado de conversaciones de memoria (`dict`) a Redis/PostgreSQL.

## Mejas (baja prioridad)
- [ ] Expandir `conversations.json` con más ejemplos reales (incluyendo casos difíciles de clima, recogidas específicas, cambios de muelle, etc.).
- [ ] Añadir un comando/shortcut (script) para re-indexar embeddings de forma segura (por ejemplo confirmación antes del `DELETE`).
- [ ] Revisar el `SYSTEM_PROMPT` del `rag_agent` para reflejar el tono definido en `brand_tone.json` y las reglas de escalado.
- [ ] Añadir tests para supervisor, RAG agent, escalado y webhook.
- [ ] Dashboard del dueño (analytics de conversaciones, servicios consultados, conversiones).
- [ ] Alembic migrations para esquema de DB.
