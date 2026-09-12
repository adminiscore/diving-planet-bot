# Prompt para la siguiente sesión

Copia y pega lo de abajo. El orden importa: primero el fallo del modelo en
`conv913` (el caso que originó todo el mecanismo y sigue roto), y solo
después `group_allocation`.

---

## PROMPT

Retomamos el trabajo de robustez del bot (rama `feature/agent-arch`, worktree
en `scratchpad/agent-arch-work`, desplegado en PRE vía `feature/pre_gadea`).
Lee primero `docs/robustness/progress-log.md` (últimas 3 entradas: 2026-09-10,
11 y 12) para el contexto completo.

**Antes de nada**: comprueba la cuota de OpenAI desde el VPS, porque casi todo
lo de abajo la necesita. Un eval-set completo son ~215 peticiones.

```bash
ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker exec dp-pre-bot python3 -c \"
import httpx
from src.config import settings
r = httpx.post('https://api.openai.com/v1/chat/completions',
    headers={'Authorization': f'Bearer {settings.openai_api_key}'},
    json={'model':'gpt-4o-mini','messages':[{'role':'user','content':'hi'}],'max_tokens':1}, timeout=30)
print(r.status_code, r.headers.get('x-ratelimit-remaining-requests'))\""
```

### Tarea 1 — Analizar y arreglar el fallo de `conv913` (prioritario)

El caso real que originó todo el mecanismo de veto **sigue fallando**, y ya
sabemos exactamente por qué:

- Mensaje: `"Pues me gustaría sacarme el primer nivel de buceo"`
- El regex resuelve `activity='certified_diving'` (por el patrón genérico de
  "buceo") y, gracias al patrón nuevo de "primer nivel", el mensaje ahora
  dispara 2 categorías → el veto SÍ se llama.
- Pero el modelo devuelve **`'certificarse'`**, que **no existe en el enum**
  de `activity`. `_clean_verified_value` lo descarta (correctamente: nunca
  aplicar un valor inventado) y el campo se queda con el valor del regex.

No es un fallo del código ni de infraestructura: es el modelo respondiendo
mal, de forma **reproducible**.

**Hipótesis a probar (barata)**: el prompt de verificación describe las reglas
de negocio pero **no enumera los valores válidos del enum**, confiando en que
el schema baste. Añadir la lista explícita al texto de
`_FIELD_VERIFICATION_RULES_ES/EN['activity']` en `src/prompts/booking.py`
probablemente lo arregle.

Cómo validarlo sin gastar el eval-set entero: prueba el mensaje suelto contra
el modelo real unas cuantas veces (es no determinista) y mira si devuelve
`padi_open_water`. Si funciona, corre el eval-set completo para confirmar que
no rompe nada más, y compara contra la referencia de abajo.

Si la hipótesis falla, **no la fuerces**: documenta el resultado negativo. Hay
alternativas (mapear sinónimos conocidos del modelo, o `strict: true` en el
tool schema si el SDK lo soporta), pero decídelo con datos.

### Tarea 2 — `group_allocation` en el mecanismo de veto

Justificación ya recogida (ver progress-log 2026-09-10): tras arreglar que un
reparto incompleto redujera el `group_size` declarado, quedan repartos
**incompletos pero visibles** (total correcto, reparto que no suma el total).
Ejemplo real: `"somos 5: 3 certificados, 1 minicurso y 1 snorkel"` → el
reparto captura solo `{minicourse:1, snorkel:1}` porque `"N certificados"` sin
verbo no matchea `activity_kw`.

Ojo con dos cosas:

1. **El 91% de `group_allocation` en el eval-set NO justifica por sí solo el
   veto**: el único caso que falla ahí es una alucinación de `fill_gaps`
   leyendo el historial (`hist-followup-must-not-rederive-resolved-group-allocation`),
   y el veto ni se dispararía (solo actúa sobre campos que el REGEX resolvió
   ese turno). La justificación real es la de arriba.
2. `group_allocation` es un **dict**, no un escalar. `verify_fields` ya lo
   contempla (`_clean_verified_value` limpia los nulls del schema estricto,
   igual que `fill_gaps`), pero conviene un test explícito.

**Proceso obligatorio** (el mismo que evitó un desastre con `activity`):
flags nuevos en `False` → desplegar → shadow-mode → batería dirigida →
eval-set → *solo entonces* decidir cutover, y con datos, no con corazonada.

### Referencia para comparar (eval-set, 107 casos, tanda limpia 2026-09-12)

| campo | agree | % |
|---|---|---|
| activity | 59/63 | 94% |
| group_size | 44/44 | 100% |
| is_certified | 31/32 | 97% |
| location | 23/23 | 100% |
| group_allocation | 10/11 | 91% |
| is_colombian | 6/9 | 67% |
| **overall** | **198/207** | **95.7%** |

El arnés declara al final si la tanda es comparable. **Si dice "TANDA NO
COMPARABLE", los números no valen para comparar** — no los uses igualmente.
El resumen se escribe también a `docs/robustness/eval-last-run.json`, que el
ruido de stdout no puede corromper (manda stderr a un fichero aparte, no lo
filtres mezclado).

### Latencia — ya medido, no hace falta repetirlo

El agrupado **gana claramente** a las llamadas sueltas. Multi-campo (4 campos
elegibles en el mismo turno):

| enfoque | coste |
|---|---|
| una petición por campo, en serie | +1.78s / +2 peticiones |
| una petición por campo, en paralelo | +1.21s / +2 peticiones |
| **todas agrupadas en una petición** | **+0.79s / +1 petición** |

Y lo estructural: **+1 petición sea cual sea el número de campos**, así que
añadir `group_allocation` al mecanismo **no encarece el turno**. Cuando no
dispara ningún veto, el coste es cero.

### Cosas encontradas y NO arregladas (cola de fondo, sin urgencia)

- Gentilicios regionales para `is_colombian` ("rolo", "catracho", "from the
  UK") → el regex se abstiene. Cola larga; es territorio de `fill_gaps`.
- `is_colombian` mide 67% y su trigger genérico es **inseguro**: hay un test
  (`test_field_veto_generic_trigger_risk.py`) que lo demuestra con
  "ninguno colombiano" y actúa de barrera. No activar su flag sin resolverlo.
- `"mi pareja"` + más gente subcuenta `group_size` (da 2 en vez de 4). Un
  intento de arreglarlo por regex **rompió un caso real validado por el
  owner**; revertido y documentado. Candidato natural para el veto.
- `"venció"/"caducó"` no marca `last_dive_over_2_years` (refresher). Mejora
  menor.

### Estado de flags en PRE

`activity` y `group_size` en **cutover real**; `is_certified` y `location` en
**shadow**; `is_colombian` **apagado**. Viven en `/opt/diving-planet-bot/.env.pre`
del VPS (no en el repo), así que un redespliegue no los pisa.
