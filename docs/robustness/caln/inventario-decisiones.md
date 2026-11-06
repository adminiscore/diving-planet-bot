# CALN-43: inventario de dónde se decide cada cosa, y los 16 graves por causa (6-nov)

Lo pidió el Claude de Gadea en #3628, mientras Gadea decidía sobre la propuesta #3627 (Coral #3629). Solo lectura, sin tocar
código. Gadea aprobó CALN-43 el 6-nov, y sus respuestas a P1-P11 están en `tablas-decisiones.md`, que manda sobre los §3 y §4 de
aquí.
Base: PRE 0.59 (216c1e6), panel 059c juzgado con Opus 5.5 (15 graves) + tanda s05f (6952). Total: 16 graves.

## 1. Los 16 graves: ¿decisión o lectura?

- **Decisión**: el bot tenía los datos bien leídos (se ve en el estado del turno) y eligió mal el plan, el enlace o la pregunta.
- **Lectura**: el que lee al cliente (extractor, Jev o una regla de texto) apuntó mal un dato, y lo demás vino detrás.

| Charla | Familia | Qué pasó | Estado del turno | Causa |
|---|---|---|---|---|
| ciego-b08 | plan | 4 buzos con hotel en la isla, «dos mañanas» → paquete de 5 con nocturna | bien: isla, hotel, 2 días | **decisión**: `_DAYS_TO_DIVES` 2 días → 5 |
| ciego-b01 | plan | pareja, él lleva más de 2 años sin bucear (necesita refresher), 2 días desde Cartagena → paquete de 5 para los dos | bien, pero el estado no guarda «solo él necesita refresher» | **decisión** (falta ese dato en la tabla) |
| ciego-a08 | plan | refresher + salida de 2 desde Cartagena → solo el enlace del refresher y el precio del paquete de 4 que ya rechazó | bien (Cartagena, 1 día) | **decisión** |
| ciego-b10 | plan | ella hace el curso referido (2 días) y su novio bucea los 2 días → «salida de 1 día» y luego «¿1 día o paquete de 5?» | t5 todo bien | **decisión** (lo eligió el escritor; CALN-24 solo pregunta cuál) |
| visto-6929 | plan | 6 certificados, «dos salidas de un día, sin dormir en las islas» → paquete de 5 | `Detected cert dive count: 5` sale de «el paquete de 5 **no** es lo que pedí» | **lectura** (regla de texto, `rutas/booking.py:471`) |
| ciego-a04 | plan | buzo + pareja que hará snorkel o irá de acompañante → «reserva snorkel + acompañante», sin la salida del buzo | reparto `{snorkel: 1, companion: 1}`: falta el buzo | **lectura** (reparto) |
| ciego-a07 | plan | certificado + pareja embarazada, «hotel del centro» → solo el enlace del snorkel, y vuelve a preguntar el origen | Jev: «¿se puede mover una reserva?» = cambio de reserva hecha → asesor de post-venta; los turnos siguientes no pasan por la extracción | **lectura** |
| ciego-a02 | pregunta ×3 | «So, would you leave from Cartagena?» tres veces | la confirmación del origen (`_CONFIRMA_ORIGEN`) no es un hueco aplazable | **decisión** (sin memoria) |
| ciego-a03 | pregunta ×3 | «¿Te animas con el minicurso, el snorkel o el Open Water?» tres veces | la actividad no está en `_SLOTS_APLAZABLES` | **decisión** (sin memoria) |
| ciego-a06 | pregunta ×3 | «How many people: just you, or more?» tres veces a quien habla en singular | `group_size` vacío | **mixto**: lectura (singular) + la regla de aplazar no lo frenó |
| visto-6940 | pase | «Yes, please. Thank you» a la oferta del asesor → no pasa | la oferta la escribió el escritor; el código reconoce solo las suyas (`_OFERTA_DEL_ASESOR`) | **mixto**: el código no sabe qué ofreció + aceptación con más texto |
| 6952 (s05f) | pase | «Sí, por favor. La casa se llama…» → no pasa, y en t4 da el enlace | el «sí» no va solo | **mixto** (arreglado en ramas: ACEPTA_EL_PASE) |
| ciego-b03 | descuento | grupo de 6 → dos enlaces para pagar online sin pedir antes el descuento de grupo | bien (6, mixto → USD) | **decisión**: `como_reserva` no mira el descuento de grupo |
| ciego-b06 | moneda | marido y niños colombianos, ella con cédula de extranjería → `is_colombian=False`, enlaces web | lectura de la nacionalidad mal; el reparto se queda en 2 de 4 (`{certified_diving: 1, minicourse: 1}`: faltan el de 13 en el minicurso y el de 9) | **lectura** |
| visto-6942 | inventa | regla de vuelo falsa | — | lenguaje |
| ciego-a10 | inventa | «el precio no es el de la web, lo fija un asesor» | — | lenguaje |

**Recuento:** decisión 7, lectura 4, mixto 3, lenguaje 2.

Solo en plan o enlace: **4 de decisión y 3 de lectura**. Esto confirma el matiz de Gadea: la tabla ataca directamente 7 de 16, y en
parte otros 3. Los 4 de lectura necesitan su propio banco de frases. Ese banco también se prueba sin juez: frase → campos
esperados, con una sola llamada por frase (ya hay uno, `docs/robustness/caln/banco-lectura.json`).

## 2. Dónde se decide hoy cada cosa (PRE 0.59)

| Decisión | Dónde (ficheros) | Cuántos sitios | ¿Probada sin IA? |
|---|---|---|---|
| **Plan del buzo** | `nucleo/plan.py` (`_resolve_cert_plan`, `_recommended_plan_intro`); `conversational_core.py:84-88` (`_DAYS_TO_DIVES`, `_DIVES_TO_BASE_PLAN`); `nucleo/extractor.py` (`paquete_nocturno_pedido` CALN-20, `_poner_duracion`, `_pide_salidas_sueltas`); `rutas/booking.py:471-486` (la regla de texto → `cert_dives`/`cert_days`); `nucleo/routing.py:86-108` (el plan que el bot acaba de describir); `extractor_turno.plan_que_propone_el_bot`; `conversational_core._effective_activity`; `cart_render.service_for_location`; `nucleo/reparto.py`; `flows/eligibility.py`; **y el escritor**, que nombra planes y enlaces por su cuenta; `slotfill_close._si_chocan_los_enlaces` (CALN-24) arbitra cuando no coinciden | ~12 sitios en 9 ficheros + la IA. `detected_cert_dives` se escribe en 4 sitios, `detected_service_id` en 5, `detected_duration` en 3 | a trozos; nadie prueba el plan final por persona |
| **Cómo reserva** (enlace, asesor, hotel primero) | `flows/como_reserva.py`: una función, 4 salidas. La usan el compositor, los hechos, el cierre, `origen_precio` y `next_missing_slot` | 1 dueño ✓ | sí, 30 tests |
| **Qué preguntar** | `conversational_core.next_missing_slot` (ya es una tabla de huecos en orden); `slotfill_close._siguiente_pregunta` (aplaza a la 3.ª, pero no la actividad, ni la confirmación del origen, ni las preguntas del escritor); `_CONFIRMA_ORIGEN`; `origen_precio` («precio sin origen → se pregunta»); el compositor (quita o deja preguntas, cuenta `preguntas_hechas`); el escritor añade las suyas | `core_pending_slot` se escribe en 7 sitios de 4 ficheros | el orden sí; «nunca 3 veces» no |
| **Pase al asesor** | `supervisor.py` (`pase_pedido_o_aceptado`, `_BARE_AFFIRMATION_RE`); `slotfill_close._quiere_reservar_o_pagar` + `_OFERTA_DEL_ASESOR` (textos exactos); `nucleo/setup.py`; Jev (`needs_staff`, `wants_human`, `booking_change_topic`); `rutas/{booking,changes,deflection,info,safety}.py` | `pending_escalation_reason` se escribe en 14 sitios de 9 ficheros | a trozos |
| **Moneda** | `flows/moneda.py`; `nucleo/extractor` (`con_la_cedula`, `mezclado_del_mensaje`); Jev (`grupo_mixto`, `tiene_cedula_extranjeria`); `como_reserva` (ASESOR); avisos (`extranjero-paga-en-usd`); el prompt (G3-07a) | `is_colombian` se escribe en 6 sitios de 4 ficheros | la regla sí; la lectura no |
| **Descuento** | `flows/cotizar.py` (la pieza de precios, CALN-3), `flows/hechos.py`, `redactor_hechos`, `catalog`, `discounts.json` y avisos | 6 ficheros | el importe sí; «pedirlo antes de pagar» no está en `como_reserva` |

`como_reserva` es el ejemplo que hay que copiar: un solo dueño, salidas con nombre y tests de casos. El plan es lo contrario,
porque lo deciden doce sitios y además el escritor.

## 3. Borrador de la tabla del plan (buzo certificado, por persona)

Lo que dice el catálogo (`services.json`), y que condiciona la tabla:
- Todos los paquetes de varios días **con enlace** llevan nocturna (5, 7 y 9; desde las islas también el 5 y el 7).
- Los de **4 diurnas** (Cartagena e islas) y el **4 mixto** de las islas **no tienen enlace**: los reserva un asesor.
- El de 3 (2 diurnas + 1 nocturna, 1 día) tiene enlace desde las islas y no desde Cartagena.
- No hay paquete de 3 o 4 días sin nocturna.

| # | Origen | Días de buceo | Nocturna | Duerme en las islas | Hoy | Propuesta | Pregunta |
|---|---|---|---|---|---|---|---|
| 1 | Cartagena | 1 | no o no lo dice | — | salida de 2 (enlace) | igual | — |
| 2 | Cartagena | 1 | sí | sí | paquete de 3 (sin enlace → asesor) | igual | — |
| 3 | Cartagena | 2 | sí | sí | paquete de 5 (enlace) | igual | — |
| 4 | Cartagena | 2 | no lo dice | sí o no lo dice | **paquete de 5, con nocturna** | ? | **P1** |
| 5 | Cartagena | 2 | no («solo mañanas») | sí | paquete de 5 | 4 diurnas (asesor) | **P2** |
| 6 | Cartagena | 2 | — | **no** (duerme en Cartagena) | paquete de 5 si Jev no marca «salidas sueltas» (6929) | 2 salidas de 1 día (enlace) | **P3** |
| 7 | Islas, hotel conocido | 1 | no o no lo dice | — | salida de 2 de las islas (enlace) | igual | — |
| 8 | Islas, hotel conocido | 2 | no lo dice o no | — | paquete de 5 de las islas, con nocturna (b08) | ? | **P1, P4** |
| 9 | cualquiera | 3 o 4 | no | — | 7 o 9, los dos con nocturna | ? | **P5** |
| 10 | cualquiera | N ≥ 2, **uno necesita refresher** | — | — | el paquete para todos (b01) | ese: refresher el día 1 + salidas los demás días; los demás: ? | **P6** |
| 11 | Cartagena | 1 + refresher | — | — | solo el enlace del refresher (a08) | refresher, y salida de 2 al día siguiente si se queda; los dos enlaces | **P7** |
| 12 | buzo que acompaña a un curso de 2 días (OW o referido) | 2 | — | sí (el curso duerme allí) | salida de 1 día (b10) | paquete de 2 días | **P8** |
| 13 | — | — | — | — | «me certifiqué hace 10 años» → más de 2 años sin bucear (a08) | no se deduce: se pregunta la última inmersión | — |

**Cómo reserva**: filas que faltan en `como_reserva`.
- Grupo de 5 o más: el descuento de grupo hay que pedirlo antes de pagar (b03). ¿Pasa por el asesor antes del enlace? → **P9**
- Plan sin enlace dentro de un grupo con enlace (acompañante, Bubble Makers, 4 diurnas…): ¿asesor para todo el grupo o solo para esa parte? Hoy se reserva por dos caminos (6951) → **P10**

**Qué preguntar**: una regla para todas las preguntas, no solo para los huecos aplazables. Se pregunta como mucho 2 veces.
Después se hace algo distinto según la pregunta → **P11**

## 4. Preguntas para Gadea (contestadas el 6-nov: ver `tablas-decisiones.md`)

- **P1.** Cliente certificado, 2 días, no dice nada de la nocturna: ¿paquete de 5 (con nocturna y con enlace), paquete de 4 diurnas
  (sin enlace, asesor) o preguntarle «¿quieres incluir una nocturna?»? Hoy le damos el de 5 sin decirle que lleva nocturna.
- **P2.** Si dice «solo de día» o «dos mañanas»: ¿4 diurnas por el asesor, o 2 salidas de 1 día con enlace?
- **P3.** Dos días durmiendo en Cartagena: ¿2 salidas de 1 día, en una reserva con dos fechas o en dos reservas?
- **P4.** Desde las islas, 2 días sin nocturna: ¿4 diurnas (asesor) o 2 salidas de 1 día (enlace)? ¿Cuál primero?
- **P5.** 3 o 4 días sin nocturna: no hay paquete. ¿Salidas sueltas, o el paquete por el asesor quitando la nocturna?
- **P6.** Si en un viaje de 2 días uno necesita refresher: ¿refresher el día 1 y salida de 1 día el día 2? ¿Y su pareja, que ya
  puede bucear: paquete de 2 días o salidas sueltas para ir juntos el día 2?
- **P7.** Si solo tiene 1 día y necesita refresher: ¿solo el refresher, y se le dice que la salida va otro día?
- **P8.** El buzo que acompaña a quien hace un curso de 2 días: ¿paquete de 4 diurnas, de 5, o lo que él diga? ¿Van en la misma lancha?
- **P9.** Grupo de 5 o más: ¿asesor antes del enlace para que no pierdan el descuento, o enlace con el aviso de pedirlo antes?
- **P10.** Grupo con una parte sin enlace: ¿todo el grupo por el asesor?
- **P11.** Tras 2 preguntas sin respuesta: actividad → ¿se dan las opciones sin preguntar? origen → ¿se dan los dos precios?
  número de personas → ¿se asume 1 si habla en singular?

## 5. Cómo seguiría (Gadea dijo que sí el 6-nov)

1. Gadea contesta P1-P11. Hecho: `tablas-decisiones.md`.
2. La tabla del plan, en una función, al estilo de `como_reserva`. Gadea: `src/flows/plan_de_buceo.py` (26dfa2b3).
   Casos de prueba sin IA, que se pasan en segundos.
3. La función reemplaza poco a poco los ~12 sitios que deciden el plan hoy. Cada sitio que se quita, con sus tests verdes.
4. El escritor recibe el plan decidido y no puede dar otro (hoy CALN-24 arbitra cuando choca: eso desaparece).
5. Lo mismo después para «qué preguntar», con memoria de lo ya preguntado (P11, Álvaro).
6. Las 4 lecturas: al banco de frases (frase → campos), sin juez.
7. El panel, solo al final, para confirmar.
