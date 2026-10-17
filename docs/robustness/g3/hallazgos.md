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
