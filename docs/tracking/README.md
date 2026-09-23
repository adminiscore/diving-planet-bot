# Páginas de seguimiento (claude.ai artifacts)

Código fuente de las páginas publicadas en claude.ai. **Los datos no están aquí**: viven en la base de
datos de cada página (tareas, fotos, bitácora, etiquetas) y se editan desde la propia página o con
Claude (herramienta ArtifactData).

| Fichero | Página publicada | Para qué |
|---|---|---|
| `plan-coral.html` | https://claude.ai/artifact/XiGd3kguTNwwqTnH7mQwgi | Seguimiento del plan maestro: fases y tareas, bitácora, gráficos de latencia y calidad por ejecución (fotos de `scripts/langfuse_snapshot.py` + nota del golden-set) |
| `calibracion-juez.html` | https://claude.ai/artifact/4kDXumzu3QT7KpTQvuenHf | Etiquetado humano para calibrar el LLM-juez del golden-set (`scripts/calibrate_judge.py`). Cerrada tras la calibración del 2026-09-17 |

## Cola de cambios cuando no se puede escribir en la página (2026-09-23)

`data/plan-coral-cambios-pendientes.json` es una **cola** de cambios para la página, no una copia de
su base de datos (eso es `data/plan-coral.json`, que se regenera exportando). Existe porque en la sesión de Claude Code de
Gonzalo la herramienta **`ArtifactData` no existe**: verificado por nombre exacto
(`select:ArtifactData` → *"No matching deferred tools found"*) y por descripción. **No es un problema
de cuenta** — esa misma sesión sí tiene `DesignSync` y `RemoteTrigger`, que autentican con el login
de claude.ai, y no hay ninguna `ANTHROPIC_API_KEY` en el entorno ni en el usuario. Tampoco se
intentó republicar el HTML en ningún momento.

**Cómo funciona**: quien no pueda escribir en la página deja ahí el cambio (colección, `doc_id` y
campos) y lo sube con su commit. Quien sí pueda lo aplica con `ArtifactData` —o a mano desde la
página— y en el MISMO commit deja `pendientes` vacío y rellena `aplicado_el`. Si la cola se queda
llena, el repo y la página divergen: esa es la señal de que alguien tiene que pasar por ahí.

**Para cambiar una página**: editar el HTML aquí y pedir a Claude que lo republique en la MISMA URL
(publicar con `url` = la de la tabla). Publicar sin `url` crea una página nueva y se pierden los datos.

Capacidades que declaran: `db` (datos compartidos) y `user` (quién edita). Colecciones de `plan-coral`:
`phases`, `tasks`, `snapshots`, `layers`, `log`. De `calibracion-juez`: `items`, `labels`.

## Dónde viven los datos y la copia de respaldo (2026-09-18)

- **Datos en vivo**: en la base de datos de la página (claude.ai). Se leen y editan desde la página
  por miembros de la organización **con sesión iniciada**. Por un enlace público, sin sesión o fuera
  de claude.ai la página no recibe esos datos.
- **Copia versionada**: `data/plan-coral.json` (todas las colecciones). Además va **incrustada** en
  `plan-coral.html`: la página la pinta al instante y la sustituye por los datos en vivo al conectar.
  Si no conecta, se queda con la copia en solo lectura y un aviso con la fecha de la copia.
- **Refrescar la copia** (tras cambios importantes, p. ej. al cerrar una tarea o una fase):
  1. Pedir a Claude "exporta la base de datos de Plan Coral" (deja un JSON por documento en una carpeta).
  2. `python docs/tracking/consolidate_export.py <carpeta>` → escribe `data/plan-coral.json`.
  3. `python docs/tracking/embed_backup.py`
  4. Republicar `plan-coral.html` en la MISMA URL y hacer commit de los dos ficheros.
