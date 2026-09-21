# Páginas de seguimiento (claude.ai artifacts)

Código fuente de las páginas publicadas en claude.ai. **Los datos no están aquí**: viven en la base de
datos de cada página (tareas, fotos, bitácora, etiquetas) y se editan desde la propia página o con
Claude (herramienta ArtifactData).

| Fichero | Página publicada | Para qué |
|---|---|---|
| `plan-coral.html` | https://claude.ai/artifact/XiGd3kguTNwwqTnH7mQwgi | Seguimiento del plan maestro: fases y tareas, bitácora, gráficos de latencia y calidad por ejecución (fotos de `scripts/langfuse_snapshot.py` + nota del golden-set) |
| `calibracion-juez.html` | https://claude.ai/artifact/4kDXumzu3QT7KpTQvuenHf | Etiquetado humano para calibrar el LLM-juez del golden-set (`scripts/calibrate_judge.py`). Cerrada tras la calibración del 2026-09-17 |

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
