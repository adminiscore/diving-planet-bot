---
description: Cargar el contexto al empezar una sesión (handoff, estado de PRE, ramas de los compañeros, Plan Coral)
---
# Start context — empezar la sesión

Úsalo al empezar, antes de tocar nada. Escribe en español.

1. Lee el bloque **"▶️ RETOMAR AQUÍ"** de `docs/project-history/session-handoff.md` (y el aviso "📏 LEER ANTES DE
   MEDIR"), la cabeza de `docs/HISTORY.md` y el último bloque "Estado al …" de la PARTE 8 de
   `docs/plan-maestro-final.md`.
2. Git: `git status --short --branch`, `git log --oneline -8`, `git fetch --all` y, para cada rama `pre_*`,
   `git log --oneline HEAD..origin/<rama>` — di qué han subido los demás desde el último relevo (con su HISTORY).
3. PRE: qué rama y commit sirve y si está sano:
   `python -m scripts.check_deploy --branch <rama que diga el handoff> --no-wait`.
4. Plan Coral: si `docs/tracking/data/plan-coral-cambios-pendientes.json` tiene `pendientes`, avisa (hay que
   aplicarlos con ArtifactData, ver `/closework` paso 8).
5. Resume al usuario: rama y sincronía, qué sirve PRE, qué hicieron los demás, el "Siguiente" del handoff y el
   recordatorio de datos sensibles (nada de claves ni datos de clientes en el chat o el repo).
6. No edites código ni docs hasta que el usuario lo pida.
