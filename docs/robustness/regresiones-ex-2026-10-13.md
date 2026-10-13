# Estudio de las regresiones de la fase EX (13-oct, Gonzalo)

Todas las regresiones de las cinco parejas A/B del 12 y 13-oct, releídas con `ab_judge_compare` y cruzadas con la
ronda más reciente (`2026-10-13-ex7-B`, el código de hoy salvo lo de este estudio) para saber cuáles **siguen
pasando**. Las parejas:

| Pareja | A → B | Regresiones |
|---|---|---|
| ex5 (ubicación) | 90,5 → 89,5 % (39 diálogos) | 10 |
| ex8 (actividad y nacionalidad, B2) | 92,1 → 91,5 % (69) | 19 |
| ex6 (certificación) | 89,4 → 92,9 % (41) | 7 |
| ex23 (escalado y atajos) | 95,3 → 95,3 % (13) | 1 |
| ex7 (grupo) | 90,6 → 91,2 % (47) | 8 |

## Por causa

| Causa | Veces | Diálogos | ¿Sigue en ex7-B? | Qué se hace |
|---|---|---|---|---|
| **Vuelve a preguntar la actividad** ("¿buceo, minicurso, snorkel o curso?") | 7 | `regateo-grupo-6` (×2), `pareja-certificados-cop-descuento-almuerzo`, `cambio-fecha-por-enfermedad`, `isla-hotel-refresher`, `pedir-fotos-postventa`, `certificado-fecha-precio-cop-descuento-transferencia` | sí (4) | **Dos causas distintas, las dos arregladas** (abajo): la instrucción contradictoria del extractor (`EXTRACTOR_PRECIO_ELIGE`) y la posventa (`POSVENTA_SIN_VENDER`). |
| **Tras pasar a una persona vuelve a vender**; el aviso médico no dice que pasa | 2 | `cambio-fecha-por-enfermedad` (`sin-repreguntas`, `pasa-a-persona-por-enfermedad`) | sí | `TRAS_PASE_SIN_VENDER`, `AVISO_MEDICO_DICE_PASE`. |
| **Posventa: ofrece actividades a quien ya reservó o ya buceó** | 3 | `pedir-fotos-postventa`, `cambio-fecha-por-enfermedad`, `equipaje-mochilas` | sí | `POSVENTA_SIN_VENDER` (Jev `ya_reservado`). |
| **Idioma** | 3 | `curso-open-water-…-frances` ("Frances"), `grupo-mixto-precio-cop-total` ("Busco el seguinte… família") | sí | **No es del bot: el juez lee mal.** "Frances" contesta qué idioma habla el ACOMPAÑANTE (el cliente interpretará); el propio criterio del golden dice que la instrucción es en español o inglés. "Busco el seguinte… família" es una frase con dos palabras en portugués y el resto de la conversación en español. → **Gadea**: revisar el criterio `global:idioma` del juez (que no cuente como petición de idioma la lengua de un acompañante ni un par de palabras sueltas). |
| **"Muelle de la Bodeguita" en una respuesta en inglés** | 2 (+1 en s427-B) | `reserva-ingles` | sí | Nombre propio del muelle. → **Gadea**: o el juez lo acepta (nombre propio) o el bot dice "Bodeguita Pier (Muelle de la Bodeguita)". |
| **Pregunta si es certificado aunque pidió un paquete de buceos** | 2 | `equipaje-mochilas`, `regreso-otro-dia-paquete-5` | no en ex6-B (lo arregló ex-6) | — (la regla del catálogo de ex-6). Ver la decisión pendiente 2(c) de Álvaro. |
| **Grupo y acompañante** | 5 | `acompanante-goteo` (×2: snorkel × 2; recomienda 2 inmersiones ignorando al acompañante de snorkel), `paquete-5-islas` ("Para dos personas" → "¿cuántos para el minicurso?"), "solo backpacker", `grupo-con-refresher` ("¿lo cambio?") | parcial: `acompanante-goteo` sigue | ex-7 arregló "¿lo cambio?" en los añadidos y "solo backpacker" (= 1). Queda `acompanante-goteo` (pendiente). |
| **Origen** | 4 | `precio-desde-islas` (×3: tarifa de Cartagena; "¿lo cambio?" a "quedándonos en el hotel"; "¡Sí! … la lancha sale desde Cartagena"), `certificado-fechas` (pregunta el origen ya dicho) | sí (`precio-desde-islas`) | Pendiente. |
| **El RAG no dice "pasadas las 4:30 se reserva igual por la web"** | 2 | `curso-open-water-…-frances` | sí | Pendiente: dato de la base (FAQ de anticipación). |
| **Variación de redacción del RAG** (San Bernardo, Barú, refresher, referido, alojamiento, "ya pasó la hora", foto de otra agencia) | ~10 | varios | — | Ruido: la puerta de cada fase no tocó esos turnos. |

## Arreglos de esta sesión (todos con flag; mini-ronda `atencion-A/B`)

1. **`EXTRACTOR_PRECIO_ELIGE`** — la regla general de las instrucciones del extractor ponía "¿cuánto cuesta el buceo
   certificado?" como ejemplo de algo que NO es un dato, y la de `activity` dice que preguntar el precio de un producto
   SÍ lo elige (Gadea, 14/27-sep). Sonda (5 preguntas de precio × 3): sin el flag **0/15** eligen la actividad; con
   el flag **15/15**, y "¿puedo bucear embarazada?" sigue sin dato.
2. **`POSVENTA_SIN_VENDER`** — pregunta nueva de Jev en la misma llamada, `ya_reservado` (≥ 0,7): el cliente ya tiene
   una reserva o ya hizo la actividad con nosotros. Mientras valga, el bot contesta lo que se pregunte pero no hace
   preguntas de la reserva ni ofrece el menú; vuelve la reserva si el cliente elige una actividad nueva. Banco
   `docs/robustness/posventa/banco-ya-reservado.json`: diseño **36/36** (2 pasadas), **ciego 14/14** (frases nuevas, una
   pasada).
3. **`TRAS_PASE_SIN_VENDER`** — con la conversación ya pasada a una persona, lo mismo (contesta o deja una nota corta).
   Antes solo una cortesía pura recibía la respuesta corta.
4. **`AVISO_MEDICO_DICE_PASE`** — el aviso médico añade "Te paso ahora con alguien del equipo…" (ya pasaba; no lo decía).
5. **`NOMBRE_POR_EXTRACTOR`** — el nombre lo lee el extractor con su cita (campo `nombre`; con el flag apagado la
   llamada es la de antes); la regex se queda con "me llamo / mi nombre es / my name is". Sonda: 9/9 (Rocío, Tom,
   Andrés, Mark sí; gringo, paisa, Canadian, "buzo advanced", el nombre de la hija, no). Banco ex0 (diseño, extractor):
   111 → 110/122 datos e inventos 3 → 2 (variación del extractor; ningún campo empeora de forma sistemática).
6. **`GRUPO_PRIVADO_PASE`** — el grupo privado / empresa marca el pase (motivo + resumen), desde el supervisor y desde
   el nodo `info` (`supervisor.private_group_event_reply`, una sola fuente).

## Pendiente (siguiente)

- `acompanante-goteo`: recomienda 2 inmersiones sin contar con el acompañante de snorkel; el snorkel se calculaba × 2.
- `precio-desde-islas`: "¿lo cambio?" a "quedándonos en el hotel" y la contradicción "¡Sí! … la lancha sale desde
  Cartagena".
- La base: "pasadas las 4:30 p. m. se reserva igual por la web para el siguiente día disponible".
- Para Gadea: el criterio de idioma del juez y "Muelle de la Bodeguita" en inglés (arriba).
