# G3 · Claude contra el chatbot, en directo — hallazgos

Sesiones con `scripts/charla_pre.py` contra PRE (cada charla entera en `docs/robustness/g3/charlas/<conv>.jsonl`).
Cada hallazgo: qué pasó, de quién es la zona (flujo/extractor = Álvaro; RAG/datos = Gadea) y su estado.

## G3-01 · Familia (2 buzos certificados + niños de 8 y 12) no llega nunca al plan — conv 5567 (17-oct, PRE 815d201)

Zona: **Álvaro** (reparto del grupo, preguntas del flujo).

1. "somos una familia de 4, mi esposo y yo somos buzos certificados y tenemos 2 hijos de 8 y 12" → contesta solo
   para un buzo ("Como ya eres buzo certificado…"), sin los niños.
2. "la salida de 2 inmersiones para nosotros dos. y los niños que pueden hacer?" → bien: 8 años Bubble Makers /
   snorkel / acompañante; 12 años minicurso / snorkel / acompañante.
3. "el de 12 minicurso y el de 8 snorkel. salimos desde cartagena, somos colombianos" → pregunta "¿un solo día o
   varios días?" para recomendar a los no certificados, que ya han elegido.
4. "un solo dia, el sabado 24" → vuelve a ofrecer el menú minicurso / snorkel / acompañante ("¿Cuál les apetece más?").
5. "ya te dije, minicurso para el de 12 y snorkel para el de 8" → "Entendido…" pero ofrece el menú "para tu
   acompañante" (el marido, que bucea).
6. "no, mi esposo bucea conmigo, los dos somos certificados…" → "¿Cuántos serían para minicurso?" (ya dicho: 1).

Resultado: en 6 turnos no hay precio ni enlace. El reparto correcto era certificado 2 + minicurso 1 + snorkel 1,
dicho en los turnos 1-3.

## G3-02 · "how do I pay?" — precio y enlace dos veces y dos preguntas de cierre — conv 5568 (17-oct)

Zona: **montaje de la respuesta** (contesta-y-sigue: el RAG contesta y el flujo añade la tarjeta de reserva).
Turista de EE. UU., Open Water, "I'd do it on the 21st and 22nd… just me. how do I pay?". La respuesta del RAG ya da
el precio (693 USD), el enlace y "Would you like help with anything else…?"; después el flujo pega la tarjeta con el
mismo precio, el mismo enlace y "Is there anything else I can help you with?". Además el aviso del USD (A6) y la nota de
la tarjeta ("same in COP or USD") dicen lo mismo. Todo correcto, pero el mensaje es el doble de largo y repite.
Los turnos 1-2 (duración, noche, teoría, 18 h antes de volar, hoteles base y de la zona) salieron bien.

## G3-03 · "Te paso con el equipo" sin pase real — conv 5569 (17-oct) — ARREGLADO con flag (apagado)

Zona: **Gadea (RAG)**. Buzo Open Water alojado en Coral Sand (Isla Grande), 3 años sin bucear, "¿puedo bucear
mañana?". La respuesta: "Te paso con el equipo para que te orienten…" y, en la misma, "¿para cuántas personas armamos
el plan?". TURN_METRICS: `escalated=False`: nadie recibe el caso. Turno 2: "Te paso con ellos para confirmar la
logística de mañana", igual. Causa: varias reglas del RAG dicen "deriva al asesor" y el modelo lo hace como si pudiera.
Arreglo: `RAG_OFRECE_EL_PASE` (regla `RAG_PASE_OFRECIDO_*`): no lo da por hecho, lo OFRECE como pregunta y el sistema
hace el pase si el cliente acepta. Banco `docs/robustness/g3/banco-g3.json` (g3-03a/b), 3 reps: **6/6 → 0/6**.
Pendiente: ronda core B con los arreglos de G3 juntos (A = el subconjunto core de CAL-F).

Visto también en esta charla (para revisar): no confirma "mañana" aunque se opera todos los días; "el almuerzo no está
incluido" sale dos veces (respuesta + aviso A6, que no vio que ya estaba) y el precio del refresh también dos veces
(respuesta + plantilla del flujo, misma clase que G3-02).

## G3-04 · Cliente que ya pagó el minicurso: bien, con detalles menores — conv 5570 (17-oct)

"ya reservé y pagué el minicurso para el sábado… ¿a qué hora es y qué tengo que llevar?" → hora y muelle, regreso,
qué llevar, teoría online y formulario médico: correcto (la FAQ del minicurso dice que la teoría se hace antes). Menor:
el saludo de bienvenida dice "te ayudo a armar tu plan" y "vas a disfrutar tu primera experiencia" a quien ya reservó.
Turno 2 ("¿lo puedo pasar al domingo?"): la plantilla de cambios responde bien pero sin tildes ("estan", "terminos"),
ya visto antes (zona del flujo).

## G3-05 · Datos y pregunta en el mismo mensaje: "no tengo ese dato" aunque la FAQ existe — conv 5571 (17-oct) — ARREGLADO con flag (apagado)

Zona: **Gadea (búsqueda del RAG)**. Pareja brasileña, nunca ha buceado: "saímos de Cartagena, dia 30. Precisa saber
nadar?" → "I don't have that specific requirement handy…". La FAQ "¿Necesito saber nadar para bucear?" existe.

No es el idioma (o no solo): en el banco, la misma charla en español ("salimos de Cartagena el día 30. ¿Hace falta
saber nadar?", g3-05b) y en inglés (g3-05c) falla igual, **3/3 en los tres idiomas**. Medido en la búsqueda de PRE:

| Consulta | La FAQ de nadar |
|---|---|
| "Do you need to know how to swim?" / "¿Hace falta saber nadar?" | la primera (1,03 / 0,73) |
| "Do we need to know how to swim for the Dive Mini Course?" | la primera (0,74) |
| el mensaje entero, con "Cartagena" y "el 30" delante (es, en, pt) | **no entra entre las 8 primeras** |
| la reescrita de CAL-D ("…the Dive Mini Course that departs from Cartagena on the 30th?") | **no entra** |

Causa: cuando el cliente da datos y pregunta a la vez, el origen y la fecha tapan la pregunta con las fichas que salen
desde Cartagena (la búsqueda es vector + palabras, sin reranking por pregunta). En portugués, además, el mensaje se
buscaba tal cual contra la base en español e inglés.

Arreglo (`BUSQUEDA_CON_LA_PREGUNTA_SOLA`): la búsqueda doble usa la **pregunta sola** (sin los datos que da el
cliente, en el idioma de la respuesta) en vez del mensaje entero: una llamada corta a gpt-4o-mini a la vez que la
búsqueda principal, solo para mensajes de 8 palabras o más o en otro idioma (los cortos ya son la pregunta). Un
mensaje en otro idioma, además, siempre se reescribe en el de la respuesta. Lo que trae se AÑADE (hasta 4 piezas tras
las 8 de siempre): la búsqueda principal no cambia.

Intentos descartados por la medida: (1) solo reescribir en el idioma de la respuesta, 3/3 → 2/3; (2) pedir al
reescritor "solo lo que cambia la respuesta" para todas las preguntas, g3-05 1/3 pero cal-42 (precio por día, que
CAL-D había arreglado) vuelve a fallar 1/3; (3) traducir el mensaje entero, 2/3 (la traducción arrastra el origen y la
fecha).

Medida (banco `banco-g3.json`, 3 reps, `--codigo-local`): **sin flag 9/9 fallan → con flag 1/9**. El que queda
(g3-05c) ya no dice "no lo tengo": contesta el precio y se salta la pregunta de nadar, aunque la FAQ está en el
contexto. Coste: una llamada de gpt-4o-mini en los turnos del RAG con mensaje largo o en otro idioma (en CAL-F, 227 de 465
mensajes tienen 8 palabras o más; 4 vienen en otro idioma). Va a la vez que la búsqueda principal, así que añade lo
que tarde de más que ella (estimado 0,3-0,5 s en esos turnos): a medir en la ronda core B y en CAL-G antes de
promocionar.

## G3-06 · Tres amigos alojados en Barú: Barú tratado como las islas y un plan que nadie pidió — conv 5572 (17-oct)

"estamos en un hotel en baru, somos 3 amigos. 2 nunca han buceado y yo tengo advanced. también vamos a san andrés…"

1. Turno 1: bien que diga que no operamos en San Andrés ni en Barú, pero en la misma respuesta "como ya están en Barú,
   la recogida depende de que el hotel tenga acceso marítimo; ¿me dices el nombre del hotel?". El estado queda
   `location=island, hotel=baru` (el flujo acepta "Barú" como isla sin nombre, `conversational_core.py:166`).
2. "estamos en el hotel las islas, en baru. ¿nos pueden recoger ahí?" → "¡Claro! La recogida en lancha está incluida si
   el hotel tiene acceso marítimo", cuando la FAQ dice que eso es para quien ya está **en las Islas del Rosario**.
3. "¿cuánto cuesta todo para los 3? sería el jueves. somos colombianos" → cotiza "el plan de buceo certificado que
   mencionamos" = **paquete de 3 inmersiones con nocturna** (665.000 COP, ya en las islas), que nadie mencionó, y dice
   que no tiene el precio del minicurso "para hacerlo desde el Hotel Las Islas" (el catálogo, que va entero en el
   contexto, sí lo tiene: 475.000 COP ya en las islas). Banco `g3-06`, en PRE: **2/3** (la otra da la salida de 2
   inmersiones, 440.000 COP).

Por qué el plan equivocado: el estado no tiene plan elegido (solo `certified_diving` y el reparto 1 + 2 minicurso) y
la búsqueda trae primero paquetes "ya en las islas" al azar: el mensaje es largo (no pasa por la reescritura de CAL-D,
que solo corre en mensajes cortos, así que no nombra las actividades) y lleva al final el marcador
`[origen_cliente]=ya en las islas`, que en el vector empuja cualquier ficha de las islas. Las reglas RAG_NO_SUPONE
("no digas «tu paquete de 3 inmersiones» si él no lo dijo") y RAG_VARIOS_PLANES ya están encendidas y no bastan.

**Pregunta de negocio para Gadea** (antes de tocar nada de Barú): ¿recogéis en hoteles de Barú con acceso al mar
(p. ej. Hotel Las Islas)? Si sí, ¿con el precio "ya en las islas" (sin almuerzo) o con otro? Si no, ¿qué se le dice:
salir desde Cartagena? Hoy el bot dice a la vez "en Barú no operamos" y "la recogida está incluida".

Siguiente (zona Gadea, búsqueda): que los mensajes largos también nombren el asunto con lo sabido, juntando la
reescritura de CAL-D y la pregunta sola de G3-05 en una llamada; medir la latencia antes de decidir.

## Búsqueda por palabras (BM25) casi muerta — visto al investigar G3-06 (17-oct)

`_bm25_search` usa `websearch_to_tsquery('simple', …)`, que exige TODAS las palabras: en la búsqueda de PRE, "¿cuánto
cuesta el minicurso?" → 1 documento; "what time does the boat leave?" → 0; un mensaje largo → 0. Además, cuando la
consulta lleva el marcador de origen, BM25 busca solo la última línea (`[origen_cliente]=ya en las islas` → 0). En la
práctica, la búsqueda es solo por vector y la fusión RRF no aporta.

Medido sin gastar (SQL en la base de PRE, las 51 preguntas de `rag_piezas`, solo BM25): con TODAS las palabras, 48/51
preguntas sin ningún documento y 4/97 datos en el top-8; con CUALQUIER palabra (OR), 0/51 vacías y 53/97. Probado
tras un flag (OR, y BM25 sobre la pregunta y no la marca de origen) y medido con `rag_piezas --solo-busqueda
--codigo-local` (18-oct): **empeora**. El dato en el top-8 baja del 86 % al 65 % (al primer puesto, del 63 % al 29 %) y
entran 19 fichas del otro origen: un BM25 que casa por cualquier palabra (con "de", "el", "la") mete ruido en la
fusión. **DESCARTADO** y el código quitado; la búsqueda por vector sola ya trae el dato el 86 % de las veces.
(Al medirlo apareció que `rag_piezas` fallaba en todo desde CAL-D, 16-oct: su espía de la reescritura no aceptaba
`hechos`. Arreglado.)

## G3-07 · Pareja de Bogotá, snorkel → minicurso — conv 5573 (17-oct)

**G3-07a · Dos monedas en el mismo mensaje (turno 1).** "somos una pareja de bogota… queremos hacer snorkel un día,
¿cuánto vale?" → el texto dice "126 USD por persona" y la tarjeta del mismo mensaje "2 × 448.000 COP" ("Como sois
colombianos/residentes…"). Banco `g3-07a`, PRE: **3/3**. Causa (TURN_METRICS del turno: `rag_adelantado:
aprovechado`): el RAG adelantado (rag-5) arranca con el estado vacío y se ADOPTA en el enrutado, antes de que el flujo
aplique la extracción (el extractor acaba a 1,9 s, el RAG a 2,7 s); la tarjeta sale después, con `is_colombian=True`.
La sonda lo confirma: el RAG contestó con `hechos: {}` y aplicó "sin nacionalidad, USD". Zona compartida (rag-5 de
Gadea, orden del turno de Álvaro). Opciones, todas con coste de latencia en esos turnos: (1) comparar la huella
también al RECOGER la respuesta y rehacerla si cambió la nacionalidad o el origen (+2,5 s); (2) lanzar un segundo RAG en
cuanto acaba la extracción si cambia esos hechos (+1,3 s); (3) en contesta-y-sigue con tarjeta, que el texto no dé el
precio (la tarjeta ya lo da; también quita la repetición de G3-02). A decidir con Álvaro y Gadea.
Además en este turno: "como sois" (España) en la plantilla, la tarjeta da un TOTAL (2 × 448.000 = 896.000, pendiente
de la decisión "sin totales"), y pasa al asesor a la vez que el texto pregunta "¿qué día les gustaría ir?".

**G3-07b · El 5 % por equipo propio, mal aplicado al minicurso (turno 3) — ARREGLADO en los datos.** "¿hay algún
descuento? tenemos nuestras propias máscaras" (minicurso) → "el 5 % por equipo propio aplica solo si llevan el equipo
completo; con las máscaras no aplica": da a entender que con el equipo completo el minicurso sí lo tendría, y no lo
tiene nunca. Banco `g3-07b`, PRE: **3/3**. Causa: la ficha indexada (`descuento:own_equipment_discount`, de
`discounts.json`) no decía la exclusión; solo el campo `applicability` ("buceo recreativo y cursos", que el escritor
lee como "minicurso" = curso) y el catálogo escrito a mano (`catalog.py:643`, "no en snorkel ni minicurso"). Arreglo:
la descripción y la nota de `pricing.json` dicen "solo en buceo recreativo y cursos PADI: no aplica al minicurso ni al
snorkel". Medido en PRE tras desplegar b4b0941 (reindexado): **3/3 → 0/3** ("El descuento por equipo propio no
aplica al minicurso, y llevar solo las máscaras tampoco cuenta como equipo completo").

Bien en esta charla: el cambio de snorkel a minicurso (turno 2) se entiende a la primera, con precio en COP, punto de
encuentro, teoría online y formulario médico.

## G3-08 · Grupo de 6 del Reino Unido (4 certificados + 2 snorkel) — conv 5574 (17-oct)

Turno 1 bien: combina buceo y snorkel en la misma salida, el 10 % de grupo (5 o más) que aplica el equipo, precios
por persona desde Cartagena, punto de encuentro, recomienda la salida de 2 inmersiones y pregunta por los 2 años.

Turno 2 ("no, we all dived last year… how do we get the group discount if we book online? do we pay first and get
refunded?"):
- **Aviso fuera de lugar**: "After more than 2 years without diving, a refresher is normally needed…", justo después
  de que el cliente diga que todos bucearon el año pasado. Medido (18-oct, banco `g3-08`, 3 reps): **0/3 sin y 0/3
  con** la condición escrita en el aviso (`cuando_texto`): no se reproduce. La condición se queda porque es la
  correcta, sin atribuirle mejora.
- **Afirma lo que la base no dice**: "No refund is needed" (salió también en la sonda). La base solo dice que el 10 %
  de grupo no es automático y lo aplica el equipo; cómo se aplica a una reserva ya pagada online no consta. Pregunta de
  negocio para Gadea: si un grupo reserva y paga online, ¿el 10 % de grupo se devuelve después o hay que pedirlo antes
  de pagar?
- Repite los enlaces (texto "¿te los vuelvo a pasar?" + tarjeta con los dos enlaces) y la tarjeta da totales (G3-02).

Medida sin hacer: el crédito de OpenAI se agotó a las 21:31 (429 `credit_balance_exhausted`, también en PRE).

## CALN1-01 · Familia (2 Advanced + niño de 11 + suegra acompañante) no llega a la tarjeta en 6 turnos — conv 6768 (27-oct, PRE integra5 0faff2c)

Sparring de CALN-1 (Claude contra el bot). Zona: **el grupo** (CALN-2) y el extractor.

1. «Vamos a estar en Cartagena… mi marido y yo buceamos (somos Advanced), mi hijo tiene 11 y nunca ha buceado, mi
   suegra viene pero no se mete al agua. ¿Qué nos recomiendas y cuánto sale?» → BIEN: recomienda sin asumir (2 inmersiones,
   minicurso, acompañante), precios en USD y COP (sin nacionalidad), sin totales. 10 s.
2. «somos colombianos. ¿Y si buceamos 2 días? ¿y el niño en 2 días?» → el escritor, muy bien (COP, paquetes de 2 días con
   noche en las islas, Open Water junior); pero el flujo pega **«¿Eres buzo certificado?»** (ya dicho: Advanced) detrás
   de su propia pregunta del asesor: repregunta y dos preguntas.
3. «ya te dije que los dos somos Advanced 😅 paquete de 5, el niño el Open Water, mi suegra de acompañante, salimos el
   sábado» → «¡Perfecto! 🙌» seco y **«¿Desde dónde saldrías?»** (dijo «vamos a estar en Cartagena» y el bot cotizó desde
   Cartagena).
4. «desde Cartagena, ya te lo había dicho» → «¡Perfecto! 🙌» y la pregunta de seguridad (correcta).
5. «no, hace 6 meses» → **menú para «quien no está certificado»** (el niño ya eligió el Open Water y la suegra acompaña).
6. «el niño el Open Water y mi suegra de acompañante, como te dije» → **«¿ya tienen esa certificación o quieren
   sacarla con el curso?»**: bucle.

Clases: el grupo persona a persona no se guarda (lo que elige cada uno se pierde) → CALN-2; certificación por nivel
(«Advanced») no leída → extractor; origen «estar en Cartagena» no guardado; el acuse seco ante una queja del cliente
(«ya te lo dije»). Pasa al banco de grupos como g21.

## CALN1-02 · Pareja (él buzo PADI, ella nunca ha buceado) cotizada como dos minicursos — conv 6769 (27-oct, PRE integra5)

1. «My boyfriend is a PADI diver and I've never tried it. How much for both of us one day?» → **solo el precio del
   minicurso** «para los dos» («your boyfriend's certification doesn't change the price of this plan»): él, certificado,
   haría la salida de buceo. Bien: sin origen, los dos orígenes y las dos monedas.
2. «staying at Isla Grande, he wants to dive, I'd try the mini course, we're from Canada» → bien (124 y 134 USD desde
   las islas, sin almuerzo); pero el flujo repite la recomendación que el escritor ya dio («I recommend the 2 dives…»).
3. «he dived last month. how do we pay?» → tarjeta correcta (dos líneas, enlaces, recogida), pero la moneda se dice tres
   veces (arriba, nota de la tarjeta y al final).

Clases: el grupo en la primera cotización (cada persona su actividad) → CALN-2 / CALN-3; redundancias del montaje
(recomendación repetida, moneda ×3) → CALN-6.

## CALN1-03 · Amigos de Medellín: «snorkel en las islas» como origen, corrección del origen sin re-cotizar y frase repetida — conv 6770 (27-oct, PRE integra5)

1. «somos unos amigos de Medellín y queremos hacer snorkel en las islas este puente, ¿cuánto vale?» → cotiza SOLO «ya en
   las islas» (150.000 COP): nombrar las islas como sitio de la actividad no es el origen (CAL-C3c, decisión
   «origen-y-precio»). Bien: «de Medellín» = COP.
2. «no no, salimos desde Cartagena… somos 5: 2 snorkel y 3 buceo, certificados» → acepta el origen y el reparto, pero
   NO re-cotiza el snorkel desde Cartagena (el cliente se queda con el precio de las islas) ni dice que lo cambió.
3. «no, todos buceamos este año. ¿y el snorkel desde Cartagena?» → tarjeta correcta (3 × 630.000 y 2 × 448.000 COP,
   pago colombiano por asesor), pero la frase del precio del snorkel sale DOS veces seguidas y «el asesor ya tiene el
   plan» va antes y después de la tarjeta. 12 s.

Clases: origen leído del sitio de la actividad → CALN-3 / extractor; corrección del origen tras un precio sin
re-cotizar → CALN-3 (el resolvedor de precios); frases repetidas del montaje → CALN-6.

## CALN1-04 · Familia de 5 con niños y suegro acompañante, contra la RAMA (feature/caln-gadea de5cb9f, `scripts/charla_rama.py`, 27-oct)

Primera charla contra el código de una rama sin desplegarla (`docs/robustness/g3/charlas-rama/familia-suegro-lancha*.jsonl`).

1. «Familia de 5, del 3 al 7 de noviembre: mi marido Advanced, yo nunca he buceado, hijas de 14 y 9 quieren probar algo,
   mi suegro solo acompaña en la lancha. ¿Qué nos recomiendas y cuánto sale?» → bien: plan persona a persona (por edad:
   Bubble Makers para la de 9), precios con los dos orígenes, «el minicurso no certifica», descuento de grupo de 5+; el
   estado, bien (suegro acompañante, 4 por elegir, 5, varios días). Mal: la última frase del escritor se corta («…no
   certifica. Así») y detrás va el **menú genérico de 4 actividades** (la pregunta de la actividad sustituye el último
   párrafo del escritor).
2. «Mi marido quiere bucear, yo minicurso, la de 14 también y la pequeña Bubble Makers. Somos colombianos. ¿Cuánto todo
   junto?» → **no guarda nada** y contesta «No tengo aquí los precios calculados para las otras actividades» (los dio
   antes) y otra vez «¿Con cuál te animas?». Causas: (a) el reparto que COMPLETA a los que faltaban por elegir lo tiraba
   el veto de Jev («nadie se suma»: cierto, ya estaban contados) o, si el extractor no nombraba al suegro, se pedía
   confirmar un «cambio» → ARREGLADO en la rama (`grupo.completado`): ahora queda {acompañante 1, minicurso 2} y 2 por
   elegir; (b) **Bubble Makers no cabe en el reparto del extractor** (no está en sus actividades): la elección de la
   niña se pierde; (c) **la recomendación para quien no ha elegido no mira la edad**: a la de 9 le ofrece minicurso y
   Open Water (desde los 10) y no Bubble Makers; (d) **el escritor solo recibe los hechos de UNA actividad** (la
   preguntada o el acompañante) y dice que no tiene los demás precios; (e) el extractor a veces no reparte «mi marido
   quiere bucear».

Clases: completar el grupo (CALN-2, arreglado); niños en el reparto y recomendación por edad (CALN-2, nuevo); los hechos
del grupo entero para el escritor (CALN-4); el montaje que corta la frase del escritor (CALN-6).

**Cómo queda en la rama (27-oct, 16:30, `familia-suegro-lancha-t2f`):** el turno 2 guarda el grupo entero (suegro
acompañante, marido buceo, 2 minicursos y Bubble Makers; nadie pendiente) y el escritor da el precio de cada uno con el
descuento de grupo explicado y sin sumar el total; sigue la pregunta de seguridad. Arreglos: `grupo.completado`
(CALN-2), Bubble Makers en el reparto y la recomendación por edad (CALN-2 3c), los hechos de todo el grupo para el
escritor (CALN-4, `redactor_hechos._actividades`). Queda: a veces el escritor omite una línea (el acompañante) y el
código añade detrás su recomendación del plan del buceo.

## CALN2-01..05 · Sparring de la 1.ª integración de CALN, contra la RAMA (feature/caln-gadea 5fb7127, 27-oct)

Cinco clientes difíciles con `scripts/charla_rama.py` (`docs/robustness/g3/charlas-rama/s2-*.jsonl`).

**Lo que va bien:** los grupos (6 amigos que pasan a 8 y dos que eligen el minicurso: el reparto 6 + 2 se guarda y la
tarjeta sale bien con 6 × 630.000 y 2 × 655.000 COP); el precio por persona de una familia (buceo, snorkel del de 7,
acompañantes); la disculpa ante la queja («ya te lo dije») y el precio bueno después; la moneda de un grupo mixto (USD).

**Lo que falla, por causa:**

1. **Los hechos del escritor se arman con lo guardado ANTES del turno** (CALN-4/CALN-3): «al final vamos a estar en Isla
   Grande, ¿cambia el precio?» → «Sí, cambia: desde Cartagena es… No tengo aquí el precio para Isla Grande» (s2-corrige,
   t2; es la causa de CALN1-03: `redactor_hechos._origen` prefiere el origen guardado a lo que dice este mensaje). El
   refresher del marido, igual: «I don't have its island price here» (s2-pareja, t2: el refresher no entra en los hechos).
2. **Precio pedido sin origen y sin actividad elegida → ningún precio** (s2-pareja, t1: «To give you the exact price I
   need to know where you're starting from»), contra la decisión «dos precios y pregunta» (CALN-3).
3. **«¿Cuántos sois?» tras «for us» / «him and me»** (s2-pareja, t2): «el refresher para él y el minicurso para mí» no
   deja el grupo de 2 (CALN-2, lectura del extractor).
4. **Un camino viejo de edades se come el turno** (s2-familia, t1): «soy buza y quiero bucear, voy con mi esposo que no
   bucea y los niños de 7 y 4» → solo lo que pueden hacer los niños por edad, sin saludo, sin la madre ni el padre, con un
   relleno robótico («Si además preguntabas por algo más concreto…»), y sin guardar el grupo de 4 (CALN-2/CALN-6).
5. **«Alojados en Cartagena» no se guarda como origen** (s2-familia): el escritor cotiza desde Cartagena y en el turno 3
   se vuelve a preguntar «¿Desde dónde saldrías?» en vez de dar los enlaces pedidos (ORIGEN-CONFIRMA, Gonzalo).
6. **El menú genérico de 4 actividades** cuando el grupo ya acota la elección (s2-amigos, t1: 4 certificados y 2 que
   dudan entre minicurso y snorkel → «Cuéntame, ¿qué te gustaría vivir…? Buceo / Minicurso / Snorkel / Cursos PADI»):
   la misma familia que las 5 repreguntas «¿Con cuál te animas?» de la ronda caln1 (siguiente tarea).
7. **El montaje repite** (CALN-6): el bloque entero de descuentos pegado tras explicar el de grupo (s2-amigos, t1); el
   descuento de grupo dos veces seguidas (t3); la regla del grupo mixto dos veces y «¿…o prefieres volver al menú
   principal?» (s2-mixta, t1).
8. **Latencia:** turnos de 9-14 s (s2-pareja t1 13,7 s; s2-amigos t3 12,1 s).

## CALN3-P01..P03 · Tanda de PRECIOS contra la rama (feature/caln-gadea b0f3a97, 27-oct, `charla_rama`)

Gadea (27-oct): foco en los precios y más sparring. Charlas en `docs/robustness/g3/charlas-rama/p*.jsonl`.

1. **«¿Cuánto cuesta bucear?» → tres turnos sin un solo precio** (p1-cuanto-cuesta-bucear): t1 «para darte el precio
   exacto necesito saber desde dónde sales»; t2 «no sé todavía, primero quiero saber precios, nunca he buceado» →
   recomienda el minicurso, «el precio online incluye el 10 %» y SIN cifra; t3 «dime el precio de las dos opciones por
   favor» → igual. La traza: `[CORE][ORIGEN] precio sin origen -> se pregunta el origen antes de cotizar` en los tres.
   Contra la decisión «dos precios y pregunta». Causa: la puerta del origen quita los importes cuando la actividad no
   está elegida y el escritor no da los dos orígenes (CALN-3: cotizar los candidatos con los dos orígenes).
2. **«We'll already be staying at Isla Barú… how much?»** (p2-cedula-extranjeria-snorkel): bien la moneda (cédula de
   extranjería → COP), pero NO toma Barú como dónde está, vuelve a preguntar el origen y no da precio (CALN-3 / el
   origen).
3. **«¿Cómo reservamos?» sin origen** (regateo-grupo-6 t5, reproducido 4 veces): los enlaces dependen de que Jev marque
   la intención `enlace`; si no, el turno sin dato escribe sin hechos (sin enlace) o se descarta si pregunta el origen
   (CALN-3: los enlaces, como los precios, una pieza del código; 9311eea arregla solo que el escritor conteste).
## CALN3-01..14 · Primera tanda de la batería fija de sparring, contra la RAMA (feature/caln-gadea b0f3a97, 27-oct)

Once personas de `docs/robustness/g3/bateria-sparring.md`, pasadas con `scripts/charla_rama.py`. Las charlas están en
`docs/robustness/g3/charlas-rama/b*.jsonl`. Los casos van al banco `docs/robustness/caln/banco-sparring.json`.

**Lo que va bien:**

- Corregir el origen tras un precio vuelve a cotizar (b3).
- El repaso tras 4 años se cotiza desde las islas, y el corte de reservas se dice tal cual, sin «cerró ayer» (b8).
- El snorkel de una pareja va directo a la tarjeta en 4 s (b10).
- El descuento de grupo se explica una vez y con sus condiciones (b6, t1).
- Una familia de 5 recibe el precio de cada persona, con su grupo entero guardado (b4, t2).
- La tarjeta final de una familia con buceo, Open Water y acompañante sale bien (b1).
- La familia con niños ya no cae en el camino viejo de edades (b5, CALN2-04).
- «Alojados en Cartagena» se guarda como origen... a veces (b5 sí, b5b no).

**Lo que falla, por causa (y su tarea):**

1. **Lo mismo dicho dos veces** (CALN-6):
   - b1 t3: la respuesta ENTERA (precios, días, lo que incluye) dos veces, con «Tienes razón…» en medio; 16,9 s.
   - b5 t2: «Como hace un año que no buceas, no necesitas refresher…» dos veces.
   - b3 t3: dos «¡Perfecto…!» seguidos (acuse y escritor).
   - b7 t1: la regla del grupo mixto (USD), del escritor y otra vez en un bloque fijo.
   - b8 t2: dos párrafos casi iguales de la recogida en el hotel.
   - b9 t1: el bloque entero de descuentos tras explicar el de grupo, más requisitos y qué llevar sin pedirlos.
2. **Más de una pregunta, o la pregunta antes del final** (CALN-6, más allá del paso 1):
   - b11: «¿te comparto los enlaces?» y, detrás del punto de encuentro, la oferta de gen-8 «Si quieres, te ayudo a
     reservar: Curso Advanced… ¿Te animas?».
   - b7: «¿te comparto el enlace?» más «¿te conecto con un asesor, o prefieres volver al menú principal?».
   - b2 t2: dos «Is there anything else…?».
   - b5 t2: «¿Quieres que te pase con un asesor?» y detrás «Les paso con un asesor».
3. **Sin origen, ningún precio, y la puerta deja trozos sueltos** (CALN-3; la decisión es «dos precios y pregunta»):
   - b2 t1: solo un título «**Already on the Rosario Islands**» sin nada debajo.
   - b4 t1: sin un solo precio para una familia de 5.
   - b5b t2: «Reserva con el de tu punto de salida.» sin los enlaces.
4. **El grupo leído a medias o no guardado** (CALN-2, lectura del extractor; Álvaro (3)):
   - b1 t1: «mi esposo y yo somos Advanced, nuestro hijo de 11… mi suegra…» → el extractor da group_size 2 (solo
     cuenta a los buzos).
   - b6: «4 tenemos certificación y 2 dudan» no deja reparto. En t2 («somos 8: 6 certificados y 2 minicurso», que el
     escritor entiende) sale «¿Con cuál te animas — buceo, minicurso…?».
   - b9: 5 certificados y 3 principiantes, sin reparto.
   - b11: «el Advanced y también Nitrox» no deja actividad.
   - b10 t2: «mejor el minicurso los dos» no cambia la actividad guardada (sigue en snorkel).
5. **La tarjeta no se rehace al corregir el reparto, y el repaso no tiene precio** (CALN-2/CALN-3, CALN2-01):
   - b2 t2: tarjeta «Dive Mini Course 2 × 134 USD» para una pareja en la que él es buzo con 3 años sin bucear.
   - b2 t3: tras «he's a certified diver, only I do the mini course», el reparto queda bien (1 + 1), pero la tarjeta
     lleva minicurso ×2 MÁS fun dives ×1: tres plazas para dos personas, y el repaso sin precio.
6. **Mi regla de DEUDA-EXT2 («voy con una amiga» = 2) acababa en una tarjeta mal cobrada**:
   - b5 t2: «mi esposo no bucea y vamos con los niños, de 7 y 4» → grupo 2 → tarjeta «Salidas de Buceo 2 × 630.000
     COP» (el esposo no bucea y los niños quedan fuera).
   - _PLURAL_COMPANION_RE no tiene «niños». ARREGLADO sin tocar la lista: con dos o más edades sabidas, el total no
     es 2 (feature/sparring-alvaro). b5b ya no sale con esa tarjeta.
7. **El origen dicho no se guarda y se vuelve a preguntar** (ORIGEN-CONFIRMA / extractor):
   - b1: «vamos a pasar unos días en Cartagena» → en t2 «¿Desde dónde saldrías?», y eso que el escritor ya decía
     «Desde Cartagena…».
   - b5b: «estamos alojados en Cartagena» unas veces sí y otras no.
8. **Cambiar la fecha ANTES de reservar se toma como el cambio de una reserva** (Jev changes_date / ya_reservado):
   - b10 t2: «el sábado en vez del viernes» → pase al asesor «para gestionar el cambio de fecha», sin reserva hecha.
9. **El escritor sin la nota de edades habla del sistema** (CALN-4/6, la misma causa que banco-edades e5):
   - b5 t1: «Para el niño de 4 años, no tengo una actividad confirmada en el contexto», en vez de ofrecer el
     acompañante.
10. **La recomendación del plan que pone el código contradice al escritor o no pega** (CALN-6, `_recommended_plan_intro`):
    - b1 t2: el escritor propone el paquete de 5 inmersiones en 2 días y detrás va «Te recomiendo el plan de 2
      inmersiones en 1 día».
    - b4 t2: lo mismo a una familia que va 5 días.
    - b3 t2: redundante.
11. **El catálogo entero de planes** (CALN-3, «2-3 candidatos»):
    - b4 t2: al buzo de la familia, los 6 planes de buceo (de 2 a 9 inmersiones).
12. **Saludo** (CALN-6):
    - b9 t1: sin saludo en el primer turno (camino del pase por la medicación).
    - b1 t1 y b4 t1: dos saludos, el fijo y el «¡Hola…!» del escritor.
13. **Colombianos con los enlaces de la web en el texto** (hechos `enlace = {asesor}`):
    - b3 t3: el escritor da los enlaces y la tarjeta dice que el pago lo coordina el asesor.
14. **Latencia:** 10-17 s en los turnos con grupo (b1 t3 16,9 s; b2 t2 11,4 s; b1 t1 9,9 s).

## CALN3-Q01..Q09 · 2.ª tanda de PRECIOS contra la rama (feature/caln-gadea b26392c, 27-oct, `charla_rama`)

Cinco personas nuevas (`docs/robustness/g3/charlas-rama/q*.jsonl`), 17 turnos, en la línea de Gadea (precios y más
sparring). CALN-0 de composición: 0 fallos en los 17. Bien: q1 t1 (dos actividades × dos orígenes, en COP); q4 (Barú
no es de las islas, no hay recogida, mismo precio desde Cartagena); q3 t3 (no hay euros, paga en USD); q5 t1 (paquete
con los dos orígenes); q1 t4 y q5 t3 (tarjeta por actividad, sin total del grupo en el texto).

1. **«she the mini course» no cuenta** (CALN-2, Álvaro): q2 t2, `[EXTRACT][EX7] 'minicourse' no se nombra en el
   mensaje`. `_reparto_valido` (nucleo/extractor.py) comprueba con `matched_activity_categories`, que no tiene el
   nombre en inglés del propio producto («mini course», dom.label «Dive mini-course»). ARREGLADO
   (feature/caln-lectura-alvaro): el producto también por su nombre del catálogo es/en (`dom.nombra_el_producto`).
2. **Repetir lo que hace ella borra al buzo** (CALN-2, Álvaro): q2 t3, «I told you, she wants the mini course» →
   {certified_diving 1} pasa a {minicourse 1} + 1 sin decidir; tercera vez «Which option does she like best?».
   ARREGLADO (feature/caln-lectura-alvaro): con esa pregunta pendiente, la actividad leída es la de quien no había
   elegido. Y la variante «she'd go for the mini course. Only one day» contestando a «¿un día o varios?» (el extractor
   solo da `actividad_preguntada`, 9/10): la respuesta corta la elige por su nombre del catálogo si la IA no lee un
   reparto (banco-lectura l04).
3. **La pregunta de quien no ha elegido supone que es el no certificado** (CALN-2, Álvaro): q1 t2, sin decidir = el
   buzo ({snorkel 2}) y la pregunta dice «a quienes no están certificados: ¿un día o varios?». ARREGLADO
   (feature/caln-lectura-alvaro): «quien(es) aún no ha(n) elegido». Queda: las opciones para quien no ha elegido son
   solo de principiante aunque sea el buzo (`personas` no guarda la certificación de cada uno).
4. **El descuento de grupo ofrecido a un curso PADI** (CALN-3, Gonzalo): q3 t1, 5 amigos y el Open Water: «10 % para
   grupos de 5 o más, que se suma al online… no aplica a cursos PADI. ¿Quieres que te pase con un asesor para
   aplicarlo?». Los hechos dan los descuentos con su texto, sin decir si ESTE aplica; la decisión (27-oct) es «el de
   grupo cuando aplica».
5. **Pregunta por el de grupo y recibe todos** (CALN-3 + arq-7b): q3 t2, el escritor contesta bien y debajo «Sobre
   los descuentos:» con el de equipo propio, la moneda y que no se acumulan. `hechos.faltan` exige todos los
   descuentos con la intención `descuento` y `_completar_con_hechos` los pega; la decisión es «los demás, solo si los
   pregunta».
   Análisis (27-oct, 21:20): choca con arq-4b (G10 nº 4: ante «¿hay algún descuento?» los hechos dan TODOS con sus
   condiciones, lo fijan test_arq4b_fallos_g10_4, test_arq8a y test_arq8h). Para separar la pregunta genérica de la
   concreta hay que saber QUÉ descuento se pregunta, y la intención `descuento` de Jev no lo dice: va con la pieza de
   precios (CALN-3) y con el juez. En Q04, el de grupo no venía de los hechos (solo 'precio'), sino de
   `catalog_facts` (catalog.py), que lleva todos los descuentos en el contexto del escritor.
6. **«Te recomiendo el plan de 2 inmersiones» a quien ya dijo cuántas** (CALN-6, Gadea): q2 t4 debajo de sus
   enlaces; q5 t2. ARREGLADO: `_recommended_plan_intro` no recomienda si el cliente dijo cuántas inmersiones o días.
   Queda el caso de CALN3-10 b1/b4 (el escritor propone otro plan y el cliente no dijo la cifra): va con CALN-3.
7. **La pregunta del origen en singular a un grupo** (CALN-6, Gadea): «¿Saldrías desde Cartagena o ya estás…?» a
   una pareja (q5 t1) y a 5 amigos (q3 t2).
8. **Lo mismo dos veces, del escritor y del código** (CALN-6 / arq-7b): q3 t3, la nota de la moneda de la tarjeta y
   un párrafo con lo mismo; q5 t3, el escritor dice qué incluye y el punto de encuentro y la tarjeta lo repite; q2 t1,
   el bloque de la recogida repite lo que el escritor acaba de decir.
9. **Varios días sin dormir en las islas** (CALN-3, banco de precios): q5, «3 días, nos quedamos en el centro». El
   escritor y la tarjeta aciertan (2 inmersiones, 178 USD, «3 salidas independientes»), pero `cotizar` en sombra
   elige el paquete de 4 inmersiones en 2 días (316 USD) por `detected_duration = multi_day`: si la pieza de precios
   pasa al código, este caso tiene que estar en el banco.

## CALN4-01..12 · Segunda tanda de la batería fija de sparring, contra la RAMA (feature/caln-gadea c1be0e4, 27-oct)

Las once personas de `bateria-sparring.md` con el mismo primer mensaje que en la 1.ª tanda (CALN3-01..14), pasadas
con `scripts/charla_rama.py` sobre c1be0e4 (3.ª ronda de CALN + CALN-2 lectura). Charlas en
`docs/robustness/g3/charlas-rama/b*-t2.jsonl` (22 turnos); casos nuevos s11..s14 en `banco-sparring.json`.

**Lo que mejora frente a la 1.ª tanda:**

- b1 t3: la respuesta ya no sale entera dos veces (16,9 → 12,3 s) y la tarjeta es la de la familia (2 × paquete de 5,
  Open Water y acompañante).
- b2 t3: al corregir el reparto, la tarjeta se rehace (buceo 1 + minicurso 1, no tres plazas para dos).
- b7: la regla del grupo mixto (USD) una vez y sin «¿…volver al menú principal?».
- b11: sin la oferta de gen-8 «¿Te animas?» detrás del punto de encuentro.
- b9: la medicación pasa a una persona del equipo y los descuentos son los que hay (efectivo sin descuento).

**Lo que falla, por causa (y su tarea):**

1. **Precio de un origen dado como del otro — GRAVE** (CALN-3, Gonzalo; decisión «dos precios y pregunta»):
   - b3 t1, «snorkel en las islas» sin decir de dónde salen: «150.000 COP por persona… ese precio es saliendo desde
     Cartagena». 150.000 es el de quien ya está en las islas; desde Cartagena son 448.000 (`cotizar` en sombra los
     tenía los dos: «faltan 448000, 497000»).
   - b3 t2: al decir «salimos desde Cartagena» no re-cotiza (la 1.ª tanda sí), y en t3 la tarjeta dice 448.000 sin
     aclarar el 150.000 de t1.
2. **Sin origen, ningún precio y títulos sueltos** (CALN-3, Gonzalo; CALN3-03 sigue):
   - b2 t1: «**Already on the Rosario Islands**» sin nada debajo.
   - b4 t1: «**Precios por persona (online / normal):**» sin un solo precio.
3. **El catálogo entero y bloques que nadie pidió** (CALN-3 / hechos; CALN3-10/11 siguen):
   - b4 t2: los 6 planes de buceo, el alojamiento de los cursos de 2 días (nadie hace un curso) y «Te recomiendo el
     plan de 2 inmersiones» a una familia que va 5 días.
   - b9 t1: 4 planes de buceo y qué llevar, sin pedirlos.
   - b2 t3: el repaso de él sin precio.
4. **El grupo leído a medias** (CALN-2, Álvaro):
   - b1 t1: «mi esposo y yo somos Advanced, nuestro hijo de 11… mi suegra…» → grupo 2 (cuenta solo a los buzos);
     t2: reparto {acompañante 1, buceo 1} en un grupo de 2 (se pierden un buzo y el niño). Se arregla solo en t3.
   - b2 t2: «I'd like to try the mini course… He hasn't been diving in 3 years» sin reparto → tarjeta «Dive Mini
     Course 2 × 134 USD» para una pareja en la que él es buzo.
   - b6 t1 y b9 t1: «4 tenemos certificación y 2 dudan», «5 buzos certificados y 3 que nunca han buceado»: sin
     reparto.
   - b11: «el Advanced y también Nitrox» no deja actividad (CALN3-04 sigue).
5. **El reparto olvida a quien escribe y una regla del código le cambia la actividad** (CALN-2, Álvaro):
   - b5 t1, «Yo tengo el Open Water y quiero bucear. Mi esposo no bucea y vamos con los niños, de 7 y 4»: el
     extractor da {companion 1, undecided 2} y grupo 3 (sin ella). La regla de negocio pone `certified_diving`
     (certificada y quiere bucear, las dos cosas dichas) y la regla CAL-F de `extractor_turno` («si la actividad no
     es de nadie del reparto, manda el reparto») la cambia a `companion`: quien escribe queda de acompañante, el
     grupo en 3, y así sigue en t2.
6. **El reparto que suma a los nuevos se descarta y la certificación se vuelve a preguntar** (CALN-2, Álvaro):
   - b6 t2, «se suman dos amigos más que también están certificados, así que somos 8. Los dos que dudaban hacen el
     minicurso»: el extractor da {certified_diving 2, minicourse 2} (solo lo nuevo; los 4 de t1 no estaban
     guardados) y `GROUP_ALLOCATION_INCOMPLETO` lo descarta (4 de 8). Sin `is_certified`, el bot pregunta «¿me
     confirmas que tienen su certificación?» a quien lo ha dicho dos veces.
7. **«book me» no es 1** (CALN-2 / extractor): b8 t2, «book me for the dive + refresher» → «how many people should I
   plan for?».
8. **El origen dicho no se guarda y se vuelve a preguntar, en singular** (ORIGEN-CONFIRMA / extractor; CALN3-07 y
   CALN3-Q07 siguen):
   - b1 t2: «¿Desde dónde saldrías?» tras «vamos a pasar unos días en Cartagena».
   - b5 t2: «¿Saldrías desde Cartagena o ya estás en las islas?» tras «estamos alojados en Cartagena», y con los
     enlaces de Cartagena ya dados. Detrás, «Reserva con el de tu punto de salida.» suelto.
   - b4 t1: «¿saldrías?» a una familia de 5.
9. **Una edad mal razonada** (CALN-4/6, nota de edades; la misma causa que banco-edades e5): b5 t1, respuesta
   adelantada (RAG5) sin la nota: «El snorkel es desde los 6 años… Con 7 y 4 años, ninguno alcanza la edad mínima».
   El de 7 sí puede; lo corrige cuando el cliente lo pregunta (t2).
10. **Lo mismo dicho dos o tres veces** (CALN-6, Gadea):
    - doble saludo en 4 de los 10 primeros turnos con la presentación: «Bienvenidos…» del escritor (b1, b3) o
      «¡Con mucho gusto te ayudo…!» repitiendo el fijo (b5, b6); b9 sin la presentación (camino del pase).
    - b8 t2: la recogida en el hotel en tres párrafos.
    - b2 t3: los enlaces (texto y tarjeta) y la nota de la moneda, dos veces.
    - b9 t1: lo médico al principio y al final; b7 t1: lo que incluye, en el texto y en la tarjeta.
11. **Dos preguntas o la pregunta en medio** (CALN-6, Gadea): b2 t2 («adding the refresher?» y «anything else?»), b5
    t2 («¿te paso con un asesor?» y «¿saldrías…?»), b11 t1 (la pregunta y detrás un párrafo suelto del punto de
    encuentro).
12. **Sin dueño todavía:** b10 t2, «mejor el minicurso los dos… el sábado en vez del viernes»: la actividad guardada
    sigue en snorkel (CALN-2) y el cambio de fecha sin reserva va al asesor (Jev changes_date / ya_reservado).

**Latencia:** 14 de 22 turnos pasan de 8 s (mediana 8,5 s; b1 12-13 s cada turno, b2 t2 10,7 s); el máximo baja de
16,9 a 13,4 s.

## CALN3-R01..R06 · 3.ª tanda de PRECIOS, sobre el paso 2 de Gonzalo (feature/caln-gadea 818f820, 28-oct, `charla_rama`)

Cinco personas (`docs/robustness/g3/charlas-rama/r*.jsonl`), 8 turnos.

1. **BIEN: «¿cuánto cuesta bucear?» ya da precio** (r1, el p17 de ayer): los dos candidatos (buceo con certificación y
   minicurso) × los dos orígenes, en USD y COP (sin nacionalidad) y una sola pregunta.
2. **BIEN: tres días durmiendo en Cartagena** (r5): las salidas de cada día; los paquetes piden dormir en las islas.
3. **El descuento de grupo ofrecido a un curso PADI, otra vez** (CALN-3, Gonzalo): r4, 5 amigos y el Open Water,
   «10 % para grupos de 5 o más, que se suma al online… ¿te paso con un asesor para gestionarlo?». Le llegan dos hechos
   que se contradicen: con el precio, «no aplica a cursos PADI» (paso 2b); en la lista de descuentos, el texto del de
   grupo, que sale solo de la descripción de discounts.json (la excepción de los cursos está en `applicability`, que no
   se lee). El escritor se queda con el segundo.
4. **El catálogo entero de paquetes** (CALN-3, Gonzalo): r2 t1, el buzo que estará «una semana» recibe los paquetes de
   3, 4, 5, 7 y 9 inmersiones; la decisión 2 es 2-3 candidatos. Con la actividad elegida, `otros_planes` va entero.
5. **«My wife has never dived» = minicurso** (CALN-2, Álvaro): r2 t1, reparto {certified_diving 1, minicourse 1}; en
   la lista de nombres del minicurso está «nunca ha buceado», así que cuenta como que lo eligió. «No asumir»: sin
   decidir y se le recomienda.
6. **El colombiano pasa a un asesor en el primer turno** (decisión de Gadea): r3, familia de 5 de Bogotá en Isla
   Grande, «¿qué precio tiene y hay descuento por ser 5?» → tarjeta (5 × 150.000 COP) y «Les paso con un asesor para
   coordinar el pago», y el escritor dice «el precio te lo confirma el asesor» encima de la tarjeta que lo da.

## CALN-S29-01..08 · Sparring de clientes nuevos contra PRE 0.38.0 (29-oct, `charla_pre`)

Seis personas que no salen del golden (`docs/robustness/g3/charlas/6771-6776.jsonl`), 14 turnos: pareja de Madrid en
Isla Grande (buzo + nunca buceó), familia de Bogotá con niños de 7 y 11, buzo Advanced canadiense con 3 años sin bucear,
residente venezolano con cédula de extranjería, grupo de 6 (4 colombianos y 2 alemanes) y posventa (cambio de fecha
por enfermedad).

- **BIEN:** el almuerzo NO incluido desde las islas y SÍ desde Cartagena; los precios de las islas en USD al de Madrid;
  la tarjeta sin total («por persona · N personas»); edades (snorkel desde 6, minicurso al de 11); el refresher de quien
  lleva 3 años, como minicurso; el residente con cédula paga en pesos; el grupo mixto paga todo en USD; el colombiano
  pasa al asesor al querer pagar; el cambio de fecha pasa al asesor con el enlace de los términos.

1. **La nota fija de la tarjeta contradice la moneda** (Gadea): «_El precio es el mismo en pesos (COP) o dólares (USD)_»
   sale en TODA tarjeta (`cart_render._goto_mixed_final_summary`), también al de Madrid (USD) y al grupo mixto, justo
   debajo de «pagan toda la reserva en dólares». Solo tiene sentido cuando van las dos monedas (sin nacionalidad).
2. **La explicación del pago del colombiano, dos veces** (Gadea): «¿cómo pagamos?» → el escritor explica el 100 % online
   o el 50 % con enlace/QR/Llave y el cierre del colombiano (`slotfill_close._finalize`) lo repite debajo.
3. **CALN-8 (3): el escritor ya no sabe la regla de la transferencia** (Gadea): «¿puedo pagar por transferencia? ¿me
   hacen el 10 %?» → «no tengo confirmado» dos veces. La regla está en policies.json (si falla el pago online, enlace
   para transferencia y se mantiene el 10 %); antes iba en el prompt y ahora ni en los hechos ni en lo que se busca.
   Arreglo por causa (como CALN-7): con la intención de pago de Jev, las políticas de pago en los hechos.
4. **«I'm staying in Cartagena old town» no da el origen** (Gonzalo, CALN-3c b): los dos orígenes y «would you leave
   from Cartagena?»; el cliente: «I told you I'm staying there». La misma clase que «sin ir de Cartagena».
5. **El texto de la recomendación del plan**: «(Si prefieres un *paquete multi-día* de 3 o más inmersiones…)» debajo de
   una lista con el «Paquete de 3 inmersiones (1 día…)»: el de 3 no es de varios días.
6. **«Elijan la fecha y las dos personas»** con una tarjeta por persona (él buceo, ella minicurso): cada enlace es de 1.
7. **¿Enlace de la web al grupo mixto?** (decisión de Gadea): 4 colombianos y 2 alemanes, todo en USD → la tarjeta con el
   enlace de la web. El juez de la rotativa lo marcó dos veces («los colombianos no reciben el enlace»); pero el grupo
   paga en USD, que es lo que cobra la web.
8. **Menor:** el cambio de fecha por una hija enferma pasa al asesor «para preguntas médicas específicas».
