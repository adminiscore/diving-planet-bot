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

## CALN-S30A-01..12 · Sparring de clientes nuevos contra la CANDIDATA 0.39 (30-oct, `charla_rama`)

Primera tanda con la meta nueva de Gadea (cerrar CALN con dos tandas seguidas sin fallos graves). Candidata
`feature/caln-integra039-gadea` 27d5e2c1 (caln-gadea + s29 + feature/caln8-sino-alvaro 9c58185). Ocho personas
(`docs/robustness/g3/charlas-rama/s30a-*`): familia de Bogotá de 5 (abuela que no se mete, niños de 8 y 11), alemán
con Open Water y 3 años sin bucear (dos días), pareja de Valencia en Isla Grande (buzo + nunca buceó), paisa con doble
nacionalidad que vive en Miami (Open Water para mañana), empresa de 8 de EE. UU. (3 certificados, factura), buzo
argentino que regatea con equipo propio, padre buzo con hija de 12, tres franceses (snorkel, uno se marea). Graves
contrastados contra PRE (`docs/robustness/g3/charlas/` s30a-pre-*).

- **BIEN:** actividades por edad (Bubble Makers no a los 12) y la abuela de acompañante; la tarjeta de la familia sin
  total, en COP; la pareja de Isla Grande: reparto 1 + 1, precios de las islas en USD, recogida y vuelta, un enlace por
  actividad; la empresa: precios por persona, el de grupo explicado corto y la factura al asesor; regatear: no hay precio
  especial y equipo propio + online sí se suman; «tengo la colombiana» corrige y contesta lo de mañana; el padre con la
  hija: minicurso para ella y buceo para él, al asesor por ser colombiano.

**Graves (3; ninguno nuevo de la candidata):**
1. **«Mi esposo y yo hacemos el minicurso» → minicurso ×1 + 1 sin elegir** (familia t2; Álvaro, modelo del grupo):
   `[CORE] merged companion activity minicourse x1` y el lector «nada que rellenar»; pregunta «¿un día o varios?» a
   «quien aún no ha elegido». Con la corrección del cliente sale bien. **También en PRE** (s30a-pre-familia): no lo trae
   la candidata. Misma clase que «both of us».
2. **«¿Nos suman el de grupo, el de equipo y el online? ¿Cuánto por persona?» → sin respuesta** (regateo t2): CALN-3
   quita las dos frases del escritor con el descuento de grupo («fuera, lo da la pieza») y queda «Hay que pedir que lo
   apliquen antes de pagar. No puedo calcular el precio final por persona» + la lista ENTERA de descuentos pegada (con la
   regla de que no se suman enterrada dentro). **También en PRE** (peor: sin texto del escritor). Es la lista de arq-7b.
3. **El refresher en inglés: dos actividades contestadas con los hechos de una** (refresher t2, «refresher on day one
   and normal dives on day two?»): «I can't confirm whether you can add regular dives on a second day» / «the available
   plan for the second day is the 2-day 4-dive package». NO es de la candidata (lo vio Álvaro, #2628; yo lo había
   contado con 200 caracteres): PRE 0/7, base 1/6, base + s29 2/6, rama de Álvaro 1/6, candidata 3/7. Causa: el escritor
   contesta solo con los hechos del refresher (`redactor_hechos._con_el_escritor`, sin búsqueda, «refresher
   ['incluye']») y el buceo del día 2 (detected_activity certified_diving) no le llega. Mío (los hechos).

**Medios:**
4. La lista ENTERA de descuentos pegada en 4 turnos (familia t1 y t2, regateo t1 y t2), con «ANTES» y «COMPLETO».
5. «Mal de mer» (mareo) → pasa al equipo «para preguntas médicas»: misma clase que la embarazada (pendiente de Gadea).
6. «Soy paisa, tengo doble nacionalidad» → «el precio depende de si conservas la nacionalidad colombiana» (la política de
   la moneda); y «¿podría empezar mañana?» sin contestar en t1.
7. «También incluye» con tres seguros y dos entradas al parque al juntar minicurso, snorkel y acompañante (familia t2).
8. El refresher: el escritor lo pone en otro día y la tarjeta dice «the guide runs the in-water review before the dive»;
   los enlaces, dos veces (refresher t3).
9. Sin el origen, «Fun Dives also includes lunch», como si el minicurso no lo incluyera (refresher t1): CALN-9b.

**Menores:** Getsemaní y Bocagrande (barrios de Cartagena) → los dos orígenes y «¿saldrías desde Cartagena?» (la clase de
«staying in Cartagena»); «No hay descuento por ser colombiano» sin que lo pregunte; la pregunta del asesor dos veces en
el mismo mensaje y otra que no va al final; al francés se le contesta en inglés y con los precios también en COP; el
menú entero de actividades después de proponer el plan (pareja t1); «Te dejo a continuación los precios».

## CALN-S30E-01..10 · 2.ª tanda de sparring contra la CANDIDATA 0.40 (30-oct, `charla_rama --env RAG_KB_ESQUEMA=kb_v2_gadea`)

Candidata `feature/caln-integra040-gadea` 9b11f6b9 (0.39 + 10b + s30a + respuestas de negocio + la rama de Álvaro), con
la base curada de la rama. Ocho personas nuevas (`docs/robustness/g3/charlas-rama/s30e-*`): luna de miel canadiense en
Barú, abuelo de Medellín (70, operado de la rodilla) con nietos de 9 y 13, despedida de soltera de 7 madrileñas (2
certificadas), australiano que pasa del Open Water a probar en un día con la novia en snorkel, venezolano con cédula de
extranjería y esposa colombiana, madre con un niño de 7, dos de Chicago que quieren bucear HOY, colombiano al que le
rechazan la tarjeta. Graves contrastados contra PRE (`docs/robustness/g3/charlas/` s30e-pre-*).

- **BIEN:** USD y no dólares canadienses; el minicurso a la luna de miel y la salida privada al asesor; el niño de 7:
  snorkel (Bubble Makers desde 8, minicurso desde 10) y la madre el minicurso a la vez; la despedida: 2 buceo + 5
  minicurso, el de grupo y «españolas → USD»; el cambio de plan (un día → el minicurso, la novia snorkel); la tarjeta
  rechazada: al equipo con la regla de la transferencia (se mantiene el 10 %); el venezolano, cuando insiste, «los dos en
  pesos»; la rodilla operada pasa al equipo (es médico, decisión «salud») contestando antes lo demás.

**Graves (3; ninguno nuevo de la candidata; 1 y 3 arreglados en feature/caln10b-espera-gadea f5b2661d):**
1. **«¿Podemos bucear HOY?» a la 1:45 pm → «sí, reservad para hoy en la web»** (hoy-mismo t1 y t2). La salida es a las
   8:00 y la web cierra a las 4:30 PM del día anterior: para el mismo día no hay. Los hechos de disponibilidad
   (`availability_always`: «siempre hay disponibilidad») no dicen nada del mismo día. **También en PRE.**
2. **Venezolano con cédula de extranjería + esposa colombiana → «grupo mixto, todo en USD»** (venezolano t1): el
   extractor marca mixed_nationality (`[EX8] grupo con nacionalidades mezcladas: USD`) sin mirar que con cédula de
   extranjería es residente (paga en pesos, `colombian_pricing`). **También en PRE.** Es la definición de mixed del
   extractor. **Probado y DESCARTADO** (30-oct): la frase «mezcla colombianos o residentes con extranjeros que no lo son»
   en la regla del extractor deja el venezolano en mixed 7/10 y empeora los casos que cambian del ex0 ×10 (aciertos
   142 → 133, inventados 34 → 40); el extractor ya lee is_colombian true (10/10) pero a la vez mixed, y el código da
   preferencia al mixto, que no se puede separar por código del «colombiano con amigos alemanes». Queda abierto.
   (`scripts/sonda_residente_mixto.py`, `docs/robustness/caln/sonda-residente-mixto-30oct.txt`)
3. **El nieto de 13 «puede hacer buceo certificado»** (abuelo t1): nadie dijo que esté certificado; los hechos de edad
   del buceo certificado (mínimo 10) no dicen que pide la certificación. PRE lo dijo con «si cuenta con certificación»
   (1 charla por lado: puede ser variación del escritor).

**Medios:** «¿se puede llevar cava?» sin contestar dos veces (está `no_alcohol_policy`: nada de alcohol antes de bucear);
el texto largo del de grupo (con «ANTES») pegado en la despedida; «would you leave from Cartagena?» con Getsemaní y el
hotel del centro (la clase de «staying in Cartagena»).

**Menores:** la moneda dicha dos veces a la luna de miel; «No calculo el precio final con el descuento aplicado»;
«La cédula de extranjería no cambia la moneda: para pagar en pesos debes ser residente» (se contradice con lo que sigue).

## CALN-S03G-01..08 · 3.ª tanda de sparring contra PRE 0.42.0, hasta reservar (3-nov, `charla_pre`)

Primera tanda con CALN-13 (charlas hasta reservar) y el criterio de gravedad de Álvaro (#2716: GRAVE si reserva mal o no
puede: importe, moneda, enlace o plan del otro origen equivocados, fecha u horario falsos, consejo inseguro, lo contrario
de una política, un callejón sin salida, la misma pregunta por 3.ª vez; MEDIO si reserva con fricción; MENOR, el estilo).
Ocho personas (`docs/robustness/g3/charlas/` 6789-6796): pareja de Lima en Getsemaní (ella OW, él nunca), familia de Cali
con niños de 6 y 10 en Bocagrande, inglés Advanced en Isla Grande que quiere el paquete de 4 inmersiones, 5 sevillanos (3
snorkel + 2 acompañantes), nacida en Cartagena con solo pasaporte de EE. UU., paisa con OW y 4 años sin bucear que quiere
el Advanced, factura de empresa y transferencia «porque sí», indeciso que acaba pidiendo el 25 de diciembre.

- **BIEN (6 de 8 llegan a reservar o al asesor):** Getsemaní y Bocagrande ya dan Cartagena (los barrios de la 0.42); un enlace
  por actividad y las tarjetas; los niños por edad; el acompañante cuenta para el grupo y tiene el descuento (decisión del
  30-oct); el pasaporte de EE. UU. paga en USD; refresher + Advanced = 3 días con la noche en las islas y, bajo cada origen,
  cómo se llega y el almuerzo (9b); la transferencia solo si falla el online; el 25 de diciembre cerrado y el 26 sí.

**Graves (1):**
1. **El paquete de 4 inmersiones desde las islas no se puede reservar** (advanced-islas t1-t3): da
   `https://divingplanet.org/buceo-islas-del-rosario/` (la página informativa) como «Book here» e insiste en que es la buena
   cuando el cliente dice que solo ve información. En services.json, `4_dives_2_days_already_on_island` (y los demás
   paquetes) no tienen `booking_url`, solo `url`. Sin enlace de reserva, debería pasar al asesor (como hace con el
   acompañante). Zona: hechos y datos (Gadea). Pregunta para Andrés: ¿enlace de reserva de los paquetes?

**Medios:** la lista entera de descuentos pegada otra vez (cinco amigos t1 y t3, aunque preguntan por uno: precios y
descuentos, Gonzalo); «I've lived in Miami since I was a baby» → «You mentioned minors are coming, what are their ages?»
(miami t3; la lectura, Gadea); «entonces lo hago el 26 de diciembre» leído como un CAMBIO de fecha → términos y pase al
asesor (indeciso t3; Jev, Gadea); la factura sin contestar en t1 y t2 («no tengo información») y bien solo cuando se
pregunta sola en t3 (la laguna CALN-11); el precio que pidió el indeciso en t2, olvidado.

**Menores:** «¿cuántas personas?» cuando dijo «yo»/«I» (advanced-islas, miami, advanced-curso); la moneda dicha dos veces;
la pregunta del asesor dos veces en el mismo mensaje; «Te dejo a continuación los precios».


## CALN-S03A-01..08 · Tanda de Álvaro (CALN-13) contra PRE 0.42 (3-nov, `charla_pre`)

PRE 0.42 6044e417. Ocho clientes nuevos hasta reservar (`docs/robustness/g3/tanda-alvaro-caln13.md`, conv 6797-6804 en
`docs/robustness/g3/charlas/`), con el criterio de gravedad de Álvaro adoptado para las dos tandas (#2716): GRAVE = el
cliente reserva mal o no puede reservar (importe, moneda, enlace o plan de otro origen; fecha, horario o
disponibilidad falsos; consejo inseguro; lo contrario de una política; callejón sin salida; la misma pregunta por 3.ª
vez). Cada grave, ×3 por versión con `charla_rama --codigo-local` (`docs/robustness/g3/charlas-rama/s03a-graves/`).

- **BIEN (6 de 8 llegan a reservar o al asesor):** el crucero (horario 8:00 → 4:15 y «muy justo», honesto); los cuatro
  estudiantes (Getsemaní → Cartagena con los barrios de la 0.42, sin descuento de estudiante, el de grupo no aplica a 4);
  la madre con hijos de 15 y 17 (Bocagrande → Cartagena, COP por ser de Cali, al asesor con el resumen y el pago); el
  cambio de fecha + hermano (posventa al asesor y sigue contestando); la pareja brasileña (mareo, tarjeta con
  pasaporte); el colombiano en Madrid (pesos, sin euros, al asesor al decir «sí»).

**Graves (2):**
1. **Silla de ruedas (DIVE TO HEAL) no llega nunca al asesor** (conv 6799 t3-t5): «sí, pásame con el asesor» tres veces;
   el bot vuelve a ofrecerlo, dice «no puedo transferir… ¿dejo registrada tu solicitud?» y luego «no puedo registrar…».
   Callejón sin salida con el cliente que más necesita a una persona. **6 de 6** en `charla_rama` (0.41 3/3, 0.42 3/3):
   viene de antes. Causa: con `adaptive_diving_context` el router manda todo a SAFETY/INFO de DIVE TO HEAL y la cascada
   (`supervisor._shared_turn_handler`) contesta con el texto fijo o el RAG ANTES de los pases por `wants_human` y por el
   «sí» a la oferta del asesor. **Arreglado en la 0.44** (Gadea, `feature/s03a-dth-gadea` 1ed89f4d, `charla_rama` 2/2):
   un solo gate del pase (`supervisor.pase_pedido_o_aceptado`) mirado antes de DIVE TO HEAL en los nodos de escalado e
   info y en la cascada; gen-13 contesta delante lo demás. La versión de Álvaro (en el router, el nodo de escalado y la
   cascada; sin subir) hacía lo mismo y se descarta: la de Gadea además quita las dos copias del pase.
2. **SSI + nitrox: «Reserva y paga aquí: https://divingplanet.org/tours-buceo-snorkel-cartagena/»** (conv 6798 t4), la
   página informativa como enlace de reserva. **0 de 6** en `charla_rama` (0.41 0/3; arreglo s03g de Gadea 9a1a1fe7
   0/3): azar del escritor, de la misma clase que el grave de s03g de Gadea.

**Medios:**
- La tarjeta final sin el nitrox después de «reservo las dos» (5 de 6 repeticiones) y una vez «no tengo aquí el enlace de
  reserva del curso de Nitrox», aunque el enlace existe (SSI t3/t4).
- La teoría online del Open Water: «no tengo confirmado si debe hacerse antes de llegar», aunque la base lo dice (madre
  t2; la clase de CALN-11).
- El paquete con inmersión nocturna ofrecido a quien vuelve al barco a las 17:00 (crucero).
- «¿Saldrías desde Cartagena?» con el barco atracado en Cartagena (crucero), y en portugués «estamos em Cartagena»
  (brasileños); la clase de CALN-3b.
- «¿Puede pagar cada uno con su tarjeta?» → «no lo tengo confirmado», sin dato en la base (CALN-12), y «este sábado» sin
  contestar (estudiantes).
- El precio del nitrox «ya en las islas» antes de saber el origen, y «un par de buceos normales… no lo tengo a la mano»
  (SSI t1-t2).
- La lancha accesible y el precio del minicurso de la hermana sin contestar hasta que insiste (silla t2).

**Menores:** «bacano» a un argentino; el enlace de reserva dos veces (crucero); la pregunta del origen dos veces en el
mismo mensaje (Madrid t1).

## CALN-S03H-01..08 · 5.ª tanda de sparring contra PRE 0.44.0, hasta reservar (3-nov, `charla_pre`)

Ocho clientes nuevos, cada uno hasta la tarjeta, el enlace o el asesor, con el criterio de gravedad de Álvaro (#2716):
japonesa alojada en Barú y vegetariana (6805), 10 amigos de Ámsterdam, 6 buzos y 4 de snorkel (6806), padre buzo con su
hija de 17 que quiere el Open Water (6807), pareja chilena de 65 y 68 sin experiencia (6808), alemán con cédula de
extranjería, el minicurso solo (6809), cambio de fecha de una reserva ya hecha (6810), madre acompañante con el bebé de 2
años mientras el marido bucea (6811), buzo canadiense que pide un nocturno (6812). Cierre: 2 con enlace (snorkel,
minicurso), 6 al asesor y la pastilla de la tensión al equipo.

- **BIEN:** Barú no son las islas, sale desde Cartagena (`baru_departs_from_cartagena`); el alemán con cédula de
  extranjería paga en pesos y lo cierra un asesor (decisión del 21-oct); el cambio de fecha CON reserva va al asesor con
  los términos; los chilenos en USD con su enlace, «no hay edad máxima» y el formulario médico; la tensión, al equipo (es
  médico); «todos han buceado este año» → sin refresher; los holandeses en USD y el de grupo «pedirlo antes de pagar»;
  «next Tuesday is November 10».

**Graves (2):**
1. **Pide el nocturno y la tarjeta es la de 2 inmersiones de día, con su enlace** (nocturno t2 y t3). A «Yes, I want the
   night dive package, that's why I asked» repite la misma tarjeta y el mismo enlace; solo a «the 3-dive package with the
   night dive» (t4) pasa al asesor. Reproducido con `charla_rama` en la 0.44 (`noct1`): el estado nunca guarda el plan
   (`detected_cert_dives` vacío) y `_resolve_cert_plan` cae en el de 2. Causa: el plan del certificado solo se elige por la
   cifra de inmersiones (R1, `dive_counts_in`) o de días; «el nocturno» no lleva cifra, y `plan_que_propone_el_bot` solo
   mira los paquetes de varios días (el de 3 con nocturna es de 1 día). Zona: la lectura (Gadea). **APARCADO** hasta
   después de CALN (decisión de Gadea, 3-nov): como campo del extractor, cada una de 6 redacciones movía otra lectura
   del ex0 (`docs/robustness/caln/sonda-plan-nocturno-3nov.md`).
2. **El bebé de 2 años «puede ir en la lancha» y «paga la tarifa de acompañante»** (madre t1 a t4). La base no dice nada
   de bebés a bordo; en t2 decía «no tengo confirmado si debe pagar» y en t4 lo afirma, con la tarjeta de 2 acompañantes.
   Un hecho y un importe inventados. Regla de Gadea (3-nov): a cualquier edad y no pagan (`policies.babies_onboard`,
   276e20e8); con ella el escritor lo dice bien (bebe2). Queda la cuenta en el grupo: el bebé sale como acompañante que
   paga o como persona «sin elegir» (bebe1; grupo, propuesta #2798 a Álvaro). El extractor no cuenta al bebé de forma estable
   (`scripts/sonda_bebes_grupo.py`, ×5: «Somos 2 y llevamos a nuestro bebé» → 2; «a couple with our 3-year-old» → 3):
   restarlo del total por código rompería el primero. Va donde se lee el grupo, medido con el banco (Álvaro).

**Medios:** «I don't have details on vegetarian options» en t1 y t2 (mensajes con tres preguntas), aunque
`food_policy` lo dice (arroz con vegetales); a la 3.ª, sola, lo contesta (la pregunta diluida, CALN-11, Álvaro). «2 are
Advanced» leído como 2 personas más que hacen el curso Advanced: 12 personas, el precio del curso en la lista y dos veces
«el descuento no aplica a cursos PADI»; en t2 pide confirmar «12 → 10 personas» que el cliente acababa de decir (la
lectura, Gadea).

**Menores:** «¿Quieres que te pase con un asesor?» dos veces en el mismo mensaje en los cierres en pesos (alemán t2,
madre t3) y, en padre-hija t2, «¿quieres que te pase?», «Les paso con un asesor» y otra pregunta (el refresher) seguidos;
el refresher preguntado a «alguno de ustedes» cuando la hija nunca ha buceado; «It must be requested from the team before
paying» sin sujeto. La clase CALN-9b (lo que incluye según el origen, #2794) no ha salido: el nocturno t1 rotula
«lunch included» y «no lunch» por origen.

**Meta:** la tanda tiene graves, así que siguen 0 de 2 seguidas sin graves.

## CALN-S03I-01..08 · 6.ª tanda de sparring contra PRE 0.45.0, hasta reservar (3-nov, `charla_pre`)

Ocho clientes nuevos, cada uno hasta la tarjeta, el enlace o el asesor, con el criterio de gravedad de Álvaro (#2716):
cuatro amigas de Medellín, snorkel, con cava para brindar y la hora de vuelta (6813); pareja de Manchester que prueba el
buceo, almuerzo vegano y el trayecto (6814); familia de Bogotá, los padres Open Water y los hijos de 11 y 7 (6815);
Open Water que quiere el Advanced, 4 días en Cartagena (6816); pareja francesa principiante, con mareo (6817); 12
compañeros de una empresa alemana, 4 buzos y 8 sin experiencia, con factura (6818); Open Water de hace 5 años con su
novia que nunca ha buceado (6819); hermanos de Cali, minicurso, efectivo el día (6820). Cierre: 3 con enlace
(veganos, Advanced, francesa), 5 al asesor (cava, familia, empresa, novia, Cali).

- **BIEN:** el almuerzo vegano (arroz con vegetales) y el trayecto de una hora en un mensaje de dos preguntas (CALN-11);
  minicurso para el de 11 y snorkel para el de 7 (Bubble Makers es de 8 a 10); el Advanced con la noche en las islas, su
  enlace y su precio; a la francesa, en inglés, el desayuno ligero y las pastillas del mareo (antes no lo encontraba); el
  efectivo solo para el 50 % del día; «no puedo confirmar el total» a la novia; el refresher «es el minicurso, en su
  propio día»; la empresa, ya con el asesor, recibe los precios y el de grupo (20 %, pedirlo antes de pagar). La francesa
  reserva para mañana: en Colombia son las 14:20 y la web cierra a las 4:30 p. m., así que está bien.

**Graves: ninguno.** Primera tanda sin graves: la meta va **1 de 2**.

**Medios:**
- **El cava, sin contestar dos veces** (amigas t1 y t2, «no tengo ese dato confirmado»), aunque `no_alcohol_policy` lo
  dice. Los dos turnos cierran con la tarjeta del snorkel: contesta el escritor con los hechos, sin búsqueda, y CALN-11 no
  llega (la ruta que Álvaro vio con la vegetariana, #2827). Zona: hechos y escritor (Gadea).
- **«Para quien aún no ha elegido: ¿un día o varios?»** cuando ya habían elegido todos (Cali t2: los dos el minicurso;
  novia t2). La lectura del grupo (Álvaro, la pieza del bebé y el R8).
- **«You'll need to complete the online theory»** para el minicurso (francesa t2): la teoría es del Open Water. Hecho
  inventado del escritor.
- **El refresher y la salida de 2 inmersiones el mismo domingo** (novia t3: «un solo día, yo el refresh y la salida»): el
  carrito lleva los dos y el texto dice «en su propio día», pero no le avisa de que en un día no caben. Lo coordina un
  asesor (pago en pesos), así que nadie reserva mal; al límite de grave.
- **La empresa pasa al asesor en t1** por la factura, antes de dar precios o el de grupo (los da en t2).
- **«El equipo debe confirmar la disponibilidad de la fecha»** (familia t2), contra `availability_always`.

**Menores:** la pregunta del asesor dos veces en los cierres en pesos (cava t1, familia t3, novia t3); «And how many
people should I plan for?» al que dijo «I» (Advanced t1); los buceos certificados en la lista de precios de la francesa
principiante; el refresh explicado dos veces (novia t1).

**Corrección (4-nov, 01:25):** la «teoría del minicurso» NO es un hecho inventado: `services.json` la pide para el minicurso desde Cartagena (`minicourse`: «Después de reservar recibirás un correo con instrucciones para completar la teoría. Es indispensable terminarla antes de comenzar la práctica»; requisito «Completar la teoría antes de empezar la práctica»). Desde las islas (`minicourse_already_on_island`) no la pide. Pregunta para Gadea: ¿el minicurso lleva teoría previa, y desde los dos orígenes?

## CALN-S04A-01..08 · 8.ª tanda de sparring contra PRE 0.46.0, hasta reservar (4-nov, `charla_pre`)

Ocho clientes nuevos, educados y que escriben bien (decisión de Gadea: los difíciles, en la fase DIF), cada uno hasta la
tarjeta, el enlace o el asesor, con el criterio de gravedad de Álvaro (#2716): luna de miel de Lima, ella no nada bien
(6834); padre de Monterrey con sus hijos de 12 y 15, los tres al Open Water (6835); cumpleaños de 7 amigas de
Barranquilla, 3 con licencia y 3 sin experiencia (6836); Advanced de Vancouver en Isla Grande, Nitrox y fun dives
(6837); pareja de un crucero, a bordo antes de las 6 p.m. (6838); fotógrafo submarino de Denver (6839); 58 años con
prótesis de rodilla, primer buceo (6840); snorkel ya pagado y pronóstico de lluvia (6841). Cierre: 5 con enlace
(luna de miel, padre e hijos, Nitrox, crucero, fotógrafo), 3 al asesor (cumpleaños, rodilla, el cambio de fecha).

- **BIEN:** el Open Water desde 10 años, con la noche en las islas y el enlace para 3 en USD; el cumpleaños con buceo
  para las certificadas y minicurso para las demás, el 20 % de grupo pidiéndolo antes y el pago en pesos con un asesor;
  el crucero, «la vuelta a las 4:15 encaja con las 6 p.m.»; la rodilla, al formulario médico y al equipo; la lluvia,
  reprogramar o reembolsar con los términos; el cambio de fecha CON reserva, al asesor; el Nitrox desde las islas con su
  enlace; el almuerzo y lo vegetariano de quien sale de Cartagena (comprobado antes de la tanda, con la 0.46).

**Graves: ninguno.** La meta vuelve a **1 de 2** (la 7.ª, de Álvaro, tuvo 2 graves que ya estaban en la 0.44).

**Medios:**
- **Luna de miel, al límite:** «¿Con cuál te animas: buceo, minicurso, snorkel o un curso PADI?» en t2 y t3, el mismo
  texto, y en t4 «para quien aún no ha elegido: ¿un día o varios?», aunque dijeron «el minicurso para los dos» y en t3 ya
  tenían el enlace. La lectura del grupo (CALN-17). Además: «no sabe nadar bien → no puedo confirmar si es adecuado» (la
  FAQ dice que no hace falta ser buen nadador) y «el viernes 13, ¿de qué mes?» (es el 13 de noviembre).
- **Nitrox t1:** «I don't have that specific detail handy» a una pregunta del catálogo (la especialidad y fun dives desde
  Isla Grande); se recupera en t2.
- **Nitrox t3:** «no hay enlace para las 2 inmersiones desde las islas» (sí lo hay: fun-dives-already-on-island/19); al
  insistir el cliente, lo da. Puede venir de la lista de planes sin enlace de la 0.46 (s03j): ahí está la de 1 inmersión
  desde las islas, con un nombre casi igual. Vigilarlo.
- **Cumpleaños t2:** «¿Son buzos certificados?» cuando dijo «3 con licencia y 3 que nunca han buceado» (lectura del
  grupo).

**Menores:** el crucero con el precio y el enlace dos veces (texto y tarjeta); el fotógrafo con toda la lista de
requisitos pegada; «And how many people should I plan for?» al que dijo «I» (Nitrox); «Quieres que te pasemos con un
asesor» en el cumpleaños.

**Pregunta de negocio para Gadea:** ¿se puede traer una cámara propia a las inmersiones? ¿Se alquilan cámaras? El bot
dijo «puedes traer tu cámara», y la base no dice nada.

## CALN-S04B-01..08 · 9.ª tanda de sparring contra PRE 0.47.0, hasta reservar (4-nov, `charla_pre`)

Ocho clientes nuevos, educados y que escriben bien, cada uno hasta la tarjeta, el enlace o el asesor, con el criterio de
Álvaro: chico de 16 de Austin al Open Water y su madre snorkel (6842); sorpresa de cumpleaños para el marido certificado,
de Medellín (6843); 5 amigos Advanced de Cali, 2 días con nocturna (6844); pareja de Madrid, ella embarazada de 5 meses
(6845); pareja de Brasil en portugués, snorkel (6846); familia de Toronto en San Pedro de Majagua, niños de 9 y 11
(6847); Divemaster de Valencia, descuento para profesionales (6848); Rescue Diver sin bucear desde hace 3 años (6849).
Cierre: 3 con enlace (Austin, embarazada, Brasil), 5 al asesor.

- **BIEN:** el embarazo (no se bucea con botella; snorkel con el visto bueno del médico) y el minicurso para él; el menor
  de 16 acompañado por un adulto; la sorpresa para otro, con un asesor; en portugués, en inglés; el Divemaster, sin
  descuento profesional pero con el online y el 5 % de equipo propio, y el de 4 inmersiones al asesor (sin enlace); el de 5
  inmersiones con nocturna y el de grupo para los de Cali; el refresher del Rescue como el minicurso, en su propio día;
  el de 11 al minicurso desde las islas, el de 9 a Bubble Makers con un asesor.

**Graves (1):**
1. **El niño de 9 años en el minicurso** (Majagua t2): «can our 11-year-old do the mini course?» → tarjeta «Dive Mini
   Course (already on the islands) · 2 people» con el de snorkel de los padres. Reproducido ×3 con `charla_rama` (0.47): el
   reparto queda {snorkel 2, minicourse 2} en 2 de 3 (la 1.ª, bien: {snorkel 2, bubble_makers 1, minicourse 1}). El de 9
   no tiene edad (minicurso desde 10) y la tarjeta cobraría 2. La lectura del grupo (CALN-17, Álvaro): el resto del
   grupo pasa a la actividad que se elige sin mirar las edades sabidas ([9, 11]). Cuando el cliente aclara «solo el de 11»,
   lo confirma bien. **La meta vuelve a 0 de 2.**

**Medios:** «el catálogo no tiene una opción que coincida exactamente» y luego describe justo la que piden (Cali t1: 5
inmersiones en 2 días con nocturna), sin darle el precio de esa; «book here» con la página informativa (Brasil t1; al
preguntar, da el enlace bueno); «el minicurso incluye teoría online» (embarazada t2) y «antes de la práctica debes
completar la teoría» (Rescue t1): la teoría es del Open Water (CALN-19); «el equipo debe confirmar la disponibilidad»
(Cali t2, contra availability_always, CALN-19).

**Menores:** «¿para cuántas personas?» a quien dijo «soy» (Divemaster t2, CALN-18); el aviso de la hora límite de mañana a
quien pedía lunes y martes; el de grupo dicho dos veces; planes que no tocan en la lista de precios (el de 4 inmersiones a
la embarazada y al Rescue); la lista entera de requisitos pegada (Rescue t1).

**Corrección (4-nov, 01:25):** la «teoría del minicurso» NO es un hecho inventado: `services.json` la pide para el minicurso desde Cartagena (`minicourse`: «Después de reservar recibirás un correo con instrucciones para completar la teoría. Es indispensable terminarla antes de comenzar la práctica»; requisito «Completar la teoría antes de empezar la práctica»). Desde las islas (`minicourse_already_on_island`) no la pide. Pregunta para Gadea: ¿el minicurso lleva teoría previa, y desde los dos orígenes?

## CALN-S04C-01..08 · 10.ª tanda de sparring contra PRE 0.48.0, hasta reservar (4-nov, `charla_pre`)

Ocho clientes nuevos, educados y que escriben bien, cada uno hasta la tarjeta, el enlace o el asesor, con el criterio de
Álvaro: Open Water de Seúl al Advanced desde Isla Grande (6850); 6 universitarios de Bogotá sin experiencia y con poco
presupuesto (6851); buzo de Lyon con su hija de 13 al snorkel en la misma lancha (6852); matrimonio de Buenos Aires de 70 y
72, él con licencia y 10 años sin bucear (6853); minicurso el sábado con un vuelo a las 7 p.m. ese día (6854); despedida
de soltera de 10, snorkel (6855); de Pereira, minicurso ya reservado y quiere pagar solo el 50 % (6856); chilenos en un
hotel de Bocagrande, ¿recogida? (6857). Cierre: 5 con enlace (Seúl, Lyon, jubilados, vuelo, Bocagrande), 3 al asesor
(universitarios, despedida, el 50 %).

- **BIEN:** el Advanced desde las islas con su horario (la nocturna incluida), la teoría de 4 h, las 18 h antes de volar y
  su enlace; el minicurso para los universitarios, en pesos, con el 20 % de grupo y el asesor; padre e hija con sus dos
  tarjetas; sin edad máxima a los de 70 y 72, el refresher de él (el minicurso, en su propio día) y la acompañante para
  ella, al asesor; el vuelo: en t2, «tras el minicurso, al menos 12 horas: un vuelo a las 7 p.m. sería demasiado pronto»
  (la base: 12 h tras el minicurso, 18 h tras bucear certificado); la despedida de 10 con el de grupo; el 50 % de una
  reserva ya hecha, al asesor; sin recogida en hoteles de Cartagena, con el enlace en USD.

**Graves: ninguno.** La meta vuelve a **1 de 2** (la 9.ª tuvo 1 grave, arreglado en la 0.48).

**Medios (al límite, para que los mire Álvaro):**
- **Jubilados t2:** «Desde Cartagena. Somos argentinos. ¿Y mi esposa qué puede hacer?» → «¿Saldrías desde Cartagena…?» y
  «¿Desde dónde saldrías?» en el mismo mensaje (con la de t1, tres veces; contando por turnos, como Álvaro, dos). En t3
  («ya te lo dije») se disculpa y sigue bien. Además, a la esposa que no bucea solo le ofrece el minicurso hasta que dice
  «sin bucear» (la regla es recomendar las opciones: snorkel, acompañante, minicurso).
  **Causa (log de PRE, conv 6853 t2):** una carrera. La respuesta en paralelo (u3-4, adelantada con rag-5) decidía la
  puerta del origen antes de que la extracción de ESE mensaje guardara «Desde Cartagena»: el escritor acabó a los 2,28 s,
  y la extracción guarda el origen tras el extractor y el lector del grupo (Haiku los dos; el lector acabó a los 2,42 s).
  Salían los precios
  de los dos orígenes con `ORIGEN_TRAS_LAS_VARIANTES` y debajo, con el origen pendiente, la pregunta de la reserva. Con
  `charla_rama`, en local, el extractor ganó y salió bien (1/1). gen-15 lo cubría con Jev solo en `_origen_antes_del_precio`;
  la rama de la pieza (`_con_la_pieza`, CALN-3 paso 4) no lo miraba. **Arreglo** (feature/s04c-origen-gadea 7c42ecec): la
  puerta la pone `_take_parallel_answer`, cuando la extracción ya acabó (`_con_la_puerta`).
- **Vuelo t1:** con el vuelo a las 7 p.m. dicho, solo da la hora de vuelta; el aviso de las 12 horas llega en t2, antes del
  enlace.

**Menores:** «And how many people should I plan for?» a quien dijo «I» (Seúl, CALN-18); el Snorkeling Tour en la lista del
Advanced; «Hay que solicitarlo al equipo antes de pagar» sin sujeto (universitarios t1); «Es una reserva separada.» suelta
(jubilados t1).

## CALN-S04D-01..08 · 11.ª tanda de sparring contra PRE 0.48.0, hasta reservar (4-nov, `charla_pre`)

Ocho clientes nuevos, educados y que escriben bien, con el criterio de Álvaro: chicos de Medellín alojados en Playa Blanca,
snorkel (6858); dos amigas de Guadalajara, una con Open Water y otra nunca (6859); de Bogotá en un hotel con muelle en Isla
Grande, Open Water (6860); 4 de Múnich, 2 Advanced y 2 Open Water, dos días (6861); «solo tengo libre de 2 a 6 de la
tarde» (6862); minicurso de mañana ya reservado y con fiebre (6863); madre de Cali con hijos de 6, 8 y 12, snorkel
(6864); de Miami con 600 inmersiones y 3 años sin bucear (6865). Cierre: 2 con enlace (Múnich, Guadalajara), 5 al asesor,
y la de la tarde, sin salida a esa hora.

- **BIEN:** Playa Blanca es Barú: salen desde Cartagena; el de 4 inmersiones al asesor y el de 5 con su enlace para los 4
  de Múnich (el arreglo de s03j); el Open Water desde las islas en pesos, al asesor; los niños de 6, 8 y 12 al snorkel,
  acompañados; la fiebre con reserva hecha, al equipo; el de 600 inmersiones lo revisa el equipo (no se le pide el
  refresher de oficio); «no hay salidas por la tarde, los horarios son fijos»; las 2 inmersiones y el minicurso, cada uno
  con su enlace.

**Graves: ninguno.** Con la 10.ª (s04c), **dos tandas seguidas sin graves**: la meta de sparring de CALN, **cumplida**
(falta comprobar los bancos sin bajar sobre la 0.48).

**Medios:** las mexicanas t2, «¿cómo reservamos?» → la fecha «se elige en el enlace de reserva», pero sin el enlace, y
«¿te animas con la salida de 2 inmersiones, un paquete o un curso avanzado?» cuando ya lo habían dicho (en t3, los dos
enlaces); Playa Blanca t2, «ese enlace sirve para pagar» y a la vez «les paso con un asesor para coordinar el pago».

**Menores:** «¿saldrías desde Cartagena?» como confirmación cuando ya lo dijeron (Guadalajara t1; ORIGEN-CONFIRMA); «¿para
cuántas personas?» a quien habla en singular (Isla Grande t1, CALN-18); la pregunta del asesor dos veces (Cali t2); «¿con
cuál te animas?» a quien se despide (la tarde t2); la lista de requisitos entera (Miami t1); «From Cartagena, you have two
options:» con la lista vacía (Múnich t1); la fiebre como «pregunta médica».

## CALN-S04E-01..08 · 12.ª tanda de sparring contra la CANDIDATA 0.49, hasta reservar (4-nov, `charla_rama`)

Ocho clientes nuevos, educados y que escriben bien, contra `feature/caln-integra049-gadea` con `kb_v2_gadea`, con el
criterio de Álvaro: pareja de Barranquilla, snorkel (s04e-barranquilla); canadiense que da el origen y pregunta en el
mismo mensaje (s04e-canada); familia de Valencia, él Advanced, ella nunca ha buceado e hija de 14 (s04e-valencia); Advanced
en el Hotel Cocoliso que quiere el Nitrox (s04e-nitrox); 5 amigos de Lima, certificados, tres días (s04e-lima); de Texas,
Open Water con tres días libres (s04e-texas); madre de Medellín con un hijo de 7 años (s04e-nino7); reserva para mañana
con lluvia en el pronóstico (s04e-lluvia). Los dos graves se repitieron contra PRE 0.48 (conv 6866 y 6867): ya estaban.

**Graves (2, de antes, arreglados en la candidata):**
- **Barranquilla t2-t3, el asesor preguntado 3 veces.** t1: tarjeta en pesos con nuestra oferta. t2 («¿a qué hora
  volvemos?»): con la tarjeta ya vista va solo la respuesta (s4-26) y la oferta se perdía; el escritor cerraba con la suya.
  t3 «Sí, por favor»: no se reconoce (solo se reconoce el sí a nuestra frase) y vuelven la tarjeta y la oferta.
  **Arreglo** (feature/s04e-oferta-gadea d69c3863): si el cierre ofrecía el asesor, la nuestra cierra el turno y el
  compositor quita la del escritor (CALN-18). Con `charla_rama`: t3 → el pase.
- **Lima, tres días → el plan de 2 inmersiones.** «queremos bucear tres días seguidos»: el extractor da 3 días de buceo,
  pero los días del plan (`cert_days`) solo los leía el regex («paquete de 3 días», «3 días de buceo»): «Te recomiendo el
  plan de 2 inmersiones en 1 día» y la tarjeta de 2 inmersiones con su enlace, mientras el escritor daba el de 7.
  **Arreglo** (feature/s04e-dias-gadea ee5f0b9a): si el regex calla, los días son los del extractor. Con `charla_rama`:
  la tarjeta del paquete de 7 inmersiones (3 días).

La meta de sparring vuelve a **0 de 2**.

**Medios:**
- **Valencia t1:** quedan frases sueltas al quitar los importes del escritor («Lancha ida y vuelta, almuerzo y equipo
  incluidos.», sin el plan al que se refieren: la frase con el nombre y el precio salió). Y a la madre que nunca ha buceado
  le da el minicurso por hecho (lo corrige el cliente en t2).
- **Niño de 7 t2:** tras recomendar snorkel o acompañante, cierra con el menú genérico («¿buceo, minicurso, snorkel o un
  curso PADI?»), sin mirar los 7 años. t3: «¿Cómo reservamos?» no pasa al asesor (Jev no da la intención del enlace) y
  vuelve a ofrecerlo.
- **Lluvia t2:** «si no salimos por el mar, ¿me devuelven el dinero?» → «lo maneja el equipo», con `weather_cancellation`
  en la base (se reprograma; si no se puede, reembolso del 100 %). Preguntado con «si la Capitanía cierra las salidas por
  el clima», lo contesta bien: depende de la búsqueda.

**Menores:** «I'm leaving the price per person below» con los precios ya arriba (Canadá t1); los paquetes de 3 y 4 en la
lista de quien pidió dos inmersiones (Canadá t1, Valencia t2); el enlace dos veces (Canadá t2); «¿para cuántas
personas?» a quien habla en singular (Nitrox t1, CALN-18); la recogida dicha dos veces con matices distintos (Nitrox t1);
«¿Quieres…?» en singular a una pareja (Barranquilla t2); el pago explicado dos veces (niño de 7 t3).

**Bien:** el origen del mismo mensaje leído sin preguntarlo (Canadá); el Nitrox desde las islas con la recogida del
hotel base; los tres planes de la familia de Valencia con el acompañante para el asesor; el Open Water de 2 días con la
noche en las islas y el almuerzo solo el día 1; los 7 años: ni Bubble Makers (8) ni minicurso (10), sí snorkel (6).

## CALN-S04H-01..08 · Tanda de contraste de Gonzalo (2.º autor) contra PRE 0.49, hasta reservar (4-nov, `charla_rama` sobre 050e512a)

Criterio de Álvaro (#2716). Clientes nuevos, educados y que escriben bien (`docs/robustness/g3/charlas-rama/s04h-*`): matrimonio peruano (él Rescue, ella
nunca), 7 de Toronto (5 Open Water y 2 nunca, con el de grupo y equipo propio), venezolana con cédula y el paquete de 5, familia holandesa (Advanced con
nocturna, snorkel, hijo de 13 al Open Water, hija de 5), alemán en Bocagrande con 3 años sin bucear y vuelo, australianos en una casa de Isla Grande fuera
de la lista, el regalo de 2 inmersiones al padre, y pareja de Quito con bebé de 10 meses. Elegidos antes de ver nada; el regalo y el bebé, a propósito,
porque eran graves conocidos.

- **BIEN:** el regalo (al asesor, sin contar a quien paga) y el bebé (no paga; tarjeta para 2), ya no fallan aquí; la venezolana con cédula en pesos, al
  asesor, con su paquete; el de grupo y el de equipo propio que no se suman (Toronto); el vuelo del jueves al viernes a las 10, «demasiado pronto».

**Graves (3), la meta sigue en 0:**
1. **«Two dives» leído como 2 DÍAS de buceo** (australianos t1-t2): piden dos inmersiones y el precio, y la lista trae los paquetes de 4, 4 y 5, sin la
   salida de 2; piden el precio otra vez y lo mismo; a la 3.ª, 124 USD. `[EX9B-6] duration='multi_day' (días de buceo; regex: None)`: el extractor pone
   dias_de_buceo=2 y varios_dias se come el plan nombrado, porque la salida de 2 es el plan base (`sin_plan`, hechos.py). No es de CALN-17. Ojo: mi a0afdfc1
   (0.48) adelantó el síntoma de t2 a t1.
2. **La misma lectura niega un enlace que existe** (Toronto t3, «five of us will do the two dives»): «for the 2-dive Fun Dives I don't have a direct booking
   link; that booking needs a team advisor», y el resto va en multi_day. Cuando insiste, «You're right», y da el enlace.
3. **Horario falso que tumba la reserva** (alemán t2): «Wednesday's dive would be too close to your Friday 10:00 a.m. flight». Son unas 46 horas. Lo
   corrige si el cliente le lleva la cuenta (t3). Es del escritor: tiene las 18 h y el vuelo, y calcula mal.

**Medios:**
- La familia holandesa t1: el texto sin sujeto al quitar los importes (CALN-19; feature/caln-frases-gonzalo, aún sin subir). En t2, «para quien aún no ha
  elegido» por la niña de 5 (CALN-17).
- «Tengo el Rescue» leído como curso que quiere (`padi_rescue` en el reparto, peruanos t1) y «Solo para confirmar, ¿lo cambio? 1 el curso Rescue Diver…» en
  t2, ya con los dos enlaces. Luego «¿han pasado más de 2 años?» dos veces, tras «hace un año».
- Toronto t2: pide los enlaces con el reparto ya dicho en t1 y le preguntan «which one are you leaning toward»: el reparto no se leyó en t1.
- El alemán t3 recibe a la vez el refresher y la tarjeta de las 2 inmersiones, cuando dijo que iba un día.

**Menores:** «El precio te lo dejo a continuación» después de la lista (venezolana t1); bebé de 10 meses guardado como edad 10 (`detected_ages`, sin efecto
visible aquí); «how many people?» a quien habla en singular (alemán); la pregunta del asesor con el texto del cierre (holanda t3).

## CALN-S04I-01..10 · Tanda de contraste de Gonzalo contra PRE 0.50 (4-nov, `charla_rama` sobre 5f40a8a1)

Criterio de Álvaro (#2716). 10 clientes nuevos, educados y que escriben bien (`docs/robustness/g3/charlas-rama/s04i-*`), elegidos antes de ver nada: 8 sin
graves y 2 con graves. Repetición en PRE 0.50 ×3 (`s04i-*` en `banco-graves.json`, `abierto`), 0 respaldos: fallan 2 de 3 cada uno.

**Graves (2):**
1. **Embarazada** (esposo Advanced, ella snorkel). t4: «selecciona 2 personas en cada enlace», cuando es 1 buceo y 1 snorkel: pagaría el doble. t2, t3 y t4:
   «¿ya tienen esa certificación o quieren sacarla con el curso?», 3 veces, tras decir Advanced en t1 y repetirlo, y con `is_certified` ya en true desde t3.
   El reparto se queda en {snorkel: 1, undecided: 1}: el esposo «buzo Advanced» no entra como buceo. La traza: «el extractor amplía el reparto…, pero Jev dice que
   ya estaba contado».
2. **Belgas** (Advanced en Isla Grande del 8 al 12, vuelo el 13 a las 7, dos días y una nocturna). t1: recomienda el paquete de 3 de un día, cuando piden dos
   días; la lista trae el snorkel y no el paquete de 4 con nocturna (236 USD), y dice «the 5-dive option's return timing would leave a very short interval before your 7
   a.m. flight»: falso, pueden acabar días antes. Además, «the second day returns to Cartagena» a quien duerme en las islas. Se corrige en t2 cuando el cliente
   lleva la cuenta. Misma clase que el alemán de S04H (CALN-19).

**BIEN:** chilenos («tengo el Rescue» ya no se lee como curso; el vuelo a 18 h, bien calculado), padre e hijo de 12 (Open Water), tensión y operación de corazón (al
asesor, sin consejo médico), lluvia (reprograma o reembolso; el cambio, al asesor), luna de miel (privado, al asesor), residente con amigo de Texas (la reserva
mixta en USD; al asesor). `two dives` se descarta bien en Londres t1 y t2 (`son inmersiones, no días`).

**Medios:**
- Londres: no da el precio con el descuento de grupo («I can't calculate», decisión de negocio pendiente); `multi_day` por la estancia («next week») y el paquete de 4 en la lista.
- Familia con niña de 8, t2: pide refresher ×2 y snorkel; da bien los dos enlaces, pero añade la tarjeta de Fun Dives para 2. Tampoco suma el total.
- Residente: t1 no contesta qué paga cada uno hasta t2; «should I change it?» al final; el descuento de grupo a una pareja.

**Menores:** «I'm leaving the prices below» debajo de la lista (niña de 8); el miedo al agua profunda de la luna de miel no se contesta.

## CALN-S04J-01..08 · 13.ª tanda de sparring contra PRE 0.51.0, hasta reservar (4-nov, `charla_pre`)

Criterio de Álvaro (#2716). 8 clientes nuevos, educados y que escriben bien, elegidos antes de ver nada (conv 6872-6879): 6 sin graves y 2 con graves. Repetición en
PRE 0.51 ×3 (`s04j-*` en `banco-graves.json`): fallan 3 de 3. **Meta de CALN-22: sigue en 0 de ~60.**

**Graves (2):**
1. **Mexicana con cédula y novio de México** (conv 6879). t1: «tú pagas en pesos colombianos; tu novio, en dólares». Un grupo mixto paga todo en USD. La tarjeta decía
   bien 178 USD, y en t2 lo corrige si se le pregunta. El extractor no marca el grupo como mixto (duda entre colombiana y no colombiana) y el escritor recibía la regla de
   cada persona. **Arreglo:** señal de Jev `grupo_mixto` (sonda 69/69), que además quita el «mixto» de más al venezolano con cédula y esposa colombiana (abierto desde el
   30-oct: 0/3 → 2/3); el escritor recibe la regla del grupo. **3/3.**
2. **Irlandés, refresher y buceo al día siguiente** (conv 6874). t4, t5 y t7: «To give you the right link: would you prefer Fun Dives or Dive Mini Course?», la misma pregunta
   3 veces tras decir «both», sin enlace. **Es de mi control CALN-24:** el escritor da un plan y la tarjeta otro, se esconde la tarjeta y se pregunta; quien quiere los dos no
   tiene salida. **Arreglo:** se pregunta una vez en la charla; si siguen saliendo dos planes, salen los dos. **3/3.**

**BIEN:** Portugal (paquete de 5, hoteles, enlace en USD), Advanced de Chile (2 días, 616 USD, pago al reservar), tres amigas de Bogotá (minicurso, COP, al asesor; el mal
tiempo, bien), cambio de fecha (al asesor), asma (al asesor, sin consejo médico), madre y niña de 10 en un hotel sin recogida confirmada (lo dice y ofrece al asesor).

**Medios:**
- **Dice que no sabe y la base lo tiene:** «una no nada muy bien» (Bogotá t2, FAQ de saber nadar). Misma clase que las mochilas de la mini (`luggage_policy`).
- **«¿Para cuántas personas?» a quien viaja solo:** irlandés t2 («travelling alone» en t1) y Advanced t2 (CALN-18). Con «Así te doy el precio exacto», que ya no se sostiene.
- **«¿Eres de nacionalidad colombiana?» tras «Como eres chileno, pagas…»** (Advanced t3), y al irlandés.
- Irlandés t3: pide el precio de las inmersiones sueltas y recibe solo los paquetes de 2 y 3 días.
- Madre y niña, t2: «¿cuál de las dos opciones?» (las dos tarjetas, minicurso y Bubble Makers) contesta con el Open Water como la otra opción.

**Menores:** la lista «También necesitas» con la excepción del refresher a quien no lo hace (Bogotá, madre y niña); «we'll pair you with a buddy», sin base (irlandés t1).

**Precio citado (de la mini de la 0.51, no de la tanda):** «los 5 buceos serían por 293» recibía «¡Perfecto!». **Arreglo:** señal de Jev `cita_precio` (sonda 72/72), que lo
trata como pregunta de precio. **0/3 → 3/3.**
## CALN-S04K-01..11 · Tanda de contraste de Gonzalo contra PRE 0.51 (4-nov, `charla_rama` sobre f5e037d1, mismo `src` que 51c9ce27)

Criterio de Álvaro (#2716). 11 clientes nuevos, educados y que escriben bien (`docs/robustness/g3/charlas-rama/s04k-*`): 9 sin graves y 2 con graves; el segundo, por
seguridad y discutible.

**Graves (2):**
1. **Español, «2 fun dives».** t1: `dias_de_buceo` 2 (`EX9B-6 duration=multi_day`, días 2). t4: confirma 178 USD y debajo saca «5 Dives - 2 days», 392 USD, con su
   enlace. La regex de S04H no lo cubre: la palabra en medio rompe `_CERT_DIVE_COUNT_RE`. `banco-fun-dives.json` ×3: PRE 0.51 13/18, `multi_day` equivocado 5 de 15;
   3624d852 de Gadea (CALN-25, Jev sin mirar la cita) 17/18, 0 de 15; el fallo que queda es de la comprobación (contesta el pago sin dar el precio; enlace y estado bien).
2. **Open Water, «nos vamos el domingo 14 por la noche».** No dice avión. PRE 0.51 ×5: 2 proponen sábado y domingo y dicen que les alcanza, sin nombrar las 18 horas; 1 lo
   avisa y pregunta si vuelan; 1 pregunta a qué hora sale su transporte; 1 pone el curso viernes y sábado, y ahí «van sobrados» es cierto. En la charla (t1), «les alcanza
   para un vuelo el domingo por la noche» y, dos frases después, que ese vuelo no cumple las 18 horas; se corrige en t2 al decir avión. Se cuenta como grave por consejo
   inseguro por omisión: quien se va de Cartagena de noche probablemente vuela. Si se decide que es medio, la tanda queda en 1 grave.

**BIEN:** Toronto (4, «two dives on Saturday»: 178 USD, sin descuento de grupo, enlace bien), tarjeta perdida con 3 años sin bucear (refresher al asesor y enlace de las 2
inmersiones), abuela de 68 con asma (al asesor), menor de 15 sin adulto (no vale el permiso firmado), embarazada de 3 meses con Open Water (no bucea, snorkel con visto
bueno), familia con hijo de 10 (reparto y dos enlaces bien), francés (FFESSM, paquete de 4 al asesor), alemanes Rescue en Isla Grande con equipo propio (188 USD, sin descuento).

**Medios:**
- Español: pide cuántos son tras «for me» y la nacionalidad tras «I'm from Spain» (aunque t1 ya dice «visiting from Spain»).
- San Andrés: «no operamos» sale en t2 con «¡Genial!» y otra vez la certificación, ya dicha, a quien acaba de saber que aquí no hay plan; en t1 va escondido tras los precios.
- Menor: tras decirle que no puede, sigue con la lista de requisitos y «¿desde dónde saldrías?».
- Familia con hijo de 10: da los 18 m del Open Water y deja la profundidad del niño al equipo; no he comprobado el límite por edad en la base.
- Alemanes: «Nitrox is available on request» no lo he encontrado en la base como aire para buzos ya certificados (solo la especialidad).
- Francés: t1 en inglés; pasa al francés cuando lo piden, con la tarjeta en inglés.
- Tarjeta perdida: «¿para cuántas personas?» a quien habla en singular.

## CALN-S04L-01..10 · Tanda de contraste de Gonzalo contra la candidata 0.52b (4-nov, `charla_rama` sobre 052ce47c, con `kb_v2_gadea`)

Criterio de Álvaro (#2716), Haiku por Anthropic. 10 clientes nuevos, educados y que escriben bien (`docs/robustness/g3/charlas-rama/s04l-*`), elegidos antes de ver nada,
con temas distintos a S04H-S04K: 9 sin graves y 1 con grave. Contando con la lista que se escribió antes: empresa, Divemaster, miopía y mareo, comida, Navidad, añadir a una
persona, nocturna sola, reservar para mañana, pareja de São Paulo, tarjeta rechazada.

**Grave (1):**
1. **Dos salidas de un día en dos fechas** (`navidad`). Dos Open Water piden 2 inmersiones el 24-dic y 2 el 2-ene, durmiendo en Cartagena. t3: el extractor da días de buceo 2
   (`EX9B-6 duration=multi_day`) y la lista trae los paquetes de 4, 5 y 7 inmersiones, sin la salida de 2 (178 USD). El texto dice bien que no hay que dormir en las islas y el
   enlace es el correcto. Pide el total en t2, t3 y t4; lo tiene en t5, cuando lo calcula él (712 USD, y el bot lo confirma). Repetido ×3 en t3 y t4: 052ce47c 0/6, PRE 0.51.1
   1/6 (1 respaldo en 21 turnos por lado): ya estaba, no lo trae la candidata. No es CALN-25: son dos días de verdad, cada uno con un plan de un día.
   En `banco-graves.json` como `s04l-dos-salidas-t4`, `abierto`.

**BIEN:** empresa de 12 (factura sí, precios y descuento de grupo, al asesor), Divemaster (internado, equipo propio, requisitos; el precio, al asesor), vegetariana alérgica al
marisco (almuerzo, avisar antes, enlace), añadir a una amiga a una reserva pagada (al asesor), nocturna sola con cámara propia (no lo confirma; al asesor), São Paulo (reparto, dos
enlaces con «solo a la persona que hará esa actividad», sin confirmar el portugués), tarjeta rechazada (enlace por transferencia con el descuento; al asesor).

**Medios:**
- Reservar para mañana, pasadas las 4:30 (`manana2`): «Sí, todavía puedes reservar para mañana: … ya no permite reservar para el jueves». La conclusión es la buena, y la primera palabra, la contraria.
- Navidad t1: a quien pregunta por el 25-dic y el 1-ene le contesta que esos días se cierra, sin precio ni otras fechas. t2: «the options are:» con la lista vacía, «You'll need to
  stay overnight» dos veces y otra vez si están certificados, ya dicho en t1. También en t3 («can you confirm…»); el cliente protesta en t4.
- Miopía t1: «I don't have specific information about prescription lenses», con las máscaras graduadas en la base (FAQ 100). En t2, preguntado directamente, lo contesta bien.
- `manana` (primera): el cliente dice que son las 6 de la tarde y el bot usa su reloj («ahora son las 4:10 p. m.»). Era cierto en Cartagena: fallo de la prueba, no del bot; por eso se repitió.

**Menores:** São Paulo t1, paquetes de 3 y 4 inmersiones en la lista de quien no los pide; añadir a una amiga, los precios de los dos orígenes; miopía t2, «Shall we go for the mini-course?» tras
darle el enlace.

## CALN-S04M-01..10 · 14.ª tanda de sparring contra PRE 0.52.0 (4-nov, `charla_pre`)

Criterio de Álvaro (#2716), Haiku por Anthropic. 10 clientes nuevos, educados y que escriben bien (conv 6881-6890), con temas distintos a S04H-S04L, elegidos antes de ver nada: 9 sin
graves y 1 con grave. Los 10 llegan al enlace o al asesor; en Rosario solo al de uno de los dos planes que pide. **Meta de CALN-22: sigue en 0 de ~60.**

**Grave (1):**
1. **Familia con hijos de 11 y 8** (conv 6888). t2: las tarjetas daban «Minicurso de Buceo [Bubble Makers]», 183 USD, con la nota de 8-10 años, y debajo «Bubble Makers», 168 USD. El de 8 parecía tener dos
   planes y la de 11 llevaba una etiqueta falsa. El escritor lo decía bien. `cart_render._ninos_del_minicurso` solo descontaba las plazas de snorkel, y el comentario decía que Bubble Makers cuesta como el minicurso,
   desde la 0.48 ya no. **Arreglo (0.53, `feature/052c-gadea`):** descuenta también las plazas de Bubble Makers; quien no tiene plan propio va a Bubble Makers con su servicio, su precio y al asesor; con 10 años vale el minicurso.

**BIEN:** Junior Open Water de 15 con su padre (edad, adulto responsable, formularios), seis amigas de snorkel (448.000 COP, descuento de grupo que hay que pedir, al asesor), diabetes tipo 1 (al asesor, sin consejo médico), GoPro
y equipo propio (5 % que se suma, cámara bajo su responsabilidad), Hotel Rosario de Mar 3 días (paquete de 7 y días sueltos, recogida si hay acceso), colombiano en Miami con esposa estadounidense (grupo mixto en USD), crucero (hora de vuelta y que no se puede garantizar el retraso), Rescue con EFR caducado.

**Medios:**
- **Pareja tratada como uno que elige y otro que no:** crucero t2, «dos Open Water» recibe «For the one who hasn't chosen yet» y el menú entero; Junior t2, «Is the other person diving too?» tras «for both of us».
- **Pide dos planes y recibe uno:** Rosario t3, «both» saca solo la tarjeta de Fun Dives, sin el enlace del paquete de 3; Open Water y Advanced, el precio de uno en cada turno.
- **Confirma el origen a quien lo acaba de decir:** «desde Cartagena» en la pregunta recibe «Entonces, ¿saldrías desde Cartagena?» (Miami t1, crucero t1, Rescue t1). Es la confirmación de ORIGEN-CONFIRMA.
- Familia t1: la lista lleva los paquetes de 3 y 4 inmersiones y no el precio de Bubble Makers.
- Crucero: la espera antes de volar, pegada por el código (0.52), a quien vuelve en barco: sin daño, pero no viene a cuento.

**Menores:** el enlace dos veces (Miami t2, Rescue t2; arreglado en la 0.53); el aviso de moneda repetido (Miami t1); «I'm leaving the price below» debajo de la lista (Junior t1); «Para aplicarlo» sin saber a qué (despedida t1).

## CALN-S05C-01..10 · 16.ª tanda de sparring contra PRE 0.54.0 (5-nov, `charla_pre`)

Criterio de Álvaro (#2716), Haiku por Anthropic. 10 clientes nuevos, educados y que escriben bien (conv 6908-6917), con temas elegidos antes de ver respuestas. **1 con grave y 9 sin graves. Meta de CALN-22: la s05b de Gonzalo (0.54.0, 10 sin graves) sumaba 10; este grave la devuelve a 0.** Los 10 llegan al enlace o al asesor, o se les dice por qué no se puede.

**Grave (1):**
1. **Aterriza el sábado a las 11:30 y vuela el domingo a las 20:00** (conv 6914). t1: «Sunday's trip returns around 4:15 p.m., which leaves a comfortable gap before your 8:00 p.m. flight»: consejo inseguro. Contradecía su propio «18 horas» en la misma respuesta, y al preguntarlo el cliente, t2, lo decía bien. No era azar: en PRE 0.54, «¿puedo bucear el sábado por la mañana y me voy a las 21:00?» dijo que sí 3 de 5. **Arreglo (0.55, solo datos):** `flight_after_diving`: para un buzo el mismo día nunca llega, también por la noche, y la lancha no lo arregla; quien dice que se va ese día, probablemente vuela; tras el refresher de día, desde las 7:00 del día siguiente. Banco de la hora de volar: **22/30 → 29/30** (s05c-mismo-dia 2/5 → 5/5; g-vuelo-dia-siguiente, «too soon» con 21 h, 3/5 → 5/5). Sigue abriendo con «Yes» algunas veces antes de explicar por qué no: sin riesgo, pero confuso.

**Medios:**
- **Rescue a quien ya está en Cocoliso** (conv 6916): t2, «the 796 USD price is for when you're already on the islands; it doesn't include transport or lunch», y en t1 decía que el almuerzo sí. Falso: Rescue, Divemaster y Mindful Diving solo tienen plan desde Cartagena, y sin plan desde las islas no había hechos. **Arreglo (0.55):** los hechos dan el de Cartagena y dicen que desde las islas lo confirma un asesor. **PENDIENTE para Andrés:** ¿se pueden hacer desde las islas y a qué precio?
- **Tres amigos** (conv 6909): t2, la tarjeta sin «· 3 personas» a quien dice «para mí y dos amigos más».
- **Mediodía t2:** el origen a quien acaba de saber que no puede bucear (menor si se va).

**Menores:** la lista larga de paquetes a un grupo con reparto (humo 054a); los paquetes en la lista de la luna de miel, antes de pasar al asesor por la lancha privada.

**BIEN:** referido alemán (carta, 2 días, vuelo al día siguiente bien calculado), otra agencia más barata (no se iguala), PayPal y efectivo (no; el enlace), Barú sin recogida (al muelle por su cuenta; niña de 7 en snorkel), italiano (contesta en inglés; comida vegetariana), minicurso y luego bucear (no certifica), colegio de Medellín (14 menores con 2 profesoras, grupo de 16, pesos, al asesor), luna de miel con lancha privada (al asesor).

**Para la revisión de la meta (Gadea):** contra la 0.53: 1 cliente con grave de 20 (s04n, s05a). Contra la 0.54: 1 de 20 (s05b, s05c). Hasta la 0.51: 17 graves en 109 clientes. Cada grave de esta noche salió de una clase nueva y entró en el banco.

## CALN-S05A-01..10 · 15.ª tanda de sparring contra PRE 0.53.0 (5-nov, `charla_pre`)

Criterio de Álvaro (#2716), Haiku por Anthropic. 10 clientes nuevos, educados y que escriben bien (conv 6895-6905), con temas elegidos antes de ver respuestas. **1 con grave y 9 sin graves. Meta de CALN-22: la s04n de Gonzalo (0.53.0, 10 sin graves) sumaba 10; este grave la devuelve a 0.** Todos llegan al enlace, al asesor o a lo que pedían; el crucero se va porque no llega.

**Grave (1):**
1. **Siete amigas de Bogotá** (conv 6898). t1: «Tres ya tenemos el Open Water» salió como 3 plazas del Curso Básico, 2.450.000 COP cada una, y el escritor decía «buceo certificado». Se corrigió al aclararlo el cliente. Lo lee Haiku en `group_allocation`; repetido ×5 no salió con esa frase, pero sí con «Two of us already have our Advanced» (A 2 de 5, candidata 4 de 5). **Arreglo (0.54):** señal de Jev `quiere_curso` (sonda 69 lecturas: 0,82-0,98 frente a como mucho 0,32); en el prompt de Haiku no se toca. Si dice que no y el reparto trae un curso que nadie había elegido, son buzos. Banco `s05a-siete-ow-t1`, `s05a-seis-advanced-en-t1` y el control `s05a-cinco-curso-control`.

**Medios:**
- **SSI y NAUI** (conv 6903): t3-t4, el refresher a quien lleva 8 meses y un año, dos veces, también tras «ninguno lleva más de 2 años». El enlace llegó bien. No se reproduce en 6 repeticiones contra la candidata; queda sin causa. t2: «¿La otra persona también va a bucear?» a quien dice «queremos» (2 de 6).
- **Cali, Advanced** (conv 6905): t2, a «Desde Cartagena» recibe «¿Desde dónde saldrías?» dentro de una frase del escritor; a «Ya te dije» lo pasa a un asesor pidiendo disculpas. **Arreglo (0.54):** el compositor quita la pregunta con algo delante y su explicación.
- **Crucero con snorkel** (conv 6899): la espera de volar 2 veces a quien hace snorkel y vuelve al barco; t3, al despedirse, la tarjeta del plan «ya en las islas». **Arreglo (0.54):** la espera, solo con buceo; `se_despide` de Gonzalo.
- **Bocagrande** (conv 6896): t2, el menú genérico; t3, «¿prefieres la salida o el minicurso?» a quien pide los dos. El menú va en la 0.54 (Gonzalo).

**Menores:** «I'm leaving the prices below» debajo de la lista (holandeses t1); «Is that your case?» separado de su aviso por el aviso de moneda (holandeses t2); el origen dos veces en el mismo mensaje (Lima t1); los requisitos enteros a quien pregunta si vale su carné SSI (t1) y el Advanced (t2).

**BIEN:** Nitrox con salida al día siguiente, mareo con snorkel, mal tiempo y reserva a nombre de otra persona (al asesor), Bocagrande sin recogida, madre acompañante con hija en minicurso, 3 años sin bucear y vuelo (refresher, 18 h, enlace), holandeses con equipo propio (5 %, no es automático).

## Mini y bancos de la 0.53 (5-nov, no es una tanda: no cuenta para CALN-22)

Fallos reales que salieron al leer la mini y el banco de graves, con su banco (`banco-053b.json`, `banco-graves.json`). Arreglados en la 0.53.0 salvo los que se indican.

- **Moneda contradictoria, ya en PRE 0.52:** venezolano con cédula y esposa colombiana, «al ser un grupo mixto, se paga en dólares» con la lista en pesos. El filtro solo buscaba «grupo mixto». Por el criterio de Álvaro, grave. Política aclarada.
- **La misma pregunta 3 o 4 veces** (origen): con el cuerpo corto el freno la dejaba salir; con «pago» también. **La tarjeta entera 4 veces** con fechas de por medio.
- **«Cómo reservamos» sin contestar:** Jev solo lo daba por «how to book online».
- **Sin arreglar:** el escritor calcula mal el vuelo (g-vuelo-dia-siguiente: «too soon» con 21 h de margen, 1 de 2); «carta de referido» al Open Water desde cero (curso-alojamiento t2); «edad mínima 10» para snorkel (familia-mixta t1, en los dos lados); «¿desde ese hotel?» y «quedándonos en el hotel» no se leen como islas (precio-desde-islas).

## CALN-S04N-01..10 · Tanda de contraste de Gonzalo contra PRE 0.53.0 (5-nov, `charla_rama` sobre 8b1f1f35)

Criterio de Álvaro (#2716), Haiku por Anthropic. 10 clientes nuevos, educados y que escriben bien (`docs/robustness/g3/charlas-rama/s04n-*`), elegidos antes de ver nada y antes de
subir la 0.53: **10 sin graves.** Valoración de un solo autor, sin repetir en PRE ×3 porque no hay nada que reproducir. No llevaba `se_despide` ni la pregunta del buzo con quien no bucea (feature/menu-gonzalo, sin subir).

**BIEN:** crucero que zarpa a las 5 (no alcanza: regreso 4:15, y no ofrece nada falso), Medellín con el 50 % de anticipo (al asesor), instructor retirado con 2.000 inmersiones (lo revisa el equipo, sin exigir el refresher de oficio),
8 universitarias (reparto 3 + 5, descuento de grupo a pedir, al asesor), epilepsia (al asesor, sin consejo médico), seguro DAN y equipo parcial (el seguro no se quita, sin el 5 %), 31 de noviembre («no existe; ¿qué fecha querías decir?»), cambio de inglés a español, cancelación por decisión propia (al asesor, sin prometer devolución), suizos con hijo de 16 (reparto y dos planes).

**Medios:**
- Pareja que dice «both Open Water» (cambio de idioma): el reparto queda {certified_diving: 1} + 1 sin elegir, y pregunta «¿La otra persona también va a bucear?» tras «los dos Open Water». Se resuelve al insistir. Clase que Gadea ya vio en S04M.
- Suizos, hotel sin muelle: t1 «hotel pick-up isn't available» frente a «the nearest dock we point you to», en la misma respuesta. t2 pregunta cómo funciona la recogida y no contesta; la tarjeta dice «Pickup at your island hotel».
- Crucero t2: «I'll skip it» recibe «how many people should I plan for?» y la regla del vuelo. Lo cubre `se_despide`, aún sin subir.
- Universitarias: pide el total con los dos descuentos y «no puedo calcularlo» (como Londres de S04I; decisión de negocio pendiente). Paquetes de 3 y 4 en la lista.

**Menores:** «I'm leaving the price per person below» debajo de los precios (idioma); la regla de 18 horas a quien no vuela (crucero t1, t2); los requisitos enteros (retirado t1); «Soy Coral, de Diving Planet» a media frase (31 de noviembre).
## CALN-S05B-01..10 · Tanda de contraste de Gonzalo contra PRE 0.54.0 (5-nov, `charla_rama` sobre 78c581a7)

Criterio de Álvaro (#2716), Haiku por Anthropic. 10 clientes nuevos, educados y que escriben bien (`docs/robustness/g3/charlas-rama/s05b-*`), elegidos antes de ver nada y antes de subir la 0.54: **10 sin graves.** Valoración de un solo autor.

**BIEN:** vuelo el mismo día a las 11 de la noche tras el minicurso («podrías volar desde la medianoche; tu vuelo sería una hora antes»), colombiana y esposo con cédula (ambos en pesos, sin grupo mixto), Barú sin recogida (sale de Cartagena), una sola inmersión desde Cartagena (el mínimo es 2),
gemelos de 11 con Junior y madre en la lancha (reparto y enlace; acompañante al asesor), minicurso ayer y salidas de certificado mañana (hace falta carné; corte de las 4:30 bien), pareja enferma (al asesor), regalo sin fecha (no hay tarjeta; a nombre de la novia), persona sorda (buceo adaptado; comunicación al asesor).

**Medios:**
- Especialidad t2: pregunta cuánto dura y si puede bucear al día siguiente, y pide los enlaces: recibe solo la tarjeta de la especialidad, sin contestar ni dar el segundo enlace. Protesta en t3 y entonces contesta todo bien. t1: «la disponibilidad la tendría que confirmar el equipo», con siempre disponible en la base.
- Gemelos t2: «no puedo calcular el total» para 2 × 178 + 80, sin descuento de grupo por medio.
- Cédula t1: «¿saldrías desde Cartagena?» cuando lo dijo; lo reconoce en t2 (ORIGEN-CONFIRMA).

**Menores:** «I'm leaving the price details below as well» (Barú), paquetes de más en la lista (Gemelos t2, Una inmersión t1, Cédula t1), Salidas de Buceo en la lista de quien nunca ha buceado (sorda t1), «¿saldrías desde Cartagena?» a quien dijo que iba a Cartagena (sorda t1).

## CALN-S05D-01..10 · 17.ª tanda de sparring contra PRE 0.56.0 (5-nov, `charla_pre`) y rejuicio con Opus de s05a y s05c

Criterio de Álvaro (#2716). 10 clientes nuevos y educados (conv 6923-6932). Los temas los fijó Gadea-Claude antes de ver respuestas, incluida la regla del hotel; los escribió y los leyó un subagente que conocía las políticas, no el código. Después, **juez Opus a ciegas × 2** (`juez_claude --charlas`, criterios generales y uno de graves). **Es el primer contraste independiente de la clasificación de las tandas.**

**Graves, leídos a mano:**
1. **Amigos de Bogotá** (conv 6929, t2): piden dos salidas de un día durmiendo en Cartagena, y la tarjeta es el Paquete de 5 inmersiones a 1.429.000 COP, que obliga a dormir en las islas. El juez lo marca en las 2 pasadas. Arreglado en 0.57 (señal de Jev `salidas_sueltas`).
2. **Familia de Canadá** (conv 6926, t1): «I don't have another age-appropriate activity listed for a 7-year-old»; el snorkel es desde los 6. Se corrige solo si insiste. El juez lo marca como grave en 1 de 2 pasadas y como invención en la otra. Arreglado en 0.57 (las opciones de cada edad, hecho obligatorio y en los candidatos).
- **Duda, Alemán** (conv 6927, t3): la conclusión es correcta (puede volar), pero «based on the Wednesday dives finishing around 4:15 p.m.»; esa hora es la llegada de la lancha. El juez: grave en 1 de 2. Sigue abierto (CALN-19, el escritor calcula el vuelo).

**Medios:** el origen preguntado a quien ya lo dijo (6924, 6925; firme en las 2 pasadas): es CALN-37. Airbnb: «You don't need to wait for that confirmation to book» (6930): **decisión de Gadea: el asesor confirma la recogida antes de reservar y pagar** (0.57). Listas de precios con planes no pedidos (6925, 6926, 6929). Pregunta compuesta a medias (6929, 6932).

**BIEN:** hotel antes de reservar (6925: aguanta la insistencia; con Cocoliso, enlace y 124 USD), moneda y pago de colombianos y residentes, sin enlace web; Barú sin recogida; mal tiempo y cambio de fecha; refresher y 18 horas.

**Rejuicio de s05a y s05c con Opus a ciegas × 2 (conv 6895-6905 y 6908-6917, 21 conversaciones):** **5 con grave, los mismos 5 en las dos pasadas; nosotros contamos 2 de 20.** 6914 (vuelo el mismo día) ya lo teníamos. Nuevos: 6898 (cotiza en COP y da el enlace de la web; curso a quien ya tiene el Open Water), 6899 (crucero sin hotel con tarjeta y enlace de las islas), 6915 (**«Sí, las profesoras pueden acompañar a los menores»**, contra la política), 6916 (Rescue desde las islas, que clasificamos como medio). Contra PRE 0.56 ya van bien 6898 y 6899; el de las profesoras seguía 1 de 2, y se trata en 0.57.

**Lectura:** nuestra clasificación se quedaba corta. Con esta vara, la tasa de clientes con grave está en torno al 20-25 %, no al 5 %. La meta de 2 en 60 se cuenta desde ahora con clasificación más juez a ciegas, y un grave se da por tal tras leerlo: 1 de cada 3 fallos de Opus es falso.

**Lectura de Gadea (5-nov, 17:28) de los 8 que Opus marca como graves:** 7 graves (6898, 6899, 6914, 6916, 6926, 6927, 6929) y 1 no es fallo (6915, las profesoras). Opus acierta 7 de 8 en lo que marca como grave. **Tasa: 7 de 31 clientes, 23 %.**

## CALN-S05E-01..10 · 18.ª tanda de sparring contra PRE 0.58.0 (5-nov, `charla_pre`)

Criterio de Álvaro (#2716). 10 clientes nuevos y educados (conv 6933-6942). Los temas los eligió el subagente que escribió y leyó las charlas, sin ver el código. Después, **juez Opus a ciegas, una pasada** (`juez_claude --charlas`, `tanda-s05e__claude-opus-medium.json`): 5 de 10 con grave, y son los 5 que había señalado la lectura (3 firmes y 2 dudas). Falta la lectura de Gadea.

**Graves:**
1. **Jake** (6938): el refresher por la mañana y las dos inmersiones ese mismo día: «Yes». El refresher va en su propio día.
2. **Ernesto** (6941): lo mismo en español: «Sí, puedes hacerlo el mismo día», y planifica con esa fecha.
3. **Priya** (6942): acaba el curso el 18 y vuela el 19 a las 9:00: «not safe», cuando puede volar desde las 7:00. Además niega el ahorro de empezar desde las islas.
4. **Sofía** (6939): vuelo a las 6:00 del día siguiente: «Sí, llegas bien», y luego se contradice.
5. **Anna** (6940): «through the online booking link» de un paquete sin enlace, y la oferta del asesor repetida aunque ya había aceptado.

**Causas:** las 5 son del escritor afirmando sin tener el dato (CALN-38). El refresher y qué planes no tienen enlace estaban decididos en `decisiones.json`, que solo lee el juez; el vuelo tiene el dato, pero el escritor contesta sí o no antes de calcular. Ninguno es de la tarjeta (CALN-39).

**Medios repetidos:** bloque de políticas en crudo; «no tengo el dato» cuando la base lo tiene; pregunta doble a medias; listas con planes ya descartados; precio final por persona con descuentos. Sueltos de invención: distancia desde Getsemaní (6933), horario de Bubble Makers en la tarjeta (6935), cómo se pide el 5 % de equipo propio (6936).

**Lectura:** 5 de 10 no es comparable con el 23 % de antes sin más: son 10 clientes y otro autor. Lo que sí dice es que la tasa no ha bajado todavía y que cada autor nuevo encuentra clases que no teníamos. La auditoría de decisiones contra la base (22: 7 cubiertas, 8 a medias, 7 no; muchas las cumple el código) va a por esa causa: 0.59 pone los huecos reales como datos en la base y 6 casos nuevos en `banco-graves.json`.

## CALN-S05F-01..10 · Tanda del segundo autor (Álvaro) contra PRE 0.59.0 (5-nov, `charla_pre`)

Criterio de Álvaro (#2716). 10 clientes nuevos y educados (conv 6943-6952). Los temas los eligió el Claude de Álvaro antes de ver ninguna respuesta, evitando los ya usados: asma, coreanos y el traslado del aeropuerto, padre con su hija de 15 que hace el Open Water, 5 argentinos (3 certificados y 2 sin experiencia), refresher en San Pedro de Majagua, japonesa con tortugas, Cali el 1 de enero, noruego con el Advanced, uruguayos con un niño de 9 y Airbnb en Isla Grande. Los escribió y los leyó un subagente que solo conocía `policies.json`, `services.json` y `discounts.json`. Después, **juez Opus 5.5 a ciegas, una pasada** (`juez_claude --charlas`, `tanda-s05f__claude-opus-medium.json`): **2 de 10 con grave**, los dos confirmados leyendo el texto.

**Graves:**
1. **Majagua** (6947): pide el refresher el 8 y bucear el 9 (se va el 10 por la tarde). La respuesta dice «el paquete de 5 inmersiones dura 2 días, así que no alcanzaría a completarlo» y debajo va la tarjeta de ese paquete con su enlace; la salida de 2 inmersiones del 9 no sale. Es la tarjeta que sigue un plan que ya no quiere (CALN-39): en t1 había dicho «bucear los dos días».
2. **Airbnb** (6952): en t1, «un asesor debe confirmar la logística antes de que reserves» y ofrece el pase; el cliente contesta «Sí, por favor» con el nombre de la casa; el bot no lo pasa, pregunta cuántos son y si hace más de 2 años de su última inmersión, y en t4 da la tarjeta con el enlace para reservar y pagar. Va contra `hotel-antes-de-reservar`.

**Medios** (los señalaron el subagente o el juez; sin leer uno a uno):
- «La disponibilidad de esa fecha la confirma el equipo» (6950 t2, 6951 t2), contra `availability_always`: la clase del francés del golden.
- Repreguntas: la última inmersión ya dicha (6945 t3, 6952 t3); «¿Los demás también van a bucear?» a cinco que bucean (6946 t2). El pase pedido en t2 no se hace hasta t5 (6946).
- El 1 de enero cerrado, sin proponer otro día ni preguntar nada (6949 t1).
- Padre e hija (6945): en t2 recomienda la salida de un día a quien pasa dos en las islas, y no dice que la hija hace la teoría online antes.
- Argentinos (6946): formulario médico de curso a certificados sin refresher (t5) y bloque de políticas en crudo con paquetes que no pidieron.
- Snorkel (6948 t1): lo que incluye, dos veces en el mismo mensaje.

**Lectura:** 2 de 10, frente a 5 de 10 en s05e contra la 0.58. Los graves de s05e, refresher el mismo día, vuelo y planes sin enlace, no salen aquí. Los dos que quedan son la tarjeta con un plan viejo (CALN-39) y la regla del alojamiento cuando el cliente acepta el pase. Son 10 clientes y otro autor: dice poco de la tasa, pero es del segundo autor, como pide la meta.
