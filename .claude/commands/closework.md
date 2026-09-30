---
description: Cerrar la sesión y dejar el relevo listo: validar, integrar, HISTORY, handoff, Plan Coral, mapa, commit, push y deploy
---
# Close work — cierre de sesión y relevo

Objetivo: que quien venga detrás (Gadea, Álvaro, Gonzalo o una sesión nueva de Claude) pueda retomar leyendo UN
bloque del handoff, con Plan Coral y el mapa al día, y con PRE sirviendo lo que dice el repo. Hazlo en orden; no
te saltes pasos. Escribe todo en español.

## 1. Contexto y estado

- Lee `docs/project-history/session-handoff.md` (el bloque "▶️ RETOMAR AQUÍ" de arriba), la cabeza de
  `docs/HISTORY.md` y, en `docs/plan-maestro-final.md`, la PARTE 8 (bloques "Estado al …").
- `git status --short --branch` y `git log --oneline -10`.

## 2. Datos sensibles

```powershell
git diff --stat -- . ':!wasap'
git diff --cached --stat -- . ':!wasap'
git status --short --ignored -- wasap data/knowledge_base
```

Nunca subas `wasap/`, `_chat.txt`, exportaciones de medios, `.bak`, `pre_dedup`, links de pago, IDs, teléfonos,
correos ni nada que identifique a un cliente sin anonimizar. Nunca pegues claves en el chat ni en el repo (van en
`.env.dev`). La contraseña de la base de datos no se repite nunca.

## 3. Integrar lo de los demás ANTES de subir

Todas las ramas `pre_*` despliegan el MISMO PRE: lo que no esté integrado se pisa.

```powershell
git fetch --all
git log --oneline HEAD..origin/<rama>        # para cada rama pre_* y la del compañero que esté trabajando
```

Si otra rama tiene commits que la tuya no tiene: avance rápido si se puede (`git merge --ff-only`); si divergen,
PARA y pregunta cómo reconciliar. Tu propia rama frente a su upstream: `git log --oneline --left-right
--cherry-pick HEAD...@{upstream}`.

## 4. Validación (si cambió código)

La suite SIEMPRE con `ENV_FILE=.env.ci` (sin él usa la clave real: ~20 min facturables y fallos aleatorios):

```powershell
$env:ENV_FILE=".env.ci"; python -m pytest -q -p no:cacheprovider; $env:ENV_FILE=$null
python -m ruff check src
```

- Si cambió un prompt: `python scripts/snapshot_prompts.py --compare <antes>.json` (prueba que no cambió sin querer).
- Si cambiaste un interruptor en `docker-compose.vps.yml`, cámbialo también en `src/config.py` (`tests/test_flags_pinned.py`).
- Si añadiste un interruptor: su frase en `docs/arquitectura/componentes.json` (`tests/test_arquitectura.py`).

## 5. Rondas y mediciones: guardar ANTES de subir

- Un push a `pre_*` **recrea el contenedor**: borra sus logs y mata cualquier medición en curso (una ronda, un
  `rag_piezas --codigo-local`, un juez). Antes de subir, mira que nadie esté midiendo:
  `ssh ... "ps -eo args | grep 'docker exec -i' | grep -v grep"` (vacío = libre) y, si trabajas con otros, avísales.
- Si hiciste una ronda: foto (`python -m scripts.turn_metrics --from-run <ronda>.jsonl --out docs/robustness/snapshots/<ronda>.json`)
  y log de PRE (`docker logs dp-pre-bot > docs/robustness/logs-pre-<ronda>.txt`) ANTES del push, y súbelos con el commit.

## 6. HISTORY

Si hubo un hito: sección nueva arriba de `docs/HISTORY.md` (siguiente versión, fecha `YYYY-MM-DD`, viñetas cortas:
qué, por qué, cómo se midió, resultado, marcha atrás si hay flag).

## 7. Handoff: UN solo punto de entrada

En `docs/project-history/session-handoff.md`:

- Escribe (o reescribe) el bloque **`### ▶️ RETOMAR AQUÍ — <fecha> (<quién>): <resumen en una línea>`** justo debajo
  del aviso "📏 LEER ANTES DE MEDIR", con este esquema:
  - **Estado:** qué rama sirve PRE y en qué commit; qué flags nuevos están encendidos/apagados; suite y ruff; si
    Plan Coral y el mapa están al día; qué deben integrar los demás.
  - **Hecho hoy (HISTORY x.y.z):** tabla o viñetas con qué, estado (promocionado / apagado con medida /
    descartado) y dónde está.
  - **Siguiente, en orden:** los pasos concretos, con su criterio de "hecho".
  - **Cómo medir** lo siguiente (comandos exactos) y **avisos** aprendidos hoy.
- El "RETOMAR AQUÍ" anterior pasa a histórico: cambia su título a `### ✅ <fecha> (<quién>) — <resumen>`. Solo
  puede haber UN "RETOMAR AQUÍ" (compruébalo con `grep -c "RETOMAR AQUÍ"`).
- Si el orden del plan cambió, añade o actualiza el bloque "Estado al <fecha>" de la PARTE 8 del plan maestro.

## 8. Plan Coral (https://claude.ai/artifact/XiGd3kguTNwwqTnH7mQwgi)

- **Si tienes la herramienta `ArtifactData`:** primero aplica la cola `docs/tracking/data/plan-coral-cambios-pendientes.json`
  si tiene entradas (lee antes cada tarea: NO apliques un estado que la página ya tenga superado —p. ej. devolver a
  "pendiente" algo que ya está "hecha"—; las notas antiguas van DETRÁS de la nota actual, marcadas con su fecha y
  autor); deja `pendientes: []` con `aplicado_el` y `aplicado_por`. Después actualiza las tareas que tocaste
  (estado `pendiente` / `en_curso` / `hecha` / `bloqueada`, nota con qué se hizo, cómo se midió y qué queda) y añade
  una entrada de bitácora (`log`, con `at`, `byLabel` y `text`). Escribe siempre con `if_version` (la versión leída).
- **Si NO la tienes** (sesiones de otra organización): escribe los cambios en la cola, con `coleccion`, `operacion`,
  `doc_id` y `campos` (o `anteponer_a_la_nota`), y súbela con el commit.
- No asignes responsables: `owner` = "—" salvo que el equipo lo diga.
- Tras cambios grandes (cerrar una fase), refresca la copia del repo: exporta las colecciones con ArtifactData
  (`list` con `out_dir`), `python docs/tracking/consolidate_export.py <carpeta>`, `python docs/tracking/embed_backup.py`
  y republica `docs/tracking/plan-coral.html` en la MISMA URL (comprueba antes que el código de la página publicada es
  el del repo).

## 9. Mapa de Coral (https://claude.ai/artifact/SnK5Dku1vAinbJ94b8aNGd)

Si cambió el grafo, `src/agents/`, `src/config.py`, `docker-compose.vps.yml` o hay una ronda medida nueva:

```powershell
$env:ENV_FILE=".env.ci"; python -m scripts.arquitectura
```

Falla si una pieza del grafo no tiene descripción o se cita un fichero, función, interruptor o modelo que no existe:
arréglalo en `docs/arquitectura/componentes.json`. Luego publica `docs/arquitectura/mapa-coral.html` con el Artifact
tool (`url` = la del mapa; `files` = `arquitectura.json`, `logos.json`, `historial/indice.json` y cada
`historial/*.json`) y haz commit de lo regenerado. Comprueba que el mapa conoce todos los interruptores de
`settings` y enseña la última ronda.

## 10. Commit y push

Añade solo lo que toca (`git add <ficheros>`), commit con mensaje en español que diga qué y cómo se midió, y:

```powershell
git push origin HEAD
```

## 11. Comprobar el deploy (ramas `pre_*`)

Un CI en rojo se salta el deploy SIN avisar. No des nada por desplegado hasta que esto salga bien:

```powershell
python -m scripts.check_deploy
```

Si la API de GitHub da 403 (límite de peticiones), repite con `--no-wait` pasados unos segundos. Si CI falló, dice
qué paso falló.

## 12. Informe final (al usuario, en español)

- Commit y rama; si PRE sirve ese commit (resultado de `check_deploy`).
- Validación (suite y ruff).
- Qué quedó en el handoff, en Plan Coral y en el mapa (o por qué no hizo falta tocarlos).
- Lo pendiente y el coste aproximado de la sesión (OpenAI) si hubo rondas o mediciones.
