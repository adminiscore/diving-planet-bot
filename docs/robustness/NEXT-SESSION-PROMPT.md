# Prompt para la siguiente sesión

Copia y pega lo de abajo. El orden importa: primero comprobar que PRE sirve lo
que creemos que sirve, y solo después tocar nada.

---

## PROMPT

Retomamos el trabajo de robustez del bot. Lee primero
`docs/robustness/progress-log.md` (las 6 entradas del 2026-09-12) y la entrada
`0.24.0` de `docs/HISTORY.md`.

**Antes de nada**, dos comprobaciones baratas:

```bash
# 1) cuota (casi todo lo de abajo la necesita; un eval-set son ~215 peticiones)
ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker exec dp-pre-bot python3 -c \"
import httpx
from src.config import settings
r = httpx.post('https://api.openai.com/v1/chat/completions',
    headers={'Authorization': f'Bearer {settings.openai_api_key}'},
    json={'model':'gpt-4o-mini','messages':[{'role':'user','content':'hi'}],'max_tokens':1}, timeout=30)
print(r.status_code, r.headers.get('x-ratelimit-remaining-requests'))\""

# 2) que PRE corre lo desplegado el 2026-09-12 (debe salir af47e04 o posterior)
ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "cd /opt/diving-planet-bot && git log --oneline -1"
```

### Estado: qué se hizo el 2026-09-12

Cinco cosas, todas medidas y desplegadas a PRE:

1. **El enum del schema, enumerado en el texto del prompt**, generado desde el
   propio schema para los 5 campos con enum y los 2 prompts que los consumen.
   Cierra `conv913`. `activity` 94%→98%.
2. **Una petición por turno en vez de dos** (`extract_and_verify`): −38%
   peticiones, −0.69s medidos. El ORDEN dentro del prompt es lo que lo hace
   funcionar (verificación primero, huecos al final) — está en el docstring,
   **no lo reordenes "por legibilidad"**.
3. **`group_allocation` en el veto**, con trigger propio (solo si el reparto no
   suma el total) y consciente del total de la CONVERSACIÓN, no solo del turno.
4. **Invariante**: un reparto que no suma el total no se guarda, venga de donde
   venga (`supervisor.enforce_group_allocation_consistency`). Si suma de menos
   se descarta; si suma de más, sube el total.
5. **Puerta de coste retirada** de `_relevant_gaps`, con el matiz de que
   `group_allocation` puede viajar de acompañante pero nunca originar la
   petición.

Números: eval-set **198/207 (95.7%) → 204/207 (98.6%)**. Batería de
conversación: repartos correctos **3/10 → 6/10**, 0 parciales, 0 alucinaciones.
Suite 1842 passed.

### Lo PRIMERO: verificar en vivo lo que se desplegó

Nada de esto se ha visto con tráfico de verdad — **PRE no tiene tráfico** (solo
nosotros 3), así que hay que provocarlo. Dos herramientas ya hechas:

```bash
ssh ... "docker exec -i dp-pre-bot python3 -m scripts.battery_group_allocation_gate 2"
ssh ... "docker exec -i dp-pre-bot python3 -m scripts.run_extraction_eval"
```

Lo que hay que mirar en los logs de PRE, que es lo único que no se puede
simular:

- `[EXTRACT][GROUP_ALLOCATION_INCOMPLETO]` — cuántos repartos se están
  descartando de verdad. Si son muchos, la invariante está siendo demasiado
  agresiva y hay que mirar los mensajes concretos.
- `[EXTRACT][GROUP_ALLOCATION_AMPLIA_TOTAL]` — cuántas veces el reparto corrige
  al total. Si son muchos, el bug de `group_size` (ver abajo) es más gordo de lo
  que parece.
- `[EXTRACT][GROUP_ALLOCATION_VETO]` — el veto está en **cutover**, así que
  `applied=True` significa que cambió una respuesta real.
- `[LLM_EXTRACTOR][DEGRADED][COMBINED]` — si aparece, la petición fusionada está
  fallando y el turno degrada a regex.

### Cola de trabajo, por orden de valor

**1. `group_size` lee mal el total con frases no listadas.** `en total 7: 4
certificados...` resuelve `group_size=4`; `seremos 7` igual. Es el mismo fallo de
lista cerrada del parser de grupo. **No lo arregles añadiendo frases al regex**
(decisión del owner, y hay precedente de un intento así que rompió un caso real
suyo). La vía es el veto de `group_size`, que existe y está en cutover en
`.env.pre` — mirar por qué no lo caza: probablemente su trigger genérico no
dispara porque el regex "acierta" con confianza. Medir con
`scripts/battery_group_allocation_gate.py`, añadiendo escenarios de esa familia.

**2. Repartos que el LLM no reconoce como contables.** `4 con titulo`,
`3 brevetados`, `2 open water`, `4 con brevet` siguen sin dar reparto (b03/b04/
b05/b10 de la batería). Hoy el desenlace es SEGURO (la invariante hace que el bot
pregunte en vez de guardar un reparto a medias), así que no es urgente. El camino
**no** es meter las reglas de verificación en el prompt de `fill_gaps`: **ya está
medido que cuesta 5 casos del eval-set** (202→197) porque esas reglas están
escritas para desconfiar, no para rellenar. Haría falta una versión **neutra**
(qué significa el campo y qué cuenta como contable, sin la carga de abstención) y
volver a medir con el eval-set Y la batería.

**3. `is_colombian` sigue al 67-78% y su trigger genérico es inseguro.** Hay un
test (`test_field_veto_generic_trigger_risk.py`) que lo demuestra con "ninguno
colombiano" y actúa de barrera. **No activar su flag** sin darle antes un
`should_verify` propio como el de `activity`/`group_allocation`.

**4. Decidir dónde vive el flag de `group_allocation`.**
`llm_group_allocation_veto_cutover` está en `True` **en el código**, mientras que
`activity` y `group_size` están en `False` en código y activados vía `.env.pre`.
Es deliberado (es el único que se activó con datos medidos de antemano) pero es
una inconsistencia: decidir si se mueve a `.env.pre` por coherencia.

**5. `ambig-curso-padi-generico-no-se-bucear`** espera `'padi_course'`, un valor
que **no existe en el enum** de `EXTRACTION_TOOL`, así que es inalcanzable para el
veto por construcción. Es decisión de producto: ¿se añade `padi_course` al enum,
o se cambia el `expected`? No lo fuerces sin decidirlo.

### Cómo trabajar aquí (lo pidió el owner explícitamente)

- **Nada de parches regex.** Arreglan el caso de hoy y pinchan con la jerga del
  siguiente que escriba. Si la solución natural parece "añadir un patrón", busca
  la vía LLM o generar lo que haga falta desde el schema.
- **Centralizar, no individualizar.** Si el error puede salir en otras zonas, se
  arregla el mecanismo común. Un fix que solo cubre el campo que falló hoy está
  incompleto. (Esta sesión empezó con dos fixes individualizados que hubo que
  rehacer.)
- **Optimizar peticiones y latencia.** El recurso escaso es
  **peticiones/día (RPD)**, no tokens.
- **Medir por caso, no solo el agregado.** Dos veces el mismo día el overall del
  eval-set escondió movimientos en sentidos opuestos. Un A/B por caso,
  reutilizando el resto del pipeline para que solo varíe lo que se prueba, es lo
  que los encontró.
- **Los resultados negativos se documentan, no se fuerzan.** Hay dos de esta
  sesión clavados con tests para que nadie los redescubra gastando una tanda.

### Referencia para comparar (eval-set, 107 casos, 2026-09-12)

| campo | agree | % |
|---|---|---|
| activity | 62/63 | 98% |
| group_size | 44/44 | 100% |
| is_certified | 31/32 | 97% |
| location | 23/23 | 100% |
| group_allocation | 10/11 | 91% |
| is_colombian | 7/9 | 78% |
| **overall (arnés serial)** | **202/207** | **97.6%** |
| **overall (petición fusionada)** | **204/207** | **98.6%** |

El arnés declara al final si la tanda es comparable. **Si dice "TANDA NO
COMPARABLE", los números no valen** — no los uses igualmente. Lee el resumen de
`docs/robustness/eval-last-run.json`, **no del stdout**: un `grep -v` del ruido de
LangSmith borró la fila de `group_allocation` en una tanda de esta sesión, que es
exactamente el fallo contra el que avisa la entrada del arnés.

### Estado de flags en PRE

`activity` y `group_size` en **cutover**; `is_certified` y `location` en
**shadow**; `is_colombian` **apagado**; `group_allocation` en **cutover desde el
código** (no hace falta tocar `.env.pre`). Los demás viven en
`/opt/diving-planet-bot/.env.pre` del VPS, no en el repo, así que un redespliegue
no los pisa.

### Aviso sobre PRE

Es **un solo entorno compartido**. Si vas a medir algo ahí, confirma con Álvaro y
Gonzalo que nadie va a desplegar encima mientras tanto.
