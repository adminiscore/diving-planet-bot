# CAL-B: criterios del golden a actualizar a la decisión de moneda del 15-oct

> **APLICADO el 16-oct (decisión de Álvaro):** los 6 criterios de abajo y además
> `familia-mixta-precio-descuento-refresher/precio-mixto-cartagena-o-pregunta-faltantes`. Choque moneda/origen:
> **opción (a)**, se pregunta el origen antes de cotizar (con el texto de `pedia_corregido` del banco). HISTORY 0.31.35.

Decisión de Gadea (15-oct): si el cliente pide precio y no sabemos su nacionalidad → precio en **USD** (no las dos
monedas); colombiano o residente → COP; grupo mixto → USD. Estos 6 criterios se escribieron antes y piden PREGUNTAR
la nacionalidad antes de cotizar: con la decisión, el bot "falla" haciendo lo que se decidió. **No se han tocado en
el golden**: el banco de CAL (`banco-fallos.json`, campo `pedia_corregido`) ya mide con la versión nueva. Si Gadea da
el visto bueno, se cambian en `golden-dialogues.json` (visibles) y `hidden-exam.json` (oculto, ya gastado).

| Caso | Diálogo / criterio | Hoy | Propuesta |
|---|---|---|---|
| cal-11 (visible-real) | `acompanante-madre-desde-cartagena` / `precio-moneda-o-pregunta` | Da el precio del catálogo para acompañante saliendo desde Cartagena en la moneda que corresponda según su nacionalidad, o pregunta nacionalidad y si sale desde Cartagena o ya está en islas antes de cotizar. | Da el precio del catálogo del acompañante saliendo desde Cartagena: en COP si el cliente es colombiano o residente, si no (o si no lo ha dicho) en USD; o pregunta si sale desde Cartagena o ya está en las islas antes de cotizar. No hace falta preguntar la nacionalidad antes de cotizar. |
| cal-19 (oculto-real) | `certificado-profundidad-precio-y-base-hotel` / `precio-cartagena-moneda` | Da el precio del catálogo para 1 buzo certificado (2 inmersiones, 1 día) saliendo desde Cartagena, en la moneda que corresponda a la nacionalidad; si no han dicho su nacionalidad, lo pregunta antes de cotizar. | Da el precio del catálogo para 1 buzo certificado (2 inmersiones, 1 día) saliendo desde Cartagena: en COP si es colombiano o residente; si no ha dicho su nacionalidad, en USD (no hace falta preguntarla antes de cotizar). |
| cal-22 (visible-real) | `paquete-5-buceos-precio-overnight-isla-grande-baru` / `precio-y-moneda-correctos` | Da el precio del catálogo del paquete de 5 buceos desde Cartagena (y, si aplica, desde islas) en la moneda correcta según nacionalidad; o pregunta la nacionalidad/moneda si falta. También confirma si sale desde Cartagena o ya está en las islas antes de cotizar. | Da el precio del catálogo del paquete de 5 buceos desde Cartagena (y, si aplica, desde islas): en COP si es colombiano o residente; si no ha dicho su nacionalidad, en USD (no hace falta preguntarla). También confirma si sale desde Cartagena o ya está en las islas antes de cotizar. |
| cal-28 (oculto-real) | `cotiza-buceo-snorkel-y-pide-link-especial` / `pide-datos-para-cotizar` | Antes de dar precios, pide si salen desde Cartagena o ya están en las islas y la nacionalidad (moneda). Si el cliente da esos datos, entrega el precio del catálogo correspondiente para buceo certificado y snorkeling. | Antes de dar precios, pide si salen desde Cartagena o ya están en las islas (la nacionalidad no hace falta preguntarla: sin ella, el precio va en USD). Con el origen, entrega el precio del catálogo correspondiente para buceo certificado y snorkeling. |
| cal-51 (oculto-real) | `open-water-precio-duracion-hospedaje` / `precio-moneda-origen` | Da el precio del catálogo para el Curso Open Water saliendo desde Cartagena y para el mismo curso si ya está en las islas; la moneda depende de la nacionalidad. Si el cliente no dijo su nacionalidad, el bot debe preguntarla antes de cotizar. | Da el precio del catálogo para el Curso Open Water saliendo desde Cartagena y para el mismo curso si ya está en las islas: en COP si es colombiano o residente; si no ha dicho su nacionalidad, en USD (no hace falta preguntarla antes de cotizar). |
| cal-66 (oculto-real) | `principiante-precio-y-evaluacion-medica` / `pide-datos-antes-de-precio` | Antes de dar un precio, pregunta si sale desde Cartagena o si ya está en las islas y su nacionalidad (moneda). Si ya los tuviera, da el precio del catálogo para el minicurso acorde a ese origen y moneda. | Antes de dar un precio, pregunta si sale desde Cartagena o si ya está en las islas (la nacionalidad no hace falta preguntarla: sin ella, el precio va en USD). Con el origen, da el precio del catálogo para el minicurso. |

## Dos más: choque de la moneda con la regla del origen

En `cal-04` y `cal-05` la cliente es colombiana y pide el precio en COP, pero nunca dice desde dónde sale: la puerta
del origen (opción C del 7-oct, "sin origen no hay precio de un origen concreto") pregunta el origen y el precio no
llega. El criterio pide el precio sin contar con eso. **Decisión de Gadea:** (a) el criterio acepta preguntar el origen
(como ya hace `colombianos-precio-minicurso-dos-inmersiones/precio-minicurso-cop-o-origen`), o (b) sin origen se dan
los dos precios en COP rotulados (Cartagena / ya en las islas).

| Caso | Diálogo / criterio | Propuesta (a) |
|---|---|---|
| cal-04 | `open-water-precio-para-colombianos-corrige-mito` / `sin-precio-especial-colombianos` | Aclara que no hay precio especial; da el valor en COP o, si aún no sabe el origen, lo pregunta antes de cotizar. |
| cal-05 | `curso-open-water-precio-cop-hoteles-y-transporte` / `moneda-cop-colombianos` | Da el precio en COP o, si aún no sabe el origen, lo pregunta antes de cotizar. |
