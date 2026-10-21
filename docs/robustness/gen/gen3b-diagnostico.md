# gen-3b · Pasar directamente cuando toca (21-oct, Gonzalo con Claude)

**Causa de G9** (del análisis por causas, sin abrir el examen): "OFRECE pasar cuando debía pasar directo (servicio
privado, cambio urgente)", parte de la causa 4 (~8 fallos).

**Decisiones de Gadea (21-oct, Coral #770):**
1. Con una reserva YA hecha pasan DIRECTAMENTE a un asesor las tres: cambiar la fecha, cancelar y cambiar el número de
   personas. Se da la política y se pasa con el motivo y el resumen, sin preguntar ni ofrecer el menú.
2. El servicio privado pasa directo SIEMPRE, en cuanto lo pide. Si ya dio cuántos son o la fecha, van en el resumen.

## Diagnóstico

El RAG no puede pasar el caso a una persona: desde G3-03 (`rag_ofrece_el_pase`) solo lo OFRECE como pregunta. Por eso
"pasar directo" tiene que decidirlo el sistema antes del RAG, y había dos huecos:

| Situación | Antes | Dónde |
|---|---|---|
| Cambiar la fecha, cancelar o cambiar el número de personas de una reserva hecha | La política y «¿Quieres que te conecte con un asesor…, o prefieres volver al menú principal?», con 2 botones. No marcaba el pase, y el menú principal ya no existe desde la Fase 4 | `rutas/changes.py:_booking_change_response` |
| Servicio privado sin las palabras exactas («la lancha solo para nosotros», «un instructor exclusivo») | Solo pasaba con «servicio privado», «grupo cerrado» o «evento corporativo» (`_PRIVATE_GROUP_EVENT_RE`). Lo demás iba al RAG, que ofrece el pase | `orchestration/router.py`, `info_agent.py` |

Además, el resumen del pase (`build_lead_summary`, con los últimos mensajes del cliente) se construía ANTES de añadir el
mensaje del turno al historial: el asesor no leía el mensaje que provocó el pase («somos 6, el sábado»).

## Cambio (dos flags, APAGADOS)

- `CAMBIO_DE_RESERVA_PASA`: en las tres, la política y «Te paso ahora con un asesor de Diving Planet para gestionar…»,
  con el pase marcado (motivo + resumen), sin botones ni pregunta.
- `PRIVADO_PASA_DIRECTO`: una pregunta nueva de Jev, `pide_servicio_privado`, en la misma llamada. Lleva al nodo `info`,
  que da la respuesta del grupo privado, ya con el pase marcado por `grupo_privado_pase`. La lista de siempre sigue
  valiendo. La frontera está escrita en la pregunta: un grupo grande en la salida normal, un descuento de grupo o
  «privado» en el sentido de privacidad NO cuentan. El criterio va en una sola función,
  `rutas/info.pide_servicio_privado`, que usan el router y el nodo.
- Con los dos flags, el mensaje entra en el historial antes del resumen del pase.

## Medida

Banco propio `docs/robustness/gen/dialogos-gen3b.json`: 13 diálogos. Nueve deben pasar: 5 de servicio privado y 4 de
cambios de una reserva hecha. Cuatro no deben pasar: la familia grande en la salida normal, la privacidad de los
datos, el descuento de grupo y la pregunta por la política de cancelación.

Se corrió con `reproducir_juez_pre --banco … --codigo-local` en PRE, 2 repeticiones, código de `pre_gadea` 1f66c3e. El
script guarda ya `pending_escalation_reason` en cada turno, y se mira si el turno pasa el caso cuando debe y no cuando no
debe.

| Variante | Turnos con el pase como toca | Mediana |
|---|---|---|
| Base (flags apagados) | 8/26: los 9 que deben pasar NO pasan 2/2 (el RAG ofrece «¿quieres que te pase…?» o pregunta «¿te conecto… o prefieres volver al menú principal?»); los 4 de la frontera, bien | 4,26 s |
| `--flag cambio_de_reserva_pasa --flag privado_pasa_directo` | **26/26**: los 9 pasan directamente con su motivo y los 4 de la frontera siguen sin pasar | 1,58 s |

Ficheros: `2026-10-21-gen3b-base.jsonl` y `2026-10-21-gen3b-con.jsonl`, en esta carpeta.

**Siguiente:** la ronda A/B sin desplegar (`ronda_local_pre`) frente a una base del mismo día, para promocionarlo.
