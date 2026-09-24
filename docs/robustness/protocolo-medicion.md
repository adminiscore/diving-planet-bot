# Protocolo de medición (decisiones del 24-sep-2026)

Dos decisiones de Gadea que aplican a **todo el equipo** desde el 24-sep-2026. Leer antes de
lanzar una prueba A/B o sacar una foto de latencia.

---

## 1. Latencia y llamadas: con nuestros logs, no con Langfuse (hasta que vuelva)

**Qué pasó:** se superó el plan gratuito de Langfuse (más de 55.000 unidades de 50.000; se
reinicia el **16-oct-2026**). Se decidió **no pagar** el plan Core (29 $/mes) por ahora.

**Qué hacemos:** cada turno del bot escribe en el log de PRE una línea
`[TURN_METRICS] {json}` (ver `src/observability.py`) con:

- el tiempo del turno, las llamadas al LLM (cuántas, cuánto tardan y con qué modelo);
- el tiempo de cada paso del grafo (router, extracción, cierre…);
- qué router decidió (`jev`, `llm_uncertain` o `llm_fallback`, ver u3-1) y cuánto tardó;
- el resumen del turno (tipo, ruta, escalado, link…). **Sin texto del cliente ni de la respuesta.**

La foto se saca con:

```
python -m scripts.turn_metrics --label "..." --from-run docs/robustness/synthetic-runs/<ronda>.jsonl --out docs/robustness/snapshots/<ronda>.json
```

Lee esas líneas por SSH (`~/.ssh/dp_pre_vps`) y devuelve **la misma foto que
`scripts/langfuse_snapshot.py`** (`all`, `by_type`, `nodes`, `business`, `client_latency`), así
que se puede comparar con las fotos antiguas y añadir a la página igual. No da tokens ni coste.

- **Gratis y sin límite.** Langfuse sigue encendido: si vuelve a aceptar datos, las dos cosas
  conviven.
- **Ojo:** `docker logs` solo guarda los del contenedor actual. **Saca la foto antes del
  siguiente deploy**, porque el deploy recrea el contenedor y se pierden los logs anteriores.
- Cuando vuelva Langfuse (16-oct), se decide si se vuelve a él, si se paga o si se sigue así.

---

## 2. Pruebas A/B más baratas (sin perder robustez)

Un A/B completo (2 rondas del core por lado + juez en las 4) cuesta ~2,3 $ y ~2,5 h de máquina.
Casi todo el gasto es el **juez** (~0,47 $ por ronda del core). Desde ahora se mide **por
escalones**, y solo se sube al siguiente si hace falta:

| Escalón | Qué | Coste aprox. |
|---|---|---|
| **0. En local** | Tests + evaluar la DECISIÓN que cambia sobre los 257 mensajes de cliente del golden (sin el examen oculto), como se hizo con Jev en l2-4. Si no pasa aquí, no se va a PRE. | céntimos |
| **1. En PRE, 1 + 1** | Una ronda B (con el cambio) contra una ronda A del **mismo día**. Se compara el **texto** del bot turno a turno y **el juez solo evalúa los diálogos cuyo texto ha cambiado**. | ~0,3-0,5 $ |
| **2. En PRE, 2 + 2** | Solo si en el escalón 1 algo empeora o hay dudas, o si es un cambio grande (p. ej. la extracción de U3). También juzgando solo lo que cambia. | ~1 $ |
| **Cierre de fase** | Ronda COMPLETA del golden (116 diálogos, con el examen oculto) + juez completo. **No se recorta.** | ~2 $ |

Reglas que se mantienen:

- **La latencia solo se compara en la misma franja horaria.** El 24-sep, las mismas rondas una
  hora más tarde fueron ~0,8 s más lentas en turnos idénticos.
- **Una ronda A se puede reutilizar** para la CALIDAD de otros cambios del mismo día si el código
  de A no ha cambiado (se hizo en l1-4). Para la latencia, no.
- **Un cambio que mejora el total y empeora un caso no vale.** El filtro es "falla en las dos B y
  pasa en las dos A" (o en la B y la A del escalón 1), y además se **lee el texto** del bot: el
  24-sep dos "regresiones" eran el mismo texto que el juez aprobó en A y suspendió en B.
- **Cada juez en su propio proceso** (si se para el script que lo lanzó, el juez muere).
- **No hacer push a `pre_*` mientras corre una ronda en PRE** (el deploy reinicia el bot).

---

Detalle y cifras: `docs/HISTORY.md` (0.29.15 en adelante) y la bitácora de la página Plan Coral.
