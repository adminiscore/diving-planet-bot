# CAL-A5 · Avisos con condiciones (16-oct, Gadea con Claude)

CAL-A reabierta por decisión de Gadea del 16-oct. Qué se ha hecho, por qué así, qué se mide y qué límites tiene.
Para Álvaro y Gonzalo.

## 1. De dónde sale

Álvaro midió A0-A4 sobre 16 casos del banco ×3 (`docs/robustness/cal/medidas/`):

| Medida | Fallan | Qué enseñó |
|---|---|---|
| A0 base | 47/48 | el suelo: estos 16 casos fallan siempre |
| A1 temperatura 0 | 44/48 | algo de azar, no la causa |
| A2 plan antes de redactar | 46/48 | contesta mejor lo preguntado, pero no avisa |
| A3 plan + revisor de completitud | 45/48 | igual: lo que falta no es un punto preguntado |
| A4 revisor de avisos | **42/48** | el único que movió la aguja |

La conclusión de Álvaro (los fallos son AVISOS que el cliente necesita y no pregunta) es correcta. Lo que no se
sostenía era cerrar la tarea: **A2 no leía la base de conocimiento** (no podía saber que el minicurso no certifica) y
**A4 sí la leía y fue el único que mejoró**, pero elegía los avisos con un modelo pequeño y metía relleno.

Así que el mecanismo de A4 se queda y **la elección pasa al código**.

## 2. Cómo funciona

1. **Los avisos son datos**: `data/knowledge_base/avisos.json`, 18 avisos con sus condiciones. Cada uno enlaza con la
   política o la ficha de la que sale (`fuente`); el texto final lo redacta el RAG con ese documento, que ya está en su
   contexto. Lo edita el negocio como `policies.json`, sin tocar código.
2. **Las condiciones son sobre datos, nunca sobre el texto del cliente** (`src/flows/avisos.py`):
   - `hechos_del_estado(state)`: actividad (del árbol, del extractor, del carrito o del reparto del grupo), origen,
     nacionalidad (mixto manda), inactividad de más de 2 años. **Ninguna lista de nombres ni de palabras**: ver §4.
   - `temas_de_los_docs(docs)`: de qué va la pregunta según **los documentos que trajo la búsqueda**: la CLAVE de todos
     ellos y los `topics` solo de los dos primeros (ver §3: por qué así).
   - `fuentes_recuperadas(docs)`: las claves de los **4 primeros** documentos, lo que la búsqueda considera más
     parecido a la pregunta.
   - `seleccionar(hechos, temas, fuentes)`: los avisos con TODAS sus condiciones cumplidas, máximo 2 por turno, y los
     de `una_vez` solo si no se han dado (se apuntan en `state.avisos_dados`). Un aviso que **no depende de nada del
     cliente** (las fotos, los horarios, el cierre del sistema) necesita además que la búsqueda haya traído **su propia
     fuente** entre las primeras: así "la pregunta va de eso" lo dice el buscador, no un modelo ni un patrón.
3. **Van al RAG como puntos obligatorios** (`bloque_de_avisos`) en el mismo mensaje de la redacción.
4. **El revisor de completitud de A3 comprueba que estén** (`rag_plan.puntos_sin_cubrir` con los textos de los avisos
   elegidos) y, si falta alguno, se reintenta una vez con ellos (`feedback_de_avisos`). Si el reintento no pasa el
   revisor de siempre, vale la primera respuesta aprobada. Ningún modelo vuelve a decidir CUÁLES hacían falta.

Todo detrás del flag `avisos_condicionados`, **apagado**. Sin el flag no hay ni una llamada ni un token de más.

## 3. Lo que enseñó la primera medida (16-oct, `scripts/sonda_avisos.py`)

La primera versión elegía mal en los dos sentidos. La sonda (reproduce el turno dentro de PRE y enseña hechos,
documentos recuperados y avisos elegidos, sin gastar el verificador) dio la causa:

| Lo que pasaba | Por qué | Arreglo |
|---|---|---|
| En una pregunta por el enlace de pago salían "las fotos no están incluidas" y "operamos todos los días" | el tema salía de los `topics` de los **8-12 documentos** recuperados: juntos cubren **10 de los 13 temas**. Una política de certificación trae el topic `photos_media` y una ficha de servicio trae diez | los `topics` solo cuentan en los **2 primeros** documentos; un aviso que solo depende de la pregunta exige **su propia fuente** entre los 4 primeros |
| Ninguna clave de política casaba nunca | las claves de la base vienen **prefijadas** (`politica:food_policy`, `faq:20`, `ficha:refresher:minicourse`) y el fichero las lista sin prefijo | `_clave()` quita el prefijo: ahora la clave es la señal fuerte (la política de la comida para una pregunta de comida) |
| Tres avisos pegados al final, como un folleto | la instrucción decía "sin cambiar lo que ya contestas" | se piden **dentro** de la respuesta, donde encajen, y como mucho **2** |
| Los avisos de `una_vez` se gastaban en el primer turno | se daban por un tema cualquiera | con las dos reglas de arriba ya no saltan sin motivo |

**Lo que sí funcionó desde el principio:** el mecanismo. Cuando el estado tiene el dato, el aviso llega a la respuesta
tal cual (cal-32, "sin cédula pagas en USD, la tarifa es la misma"). El problema era la elección, igual que en A4.

## 4. Por qué es genérico y no un parche

- No hay un aviso por caso del banco: son las reglas del negocio que ya están en `policies.json`, con la condición en
  la que un asesor las diría. Los 16 casos del banco son la medida, no la lista.
- **Ninguna lista de nombres ni de palabras.** La primera versión traía una tabla con cuatro nombres de hoteles de Barú
  (`playa tranquila`, `cholón`…) sacados de los casos del golden: eso acierta esas conversaciones y falla las demás,
  justo lo que la norma del proyecto prohíbe. Se quitó. El aviso pasó a depender de que la búsqueda traiga su propia
  política (`dive_area`), que es una señal del buscador, y un aviso que depende de DÓNDE está el cliente espera a que
  el dato esté en el estado (plan EX), en vez de adivinarlo del texto. Un test lo fija
  (`test_no_hay_listas_de_nombres_de_lugares_ni_de_palabras`).
- La decisión la toma el código con campos estructurados: lo mismo que la moneda en CAL-B. Cada decisión que sale del
  modelo es una fuente de azar menos (el 23 % de los fallos no se reproducía).
- Lo que diga un buen asesor deja de vivir solo en los criterios del juez (en el examen) y pasa al producto. Por eso el
  examen oculto no mejoraba: arreglábamos respuestas, no el conocimiento.

## 5. La medida (16-oct, `cala-A5-final`)

Los 16 casos de CAL-A del banco ×3, con el código local dentro de PRE (PRE no cambia: el flag va solo en ese proceso).

| Medida | Fallan | |
|---|---|---|
| A0 base | 47/48 | el suelo |
| A4 revisor de avisos (modelo elige) | 42/48 | lo mejor de Álvaro |
| **A5 avisos con condiciones (código elige)** | **37/48** | **lo mejor hasta ahora** |

Arreglados **3 de 3** (la regla de promoción): **cal-15** (las fotos no están incluidas), **cal-32** (sin cédula se
paga en USD, misma tarifa) y **cal-48** (el minicurso no certifica, y el Open Water son 2 días con noche en las
islas). **cal-26** a 1/3 (el formulario médico se dice, pero a veces lo coloca antes de reservar).

Son tres medidas seguidas, con los ajustes que dio la sonda entre ellas: 39/48 → 37/48 → **37/48 con el código
final** (`cala-A5-avisos-datos`, `-v2`, `cala-A5-final`). La de referencia es la última.

**Por qué fallan los 12 que siguen fallando** (leído caso a caso, no son cosa de los avisos):

| Causa | Casos | Qué haría falta |
|---|---|---|
| **El turno NO lo contesta el RAG**: contesta el flujo guiado con el menú de actividades, y los avisos solo viven en el RAG | cal-55, cal-69, cal-70, cal-64 (parte) | que los avisos lleguen también a lo que escribe el núcleo. **Es la continuación natural de CAL-A** (C1 de Álvaro quita el menú, pero la respuesta sigue siendo del flujo) |
| **El estado no tiene el dato** que condiciona el aviso | cal-47 (no consta que está en las islas), cal-24 (ni hotel ni isla), cal-18 (el nivel del tío), cal-32 (a veces no deduce "sin cédula" = extranjero) | CAL-C y el plan EX: el extractor deja el dato, el código decide |
| **La búsqueda no trae la fuente del aviso entre las primeras** | cal-14, cal-64, cal-49 | CAL-D/E (la búsqueda). Bajar la exigencia haría volver el ruido |
| **El criterio no pide un aviso**, pide otra cosa | cal-42 (da el precio del paquete de 5 en vez del de 2 inmersiones), cal-36 (enumerar los descuentos vigentes) | CAL-D (búsqueda) y una decisión de negocio |

## 6. Cómo repetirlo

```
# la medida (16 casos ×3 dentro de PRE, con el código local; PRE no cambia)
ENV_FILE=.env.dev python -m scripts.banco_fallos medir --tarea CAL-A --reps 3 \
    --flag avisos_condicionados --codigo-local --etiqueta cala-A5-avisos-datos

# el diagnóstico: hechos, documentos recuperados y avisos elegidos, SIN juez (no gasta el verificador)
ENV_FILE=.env.dev python -m scripts.sonda_avisos --ids cal-32,cal-47,cal-48 --codigo-local
ENV_FILE=.env.dev python -m scripts.sonda_avisos --tarea CAL-C --codigo-local   # falsos positivos
```

**Falsos positivos** (la condición de promoción, tanto como la mejora): que no aparezcan avisos que no tocan, el
defecto de A4. Se comprueba con la sonda sobre los casos de OTRA tarea (CAL-C): se mira qué avisos salen en
conversaciones que no van de eso. Lo que queda pendiente antes de promocionar es la **ronda A/B del golden visible**,
que necesita desplegar (el golden entra por Chatwoot y usa el código de PRE, no el local): decisión de Gadea.

## 7. Límites conocidos (y qué falta)

- **`plan-no-cabe-en-la-estancia` no puede cumplirse todavía**: las fechas del cliente no están en el estado (campo del
  extractor, CAL-C). Hasta entonces, `estancia_menor_que_plan` es siempre falso. Afecta a cal-48 en parte ("se van
  mañana al mediodía").
- **Nadie sabe que el cliente habla de Barú**: `intent_detector.island_patterns` no tiene id para Barú, así que
  "Playa Tranquila en Isla Barú" dicho de paso no llega a `state.island`. La primera versión lo tapaba con una tabla de
  cuatro nombres de hoteles sacados del golden y se quitó (§4): hoy el aviso "solo operamos en las Islas del Rosario"
  se da cuando la búsqueda trae su política, y el camino bueno para el lugar es el **plan EX** (el LLM extrae el lugar,
  el código decide). Afecta a cal-23 y cal-55.
- **El estado llega tarde o no llega**: la sonda vio turnos donde el aviso correcto no podía saltar porque el estado
  no tenía el dato que lo condiciona (cal-26: el cliente dice "I'm gonna need a little refresher" y no queda ni
  `refresher_interested` ni la actividad; cal-47: está alojado en las islas y `location` sigue vacío). Eso es CAL-C
  (que el bot entienda sin repreguntar), no CAL-A: **el techo de los avisos es lo que el extractor deja en el estado.**
- **La respuesta adelantada (rag-5) se calcula antes del extractor del turno**: sus avisos se eligen con el estado
  viejo. Cuando el estado cambia, la huella no coincide y la respuesta se rehace con los hechos buenos (visto en
  cal-32); los avisos de la respuesta que se tira no se apuntan como dados.
- **Los temas vienen de los documentos recuperados**: si la búsqueda no trae nada del tema, el aviso no salta. Es
  deliberado (un aviso sin su fuente en el contexto no se puede redactar sin inventar), pero liga CAL-A a la calidad de
  la búsqueda; CAL-D/E son justo eso.

## 8. Ficheros

| Fichero | Qué |
|---|---|
| `data/knowledge_base/avisos.json` | los 18 avisos, sus condiciones, los temas y las zonas (lo edita el negocio) |
| `src/flows/avisos.py` | hechos del estado, temas de los documentos, selección y bloque obligatorio |
| `src/agents/rag_agent.py` | `rag_answer(..., avisos_hechos=...)`, el bloque en la redacción y la comprobación |
| `src/agents/conversational_core.py` | `_entradas_rag` pasa los hechos; la respuesta adelantada (rag-5) no apunta avisos que luego se tiran |
| `src/flows/state.py` | `avisos_dados`: los de `una_vez` ya dados |
| `tests/test_cal_a5_avisos_condicionados.py` | 17 tests: hechos, temas, selección, cableado y validez del fichero |
