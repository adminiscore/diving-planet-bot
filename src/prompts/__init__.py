"""Los prompts del bot, como artefacto de primera clase (Fase 3.2 del refactor).

`docs/multi-agent-refactor-plan.md` §4: *"Los prompts, como en IBM, son el
corazón del control. Cada nodo tiene **su** prompt corto, enfocado a UN caso de
uso, en `src/prompts/` — legible, revisable, versionado."*

Un módulo por nodo dueño (el mapa completo red LLM → nodo está en
`docs/agent-arch-design.md` §7):

| Módulo | Nodo | Redes LLM cuyo prompt vive aquí |
|---|---|---|
| `router.py` | router | `detect_routing_signals` (9 señales, 1 llamada/turno) |
| `booking.py` | booking (subgrafo) | `fill_gaps` · `detect_special_signals` · `resolve_slot_answer` · `compose_acknowledgement` · `detect_language_llm` |
| `info.py` | info | `condense_query` · respuesta RAG (persona + seguridad + reglas) · `is_grounded` |
| `memory.py` | transversal | `extract_notes` · `maybe_update_summary` |

**Qué cuenta como prompt aquí:** el texto del mensaje de sistema **y** el
*tool schema* de las redes que usan function-calling. Las descripciones de cada
campo del schema son instrucción real para el modelo (varias se afinaron
midiendo en vivo — p. ej. el caso negativo del plural vago en `group_size`), así
que se leen y se revisan junto al prompt, no aparte.

**Reglas de este paquete:**

1. **Solo texto.** Estos módulos no importan nada de `src/` (son una hoja del
   grafo de dependencias) y no llaman al LLM: quien hace la llamada es la red en
   `src/agents/`. Así un prompt se puede leer/diffear sin arrastrar el runtime.
2. **Los HECHOS no se piden al LLM** (principio #4 del plan): ningún prompt de
   aquí produce precios, links, cupos ni confirmaciones — eso lo pone la capa
   determinista (`src/flows/`). Los prompts que lo mencionan es para
   PROHIBIRLO.
3. **Cambiar un prompt cambia conducta.** `scripts/snapshot_prompts.py` renderiza
   los 11 prompts en sus 61 variantes (idioma × argumentos, más el prompt RAG ya
   ensamblado) con su SHA-256: úsalo para probar que un refactor NO los cambia
   (`-o antes.json` → cambio → `--compare antes.json`), y para leer la superficie
   de prompt entera de un golpe. `tests/test_prompts_surface.py` exige que todo
   prompt nuevo entre también en el snapshot.
"""
