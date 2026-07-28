# Carrito de botones vs. bot conversacional que interpreta — estudio

> Escrito 2026-07-22 a petición del owner tras probar el flujo de Rocío en PRE
> ("me parece que lo del carrito no es tan buena idea… ¿no podríamos implementar
> un bot como el que tenemos al principio que interprete?"). Objetivo: decidir con
> rigor, sobre el código real, si seguir con el carrito de botones o pasar a un
> flujo conversacional, y cómo.

## 1. La pregunta bien planteada

No es "carrito **sí o no**". El "carrito" mezcla dos cosas distintas que conviene separar:

1. **El modelo de datos de reserva** (`mixed_cart`: N personas × M actividades ×
   variantes de plan + preguntas de seguridad + precios). Esto es **necesario e
   irreductible**: una reserva de buceo real tiene estructura (1 certificado 2
   inmersiones + 1 acompañante snorkel + un minicurso para el hijo…). Cualquier bot,
   por muy conversacional que sea, tiene que mantener ese estado por dentro.
2. **Cómo se conduce ese modelo**: hoy, con **menús de botones** paso a paso
   (`Añadir actividades` → `¿Qué actividad?` → preview → `Volver`…). Esto es
   **opcional** y es la fuente real de la fricción que se ve en los pantallazos.

**El "bot del principio que interpreta" no es un bot diferente.** Es exactamente el
mismo carrito, pero conducido por la capa de interpretación en vez de por los menús.
Por eso la entrada ("hola soy Rocío, tengo el open water y quiero bucear") se siente
natural y el resto se siente rígido: en la entrada manda el intérprete; en el carrito
mandan los botones.

## 2. Lo que ya existe (importante: no partimos de cero)

El stack conversacional **ya está construido**, solo que subordinado a los botones:

| Capa | Qué hace | Estado |
|---|---|---|
| `intent_detector.py` (regex) | Extrae campos sueltos (actividad, cert, grupo, ubicación, edades, nacionalidad) | Maduro |
| `llm_extractor.py` (Gadea, Fases 0-8) | **Gap-filler**: el LLM rellena solo los campos que el regex dejó vacíos, con abstención segura | Nuevo, cutover por dominio |
| `orchestrator.py` (`_dispatch_orchestrator`) | 10 tools que mapean lenguaje natural → mutaciones del carrito (`add_to_cart`, `remove_item`, `set_location`, `cart_action:confirm/add/modify`, `set_profile`…) | Maduro, se invoca en todos los pasos `_MIXED_FLOW_STEPS` |
| `decision_tree.py` (~30 pasos `MIXED_*`) | State machine que produce los **menús de botones** | Maduro, es el conductor por defecto |

Es decir: la reserva ya se puede conducir por texto ("añade 2 snorkel", "quita el
curso", "quiero reservar"). Lo que falla es que el **default** de cada paso es sacar
un menú, y el intérprete solo actúa cuando el texto no encaja en un botón.

## 3. Cómo lo hacen otros bots (los tres paradigmas reales)

1. **Guiado por menús / árbol de decisión** (IVR, muchos bots de FAQ, formularios de
   chat). El bot manda; el usuario elige de una lista. **Ventaja**: determinista,
   barato, sin alucinación, fácil de testear. **Desventaja**: rígido, no absorbe
   información que el usuario ya dio, obliga a "volver" y a navegar. **Es lo que
   tenemos en el carrito.**
2. **Conversacional por relleno de huecos (slot-filling)** — el patrón estándar de
   los asistentes de reserva serios (aerolíneas, hoteles, restaurantes) y de los
   agentes LLM modernos. El bot mantiene un **estado estructurado de la reserva**,
   en **cada turno extrae los slots** que pueda del mensaje, y **solo pregunta por
   lo que falta y es obligatorio**, en lenguaje natural. Los botones existen como
   **quick-replies opcionales** (atajos), no como el volante. **Ventaja**: fluido,
   nunca re-pregunta lo ya dicho, absorbe varios datos de una frase. **Desventaja**:
   depende del LLM (latencia, coste, extracción ocasionalmente errónea) → exige red
   de seguridad determinista.
3. **Híbrido** (lo que de facto es hoy, mal balanceado). Intérprete para arrancar,
   menús para el resto. El problema no es el híbrido en sí, sino **quién es el
   default**: hoy el default es el menú y el intérprete es la excepción.

**Los bots que se sienten "profesionales" en reservas son slot-filling (paradigma 2)
con botones como adorno, no como control.** Es a lo que apunta el owner.

## 4. Por qué el carrito se siente torpe: los 5 bugs son síntomas del paradigma

Los errores reportados no son fallos sueltos: son consecuencia estructural de
conducir por menús un state machine que no comprueba qué ya sabe.

| # | Síntoma (pantallazo) | Causa raíz | En slot-filling… |
|---|---|---|---|
| 1 | "¡Genial!" repetido dos veces | Se concatenan dos copys que ambos abren con "Genial" (confirmación + prompt de ubicación) | El turno compone **un** mensaje coherente, no dos plantillas pegadas |
| 2 | Botón "Volver" en la pregunta de ubicación que lleva a "armar tu reserva paso a paso" (pantalla genérica sin contexto) | Navegación por botones sobre un state machine: "volver" es un salto de paso, no una intención | No hay "volver"; el usuario dice qué cambiar y el estado se actualiza |
| 3-4 | Re-pregunta "¿han pasado 2 años?" tras añadir al acompañante snorkel | `_start_cert_companion_split` re-entra en `MIXED_CERT_LAST_DIVE` sin mirar que esa respuesta ya se dio | El estado recuerda `last_dive`; solo se pregunta lo que falta |
| 5 | Al añadir snorkel no pregunta cuántas personas | El paso de menú "añadir actividad" no ata la cantidad | El extractor saca la cantidad de la frase, o se pregunta solo si falta |

Los cuatro se **arreglan puntualmente** (ver §7), pero es jugar al topo: cada paso de
menú es una oportunidad nueva de olvidar contexto. **El slot-filling los previene por
construcción.**

## 5. Opciones

- **Opción A — Seguir con el carrito de botones y pulir.** Arreglar los 5 bugs, seguir
  parcheando fricciones. **Coste bajo, techo bajo**: nunca dejará de sentirse un
  formulario; los bugs de "olvida/repite" reaparecerán en cada paso nuevo.
- **Opción B — Conversacional-first, carrito como estado invisible (RECOMENDADA).**
  Invertir quién manda: el intérprete (extractor + orquestador) pasa a ser el conductor
  por defecto; el `mixed_cart` se queda como **estado interno** (sigue siendo el modelo
  de datos correcto y alimenta precios/resumen); los menús de botones bajan a
  **quick-replies opcionales** (se ofrecen, pero siempre se acepta y se prefiere el
  texto). Cada turno: (1) extraer slots del mensaje, (2) actualizar el estado, (3)
  calcular qué **obligatorio** falta, (4) preguntar solo eso en lenguaje natural, (5) al
  estar completo → resumen + confirmación. **Reusa casi todo lo ya construido** (§2); es
  reorganizar el volante, no reescribir el motor.
- **Opción C — Reescritura desde cero.** Descartada: tiramos un state machine y un
  orquestador maduros y probados; alto riesgo, sin necesidad.

## 6. Recomendación: Opción B, por fases, sobre lo existente

La clave es que **el modelo de datos (carrito) se queda** y **la máquina de estados se
adelgaza** a favor del bucle de slot-filling que ya tenemos medio montado.

**Fase 1 — Un solo punto de comprensión al principio del turno.** Antes de que ningún
paso saque su menú, correr extracción + orquestador y aplicar todo lo que el mensaje
diga (esto es justo el "cutover único temprano en `_route_message_inner`" que la Fase 8
de robustez de Gadea ya dejó apuntado como el refactor correcto — se alinean). Resultado
inmediato: se dejan de re-preguntar cosas ya dichas (bugs 3-4) y se absorben varios
datos de una frase (bug 5).

**Fase 2 — El "siguiente paso" se calcula, no se cablea.** Sustituir el "cada paso
llama a su menú" por una función `next_missing_slot(state)` que devuelve el único dato
obligatorio que falta (ubicación → plan → cantidad → seguridad → confirmar), y un
redactor que lo pregunta en lenguaje natural. Los pasos `MIXED_*` que solo existían para
enrutar botones desaparecen o quedan como fallback.

**Fase 3 — Botones como adorno.** Mantener quick-replies donde ayudan (Cartagena/islas,
sí/no de seguridad, confirmar), pero sin "Volver" ni menús de navegación: los cambios se
dicen ("mejor quita el snorkel", "en realidad somos 3").

**Qué NO tocar / cuidar** (rigor, no entusiasmo):
- La **confirmación final, el precio y la pregunta de seguridad ("2 años")** siguen
  siendo momentos **explícitos y deterministas** — nada de dejar que el LLM improvise un
  cobro o se salte el gating de seguridad.
- El conversacional-first **apoya más peso en el LLM** (latencia + coste + extracción
  errónea ocasional). Por eso importa la red de seguridad que ya diseñó Gadea: extractor
  como **gap-filler con abstención** (nunca misfill), guards deterministas, y la Fase 6
  (bucle de datos reales) para medir la fiabilidad por campo antes de fiarnos.
- Migrar **por vertical** (empezar por el camino certificado de 1 actividad, que ya es
  casi conversacional) y medir en PRE, no un big-bang.

## 7. Los 5 bugs — arreglo inmediato (independiente de la dirección)

Se pueden arreglar ya, y conviene, porque incluso en la Opción B algunos copys/estados
se reutilizan:

1. **"Genial" duplicado** — quitar el "Genial" de uno de los dos copys (la confirmación
   de cert o el prompt de ubicación).
2. **"Volver" en ubicación → pantalla genérica** — quitar el botón `back` de ese paso de
   ubicación (mismo patrón que `_CART_MENU_KEYS` de v0.20.27; parece que este paso de
   ubicación quedó fuera del set) y, en la Opción B, sustituir "volver" por texto.
3-4. **Re-pregunta "2 años"** — `_start_cert_companion_split` no debe re-entrar en
   `MIXED_CERT_LAST_DIVE` si `last_dive` ya se respondió para el subgrupo certificado;
   comprobar el estado antes de preguntar.
5. **No pregunta cantidad al añadir** — el paso de "añadir actividad" debe ir a
   `MIXED_ADD_QTY` (o extraer la cantidad de la frase) antes del preview, en vez de
   asumir 1.

## 8. Decisión pendiente del owner/equipo

- ¿Vamos a la **Opción B** (conversacional-first por fases) o nos quedamos en **A**
  (pulir el carrito)? Recomendación: **B**, porque es el "bot que interpreta" que pide el
  owner, reusa lo ya construido, y ataca la causa raíz de los bugs en vez de los
  síntomas.
- Si B: encaja de forma natural con el trabajo de robustez de Gadea (el extractor LLM es
  precisamente el motor del slot-filling; la Fase 6 mide su fiabilidad). Conviene
  coordinarlo con Gadea para no duplicar.
- Independiente de A/B: arreglar los 5 bugs de §7 ya.
