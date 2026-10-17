# CAL-D · Que la búsqueda traiga lo que pide la pregunta (16-oct, Gadea con Claude)

Flag `consulta_con_lo_sabido`, **APAGADO**. Sale de lo que midió CAL-A5: de los 12 casos que seguían fallando, 3 o 4
eran de búsqueda, no de avisos.

## 1. La causa, medida (no supuesta)

`scripts/sonda_senales.py` dentro de PRE, en los dos casos de búsqueda. **El reescritor de consultas sí corre**, pero
arregla la gramática y deja la elipsis:

| Caso | Mensaje | Reescritura de hoy | Qué trae la búsqueda | Qué faltaba |
|---|---|---|---|---|
| cal-42 | "And how much is per a day" | "How much is the price per day?" | la política del segundo día y los paquetes de varios días; **la ficha del plan de 1 día no entra en el top-8** | un día de buceo, desde Cartagena, buzo certificado |
| cal-14 | "Vale, en concepto le coloco otros?" | "¿Le coloco otros en concepto?" | descuentos, formulario del seguro, hoteles de las islas | al pagar la reserva por el enlace |

Es la misma causa que en el enrutador (CAL-E5): **donde se decide algo falta el contexto**. Aquí, la consulta con la
que se busca.

## 2. El arreglo

En un solo sitio (`src/agents/query_rewriter.py`), para todas las preguntas:

1. el reescritor recibe **lo que ya sabemos del cliente** en campos estructurados del estado (actividad, origen,
   nacionalidad: los mismos hechos que eligen los avisos de CAL-A5), y
2. una regla: *una consulta que deja una elipsis o un pronombre ("por día", "ese", "en concepto") NO es
   autosuficiente; escríbela entera. No inventes datos que no consten.*

Ni una llamada de más (el reescritor ya se llamaba) y ninguna lista de frases.

## 3. La medida (`cald-D1-consulta`, banco CAL-A 16 casos ×3)

| Medida | Fallan |
|---|---|
| A0 base | 47/48 |
| A5 avisos | 37/48 |
| **A5 + consulta con lo sabido** | **36/48** |

- **cal-42 arreglado 3 de 3**: "For a one-day trip from Cartagena, 2 dives cost USD 178 per person online (regular
  USD 197)", en vez del paquete de 5 inmersiones. Es el caso que CAL-D buscaba.
- **cal-14, cal-49 y cal-64 siguen 3/3**: la consulta mejora, pero la fuente que contesta sigue sin entrar entre los
  primeros documentos. Eso ya no es la consulta: es el índice y el reranking (CAL-D segunda parte).
- **cal-26 y cal-32 bailan** entre medidas (1/3 ↔ 2/3 y 0/3 ↔ 1/3): son los casos inestables de siempre, la variación
  que queda tras temperatura 0. Se promociona solo lo que pasa 3 de 3, así que no cuentan.

## 4. Lo que queda de CAL-D

- **cal-14** ("en concepto le coloco otros?"): la política `how_to_book` no se recupera para un mensaje sobre un campo
  de un formulario. Hipótesis para medir: el aviso `reserva-confirmada-al-pagar` exige su fuente entre las 4 primeras
  y la búsqueda no la trae; con la consulta nombrando "pagar la reserva por el enlace" debería entrar.
- **cal-49** (carta de referido): la ficha `referral` no entra entre los primeros; el aviso depende de la actividad
  `padi_open_water_referral`, que el estado no tiene.
- **cal-64** (cierre a las 4:30): primer turno largo, la política `booking_system_info` no entra en el top-4.
- El revisor del PLAN exacto contra la ficha del catálogo (lo que el plan original pedía para CAL-D) sigue pendiente;
  cal-42 se arregló por la consulta, que es más barato y más general.

## 5. Cómo repetirlo

```
ENV_FILE=.env.dev python -m scripts.banco_fallos medir --tarea CAL-A --reps 3 --codigo-local \
    --flag avisos_condicionados --flag consulta_con_lo_sabido --etiqueta cald-D1-consulta
ENV_FILE=.env.dev python -m scripts.sonda_senales --ids cal-14,cal-42 --codigo-local --solo-ultimo
```

## 7. La segunda parte de CAL-D NO es de búsqueda (medido el 17-oct)

La hipótesis era que en cal-14, cal-49 y cal-64 "la búsqueda no trae la fuente que contesta". Se midió con la sonda y
es verdad que no la trae, pero **eso no es la causa**, porque el dato ya está en el contexto por otra vía:

| Dato que falta | ¿Lo trae la búsqueda? | ¿Está en el contexto fijo? |
|---|---|---|
| el cierre a las 4:30 del día anterior (cal-64) | no | **sí, cuatro veces** en el bloque de políticas (`rag_politicas_en_contexto`, siempre encendido) |
| la carta de referido (cal-49) | no | **sí**, en políticas y en el catálogo |
| la reserva se confirma al pagar (cal-14) | no (ningún documento pasa el umbral de confianza: 0,31-0,33 frente a 0,40) | **sí**, en políticas |
| el Open Water son 2 días (cal-74) | — | **sí**, en políticas y en el catálogo |

Así que subir el número de documentos recuperados no arreglaría nada: **el modelo tiene el dato delante y no lo
dice**, porque el cliente no ha preguntado por eso. Es el mismo problema que CAL-A intentó resolver con los avisos, y
las tres rondas del golden dijeron que forzarlo empeora la respuesta (§§9-10 de `cal-a5-avisos-condicionados.md`).

**Lo que queda, entonces, no es técnico sino una decisión de Gadea.** Los criterios que fallan piden que el bot
**añada** lo que un asesor diría aunque no se lo pregunten (el cierre a las 4:30 cuando preguntan por cursos; que la
reserva se confirma al pagar cuando preguntan por un campo de un formulario). Las tres opciones, con lo que ya sabemos
medido:

1. **Un mecanismo distinto para los avisos**: no obligatorio en la redacción, sino una comprobación posterior que
   añade UNA frase sin reescribir la respuesta (idea 1 de la §10). Es lo único que no se ha probado y lo que mejor
   encaja con lo medido: el daño venía de reescribir, no de añadir.
2. **Aceptar que algunos criterios cuestan más de lo que valen** y marcarlos como "lo diría un asesor, no el bot".
   Decisión de negocio: el banco deja de medirlos y el golden también.
3. **Dejarlo como está**: PRE contesta bien lo que se le pregunta y no añade. Es lo que hay hoy, con el 97,4 % de
   criterios del suelo.

Mi recomendación: la 1, porque es barata de probar (el revisor de completitud ya existe) y porque el diagnóstico dice
que el problema era el desplazamiento, no el aviso.
