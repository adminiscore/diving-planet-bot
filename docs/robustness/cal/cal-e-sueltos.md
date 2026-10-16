# CAL-E · Los "sueltos": contacto, idioma, enlaces, link especial (16-oct, Gadea con Claude)

Los 6 casos con `tarea == "CAL-E"` en el banco de fallos. Para Álvaro y Gonzalo. Todos los flags **APAGADOS**: PRE se
comporta igual.

## 1. La base (`cale-E0-base`, 6 casos ×3): 12/18

| Caso | Criterio | Falla | Qué pasa hoy |
|---|---|---|---|
| cal-03 | sin invenciones | 3/3 | da el WhatsApp oficial y añade "(solo mensajes de WhatsApp, no llamadas)", que **no está en la base** |
| cal-12 | idioma | 3/3 | primer mensaje en portugués ("Busco el seguinte: Vamos en família a Cartagena") → contesta en español |
| cal-29 | link especial → asesor | 3/3 | explica que no hay enlace personalizado y nombra al asesor, pero **no ofrece pasar** con él |
| cal-33 | sin invenciones | 3/3 | el cliente pide el número que perdió y el bot **se niega** ("no puedo compartir números"), contra la decisión del 17-sep |
| cal-38 | sin invenciones | **0/3** | ya no inventa "el link no funcionó": contesta que el 10 % es automático |
| cal-39 | descuento automático | **0/3** | igual: lo explica bien |

**cal-38 y cal-39 ya pasan sin tocar nada.** El fallo de ex-10 (escalaba diciendo "sorry the link didn't work") no se
reproduce hoy. Se deja medido y se queda como regresión; el arreglo E2 (abajo) se queda hecho porque la frontera es
correcta, pero **no tiene un caso que lo demuestre**: eso hay que decirlo y no contarlo como mejora.

## 2. Las causas y el arreglo (cada uno en UN sitio, con su flag)

| Flag | Caso | Causa | Arreglo |
|---|---|---|---|
| `contacto_pasa_a_persona` | cal-03, cal-33 | **DECISIÓN DE GADEA del 16-oct** (sustituye a la del 17-sep): esto es un chatbot y **no da números**. Antes daba el WhatsApp y le añadía "(solo mensajes, no llamadas)", que la base no dice | quien pide un número o quiere hablar con alguien **pasa con un asesor**, con el mismo pase que la posventa (paso, motivo y nota del lead). Criterio del golden `contacto-real` y casos cal-03 y cal-33 del banco actualizados; y **28 menciones del número salieron de las respuestas de la base** (13 preguntas frecuentes, es/en): ninguna manda ya escribir a un número, todas pasan con un asesor |
| `pase_si_pide_fuera_del_sistema` | cal-29 | "Pero un link especial" no era, para la señal, algo que solo pueda hacer una persona, así que el bot explicaba que no existe sin ofrecer el pase | la señal `needs_staff` incluye la clase: un enlace de pago a medida, una factura, tarifas especiales o una salida privada por cotizar |
| `idioma_del_extractor` | cal-12 | el idioma del primer turno lo decide una **lista de palabras vacías** que corta la cadena antes del LLM; un portugués con muchas palabras iguales al español sale "es" | lo dice el **extractor** (campo `idioma`), que ya va lanzado en paralelo con el enrutador: ni una llamada más ni una lista de palabras. "es"/"en" tal cual, cualquier otro → inglés (G-10) |
| `jev_con_contexto` | cal-29, cal-33 | **Jev contesta las señales viendo solo el mensaje del turno**: un mensaje referido pierde a qué se refiere ("Me lo podrías compartir por favor" tras "se me perdió el número"; "Pero un link especial") | le viajan los **dos últimos mensajes** como referencia, dejando claro que las preguntas son sobre el último. Beneficia a TODAS las señales |
| `queja_solo_si_algo_falla` | (cal-38, cal-39: ya pasan) | lo que el cliente esperaba ver y no ve se tomaba por avería | frontera de la clase en las señales de queja de enlace y tema sensible: un descuento, un precio, una opción o un código que no aparecen son una **pregunta** que contesta la base |

Nada de esto añade una lista de frases ni un patrón: **la lista de palabras es justo el fallo que se arregla** en
cal-12, y el contexto que le faltaba a Jev es lo que hacía inútil cualquier lista en cal-33 (ninguna frase cabe en "me
lo podrías compartir").

## 3. La medida con los flags (`cale-E1245`, los cuatro juntos): 9/18

| Caso | Base | Con los flags | Qué pasó |
|---|---|---|---|
| cal-03 | 3/3 | **0/3** | E1: no da número y pasa con un asesor |
| cal-12 | 3/3 | 3/3 | **E4 no mueve el caso**: hay que ver si el extractor también dice "es" en ese portugués mezclado |
| cal-29 | 3/3 | **0/3** | E3: la señal ve que un enlace a medida lo hace una persona, y pasa |
| cal-33 | 3/3 | **0/3** con el contexto completo | E5: con los últimos turnos la señal sube a 0,63, cae en la zona de duda y **decide el enrutador de respaldo, que veía solo el mensaje**: la mitad del arreglo estaba ahí |
| cal-38, cal-39 | 0/3 | 0/3 | ya pasaban |

**El diagnóstico fue lo que los arregló.** `scripts/sonda_senales.py` (nueva) reproduce el caso dentro de PRE y
enseña, turno a turno, las señales del enrutador, el idioma del estado y la traza de las líneas que deciden, sin
gastar el verificador. Con ella se vio que (1) en cal-33 la señal SÍ subía con el contexto, pero caía en la zona de
duda y la decidía el enrutador de respaldo, que no tenía contexto; (2) en cal-12 el extractor lee ese mensaje como
español, así que el mecanismo funciona y el caso no se mueve. **cal-12 sigue fallando y se deja así**: tocar el prompt
del extractor por un caso es lo que la norma prohíbe.

Cuentas finales: **cal-03, cal-29 y cal-33 arreglados 3 de 3** (medidas `cale-E135-pase` y `cale-E145-con-respaldo`),
cal-38 y cal-39 ya pasaban, **cal-12 sigue fallando** por una decisión del modelo que no vamos a forzar.

## 4. Decisión pendiente de Gadea

**¿El WhatsApp oficial es solo para mensajes?** Si lo es, se añade a la base como `contact_info.nota_es` /
`nota_en` y el bot vuelve a decirlo, esta vez respaldado. Si no, se queda sin decir. Hoy el código lo afirmaba sin
que nadie lo hubiera escrito en la base.

## 5. Cómo repetirlo

```
ENV_FILE=.env.dev python -m scripts.banco_fallos medir --tarea CAL-E --reps 3 --codigo-local --etiqueta cale-E0-base
ENV_FILE=.env.dev python -m scripts.banco_fallos medir --tarea CAL-E --reps 3 --codigo-local \
    --flag contacto_solo_lo_de_la_base --flag idioma_del_extractor --flag jev_con_contexto \
    --flag queja_solo_si_algo_falla --etiqueta cale-E1245
```

Los cuatro flags van juntos porque atacan casos distintos: qué arregla cada uno se lee en qué caso cambia. `jev_con_contexto`
toca TODAS las señales, así que antes de promocionarlo hace falta una ronda del golden (como el flag de los avisos).

## 6. Ficheros

| Fichero | Qué |
|---|---|
| `src/agents/supervisor.py` | `_nota_del_whatsapp` y el texto del pase (E1) |
| `src/agents/jev_router.py` | `_estado_para_jev` (E5) y la frontera de las señales (E2) |
| `src/agents/conversational_core.py` | `_idioma_del_extractor` (E4) |
| `src/agents/escalation.py`, `src/orchestration/graph.py` | el historial llega a las señales |
| `tests/test_cal_e_senales_y_contacto.py` | 25 tests de las cuatro causas |
| `scripts/sonda_senales.py` | señales, idioma y traza de un caso del banco dentro de PRE, sin juez |
