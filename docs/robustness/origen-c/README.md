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
