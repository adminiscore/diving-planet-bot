# CALN-30 · Quitar la segunda lectura de la nacionalidad (CALN-10b) con una señal de Jev — estudio (5-nov, Gonzalo)

**Recomendación (6-nov, tras la medida grande): quitar 10b.** Sin ella y con la señal de residente, 0 de 540 nacionalidades
equivocadas sobre la 0.59 (por debajo del 0,55 %, frente al 2,5 % que justificó 10b), y 0,8 llamadas menos por turno. Quitarla borra
código (la 2.ª lectura y su comparación). Decide Gadea.

(Primera medida, 5-nov: quitar 10b es razonable, pero 0 de 108 no descartaba una tasa del 2,5 %.)

## Qué se midió

Rama `feature/caln30-gonzalo` sobre la 0.54.0 (78c581a7), mismo código y misma base en los dos lados.

- **Señal `es_residente_colombia`:** una fila de `_DEL_TURNO`, que `con_la_cedula` usa como `tiene_cedula_extranjeria`. El grupo mixto manda sobre ella.
- **A:** con 10b. **B:** sin 10b (`CALN30_SIN_10B=1`, interruptor solo para medir; no se integra).

## Sonda de Jev

`scripts/sonda_jev_residente.py`, 24 frases × 3: **72/72.** Quien se dice residente, 0,87-0,96. Los demás, como mucho 0,19: «vivo en Colombia», «I live in Bogotá», residente de otro país, «¿los residentes pagan en pesos?», «mi hermana es residente», «no soy residente».

## Con y sin 10b

| | A, con 10b | B, sin 10b |
|---|---:|---:|
| Nacionalidad equivocada (`banco-nacionalidad`, 18 casos × 6) | 0 de 108 | 0 de 108 |
| Dicha y bien leída | 78 de 78 | 78 de 78 |
| No la dice: sin dato / False | 20 / 10 | 18 / 12 |
| Llamadas por turno | 4,11 | 3,19 |
| Llamadas al extractor por turno | 1,82 | 1,00 |
| Latencia p50 / p90 | 3,67 / 4,40 s | 3,41 / 4,18 s |
| `banco-moneda` ×3 | 31/33 | 32/33 |
| Moneda: llamadas por turno | 4,04 | 3,44 |
| Moneda: latencia p50 / p90 | 3,35 / 5,69 s | 3,20 / 4,95 s |

Suite: 3393 con el interruptor apagado; encendido fallan 5, los tests del propio mecanismo de 10b (`test_caln10b_nacionalidad.py`).

El único caso que cambia: «I live in Bogotá but I'm American» sale sin dato 2 de 6 con 10b y False 6 de 6 sin ella; es el valor correcto. En 108 turnos, 10b deshizo una vez una lectura distinta.
m1 («nací en Colombia y vivo en Madrid») falla en los dos lados, A 1/3 y B 2/3: no pide la nacionalidad o la cédula con esas palabras.

## Límites

- **El tamaño:** 0 de 108 es compatible con una tasa de hasta un 2,7 % (95 %), y 10b se puso por un 2,5 % de equivocadas (`estudio-caln10-lecturas.md`). Esta medida no puede distinguirlas. Para 1 de 200 harían falta unos 600 turnos por lado.
- **Primer turno:** el banco de nacionalidad mide solo un primer mensaje. La moneda sí mira varios turnos.
- **Latencia:** dato secundario, con una tanda de Gadea a la vez. Intercalado en nacionalidad; moneda en serie, A y luego B.
- **El banco lo escribí yo**, con frases nuestras, sin el golden.

## Segunda medida, grande, sobre la 0.59 (5-6 nov)

Rama `feature/caln30b-gonzalo` sobre 216c1e6 (0.59) con la señal de residente; A con 10b y B sin ella, `--codigo-local`, tandas de 54
intercaladas (A B / B A). Se pidieron 11 por lado; se cortó la red en la 20.ª, así que quedan 9 de A y 10 de B. Sin juez; cuenta
`is_colombian` del estado tras el primer turno contra el banco, sumando todas las tandas (no por `rep`).

| | A, con 10b | B, sin 10b |
|---|---:|---:|
| Turnos | 486 | 540 |
| Nacionalidad equivocada | **0** | **0** |
| Dicha y bien leída | 351 de 351 | 390 de 390 |
| No la dice: sin dato / False | 81 / 54 | 91 / 59 |
| Llamadas por turno | 3,98 | 3,15 |
| Llamadas al extractor por turno | 1,83 | 1,00 |
| Latencia p50 / p90 (secundaria: medían Álvaro y Gadea a la vez) | 3,63 / 5,08 s | 3,36 / 4,21 s |
| `llm_errores` / Jev cortado | 0 / 0 | 0 / 0 |
| Respaldos | rag 18, notas 1, extractor 1 | rag 12, notas 1 |

**0 de 540 sin 10b** deja la tasa de equivocadas por debajo del 0,55 % (95 %, regla del 3); sumando las 108 de la 0.54, 0 de 648,
por debajo del 0,46 %. 10b se puso por un 2,5 %: con la señal de residente, ese riesgo ya no está en este banco. Límites que siguen:
solo primer turno, y el banco es de frases nuestras.

## Qué falta para decidir

Un banco de unos 600 turnos por lado, con las frases dudosas, si se quiere afirmar que no hay más equivocadas; son unos 60 minutos de PRE y sin juez. O decidir con este dato, aceptando ese margen: una moneda equivocada es grave, pero el coste de 10b también se paga en todos esos turnos.
