# TODO

## Infraestructura multi-entorno

### DEV (local — Windows)
- [x] Instalar y dejar disponible **Python 3.11+** en el PATH (que funcione `python --version`).
- [x] Instalar **Docker Desktop** y verificar que funciona (`docker compose version`).
- [x] Copiar `.env.dev.example` a `.env.dev` y configurar `OPENAI_API_KEY`.
- [x] Levantar infra local: `docker compose up -d` (PostgreSQL + Redis).
- [x] (Opcional) Levantar Chatwoot local: `docker compose --profile chatwoot up -d`.
- [x] Instalar dependencias del proyecto: `pip install -e ".[dev]"`.
- [x] Crear DB de Chatwoot si aplica: `docker exec dp-dev-postgres psql -U postgres -c "CREATE DATABASE chatwoot_dev;"`.
- [x] Ejecutar carga de embeddings: `python -m scripts.load_embeddings`.
- [x] Arrancar el bot: `python -m src.main` y verificar `http://localhost:8000/health`.
- [x] **CHATWOOT INTEGRATION FUNCIONAL**: Widget local funcionando y bot respondiendo mensajes.

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

## Funcionalidad implementada (Phase 1 completada)
- [x] **Decision Tree**: Árbol de decisiones completo con flujos guiados
- [x] **Botones interactivos**: Integración con Chatwoot para menús interactivos
- [x] **Supervisor Agent**: Routing inteligente entre decision tree y RAG
- [x] **RAG Agent**: Respuestas a preguntas libres usando base de conocimiento
- [x] **Chatwoot Integration**: Webhooks, envío de mensajes, y polling de interacciones
- [x] **Multi-idioma**: Soporte ES/EN en todo el flujo
- [x] **Base de conocimiento**: Embeddings cargados en pgvector
- [x] **Tests**: Tests unitarios para botones y decision tree

## Funcionalidad pendiente (Phase 2 - LangGraph multi-agent)
- [x] Validar que `data/knowledge_base/conversations.json` está siendo indexado correctamente en `kb_documents`.
- [ ] Ajustar/añadir reglas de privacidad para que el bot no pida ni repita datos sensibles (IDs, cuentas, comprobantes) y siempre derive a humano.
- [ ] Implementar **Booking Agent** (integración Roverd deep links).
- [ ] Migrar estado de conversaciones de memoria (`dict`) a Redis/PostgreSQL.
- [ ] Implementar **Escalation Agent** con handoff a humano en Chatwoot.

## Mejoras (baja prioridad)
- [x] Expandir `conversations.json` con más ejemplos reales (WhatsApp) y sanitización básica.
- [x] Importador WhatsApp con chunking temático (`*_partN`) + extracción heurística de topics.
- [x] Script de limpieza para mantener solo `whatsapp_import_*_partN`.
- [x] Retrieval híbrido topic-aware: boost por topics + pesos por `source` (policies/faqs/services/conversations).
- [x] Normalizar topics legacy en conversaciones curadas al indexar (mapping a topics canónicos) para mejorar overlap en reranking.
- [x] Logging de diagnóstico de retrieval (topics detectados + preview de scores).
- [ ] Añadir un comando/shortcut (script) para re-indexar embeddings de forma segura (por ejemplo confirmación antes del `DELETE`).
- [ ] Revisar el `SYSTEM_PROMPT` del `rag_agent` para reflejar el tono definido en `brand_tone.json` y las reglas de escalado.
- [ ] Añadir tests para supervisor, RAG agent, escalado y webhook.
- [ ] Dashboard del dueño (analytics de conversaciones, servicios consultados, conversiones).
- [ ] Alembic migrations para esquema de DB.

## Próximos pasos inmediatos
1. **Testing end-to-end**: Verificar flujo completo desde widget hasta reserva
2. **Optimización RAG**: Mejorar respuestas con más contexto de negocios
3. **Privacy rules**: Implementar filtros para datos sensibles
4. **Booking integration**: Conectar con Roverd API para reservas automáticas
5. **Deploy VPS**: Configurar entorno de pre-producción

## Pendientes (RAG)
- [ ] Confirmar con cliente la info de: “¿Cuál es la profundidad máxima?” / “What is the max depth?”
- [ ] Añadir FAQ específico de profundidad máxima (ES/EN) una vez confirmado.
- [] Definir los precios de servicios
- [] Memoria en el chat?
- [] Almuerzo = Comida
- [] Info sobre la comida

## A tener en cuenta (ajustes menores opcionales)
- [ ] Q19 “alojamiento incluido”: el top-1 FAQ tiene topics raros (`meeting_point`/`schedule`/`equipment`). Indica que ese FAQ es multi-tema.
      Si la respuesta final sale bien, no tocar. Si no, revisar ese FAQ para hacerlo más atómico.