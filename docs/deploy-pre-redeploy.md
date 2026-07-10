# Redeploy a PRE (staging VPS) — runbook

> **Desde 2026-07-06 esto es automático.** Cada push a `feature/pre_gadea`,
> `feature/pre_alvaro` **o `feature/pre_pruebaGon`** que pase el job `Lint + Tests`
> de CI dispara el job `deploy-pre` en `.github/workflows/ci.yml`, que hace
> exactamente los pasos de este documento por SSH (usa los secrets `PRE_VPS_HOST` /
> `PRE_VPS_SSH_KEY` del repo), desplegando siempre la rama que hizo el push
> (`github.ref_name`). El VPS ahora es un `git clone` real en
> `/opt/diving-planet-bot` (antes se desplegaba con `tar | ssh`), así que el
> `git fetch && git reset --hard` del job funciona igual que en cualquier otro
> deploy basado en git.
>
> **`feature/pre_alvaro`, `feature/pre_gadea` y `feature/pre_pruebaGon` son ramas
> "espejo" de disparo**: cada quien trabaja normalmente en su rama de integración
> (`feature/dev_alvaro`, `feature/dev_gadea`, `feature/pruebaGon`) y solo cuando
> quiere desplegar de verdad a PRE, actualiza su rama `pre_*`
> (p.ej. `git push origin pruebaGon:pre_pruebaGon --force-with-lease`, o
> mergea/rebasea) — así un commit rutinario en la rama de integración NO dispara un
> rebuild + reindex de KB en PRE cada vez.
>
> **PRE es UN solo entorno compartido** (un único `dp-pre-bot`/`dp-pre-postgres`).
> No hay una copia por rama/persona — si Gadea y Álvaro suben código casi a la vez,
> el push que llega después sobreescribe el código desplegado por el anterior (no
> se pierde nada en git, solo cambia qué versión está sirviendo PRE en ese momento).
> Si vas a probar algo específico en PRE, confirma con el resto del equipo que nadie
> más va a desplegar encima mientras pruebas.
>
> Usa el procedimiento manual de abajo (o `scripts/redeploy_pre.sh BRANCH=<rama>`)
> solo como fallback si la Action falla o si necesitas desplegar una rama distinta
> a las dos anteriores.
>
> **Nota (2026-07-07)**: el repo del VPS se clonó originalmente con
> `git clone -b feature/pre_gadea ...`, lo que por defecto crea un clon
> "single-branch" — el `.git` solo rastrea esa rama y `git fetch` nunca ve ramas
> nuevas (ej. `feature/pre_alvaro`) por más veces que se corra. El job y
> `scripts/redeploy_pre.sh` ahora corren `git remote set-branches origin '*'`
> antes de cada fetch para arreglarlo (idempotente, seguro repetir siempre).

Actualiza el entorno **PRE** (`dp-pre-bot` en el VPS) con la rama `feature/pre_gadea`
(pruebaGon mergeada, v0.19.13+): nuevo código + KB reindexada + `RAG_MIN_SCORE=0.50`.

> No hay migraciones de DB nuevas en estos cambios → **no** hace falta `alembic upgrade`.
> Los campos nuevos de estado (edades, cola de auto-armado) viven en Redis y se
> autocompletan con sus defaults; los estados viejos siguen siendo válidos.

Los comandos asumen que el repo está clonado en el VPS (ej. `~/diving-planet-bot`)
y que `docker-compose.vps.yml` + `.env.pre` ya existen ahí. Sustituye la ruta si difiere.

---

## 0) Entrar al VPS y al repo

```bash
ssh root@<ip-del-vps>
cd /opt/diving-planet-bot          # ruta del repo en el VPS (git clone real)
```

## 1) Actualizar el código a feature/pre_gadea

```bash
git fetch origin
git checkout feature/pre_gadea      # si ya estás en ella, basta el pull de abajo
git pull origin feature/pre_gadea
git log --oneline -1                # debe mostrar 'v0.19.13' o posterior
```

## 2) Poner RAG_MIN_SCORE=0.40 en .env.pre

**Actualizado 2026-07-09.** Antes este runbook decía `0.50`. Se midió y **0.50 era
demasiado alto**: con `text-embedding-3-small`, una pregunta corta contra un FAQ
largo produce cosenos de ~0.45-0.55 aunque la coincidencia sea perfecta, así que
0.50 cae justo en medio de la distribución de los buenos aciertos y descarta
respuestas correctas. Medido sobre 27 preguntas habituales: **7 (26%) perdían su
contexto de KB a 0.50** y lo recuperan a 0.40 — entre ellas "¿qué animales se ven?",
"¿qué debo llevar?", "where do we meet?", "how long is the course?".

`0.40` es además el default del código (`src/config.py`) y el valor con el que se
validó toda la batería de 176 casos — hasta ahora PRE corría una configuración más
estricta que nada de lo testeado.

```bash
# Si ya existe la línea, la reemplaza; si no, la añade.
grep -q '^RAG_MIN_SCORE=' .env.pre \
  && sed -i 's/^RAG_MIN_SCORE=.*/RAG_MIN_SCORE=0.40/' .env.pre \
  || echo 'RAG_MIN_SCORE=0.40' >> .env.pre
grep '^RAG_MIN_SCORE=' .env.pre     # verifica: RAG_MIN_SCORE=0.40
```

> **Riesgo de bajarlo**: entran documentos algo más marginales al contexto. Cubierto
> por los guards deterministas (precios/URLs/capacidad) + el juez de grounding, que
> desde v0.20.8 corre **también** en el camino del agente cuando no hay soporte de KB.
> Verificado: precios idénticos a 0.40 y 0.50; ninguna respuesta se degradó.

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
