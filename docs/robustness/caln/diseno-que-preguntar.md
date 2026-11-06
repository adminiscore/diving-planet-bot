# CALN-43: qué preguntar, antes de escribir (diseño, 6-nov)

Encargo de #3664 (decidido por Gadea): «qué preguntar antes de escribir, en vez del filtro de P11». Reglas del bloque: nada de piezas por
caso, el código encoge, tests sin IA, panel solo al final. **Diseño para que lo vea el Claude de Gadea antes de tocar código.** Base:
7e647345.

## Hoy: la pregunta se pone, se corrige y se borra en muchos sitios

```
al empezar el turno: fijar_pregunta_del_escritor → el escritor recibe la pregunta pendiente (pregunta_final) y cierra con ella
   (y su prompt le dice además «cierra con una pregunta útil»: rag_agent.py:95)
después de leer el mensaje: si la pregunta cambió, _con_la_pregunta / _answer_question la sustituyen («variante corrige»)
si no contestó: _sin_dato llama otra vez al escritor y le pega la pendiente
el flujo: _siguiente_pregunta aplaza a la 3.ª seguida (veces_sin_respuesta, preguntas_aplazadas), salvo la actividad
el origen: origen_precio, _CONFIRMA_ORIGEN y ORIGEN_TRAS_* lo preguntan por su cuenta
al final: el compositor busca las copias de la pregunta en el texto, las borra, pone una al final, cuenta, y frena a la 3.ª
   (_sin_las_preguntas, _frase_sin_la_pregunta, _sin_las_frases_de, _con_el_freno_del_origen, _ya_pregunta, P11)
```

Hay tres caminos que escriben la pregunta y cuatro que la arreglan después. Las veces solo se cuentan en algunos (el compositor, la
seguridad de la tarjeta y el hotel primero), y la 3.ª vez se colaba por una excepción del freno (a02, a03 y a06).

## Propuesta: una decisión, un sitio que la pone

```
mensaje → leer (Jev + extractor) → TABLA «qué preguntar» (una vez, con lo ya preguntado) → el escritor contesta lo que preguntó el
cliente, sin preguntas de la reserva → el código pone al final la pregunta decidida, una vez, y la cuenta
```

- **La tabla** (`src/flows/que_preguntar.py`, se aprovecha la de P11): entra lo que falta, en el orden de `next_missing_slot`, y cuántas
  veces salió cada pregunta. Sale la pregunta del turno o nada, y qué hacer en su lugar (P11: las dos salidas, o seguir con lo que hay).
  La aplazada y la 3.ª vez salen de aquí, no del flujo ni del compositor.
- **Un solo sitio la pone y la cuenta:** el final del turno, detrás de lo que escribió el escritor.
- **El escritor no pregunta datos de la reserva** en un turno de la reserva: no recibe `pregunta_final` y su prompt lo dice. Fuera de la
  reserva, sigue igual.
- **El origen** antes de cotizar y su confirmación pasan por la misma tabla: son la pregunta del origen y cuentan como ella.

## Qué se borra (estimación: unas 250 líneas, más los tests de lo borrado)

| Fichero | Se va | Líneas aprox. |
|---|---|---|
| `conversational_core.py` | `fijar_pregunta_del_escritor`, `pregunta_final` en las entradas, el bloque `escrita` de `_answer_question`, el recorte de `_prepend_parallel_answer` | ~45 |
| `slotfill_close.py` | `_con_la_pregunta`, la pregunta que pega `_sin_dato`, el aplazamiento de `_siguiente_pregunta` (y `veces_sin_respuesta`, `preguntas_aplazadas` del estado) | ~60 |
| `compositor.py` | `_sin_las_preguntas`, `_frase_sin_la_pregunta`, `_sin_las_frases_de`, `_con_el_freno_del_origen`, la mayor parte de `_componer` y mi filtro de P11 | ~130 |
| `origen_precio.py` | `_cierra_preguntando_el_origen`, `_answer_already_asks`, `_sin_la_pregunta_final` (lo que queda de ellas pasa a la tabla) | ~25 |
| `rag_agent.py` / prompt | `pregunta_final` y la orden de cerrar con ella | ~10 |

## Por pasos, cada uno con su test de tabla antes de borrar

1. **La tabla y el único sitio que pone la pregunta.** Tests de la tabla: todas las combinaciones de lo que falta, de 0 a 3 veces cada
   pregunta, contestó o no (cientos de casos, sin IA). Tests del turno con el extractor simulado (como `tests/test_conversational_core.py`):
   ninguna conversación lleva la misma pregunta 3 veces, por ningún camino.
2. **El escritor deja de cerrar con la pregunta.** Se quita `pregunta_final`, y con ello `_con_la_pregunta` y el bloque `escrita`. Cambia el
   prompt del escritor: la foto de prompts (`scripts/snapshot_prompts.py --compare`) dice qué cambia.
3. **Fuera el aplazamiento del flujo** (lo hace la tabla).
4. **Fuera los borrados del compositor.** Antes, un test con los textos reales de los paneles en los que el escritor metió la pregunta.
5. **El origen, por la tabla.**

Señal de que va bien: tras cada paso, menos líneas en `src` y más tests sin IA. Lo único que depende de la IA es que el escritor obedezca
«no preguntes datos de la reserva». Eso se mira al final del bloque, con el panel.

## Lo que hay que decidir (Claude de Gadea; si es de negocio, Gadea)

1. **Turnos de la reserva:** ¿el escritor no hace ninguna pregunta de la reserva, o puede hacer otras que no sean de la reserva («¿quieres
   que te cuente más del curso?»)? Hoy, si el escritor pregunta otra cosa, la de la reserva espera al turno siguiente (paso 2 de CALN-6).
   Propongo que **la decidida vaya siempre** y que el escritor no pregunte en esos turnos: es más simple y sin excepciones.
2. **Lo que se pierde de LAT-9 paso 2:** la pregunta, escrita por el escritor, sonaba más natural que la nuestra fija. Volver a la fija,
   ¿es aceptable? No añade llamadas ni tiempo: el escritor sigue corriendo a la vez que la lectura.
3. **`_sin_dato`** (el cliente no contesta: «gracias», «voy solo»): ¿se queda la llamada al escritor para contestar a lo que dijo (sin
   pegar la pregunta), o va solo la tabla?
