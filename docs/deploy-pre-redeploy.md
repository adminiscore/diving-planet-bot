# Redeploy a PRE (staging VPS) — runbook

Actualiza el entorno **PRE** (`dp-pre-bot` en el VPS) con la rama `feature/pruebaGon`
(v0.19.13+): nuevo código + KB reindexada + `RAG_MIN_SCORE=0.50`.

> No hay migraciones de DB nuevas en estos cambios → **no** hace falta `alembic upgrade`.
> Los campos nuevos de estado (edades, cola de auto-armado) viven en Redis y se
> autocompletan con sus defaults; los estados viejos siguen siendo válidos.

Los comandos asumen que el repo está clonado en el VPS (ej. `~/diving-planet-bot`)
y que `docker-compose.vps.yml` + `.env.pre` ya existen ahí. Sustituye la ruta si difiere.

---

## 0) Entrar al VPS y al repo

```bash
ssh <usuario>@<ip-del-vps>
cd ~/diving-planet-bot          # ruta del repo en el VPS
```

## 1) Actualizar el código a feature/pruebaGon

```bash
git fetch origin
git checkout feature/pruebaGon      # si ya estás en ella, basta el pull de abajo
git pull origin feature/pruebaGon
git log --oneline -1                # debe mostrar 'v0.19.13' o posterior
```

## 2) Poner RAG_MIN_SCORE=0.50 en .env.pre

El `.env.pre` del VPS probablemente tiene `RAG_MIN_SCORE=0.72` (demasiado alto →
causa fallbacks falsos). Bájalo a 0.50:

```bash
# Si ya existe la línea, la reemplaza; si no, la añade.
grep -q '^RAG_MIN_SCORE=' .env.pre \
  && sed -i 's/^RAG_MIN_SCORE=.*/RAG_MIN_SCORE=0.50/' .env.pre \
  || echo 'RAG_MIN_SCORE=0.50' >> .env.pre
grep '^RAG_MIN_SCORE=' .env.pre     # verifica: RAG_MIN_SCORE=0.50
```

## 3) Reconstruir y reiniciar SOLO el bot de PRE

(No toca Postgres/Redis/Chatwoot ni sus datos.)

```bash
docker compose -f docker-compose.vps.yml up -d --build dp-pre-bot
docker compose -f docker-compose.vps.yml logs --tail=30 dp-pre-bot   # sin errores de arranque
```

## 4) Reindexar la KB en el Postgres de PRE

Se corre **dentro** del contenedor del bot (ya tiene `data/`, `scripts/`, la
`DATABASE_URL` de PRE y la `OPENAI_API_KEY` de `.env.pre`). `--yes` salta la
confirmación de borrado. Tarda ~1-3 min y hace llamadas de embeddings a OpenAI.

```bash
docker compose -f docker-compose.vps.yml exec dp-pre-bot python -m scripts.load_embeddings --yes
# Esperado al final: "Stored 779 documents in kb_documents" / "Done!"
```

## 5) Verificar

```bash
# Salud del bot
docker compose -f docker-compose.vps.yml exec dp-pre-bot \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"

# Nº de documentos indexados en la DB de PRE
docker compose -f docker-compose.vps.yml exec dp-pre-postgres \
  psql -U postgres -d diving_planet -c "SELECT count(*) FROM kb_documents;"
# Esperado: ~779
```

Luego prueba en el widget de Chatwoot de PRE (`pre.is-core.dev` / el dominio que uses):

- **Framing positivo**: "¿es buena época bucear en septiembre?" → responde en positivo.
- **Sin descuento colombiano**: "¿tienen descuento para colombianos?" → "no hay descuento
  especial, colombianos pagan en COP y extranjeros en USD".
- **RAG que antes fallaba** (valida el 0.50): "mi hijo tiene síndrome de Down, ¿puede
  bucear?" → info de DIVE TO HEAL (no el "no tengo información").
- **Precio colombiano**: "soy colombiano, ¿cuánto el minicurso?" → precio en COP.

## Rollback (si algo va mal)

```bash
git checkout <commit-anterior>      # p.ej. el que estaba desplegado antes
docker compose -f docker-compose.vps.yml up -d --build dp-pre-bot
# (opcional) volver RAG_MIN_SCORE a su valor previo en .env.pre y reindexar si hiciste cambios de KB
```

## Notas

- Para **PRO** es idéntico cambiando `dp-pre-bot`→`dp-pro-bot`, `dp-pre-postgres`→`dp-pro-postgres`
  y `.env.pre`→`.env.pro`. No lo hagas hasta validar en PRE.
- El pipeline `webhook → supervisor → gpt-4o + pgvector → respuesta` es el mismo que
  se validó en local, así que el comportamiento debería coincidir.
