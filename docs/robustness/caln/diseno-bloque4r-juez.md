# 4R: los textos del juez (C6), para el próximo cambio de referencia

Propuesta para el Claude de Gadea (#3744 c). Entran al cerrar el bloque 4 entero, con los dos lados juzgados con la huella nueva.
Solo cambia el `texto`, que es lo que lee el juez (`judge_golden_set.py:127-131`). Las `instruccion_*` son del bot y van en el código
del 4R: no cambian la huella.

## `origen-y-precio` (añadir al final)

> Con el enlace de reserva, lo mismo: sin saber el origen, el bot NO da ningún enlace (tampoco el de Cartagena). Da los precios de cada
> salida con su rótulo y pregunta el origen. Si el cliente quiere reservar y sigue sin decirlo, el bot lo pide una vez más, con el
> motivo («para darte el enlace necesito saber desde dónde sales: ¿desde Cartagena o ya estás en las islas?»). Si tampoco lo dice, pasa
> con un asesor (Gadea, 10-nov).

## `sin-tercera-pregunta` (sustituir)

> Decisión de Gadea: tras 2 preguntas sin respuesta se sigue con lo que hay (el precio por persona, o los precios de las dos salidas,
> sin enlace). Nunca una 3.ª vez, con una excepción (10-nov): en el momento de reservar, sin saber el origen, el bot lo pide una vez más
> con su motivo y, si no lo dice, pasa con un asesor.

## `pago-y-reserva` (añadir al final)

> Si la nacionalidad sigue sin saberse tras 2 preguntas y el cliente quiere reservar, el bot da el enlace y añade «si eres de
> nacionalidad colombiana o tienes cédula de extranjería, dímelo y te paso con un asesor para pagar en pesos». Si dice que no es
> colombiano, el enlace sin más (Gadea, 10-nov).

## `grupo-por-el-asesor` (añadir al final)

> Si aún no ha pedido reservar, el bot lo dice una vez («este plan se reserva con un asesor, por…»), sin preguntarle si quiere que le
> pase, y le pasa cuando quiera reservar. Vale igual para el equipo propio y la recogida por confirmar (Gadea, 10-nov).

## `por-otros` (cambiar «su enlace»)

> …recibe el mismo trato que un cliente: el precio por persona del catálogo y el enlace de su plan, con las mismas reglas que
> cualquiera (el origen sabido, el grupo de 5 o más con un asesor…). No hay precio de agencia ni comisión.

## Nueva: `horario-por-el-asesor` (10-nov)

> Decisión de Gadea: los horarios de salida y recogida son fijos. Si al reservar el cliente pide otro horario, el bot se lo dice y le
> pasa directamente con un asesor.

## Pendientes que ya tenías (#3744 c)

- `escalation_rules.json:16` (agencias al pase).
- El texto de `cambio-de-fecha` (17-sep).
- El caso del golden `agencia-solicita-tarifas-escalar`.
- El criterio del enlace especial.
- `complex_logistics` («coordinación con agencias»), que choca con `por-otros`.
