# CAL-A6 · El aviso que falta, como una frase añadida al final (17-oct)

Flag `avisos_al_final` (APAGADO) y modelo `avisos_al_final_model`. Código: `src/agents/rag_plan.py`
(`aviso_al_final`, `insertar_frase`), `src/flows/avisos.py` (`lista_para_el_revisor`, `condicion_en_palabras`),
cableado en `src/agents/rag_agent.py` (junto al juez de grounding). Tests: `tests/test_cal_a6_avisos_al_final.py`.

## 1. De dónde sale

Los casos de CAL-A que quedaban (cal-49, cal-15, cal-24, cal-47, cal-48) fallan por lo mismo: a la respuesta le
falta un **aviso** que el cliente necesita aunque no lo pregunte (la carta del curso referido, que las fotos no están
incluidas, que desde las islas no hay almuerzo, que el minicurso no certifica). Lo que ya se había probado:

| Intento | Qué hacía | Qué enseñó |
|---|---|---|
| A4 (`rag_revisor_avisos`) | un modelo buscaba avisos en TODA la información y se rehacía la respuesta | metía avisos que no tocaban |
| A5 (`avisos_condicionados`) | el CÓDIGO elegía el aviso con campos del estado y la redacción lo tenía que decir | el banco mejora y el golden empeora dos rondas: el aviso obligatorio desplaza lo que la respuesta tenía que decir; y no ve condiciones que el estado no tiene (cal-49 habla del curso referido sin "elegirlo"; cal-47 se aloja en las islas y `location` está vacío) |

A6 es lo que dejó por probar el §10 de `cal-a5-avisos-condicionados.md`: **no tocar la redacción**. Tras redactar,
a la vez que el juez de siempre, un revisor lee la conversación, la respuesta y la lista cerrada de avisos de A5 (con
sus condiciones en palabras) y, si falta UNO, se **añade una frase** sin reescribir nada.

## 2. Cómo funciona

1. `lista_para_el_revisor`: los avisos de `avisos.json`, cada uno con cuándo aplica en palabras (de su `cuando`, o
   de un `cuando_texto` escrito a mano cuando la condición no cabe en campos: "pregunta por un sitio donde no
   operamos"; el curso referido descrito sin nombrarlo). Varias condiciones = "TODAS estas: (1)…; (2)…". Sin los de
   `una_vez` ya dados.
2. El revisor devuelve `{aviso, cita_del_cliente, cita_del_ultimo_mensaje, frase}`. **El código descarta** el aviso si
   no está en la lista, si ya se dio, si la cita de la condición no son palabras reales del cliente, o si la segunda
   cita no está en su último mensaje (el aviso tiene que ver con lo que pregunta AHORA).
3. La frase pasa las mismas guardas deterministas que la respuesta (importes, enlaces, teléfonos, datos personales)
   y se inserta en su propio párrafo, antes de la pregunta final si la hay. El aviso queda apuntado como dado.
4. Solo cuenta si la respuesta pasa el juez; si la llamada falla, el turno sigue como siempre.

## 3. Medido en local, sin bot (scripts del scratchpad, ~3 USD en total)

Banco del revisor: los 5 casos que necesitan aviso (respuestas reales de PRE con `sonda_senales`) y los 93 turnos de
la ronda core `2026-10-17-cal-D` (la mayoría no lo necesita), con los avisos dados apuntados como en el bot.

| Versión | Modelo | Aciertos (5) | Turnos de la ronda con aviso (93) |
|---|---|---|---|
| v1 (sin citas) | gpt-4.1-mini | 0 (en PRE: elige mal y escribe en español a clientes en inglés) | — |
| v2 (condiciones en palabras, idioma explícito) | gpt-4.1-mini | 4 | 64 (relleno) |
| v2 | gpt-4.1 | 4 | 24 |
| v3 (dos citas comprobadas por el código) | gpt-4.1 | 4 | 20-24 |
| v3 | GPT-6 Luna sin razonamiento | 4 | 24-27 |

cal-24 no sale con ninguno (la respuesta ya pregunta en qué hotel se aloja). En los 5 casos, la frase es la buena
y en el idioma del cliente.

**Latencia** (lanzando el revisor A LA VEZ que el juez de grounding, como en el bot, con el historial de cada turno,
25 turnos reales):

| Modelo del revisor | revisor p50 | juez p50 | lo que AÑADE al turno |
|---|---|---|---|
| gpt-4.1 | 0,95 s | 1,36 s | p50 0,00 s · p90 0,05 s · máx 0,14 s |
| GPT-6 Luna (sin razonamiento) | 1,55 s | 1,40 s | p50 0,39 s · p90 0,76 s · máx 1,27 s |

Con gpt-4.1 el revisor termina antes que el juez: no se nota. Luna es más barata pero aquí más lenta.

## 4. La ronda core SIMULADA (sin bot, sin su ruido)

Las respuestas reales de la ronda `2026-10-17-cal-D` (la A) con la frase que el revisor añadiría, juzgadas con el
juez del golden (gpt-5-mini, con su caché: solo se pagan los diálogos que cambian, ~0,3 USD por ronda) y comparadas
criterio a criterio con `ab_judge_compare --rejuzgar 2` (repite los juicios que cambian para quitar el ruido del juez).
Como las respuestas son las mismas salvo la frase, lo que cambie es de la frase.

| Ronda | Criterios | Diálogos sin fallo | Mejoras reales | Regresiones reales |
|---|---|---|---|---|
| A (cal-D, real) | 96,5 % | 25/32 | — | — |
| A6 v3 con gpt-4.1 | 95,6 % | 22/32 | 0 | 1: "al no ser colombianos **ni residentes**" cuando el cliente solo dijo "ninguno colombiano" |
| A6 v3 con Luna | 96,1 % | 24/32 | 1 (el referido deja de inventar) | 1: pide el nombre del hotel a quien ya dijo "Coral Sand" (el texto del aviso lo pedía) |

Lo que se arregló con eso (todo genérico, en los datos o en la regla, nada por caso):
- El texto de los avisos dice lo que dice la base: "la reserva queda confirmada al pagar" contradecía la FAQ (el pago
  se registra al momento y el equipo lo concilia después); el de la recogida ya no pide el hotel; el del USD es una
  regla ("quien no es colombiano ni residente…"), no algo que se afirma del cliente.
- El revisor no afirma nada del cliente que no haya dicho tal cual y nunca le pide datos.
- **`"al_final": false`** en los avisos que son información general (el cierre de las 4:30, que se opera todos los
  días, el formulario médico, la conciliación del pago, el 10 % online): eran 19 de los 33 avisos que Luna añadía, casi
  todos relleno. El revisor solo añade lo que evita que al cliente le salga mal lo que hace.

Con eso (v4, Luna): **3 de 5 casos** (cal-15, cal-48, cal-49; cal-47 ya no, porque la respuesta da los dos casos,
Cartagena e islas, y eso es lo que pide el revisor) y aviso en **12 de 93** turnos de la ronda, todos de los que
evitan un error (USD a quien dijo que no es colombiano, el refresh a quien lleva 5 años, sin precio especial para
colombianos, las fotos, la carta del referido, la recogida y el almuerzo en las islas).

## 5. Lo que falta

- La ronda simulada v4 (Luna, con todo lo anterior) contra la A.
- El banco CAL-A en PRE (16×3) con `avisos_al_final` y `catalogo_profundidad`, contra la base del 17-oct (38/48).
- Si las dos salen bien: la ronda core B en PRE (la A es cal-D) y promocionar.
