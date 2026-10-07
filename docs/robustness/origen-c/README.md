# Punto 3, opción C — escalón 0 en PRE (7-oct, Gonzalo)

**Qué se mide.** La opción C del punto 3 (Álvaro, `c99d3bb`, HISTORY 0.29.99): si el cliente pide un precio y no
sabemos desde dónde sale, el **código** pregunta el origen antes de cotizar (`conversational_core._origen_antes_del_precio`,
flag `RAG_ORIGEN_PREGUNTA`). Paso 1 del relevo del 7-oct.

**Cómo.** `scripts/reproducir_juez_pre.py <diálogo> --reps 1 --flag rag_origen_pregunta` para los 8 diálogos del
relevo, dentro de `dp-pre-bot` (PRE sirviendo `c99d3bb`, `check_deploy` en verde; el flag solo en ese proceso: el bot de
verdad no cambia). Comparado con OFF/V1/V2 del 6-oct (`docs/robustness/origen-2026-10-06.json`) con
`scripts/origen_c_comparar.py` (nuevo). Una salida por diálogo: `<diálogo>.jsonl`.

## Resultado: PASA

| diálogo | criterio | OFF (hoy) | **C** |
|---|---|---|---|
| `open-water-precio-para-colombianos-corrige-mito` | preguntar, no cotizar | cotiza (t1) | ✅ pregunta, no cotiza |
| `minicurso-precio-colombianos-origen-pendiente` | preguntar, no cotizar | cotiza (t4) | ✅ pregunta en t4, no cotiza |
| `precio-fundive-datos-faltan` | preguntar, no cotizar | nada | ✅ pregunta |
| `colombianos-precio-minicurso-dos-inmersiones` | preguntar, no cotizar | no pregunta | ✅ pregunta (t2 y t5), no cotiza |
| `reserva-paquete-5-buceos-solicita` | preguntar, no cotizar | pregunta (flujo de reserva) | ✅ igual: pide RESERVAR, no un precio; no cotiza |
| `paquete-5-buceos-cop-refresh-y-hoteles` | preguntar, no cotizar | cotiza (t1 y t2) | ⚠️ pregunta en t1, **cotiza en t2** |
| `referral-mas-refresher-hotel-y-domingo-pascua` | NO repreguntar | — | ✅ pregunta una vez (t1, pedía precio sin origen) y en t3, ya dicho "hotel on the island", cotiza sin repreguntar |
| `curso-open-water-transporte-y-regreso-otro-dia` | NO repreguntar | — | ✅ no pregunta nunca |

**Mejor que el bot de hoy en todos, peor en ninguno, y arregla las 2 regresiones de V1** (que repreguntaba lo que el
cliente ya había dado a entender). Es la primera de las tres variantes que funciona — y la única que va por **código**:
V1 y V2 eran redacción del prompt (ver el patrón en `docs/robustness/rag-3/README.md`).

## El hueco que queda: "¿y en pesos?"

En `paquete-5-buceos-cop`, turno 2, el cliente escribe **"Gracias - y en pesos? Para colombianos?"**: pide un precio,
pero sin ninguna de las palabras que la puerta reconoce (`_PIDE_PRECIO_RE`: "precio", "cuánto cuesta", "how much"…).
La puerta no salta y el RAG cotiza Cartagena. Es una repregunta típica de conversación, justo después de que el bot
haya preguntado el origen (la pregunta del precio está guardada en `state.pregunta_precio_pendiente`).

No vale añadir "pesos" a la expresión regular: sería un parche, y la siguiente forma ("¿y para dos?", "¿y con
almuerzo?") fallaría igual. Dos arreglos con fundamento, para después de la ronda:

1. **Mirar la RESPUESTA, no la pregunta.** Si el origen no consta y lo que va a decir el bot lleva un importe, está
   cotizando sin origen, sea cual sea la forma de la pregunta. La regla de la opción C es "no cotizar sin origen"; se
   comprobaría justo eso. Coste: la llamada al RAG se hace y se tira.
2. **Con la pregunta del origen ya hecha y sin contestar**, tratar la siguiente pregunta de importe como la misma.

## Comprobaciones gratuitas antes de gastar (cobertura de la puerta, sobre el golden visible)

- De 36 mensajes que piden precio, la puerta preguntaría en 24 y se calla en 12 porque el cliente nombró un origen.
  **Solo 2 se callan únicamente por "isla"**, y uno es correcto ("**estaremos** en islas del rosario en junio" sí es
  origen). El otro es un falso silencio: "hoping to include the **island visit**" es el destino. **1 de 36.**
- "Cotizar"/"quote" no es un hueco: el único caso del golden es "¿cotizan los **hoteles**…?", y el precio del hotel es
  lo que la puerta excluye a propósito.

## Error de medida que corregí

Mi primer comparador contaba como "pregunta el origen" el **saludo de bienvenida** ("departing from Cartagena or
right from the islands"), que es una frase afirmativa. Falseaba el turno 1 de casi todos los diálogos. Ahora solo
cuenta el origen dentro de una frase que acaba en "?", y la C se reconoce por su texto exacto.

## Escalón 1: ronda core `origen-c-B` (7-oct) — la idea funciona, la puerta miraba lo que no era

Flag encendido en PRE (`6d6babf`), ronda core (32 conv / 93 turnos, 0 sin respuesta, p50 2,0 s, p95 5,4 s) frente a A =
`2026-10-01-privacidad-B` (referencia curada; A seguía 100 % en caché, misma referencia). La puerta saltó 5 veces, en
4 conversaciones (`[CORE][ORIGEN]` en `logs-pre-2026-10-07-origen-c-B.txt`).

**A 93,9 % → B 92,9 %** (214/228 → 210/226), 4 mejoras, 8 regresiones. Leídas una a una:

| regresión | ¿la puerta? | qué es |
|---|---|---|
| `moneda-precios…` / `moneda-por-nacionalidad` (ya no_cumple en A, pero peor) | **sí, t5** | **real.** "Amigo el precio que está allí es en dólares o pesos colombianos": dice "precio" pero pregunta la MONEDA. A explicaba USD/COP; B solo repite la pregunta del origen (que el bot ya había hecho en t4). |
| `paquete-5-buceos-cop` / `sin-invenciones` → revisar | sí, t1 | **real, ya conocido:** "Gracias - y en pesos?" (t2) cotiza 1.429.000 COP sin origen. A cotizaba igual: no está peor que hoy. |
| `open-water-precio…` / `importes-catalogo` cumple → no_aplica | sí, t1-t2 | **buscada:** ya no da importes sin saber el origen. |
| `referral…` / `hoteles-base-sin-incluir` | no (t2) | variación del RAG: en t2 (hoteles) la puerta no intervino; olvidó "alojamiento no incluido". |
| `grupo-con-refresher` (×2), `manual-duracion-curso`, `minicurso-islas…`, `pedir-fotos-postventa` | no | ruido: la puerta no saltó ni una vez en esas conversaciones. |

Mejoras: `paquete-5` `precio-cop-segun-origen` y `sin-repreguntas` (lo que se buscaba), y dos de ruido.

**Lección:** las dos fallas reales son la misma: la puerta decidía mirando **la pregunta** (¿dice "precio"?). Falla
por los dos lados: pregunta de moneda con "precio" (se calla de más) y repregunta de importe sin "precio" (cotiza).

## Arreglo (7-oct, Gonzalo): la puerta mira la RESPUESTA

`_origen_antes_del_precio(state, message, answer)`: el RAG se llama siempre y la pregunta del origen **sustituye** a
su respuesta solo si esa respuesta **lleva un importe** (`_IMPORTE_RE`: "1.429.000 COP", "USD 178", "$630,000"…), el
origen no consta, el cliente no lo ha dado a entender, no es precio del hotel, y el cliente pide un precio **o**
repregunta con la pregunta del origen ya hecha y sin contestar (`state.pregunta_precio_pendiente`: "¿y en pesos?").
Un importe en la respuesta a otra cosa ("¿qué incluye?") se deja como hoy. Coste: la llamada al RAG que antes se
ahorraba (con rag-5 va en paralelo al enrutador: no añade espera).

Tests (`tests/test_rag_origen_pregunta.py`): los dos casos de la ronda, y uno de punta a punta de "¿y en pesos?" que
**falla con el código anterior** y pasa con este.
