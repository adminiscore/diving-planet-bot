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
