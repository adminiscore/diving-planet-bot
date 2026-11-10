# Bloque 4P: el pase y la posventa fuera de la reserva (diseño, 10-nov; v2 tras la revisión)

**Ficha:**
- **Rama:** 4P, en `feature/bloque4p-gadea`, sobre `bloque1-gadea` b16e3612.
- **Mecanismo:** el pase fuera de la reserva tiene un solo dueño, da la política cuando toca y no se repite.
- **Familias:** la agencia, quien ya reservó (cambiar, cancelar o cambiar el número) y el pase que vuelve.
- **Banco:** sin IA, `tests/test_bloque4p.py`. **Contador:** `[CORE][4P]`.

**v2 (10-nov):** un agente revisó la v1 contra el código, sin mi conclusión. Comprobé cada punto que cambiaba algo. Lo que cambia:
- un **arreglo de la vara** (C0);
- la agencia, con una **instrucción** en su decisión en vez de un FAQ;
- **C3**, en otro sitio;
- el saldo y la meta, más realistas.

El 4R, el momento de reservar, es de Álvaro (#3721). No se tocan `compositor.py`, `slotfill_close.py`, `como_reserva.py`,
`brand_tone.json` ni sus líneas de enlaces.

## Lo que hay que cumplir (decisiones de Gadea, ya en el juez)

| Situación | Qué hace el bot | Decisión |
|---|---|---|
| Una agencia, un instructor de otro centro o quien paga por otros | Lo mismo que con un cliente: precio por persona del catálogo y su enlace; no hay precio de agencia ni comisión | `por-otros` (9-nov) |
| Ya reservó y pregunta lo que está en la base | Lo contesta | `ya-reservado` (9-nov) |
| Ya reservó y quiere cambiar la fecha, cancelar o cambiar el número de personas | Da la política y pasa con un asesor, directamente | `ya-reservado` (21-oct y 9-nov) |
| Ya reservó y pregunta algo que la base no tiene | Pasa con una persona | `ya-reservado` (9-nov) |
| Algo médico de verdad | Pasa al equipo sin perder lo demás que preguntaba | `salud` (30-oct) |

## Cómo está hoy (comprobado en el código)

**M0. La vara arrastra el pase y producción no.**
- En producción, `chatwoot.py:288-290` borra `pending_escalation_reason` después de cada pase.
- `reproducir_juez_pre`, de donde sale el panel, y `charla_rama` no lo borran (`ronda_local_pre._entrega` sí).
- Resultado: en el panel del bloque 1, 51 de 384 turnos (un 13 %) llevan el pase del turno anterior; en 18 vuelve a salir el texto
  fijo del pase. En producción, gen-13 sí contestaría lo demás.
- Parte de M3 en el panel es, por tanto, del arnés. Por ejemplo, el vuelo sin contestar de visto-6937.

**M1. La agencia va al pase por definición.**
- La pregunta `needs_staff` incluye «a travel agency, tour operator or company writing as a business (…rates or group deals)»
  (`jev_router.py:295-303`). `_FUERA_DEL_SISTEMA` añade «for several customers, for an agency» y «special rates» (`:1056-1061`).
- La cascada llama a `_needs_staff_handoff` (`supervisor.py:414`), y el nodo de escalado delega en ella (`escalation_agent.py:226`).
- Nada de lo que lee el bot dice que no hay precio de agencia: `por-otros` no tiene `instruccion_es/en`.

**M2. El cambio de una reserva hecha tiene dos dueños.**
- `needs_staff` es TRUE para cambiar o cancelar una reserva hecha (`_YA_RESERVO_NO_BASTA`, `jev_router.py:1067-1073`), y se mira
  antes que los cambios (`router.py:134` y `supervisor.py:414`, frente a `router.py:138-152` y `supervisor.py:428-450`). El pase sale
  sin la política.
- La detección del cambio está tres veces: en `router.py`, en `changes_agent.py:71-88` y en la cascada. Son 17, 18 y 21 líneas de
  código, 82 con comentarios.
- Con la reserva hecha:
  - el cambio de fecha ya se salta el guardia de reserva nueva (`_jev_changes_date`, `rutas/changes.py:146`);
  - cancelar y cambiar el número de personas no se lo saltan: `_in_active_cart_building` apaga `booking_change_topic`.

**M3. El pase que vuelve.**
- En producción, si un turno posterior cae otra vez en un pase de texto fijo (lo médico, `needs_staff`, `wants_human`, el
  contacto, el cambio o el clima):
  - se repite el texto del pase, con «el asesor ya tiene tu caso» encima de «te paso ahora»;
  - y sale otra nota a Chatwoot.
- `pasar_a_persona` sustituye el motivo, no lo junta (`lead_summary.py:164`).
- Además, «¿eres un bot?» deshace el pase: pone `FREE_TEXT` (`deflection_agent.py:97`, `supervisor.py:483`).

**M4. Ya reservó y pregunta lo que la base no tiene: no lo decide nadie.** Queda para un segundo paso (4P-2), con su propio diseño.

## El cambio

**C0. La vara, como producción (bloque 0).** `reproducir_juez_pre` y `charla_rama` borran `pending_escalation_reason` al acabar cada
turno, como `chatwoot.py:290`. Por eso la próxima comparación necesita volver a pasar el lado A con el arnés arreglado
(~1,5 $ de OpenRouter y ~30 % de la ventana de Claude).

**C1. La agencia, como un cliente.**
- **La definición de `needs_staff`:**
  - fuera la agencia que escribe como empresa;
  - fuera, de `_FUERA_DEL_SISTEMA`, «for several customers, for an agency» y «special rates» (el enlace normal ya deja elegir el
    número de personas);
  - siguen en el pase la factura, coordinar fuera de la web y el enlace que se salta la fecha.
- **El evento de empresa y el grupo de 5 o más** siguen yendo al asesor por sus propias decisiones (`pide_servicio_privado`,
  `grupo-por-el-asesor`; el segundo es del 4R).
- **La instrucción, por el canal de las decisiones:** `instruccion_es/en` en `por-otros`, y `por-otros` se suma a la lista de
  `reglas_del_escritor` (`prompts/info.py:451`; hoy, moneda, origen y precio, y sin totales). Así la reciben los escritores en
  cada turno.
  - El juez solo lee id, fecha y texto (`judge_golden_set.py:131`): **la huella no cambia**.
  - Un FAQ la cambiaría y además obligaría a recargar `kb_v2` en el Postgres de PRE, que compartimos todos.
- **La sonda de `needs_staff`:**
  - pregunta con la misma pregunta que usa el bot (`_questions_for_turn()[NEEDS_STAFF]`), no con `_NEEDS_STAFF_Q` sola;
  - pasa las agencias a los negativos;
  - y añade la factura, el cambio y la cancelación.
- Se avisa en Coral antes de tocar `jev_router.py`.

**C2. Una sola decisión del pase fuera de la reserva.**
- `decidir_pase(state, message, signals)` en `rutas/pase.py`. Es pura: decide, no pasa a nadie. Devuelve `cambio` (y su tipo),
  `persona`, `privacidad` o nada.
- Un solo «tiene reserva hecha», con el guardia `_reserva_nueva_en_curso` de `_modo_posventa`. Con la reserva hecha, el cambio va
  antes que `needs_staff`.
- `_in_active_cart_building` no se toca: también lo usa la disponibilidad.
- El router, el nodo de cambios y la cascada cambian a la vez y llaman a la función. Si cambiara solo el router, el nodo de cambios
  delegaría en la cascada y esta volvería a pasar sin política.
- **Efecto que se prueba:** la negativa de privacidad sale también sin `needs_staff` (hoy solo sale con él).

**C3. El pase que vuelve, en un solo sitio: el cierre del turno (`route_message`).**
- `pasar_a_persona` marca «pase en este turno».
- Si la conversación ya estaba en ESCALATE al empezar el turno, y este no es de los que van solos (`_PASE_QUE_VA_SOLO`):
  - el texto fijo del pase se cambia por lo que contesta `lo_contestable_en_cualquier_pase`, que mantiene el freno de no tocar lo
    médico, más una línea corta («tu caso ya lo tiene el equipo»);
  - la nota a Chatwoot sale con el motivo nuevo.
- Vale igual en producción y en el arnés, y no hace dos llamadas al RAG.
- La deflexión («¿eres un bot?») deja de deshacer el pase.

## Cómo se prueba y se mide

- **Banco sin IA (`tests/test_bloque4p.py`):** `decidir_pase` con señales grabadas.
  - Reserva hecha más un cambio (fecha, cancelación, número), con y sin `needs_staff`: política y pase.
  - Reserva nueva con «mejor 3 días» o «somos 4»: nada.
  - `needs_staff` solo: pase.
  - `pide_datos_ajenos`: privacidad.
  - Equivalencia entre el router, el nodo de cambios y la cascada.
  - C3: ya en ESCALATE con lo médico o `needs_staff`, sin texto fijo y con la nota; una queja o emergencia va sola.
  - Ojo: `test_s4_fixes.py:97` parchea `supervisor._in_active_cart_building`.
- **La sonda de `needs_staff`:**
  - 0 agencias que piden precio o tarifa al pase;
  - la posventa, la factura, el cambio y la cancelación, al pase, como antes.
- **Mecanismo, ×5 con `charla_rama`** (ya con C0):
  - **De la tanda:** la agencia, el cambio, la recogida y qué llevar.
  - **Del panel:** los clientes del 4P y visto-6937.
  - **Meta:**
    - **La agencia:** la que pide precio o tarifa nunca va al pase, y oye que no hay precio de agencia.
    - **El cambio de una reserva hecha:** siempre con la política.
    - **Un pase ya hecho:** nunca se repite.
- **El panel, al cerrar el bloque 4 entero** (con el 4R): debe bajar al menos 3 desde la partida, medida otra vez con C0.

**Saldo previsto:**
- C2 borra 82 líneas (56 de código) y deja una función con sus tres llamadas, de unas 45-55: entre −25 y −35 contando
  comentarios, como medimos siempre; en código, cerca de cero.
- C3, unas +10. C1, unas +6 (los datos de la instrucción).
- Neto: negativo, pero poco. Si no basta, se busca qué más borra antes de cerrar.

**Riesgos:**
- Con la señal cruda `ya_reservado`, un «ya buceé con ustedes» a mitad de una reserva nueva podría volver a pasar «mejor 3 días».
  Por eso se usa el guardia `_reserva_nueva_en_curso`.
- Una urgencia médica que Jev marque solo como `medical_questions` después de un pase la contestaría el RAG con su freno. Las
  urgencias de verdad (`complaints_or_emergencies`) siguen yendo solas.

## Fuera del 4P, para quien corresponda

- **4R (Álvaro):** en posventa no corre `slotfill_close`, así que la recogida fuera de los puntos de siempre (`fuera-de-la-base`) no
  se aplica a quien ya reservó.
- **La referencia del juez, en su próximo cambio** (decide Gadea cuándo): quitar `escalation_rules.json:16` (agencias al pase);
  alinear con `por-otros` el caso del golden `agencia-solicita-tarifas-escalar` y un criterio del examen oculto sobre el enlace
  especial; y el texto de `cambio-de-fecha` (17-sep: un cambio sin pagar pasa a un asesor), que choca con lo que hace el código
  desde el 3-nov (solo con la reserva hecha).
