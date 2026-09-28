# RAG por piezas (rag-1)

Instrumento de la fase RAG de Plan Coral: separa si un fallo del RAG es de **búsqueda** (el dato no llega al
contexto), de **redacción** (llega y la respuesta no lo dice), del **juez/guardas** (la respuesta acaba en "no lo
tengo") o una **contradicción**. Todo cambio de rag-2 a rag-5 se mide con esto antes de la ronda B.

- `preguntas.json`: 47 preguntas **visibles** (nunca el examen oculto; el script se niega si alguna viene de ahí),
  93 datos con anclas, sacadas de los fallos del RAG del paso 8 y de las intenciones más frecuentes. La verdad sale de
  `data/knowledge_base` y del catálogo, no de lo que contestó el bot. 5 datos son **opcionales** (útiles, pero el
  cliente no los pidió) y 1 es un **cálculo** (el total de un grupo).
- `scripts/rag_piezas.py`: corre `rag_answer` dentro de PRE con el estado del cliente (`_build_extra_context`), espía
  cada pieza y un verificador gpt-4.1 marca cada dato (dice / no dice / contradice).

```
python -m scripts.rag_piezas --name X                  # completo, ~0,03 $ por pregunta, ~5 min
python -m scripts.rag_piezas --name X --solo-busqueda  # solo la búsqueda, céntimos
python -m scripts.rag_piezas --comparar A.json B.json  # antes/después, con los datos que cambian
python -m scripts.rag_piezas --repuntuar A.json        # recalcula con las anclas actuales, sin volver a PRE
```

## Línea base (base de hoy, 47 preguntas × 2) — `2026-09-28-base.json`

| Pieza | Resultado |
|---|---|
| **Búsqueda** | el dato está en el top-8: **69 %** (top-1 49 %, top-3 66 %). Con catálogo y estado, el modelo lo tiene en el contexto el **83 %** de las veces |
| **Respuesta** | cubre el **81 %** de los datos. Faltan por: búsqueda 17 · contradice 7 · redacción 7 · juez/guardas 3. 4 afirmaciones prohibidas |
| **Juez** | 16 rechazos en 94 respuestas, 14 regeneraciones, 2 "no lo tengo" |
| **Tiempo** | p50 3,2 s · p90 5,4 s · 3,4 llamadas LLM · contexto medio 31.600 caracteres (26.000 del prompt de sistema) |
| **Ruido** | 8 de los 93 datos cambian entre las dos repeticiones; 18 fallan siempre |

**Qué dice (confirmado a mano en los contextos):**

1. **La búsqueda es la mayor causa y tiene patrones claros:**
   - **Los clones "si ya estoy en las islas" se comen el top-8**, sobre todo en inglés: en *Open Water con transporte*,
     *regreso otro día*, *equipaje* y *horario del día 1* los 8 fragmentos son FAQs casi iguales de "...if I'm already
     on the Rosario Islands". Y no solo falta el dato: **el modelo contesta con la variante equivocada** (dice que el
     Open Water no incluye la lancha desde Cartagena y da el horario de recogida en el hotel de las islas), aunque el
     catálogo del prompt diga lo contrario.
   - **Los fragmentos de precios se comen las preguntas de moneda y descuentos:** en *residentes* y *código de
     descuento*, 6-8 de los 8 son "Precios de ...". La política de la cédula de extranjería y la del descuento de
     grupo no aparecen.
   - **Las políticas cortas no llegan:** equipaje, regreso en otra fecha, formulario médico y dirección de la oficina.
     Son 34 documentos frente a 135 FAQs y 176 trozos de servicios.
   - *Refresher: ¿qué completo antes?* se queda por debajo del umbral y acaba en "no lo tengo".
2. **Las contradicciones nacen de la base, no del modelo.** 5 de 7 vienen de la variante equivocada (islas en vez de
   Cartagena) o de que la política no llega. La 6.ª es el 5 % por equipo propio aplicado al snorkel: el catálogo no
   dice a qué aplica. La 7.ª es "vives en Colombia → COP": el catálogo y las FAQs dicen "colombianos/residentes" y la
   regla precisa (nacido en Colombia o cédula de extranjería) no llega.
3. **El juez deja pasar un invento y corta una respuesta buena:**
   - Deja pasar "we are located in the Rosario Islands".
   - En *grupo mixto* corta un precio correcto (una guarda de importe más el juez) y la respuesta acaba en "no lo tengo".
4. **Redacción:** pocas y parciales. En *salida confirmada* dice que "el equipo confirma manualmente" (la
   contradicción del prompt "el pago lo cierra el equipo"). En *grupo mixto* toma "buzo avanzado" por el curso Avanzado.

**Para rag-2 (base curada) y rag-3 (búsqueda con estado):**
- Fuera los clones por origen: una ficha por servicio y origen, y con el origen conocido, solo la suya.
- Precios fuera de la búsqueda: ya están en el catálogo.
- Las políticas escritas para que se encuentren.
- La regla de la moneda, una y precisa.
- Criterio de éxito con este instrumento: el dato en el top-8 ≥ 90 %, contradicciones ≤ 2, cobertura ≥ 90 %, sin
  subir el tiempo.
