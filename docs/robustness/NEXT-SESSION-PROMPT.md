# Prompt para la siguiente sesión

Copia y pega lo de abajo. El orden importa: primero comprobar que PRE sirve lo
que creemos que sirve, y solo después tocar nada.

---

## PROMPT

Retomamos el trabajo de robustez del bot. Lee primero
`docs/robustness/progress-log.md` (la entrada del 2026-09-14 y, si hace falta
contexto, las del 2026-09-12) y la entrada `0.24.1` de `docs/HISTORY.md`.

**Antes de nada**, tres comprobaciones baratas:

```bash
# 1) cuota (casi todo lo de abajo la necesita; un eval-set son ~215 peticiones,
#    una pasada de la bateria ~300)
ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker exec dp-pre-bot python3 -c \"
import httpx
from src.config import settings
r = httpx.post('https://api.openai.com/v1/chat/completions',
    headers={'Authorization': f'Bearer {settings.openai_api_key}'},
    json={'model':'gpt-4o-mini','messages':[{'role':'user','content':'hi'}],'max_tokens':1}, timeout=30)
print(r.status_code, r.headers.get('x-ratelimit-remaining-requests'))\""

# 2) que PRE corre lo del 2026-09-14 (el commit de 0.24.1 o posterior)
ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "cd /opt/diving-planet-bot && git log --oneline -1"

# 3) flags reales del contenedor (booleanos, sin leer el .env con secretos)
ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker exec dp-pre-bot python3 -c \"
from src.config import Settings, settings
for k in sorted(Settings.model_fields):
    if 'veto' in k: print(k, getattr(settings, k))\""
```

### Estado: qué se hizo el 2026-09-14

1. **El total que cuenta es el que se GUARDA.** La invariante del reparto y el
   trigger de su veto comparaban con el total del turno, que es el que el regex
   lee mal; se guardaban repartos parciales **en PRE con los dos vetos
   encendidos** (`b10`: "4 con brevet, 2 minicurso y 1 snorkel" con 7 sabidos →
   reparto de 3). `_group_size_that_will_persist` es ahora la única fuente y la
   usan los tres sitios. Batería, config PRE: parciales 1 → 0, correctos 6 → 7.
2. **Cutover medidos al código**: `activity` y `group_size` en `True` por
   defecto, como `group_allocation`. Shadow sigue en el entorno.
3. **`is_colombian` con trigger propio** (`nationality_is_ambiguous`, polaridad
   contradictoria). Eval-set: `is_colombian` 7/9 → 9/9, overall 202 → 204/207,
   sin casos a peor — pero ningún caso del eval-set es ambiguo (ver cola, punto 2). **Flag apagado.**
4. **Batería de grupo reescrita**: estado final, los dos vetos, familia "total".

La tarea 1 del prompt anterior (total mal leído) resultó estar ya resuelta en PRE
por el veto de `group_size`; su hipótesis ("el trigger no dispara") era falsa.

### Lo PRIMERO: verificar desde la imagen lo que se desplegó

El 2026-09-14 todo se midió **inyectando el código local en memoria** dentro del
contenedor (ver "Cómo se midió sin desplegar" en el progress-log). Tras el
despliegue hay que repetirlo desde la imagen:

```bash
ssh ... "docker exec -i dp-pre-bot python3 -m scripts.battery_group_allocation_gate 2"
```

El eval-set **no está dentro de la imagen** (`docs/` no se copia), así que antes:

```bash
scp -i ~/.ssh/dp_pre_vps docs/robustness/eval-set.json root@89.167.4.161:/tmp/eval-set.json
ssh ... "docker exec dp-pre-bot mkdir -p /app/docs/robustness && \
         docker cp /tmp/eval-set.json dp-pre-bot:/app/docs/robustness/eval-set.json && \
         docker exec -i dp-pre-bot python3 -m scripts.run_extraction_eval"
```

Qué esperar (config de PRE, variante `ambos` de la batería): beneficio 7/10, total
12/13, **TOTAL_MAL 0, PARCIAL 0, ALUCINA 0**. Eval-set: ver la tabla de abajo.

Lo que hay que mirar en los logs de PRE (lo único que no se puede simular):

- `[EXTRACT][GROUP_ALLOCATION_INCOMPLETO]` — repartos descartados de verdad. Ahora
  también descarta los que solo cuadraban con un total de turno mal leído: si
  salen muchos, mirar los mensajes.
- `[EXTRACT][GROUP_ALLOCATION_AMPLIA_TOTAL]` — ahora sube también el total del
  estado. Si aparece a menudo, revisar que no esté subiendo totales con repartos
  inventados.
- `[EXTRACT][GROUP_ALLOCATION_VETO]` / `[EXTRACT][GROUP_SIZE_VETO]` — en cutover:
  `applied=True` cambió una respuesta real.
- `[LLM_EXTRACTOR][DEGRADED][COMBINED]` — la petición fusionada falla. **Ojo**: ante
  ese fallo el turno se queda sin huecos rellenados (ver cola, punto 5).

### Cola de trabajo, por orden de valor

**1. Repartos que el LLM no reconoce como contables.** `b03` "4 con titulo",
`b04` "3 brevetados", `b05` "2 open water", `t05` "7 in total: 4 certified, 2
minicourse and 1 snorkel" siguen en VACIO. Es seguro (el bot pregunta), pero es
lo que más beneficio queda por sacar. El camino **no** es meter las reglas de
verificación en `fill_gaps`: ya está medido que cuesta 5 casos del eval-set
(202→197). Hace falta una versión **neutra** de las reglas (qué significa el
campo y qué cuenta como contable, sin la carga de abstención) y medir con el
eval-set **y** la batería, A/B por caso.

**2. `is_colombian`: decidir el flag, con medida.** El trigger propio ya existe y el eval-set
sube a 9/9, pero **ninguno de sus 9 casos de nacionalidad es ambiguo**: el veto
no se ejercitó en ninguno, así que no hay medida de si acierta cuando dispara.
Primero añadir al eval-set casos de polaridad contradictoria (partir de los de
`tests/test_nationality_veto_trigger.py`: "dos somos colombianos pero uno es
extranjero", "mi pareja es colombiana, yo no"…), medir en shadow y solo
entonces decidir el cutover. Ojo: con grupos mixtos el campo es por persona y
`is_colombian` es un booleano único — puede que la respuesta correcta no sea
ni True ni False sino `_detect_mixed_nationality_request`.

**3. `is_certified` y `location` siguen con el trigger genérico** (hoy en shadow
en PRE). Mismo riesgo que tenía `is_colombian`: antes de pensar en su cutover,
darles `should_verify` propio (ambigüedad autodiagnosticada, reutilizando los
patrones del detector) y medir.

**4. Observabilidad: revisar si merece la pena Langfuse frente a LangSmith.**
LangSmith (plan gratuito, 5.000 trazas/mes, reset el día 1 en UTC) se agotó el
2026-09-10 por el bucle de re-respuesta: 790 trazas del 1 al 9-sep y 3.850 del 9
al 11. Borrar trazas no devuelve cuota. Decisión del owner (2026-09-14): **no
pagar**; se deja LangSmith como está hasta decidir. A comparar: Langfuse Cloud
Hobby (gratis, 50k unidades/mes, 30 días de datos; una unidad es cada traza,
observación o score, así que un turno ≈ 10 unidades) o Langfuse autoalojado
(gratis, sin límites, pero en un VPS con historial de problemas de disco).
Coste de migrar: el envoltorio de OpenAI está centralizado en
`src/llm_client.py::trace_openai`, más el callback del grafo. Contrapartida: el
contenido de las conversaciones pasa a otro proveedor. No afecta a las
respuestas del bot.

**5. El fallback de la petición fusionada no existe.** `_understand` comprueba
`_combined_patch is None` para volver a `fill_gaps`, pero `extract_and_verify`
devuelve `({}, {})` ante cualquier error. Decidir si se quiere ese fallback (una
petición más contra una API que acaba de fallar) o si se borra el comentario que
lo promete.

**6. `ambig-curso-padi-generico-no-se-bucear`** espera `'padi_course'`, que **no
existe en el enum** de `EXTRACTION_TOOL`: inalcanzable por construcción. Decisión
de producto (¿se añade al enum o se cambia el `expected`?). No forzarlo.

### Cómo trabajar aquí (lo pidió el owner explícitamente)

- **Nada de parches regex.** Arreglan el caso de hoy y pinchan con la jerga del
  siguiente que escriba. Si la solución natural parece "añadir un patrón", busca
  la vía LLM o generar lo que haga falta desde el schema.
- **Centralizar, no individualizar.** Si el error puede salir en otras zonas, se
  arregla el mecanismo común. (El 2026-09-14: una regla — qué total se guarda —
  usada por tres sitios en vez de tres comprobaciones parecidas.)
- **Optimizar peticiones y latencia.** El recurso escaso es
  **peticiones/día (RPD)**, no tokens.
- **Medir por caso, no solo el agregado.** El A/B por caso es lo que distingue
  una mejora de dos movimientos que se compensan.
- **Juzgar el estado, no el intent.** El fallo del 2026-09-14 solo se veía en el
  estado final del turno.
- **Los resultados negativos se documentan, no se fuerzan.**

### Referencia para comparar (eval-set, 107 casos)

| campo | 2026-09-12 | 2026-09-14 (local, inyectado) |
|---|---|---|
| activity | 62/63 (98%) | 62/63 (98%) |
| group_size | 44/44 (100%) | 44/44 (100%) |
| is_certified | 31/32 (97%) | 31/32 (97%) |
| location | 23/23 (100%) | 23/23 (100%) |
| group_allocation | 10/11 (91%) | 10/11 (91%) |
| is_colombian | 7/9 (78%) | **9/9 (100%)** |
| **overall (arnés serial)** | **202/207 (97.6%)** | **204/207 (98.6%)** |

El arnés declara al final si la tanda es comparable. **Si dice "TANDA NO
COMPARABLE", los números no valen.** Lee el resumen de
`docs/robustness/eval-last-run.json`, no del stdout filtrado: un `grep -v` del
ruido de LangSmith ya borró una fila una vez (y ahora LangSmith mete ~270 líneas
de 429 por pasada).

### Estado de flags

En el **código**: cutover en `True` para `activity`, `group_size` y
`group_allocation`; todo lo demás en `False`. En `/opt/diving-planet-bot/.env.pre`
del VPS: shadow de `is_certified`, `location` y `group_size`, y los cutover que ya
estaban (ahora redundantes con el código, inofensivos). `is_colombian`
**apagado** en los dos sitios.

### Aviso sobre PRE

Es **un solo entorno compartido**. Si vas a medir algo ahí, confirma con Álvaro y
Gonzalo que nadie va a desplegar encima mientras tanto.
