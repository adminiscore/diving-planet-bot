# El nocturno como dato del extractor (sparring s03h, 3-nov): APARCADO

Grave 1 de la tanda s03h (`docs/robustness/g3/hallazgos.md`, CALN-S03H): «I'd love to do a night dive» y luego «yes, the
night dive package» dejaban la tarjeta de 2 inmersiones de día con su enlace. El plan del buzo certificado solo se elige
por la cifra de inmersiones (R1, `dive_counts_in`) o de días; «el nocturno» no lleva cifra.

Arreglo probado (commit ef2a94f1, revertido en b526b387): un campo `plan_nocturno` en el extractor y el paquete del
catálogo (`dom.paquete_con_nocturna(días)`: 1 día → 3 inmersiones, 2 → 5, 3 → 7, 4 → 9, de `includes_night_dive`).
Con `charla_rama` (noct2) la tarjeta era la del paquete de 3, al asesor.

**Decisión de Gadea (3-nov, 18:15): aparcado hasta después de CALN.** Queda como grave conocido; el bot ya explica que el
plan de 2 no lleva nocturna y ofrece cambiar.

## Por qué: cada redacción mueve otra lectura del extractor

Método de CALN-8 (4), con `scripts/sonda_plan_nocturno.py` (A = sin el campo, B = con él, intercalados): frases propias
×10, banco ex0 de diseño ×3, los casos que cambian ×10 y los dudosos ×20. Las frases salieron bien en las 6 versiones
(60/60; «no la quiere» da false, que no hace nada).

| Versión | Qué cambia | Los que cambian ×10, A → B (acierto / equivocado / perdido / inventado) | Lo que se rompe (×20) |
|---|---|---|---|
| A1 | el campo en todas las llamadas | 131/7/72/16 → 136/20/54/19 | «what if I stay one day longer in rosario» → location island 3-4/10 (A 0) |
| A2 | solo en la apertura o con el buceo certificado en juego | 122/7/81/21 → 123/23/64/29 | familia mixta «3 of us will dive and 3 will snorkel» → {snorkel 3, undecided 3} 10/10 (A 1) |
| A3 | la regla sin «elige el plan» | 95/0/75/18 → 113/9/48/14 | la familia mixta 5/20 (A 0) |
| A4 | + «el nocturno es buceo certificado: no cambia la actividad ni el reparto» | 78/6/26/27 → 86/9/15/16 | «I would love to dive here… fun dives?» pierde la actividad 9/20 (A 0) |
| A5 | ejemplos sin «I'd love to» | 109/5/36/11 → 118/14/18/14 | «quiero bucear certificado» → is_certified true 10/10 (decisión: no se deduce) |
| A6 | sin «es buceo certificado» | 106/0/54/12 → 111/11/38/0 | «¿cuál es el costo para colombianos?» pierde is_colombian 19/20 (A 0) |

En todas, `acompanante-goteo-t4` («él quiere hacer snorkel») falla en los dos lados: A lo pierde, B escribe
{snorkel 1, undecided 1}.

Lo que se ve: el prompt del extractor va al límite (como el esquema grande de ex9b) y cualquier campo nuevo con su regla
mueve lecturas que no tienen que ver. Seguir retocando la redacción hasta que el banco salga limpio sería ajustarse al
banco.

## Para retomarlo

- Otro sitio: una señal de Jev («pide el nocturno»), medida con su banco; o una lectura que no comparta prompt.
- La versión A6 de la regla, por si sirve de punto de partida:
  «plan_nocturno: true si pide hacer una inmersión nocturna («¿puedo hacer la nocturna?», «sí, el del nocturno»). null
  si solo pregunta qué es o no la quiere. El nocturno no cambia la actividad ni el reparto: quien va a bucear sin decir
  cuántas inmersiones ya ha elegido.» Solo en la apertura o con el buceo certificado en juego (`campos_paso6(history,
  sabido)`).
- La sonda necesita el campo en el código: recuperar ef2a94f1 (y `campos_paso6` con `sabido`) antes de correrla.
