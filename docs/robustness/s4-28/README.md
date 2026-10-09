# s4-28 (casos 2 y 3) y un fallo del flujo de reserva — 9-oct (Gonzalo)

Sigue al primer caso de s4-28 (`JEV_LUGAR_CLIENTE`, Gadea, HISTORY 0.30.4). Herramienta mejorada para encontrar las
causas: `scripts/reproducir_juez_pre.py` guarda ahora, por turno, el **estado de la reserva** (`estado`: origen, slot
pendiente, pregunta del precio guardada, actividad, grupo…) y las **líneas del flujo** (`traza`: `[EXTRACT]`,
`[LLM_EXTRACTOR]`, `[CORE]`, `[INTENT]`, `[ROUTER]`), y admite `--hasta N` (solo los N primeros turnos, para repetir
mucho un turno concreto).

## Caso 2 — el origen dado a entender tarde ("desde ese hotel"): YA FUNCIONA, no se toca

`reproducir_juez_pre precio-desde-islas-vs-cartagena --reps 2` en PRE `2ad4c7c` → `precio-desde-islas-hoy.jsonl`: t5
("¿el precio de las 2 inmersiones? Desde ese hotel?") da **124 USD con su condición** ("si ya están hospedados en San
Pedro de Majagua o Cocoliso…") 2/2; t6 ("Osea quedándonos en el hotel") deja `location=island` (relleno con Jev
`affirms_location` sí); t7 compara 124 frente a 178 USD 2/2. Lo resuelven juntos `JEV_LUGAR_CLIENTE`, la respuesta del
RAG en Luna y `RAG_PLAN_NOMBRADO`.

Lo que sí falla en ese diálogo es otra cosa (va con el punto 3 de abajo): "Somos una pareja Advanced O.W." se lee como
"quieren el curso Advanced" y el bot repite "¿ya tienen el Curso Advanced o quieren sacarlo?" en CADA turno.

## Caso 3 — el extractor se inventa el origen: `ORIGEN_DEL_CLIENTE`

**Causa** (`familia-mixta-precio-descuento-refresher`, reproducido en PRE 1 de 3 → `familia-mixta-hoy.jsonl`): con la
pregunta del origen pendiente, el cliente contesta "May 3rd" y el relleno del extractor (`[LLM_EXTRACTOR][COMBINED]`,
que ve todo el historial) devuelve `location=cartagena`. **Ningún mensaje del cliente nombra un lugar**: sale del texto
del bot ("¿saldrías desde Cartagena…?"). El relleno de turnos sin pregunta no tenía guarda para el origen (solo para los
booleanos), y el bot contestaba la pregunta guardada con el precio de Cartagena.

**Arreglo** (`conversational_core._cliente_nombra_un_lugar`): el `location` del relleno vale si algún mensaje del
CLIENTE nombra un lugar (el detector de siempre: Cartagena y sus apodos, las islas, los hoteles; las pistas de la puerta
del origen: Barú, Tierra Bomba; y muelles/barrios de Cartagena que el detector no conoce: Bocagrande, Getsemaní,
Bodeguita, Todomar…) **o** si Jev dice que este mensaje lo afirma. Si no, se descarta (`[CORE] location del relleno
descartada`).

**Comprobación gratis** sobre los logs de PRE del 2 al 9-oct: 11 rellenos de `location`; con el arreglo se tiran 2,
los dos inventos ("May 3rd"; "Full name of dive center, location, dates" en `curso-referido`, antes de que el cliente
diga Cartagena en el turno siguiente). Los otros 9 se quedan (uno parecía tirarse por un artefacto del log: el mensaje
tenía saltos de línea; con el texto entero se queda). El repaso encontró el hueco de "Todo Mar"/"Boca Grande"
(`punto-encuentro`), ya cubierto.

**Escalón 0 en PRE** (código local): `--hasta 2 --reps 8` → `familia-mixta-origen-del-cliente-t2x8.jsonl`: en las 8 el
origen queda sin saber y el bot vuelve a preguntarlo; el extractor se lo inventó 1 vez de 8 y se descartó.

Tests: `tests/test_s4_28_origen_del_cliente.py` (12).

## Flujo de reserva — el grupo dado con edades: `GRUPO_POR_EDADES`

**Causa** (mismo diálogo, turno 1): "2 adults (ages 42, 19) / 1 youth (age 17) / Snorkeling / 1 Adult (Age 43) / 2 kids
(Ages 14, 10)". El extractor devuelve bien {buceo 3, snorkel 3}, pero la guarda de cifras exige que cada cantidad esté
escrita en el mensaje y **ningún "3" lo está** (2 + 1 y 1 + 2): tiraba el reparto y el bot preguntaba "How many people
would that be for certified diving?" (`global:sin-repreguntas` en el mapa de fallos del 8-oct). Además el detector no
leía "age 17" en singular (perdía 2 de 6 edades).

**Arreglo:** cada edad que da el mensaje cuenta como una persona para respaldar el reparto, igual que una persona
nombrada (la regla F.2 de siempre: el reparto vale si suma justo las personas); las edades se cuentan sobre el mensaje
(en el turno con pregunta la puerta de u3-4 ya las quitó del intent). El detector lee "age N" en singular, salvo
"minimum age N" (una regla, no una persona). En los 266 mensajes del golden visible, el detector solo cambia en ese.

**Escalón 0 en PRE** (código local, `--hasta 1 --reps 3` → `familia-mixta-edades-t1.jsonl`): **3/3 guardan 6
personas, 3 buceo y 3 snorkel** (antes, nada en el turno 1 y solo "3 buceo" desde el turno 2).

Tests: `tests/test_grupo_por_edades.py` (7).

## Medida: mini-ronda A/B (PENDIENTE — se acabó el crédito de OpenAI)

8 diálogos: los dos donde actúan (`familia-mixta`, `curso-referido`) y controles (`punto-encuentro`,
`precio-desde-islas`, `grupo-mixto-precio-cop-total`, `nino-7-familia`, `grupo-recompuesto`,
`minicurso-islas-y-acompanante-lancha`). **A** (`2026-10-09-s428-A`, PRE `2ad4c7c`, flags apagados): hecha, 44 turnos,
0 sin respuesta; logs y foto guardados. **Su juez falló: "no credits remaining" (429)**. Falta: recargar, juzgar A,
desplegar B (los dos flags encendidos en config y compose, sin subir), ronda B, comparar, leer regresiones, decidir.

## Pendiente que sale de aquí

- **La pregunta fija repetida en cada turno** (s4-29): "¿saldrías desde Cartagena…?" 6 veces seguidas en `familia-mixta`
  (los turnos escritos nunca contestan) y "¿ya tienen el Advanced…?" en `precio-desde-islas`. Es el siguiente arreglo
  del flujo: no repetir la misma pregunta fija si el cliente la ignoró y pregunta otra cosa.
- "We are a family of 6 and 3 of us will dive and 3 will snorkeling" con {buceo 3} guardado acaba en "¿lo cambio? 3
  buceo → 3 buceo, 3 snorkel": es una AMPLIACIÓN, no una corrección; preguntar "¿lo cambio?" sobra.
- "edad mínima 8 años" se lee como la edad de una persona (ya pasaba antes; el patrón de "N años").
