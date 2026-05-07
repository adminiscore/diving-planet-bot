# TODO

## Pendiente (alta prioridad)
- [ ] Instalar y dejar disponible **Python 3.11+** en el PATH (que funcione `python --version`).
- [ ] Asegurar acceso a **PostgreSQL + pgvector** (local o remoto) y validar `DATABASE_URL` en `.env`.
- [ ] Configurar `OPENAI_API_KEY` en `.env`.
- [ ] Instalar dependencias del proyecto: `pip install -e ".[dev]"`.
- [ ] Ejecutar carga de embeddings (esto borra y re-crea `kb_documents`): `python -m scripts.load_embeddings`.

## Pendiente (media prioridad)
- [ ] Confirmar el entorno donde corre el bot (Windows directo / WSL / servidor) para estandarizar el flujo de deploy.
- [ ] Validar que `data/knowledge_base/conversations.json` está siendo indexado correctamente en `kb_documents`.
- [ ] Ajustar/añadir reglas de privacidad para que el bot no pida ni repita datos sensibles (IDs, cuentas, comprobantes) y siempre derive a humano.

## Pendiente (baja prioridad / mejoras)
- [ ] Expandir `conversations.json` con más ejemplos reales (incluyendo casos difíciles de clima, recogidas específicas, cambios de muelle, etc.).
- [ ] Añadir un comando/shortcut (script) para re-indexar embeddings de forma segura (por ejemplo confirmación antes del `DELETE`).
- [ ] Revisar el `SYSTEM_PROMPT` del `rag_agent` para reflejar el tono definido en `brand_tone.json` y las reglas de escalado.
