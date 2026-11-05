# CALN-30 · Quitar la segunda lectura de la nacionalidad (CALN-10b) con una señal de Jev — estudio (5-nov, Gonzalo)

**Recomendación: quitar 10b es razonable, pero el dato no basta para decir que es igual de seguro.** Con la señal de residente, en esta medida no sale ninguna
nacionalidad equivocada y baja el coste. Pero 0 de 108 no descarta una tasa del 2,5 %, la que justificó poner 10b. Decide Gadea.

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

## Qué falta para decidir

Un banco de unos 600 turnos por lado, con las frases dudosas, si se quiere afirmar que no hay más equivocadas; son unos 60 minutos de PRE y sin juez. O decidir con este dato, aceptando ese margen: una moneda equivocada es grave, pero el coste de 10b también se paga en todos esos turnos.
