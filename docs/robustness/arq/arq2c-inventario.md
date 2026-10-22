# arq-2c · Retirar las capas que sobran con el redactor de hechos

22-oct, Gonzalo con Claude. Base `pre_gadea` 5aefc27 (arq-1d, 1e, 1f, 1g, 2b y 3, con los flags apagados).

## 1. ord-9 retirado (`listas_del_dato`)

ord-9 (21-oct) hacía que, si Jev decía que el cliente preguntaba qué incluye un plan concreto, el RAG no enumerara
(`sin_lista`) y el código añadiera la lista de la ficha. Lo sustituye el redactor de hechos (`hechos_por_codigo`), que
da la lista de la ficha. Se ha quitado:

- `conversational_core`:
  - las funciones `_servicio_concreto`, `_pide_la_lista`, `_sin_lista_si_hace_falta` y `_con_lista_del_dato`;
  - sus tres llamadas;
  - `sin_lista` de `_entradas_rag`;
  - la parte «lista» de la huella de rag-5 (`_huella_rag`, `_PARTES_HUELLA`).
- `rag_agent.rag_answer`: el parámetro `sin_lista` y su texto.
- `prompts/info`: `RAG_SIN_LISTA_ES/EN`.
- `orchestration/graph`: `conv._jev_pide_incluye`.
- `config`: el flag.
- `jev_router`: la pregunta `PIDE_QUE_INCLUYE` **se queda**, porque la usa el redactor, pero solo con `hechos_por_codigo`.
- `componentes.json`: la ficha y la entrada en el RAG.
- `scripts/snapshot_prompts.py`: las dos piezas.
- `tests/test_ord9_listas_del_dato.py`: el fichero entero.

**Equivalencia:** el flag estaba apagado en config y en el compose.

- Foto de prompts antes y después: 0 cambiados, solo faltan `info/rag.sin_lista.{es,en}`.
- Suite completa en verde.
- Banco fijo ×3 (`2026-10-22-arq2c-{A,H}.jsonl`, 14:10-14:30, base 5aefc27), dentro del ruido de las medidas de hoy:
  - sin hechos, 103/120 (arq2a-A de las 12:20: 105);
  - con hechos, 113/120, 1 invención (arq2a-HA: 115).

  Los fallos son los conocidos y ninguno pasa por ord-9:
  - p6 (Medellín) lo arregla `el_verbo_no_la_ciudad`, apagado en esta medida;
  - c3 (la edad «desde los 10») lo arregla 817f2d5, que no estaba en la base;
  - c4 da una invención sobre documentos en 1 de 3.

  Medianas: 4,13 s sin hechos y 2,96 s con hechos.
- Al quitar `_con_lista_del_dato`, `_puerta_del_origen` devolvía None cuando la puerta no actuaba: el `or` de ord-9 era
  el que devolvía la respuesta. La suite lo cazó (30 tests) y se arregló con `… or answer`. El primer banco, corrido con
  el fallo (18/120), se tiró.

## 2. Inventario: ¿qué más sobra con el redactor?

**En el camino del redactor no queda ninguna capa ejecutándose.** Cuando contesta el redactor, `_rag_answer` y
`_adoptar_o_rehacer` devuelven su respuesta **antes** de `_puerta_del_origen`. Los avisos al final (`avisos_al_final`,
`aviso_al_final`) y el revisor de completitud viven dentro de `rag_agent.rag_answer`, que no se llama. La pregunta del
origen la pone el propio redactor (`ORIGEN_TRAS_LAS_VARIANTES_*` / `ORIGEN_TRAS_LOS_ENLACES_*`) cuando el bloque trae
`pregunta_pendiente == "origen"`.

**En el camino del RAG siguen haciendo falta** (Gadea, #1275). Ese camino sigue contestando:

- los mensajes mezclados (con `hechos_al_rag` recibe los hechos de la parte cubierta);
- cuando el redactor dice FALTA;
- lo que no es de la tabla;
- todo, con `hechos_por_codigo` apagado.

Ahí se quedan:

| Capa | Por qué se queda |
|---|---|
| Puerta del origen + dos variantes (ord-7, `origen_dos_variantes`) | el RAG puede cotizar o enlazar sin saber el origen en un mensaje mezclado |
| Avisos al final (`avisos_al_final`) | el RAG puede omitir un aviso; el redactor no los necesita porque los hechos ya los traen |
| `RAG_VARIOS_PLANES_*` | el RAG puede elegir un plan cuando encajan varios |
| Tarjeta de edades en cifra (`tarjeta_edades_en_cifra`) | flujo de la reserva, fuera del redactor |

**Qué se podría retirar más adelante** (decisión de Gadea, después del G10 de arq-4 y de promocionar arq-1d): medir con
`hechos_por_codigo` y `hechos_al_rag` encendidos cuántas veces el RAG sigue cotizando sin origen o dejándose un aviso. En
el banco fijo con hechos (HB, 22-oct), el RAG contestó 37 de 141 turnos. Si con `hechos_al_rag` esas capas no actúan
nunca en el banco y en una ronda core, se retiran como ord-9.
