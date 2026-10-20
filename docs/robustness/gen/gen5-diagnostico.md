# gen-5 · Idioma del primer turno (20-oct, Gonzalo con Claude)

**Causa de G9** (del análisis por causas, sin abrir el examen): "primera respuesta en otro idioma (también portugués →
debía ser inglés)", 4 fallos, 2 diálogos de un solo fallo. Regla G-10 (Gadea, 14-oct): español → español, inglés →
inglés, cualquier otro idioma → inglés.

## Diagnóstico

El idioma del primer mensaje se decidía en **cuatro sitios**, cada uno a su manera:

| Camino del primer turno | Quién decidía el idioma | G-10 |
|---|---|---|
| Reserva y RAG (`nucleo/setup._setup_phase`) | extractor → palabras vacías → LLM → pistas | sí |
| Tema sensible: médico, clima (`supervisor._reply_language`) | palabras vacías → pistas | no |
| Pide un contacto, "¿eres un bot?" (`supervisor._infer_language`) | solo pistas | no |
| Edad, buceo adaptado | nadie: el `"es"` por defecto del estado | no |

Por eso un "Could you send me the phone number…" recibía la respuesta en español, y un mensaje médico en portugués se
contestaba en español en vez de en inglés.

## Cambio (flag `IDIOMA_UNICO_DE_APERTURA`, APAGADO)

- La cadena de la reserva sale a una función propia, `nucleo.setup.idioma_de_apertura`, con el mismo código.
- Con el flag, el router del grafo (`orchestration/graph._router_node`) la llama una vez por conversación, **a la vez
  que las señales** de Jev. Fija `language` y `detected_language`, y todas las rutas lo heredan: `_reply_language` y
  `_infer_language` ya respetan un idioma fijado.
- `_setup_phase` no vuelve a decidirlo si el router ya lo hizo en ese turno.
- Sin el flag, el comportamiento es idéntico: `_setup_phase` llama a la misma función con el mismo código de antes.

## Medida

Banco propio `docs/robustness/gen/dialogos-gen5.json`: 16 primeros mensajes en es, en, pt, fr, it y de, uno por cada
camino del turno (reserva, RAG, médico, clima, contacto, "¿eres un bot?", edad, mensaje corto). Se corrió con
`reproducir_juez_pre --banco … --codigo-local`, dentro de PRE y sin desplegar. Cada párrafo de cada respuesta se
comprobó con las palabras vacías del bot.

| Variante | Respuestas enteras en su idioma | Mediana |
|---|---|---|
| Base (código de `pre_gadea` f6bb4a6), 2 reps | 22/32: fallan en-contacto, en-bot, en-edad, pt-medico, pt-contacto (2/2 cada uno) | 3,95 s |
| Con el flag, 2 reps | **32/32** | 3,71 s |
| Con el flag, 3 reps (otra tanda) | **48/48**: banco 3/3 en los 16 | 3,84 s |

Ficheros: `2026-10-20-gen5-base.jsonl`, `2026-10-20-gen5-con.jsonl` y `2026-10-20-gen5-con-3.jsonl`, en esta carpeta.

## Pendiente

- La ronda core A/B frente a una base del mismo día, para promocionarlo. Necesita subir a `pre_*`, así que se coordina
  en Coral.
- No resuelto aquí: un primer mensaje de una o dos palabras en otro idioma ("Olá!") se sigue decidiendo por palabras
  vacías y pistas, porque G-10 no mira mensajes tan cortos a propósito (ronda flujo1-B2).
