# Tanda de la vara (bloque 0 del Plan Gadea, 10-nov)

Diez clientes que reaccionan, con la mezcla de los 75 episodios reales en vez de la del panel: un tercio ya ha reservado,
una agencia, dos con lo que la base no contesta y cuatro de precio y reserva. Escriben como escriben los reales. Es la
tanda del bloque 0 y se pasa igual contra la versión de antes y contra cada candidata.

**Cómo se pasa.** Con `scripts/charla_rama.py` contra la rama, sin desplegarla, y la hora fija de la tabla:

    python -m scripts.charla_rama nueva --nombre b0-01-recogida --reloj despues
    python -m scripts.charla_rama di --nombre b0-01-recogida "a q hora me recogen mañana?"

Al acabar, el juez dos veces y el marcador:

    python -m scripts.juez_claude --charlas b0-01-recogida,b0-02-cambio,… --nombre b0-<rama>
    python -m scripts.juez_claude --charlas … --nombre b0-<rama> --sufijo=-p2 --no-cache
    python -m scripts.marcador --a <los dos juicios de antes> --b <los dos de la candidata>

## Cómo escribe el cliente

- **Corto:** de 2 a 10 palabras por mensaje, como mucho una pregunta, sin saludos largos. Faltas y abreviaturas a veces.
  Los reales escriben 31 caracteres de mediana.
- **En ráfagas:** en las 3 charlas marcadas, dos mensajes seguidos. El segundo se manda sin leer la respuesta al primero,
  como en WhatsApp.
- **Reacciona como un cliente:** contesta lo que sabe cuando el bot pregunta; a veces no contesta e insiste en lo suyo.
  Como mucho 6 turnos; si el bot lo resuelve, se despide.
- **Frases nuestras:** no salen de las charlas reales, del golden, de G9 ni de G10. Sin nombres, teléfonos ni correos.

## Los diez

| # | Nombre | Reloj | Idioma | Quién es y qué quiere | Cómo empieza | Qué se mira (bloque) |
|---|---|---|---|---|---|---|
| 1 | b0-01-recogida | después | es | Ya reservó el minicurso desde Cartagena para mañana; quiere saber a qué hora y dónde | «a q hora me recogen mañana?» | Contesta con la base (punto de encuentro, hora); no vuelve a vender ni pasa sin motivo (4) |
| 2 | b0-02-cambio | antes | es | Ya reservó dos inmersiones para el sábado y quiere pasarlas al domingo. Ráfaga | «tengo reserva el sabado» + «se puede cambiar a domingo?» | Da la política y pasa directamente con un asesor, sin más preguntas (4) |
| 3 | b0-03-que-llevar | antes | es | Ya reservó el Open Water; pregunta qué llevar y si tiene que hacer algo antes | «que tengo que llevar al curso» | Qué llevar y el formulario, de la base; nada inventado (4 y 5) |
| 4 | b0-04-agencia | antes | es | Agencia de turismo que cotiza para 4 clientes extranjeros: 2 certificados y 2 de snorkel, desde Cartagena | «buenas, somos agencia. precio para 4 personas?» | Como cualquier cliente: precio por persona y su enlace, sin precio de agencia ni total (4 y 2b) |
| 5 | b0-05-clima-baru | antes | es | Está en Barú; pregunta si mañana se sale con el tiempo y si la recogen allí. Ráfaga | «mañana si salen con este clima?» + «me pueden recoger en baru» | El clima, con el texto del 20-oct y el pase; en Barú no operamos: recogida fuera de los puntos de siempre, con una persona (4) |
| 6 | b0-06-hotel-pecio | antes | en | Pareja certificada; pregunta el precio de una noche en el hotel de las islas y si se ve un pecio | «how much is a night at the island hotel?» | Los hoteles de la base y el precio con el hotel; los puntos de buceo los decide el instructor; nada inventado (4 y 5) |
| 7 | b0-07-colombianas | antes | es | Dos amigas colombianas certificadas; precio desde Cartagena para el sábado; luego quieren reservar | «precio para 2 buzas desde cartagena» | COP; al reservar, un asesor y no el enlace de la web (2b y 4) |
| 8 | b0-08-para-manana | después | es | Pareja que quiere el minicurso mañana desde Cartagena; escribe pasadas las 4:30 | «se puede hacer el minicurso mañana?» | El cierre de las 4:30 es firme: dice que mañana ya cerró y ofrece el primer día que se puede (3) |
| 9 | b0-09-refresher | antes | es | Certificado, lleva 3 años sin bucear, está en Isla Grande; primero un día y luego dice que mejor dos | «hace 3 años q no buceo, puedo ir?» | El refresher; re-cotiza al cambiar de idea; no repregunta lo que ya dijo (2b y 5) |
| 10 | b0-10-bautizo | después | es | Dos amigos que nunca han buceado; no dicen desde dónde salen y al final piden el enlace. Ráfaga | «hola» + «cuanto vale el bautizo» | Precio de los dos orígenes; el enlace solo con el origen conocido; una pregunta cada vez (0,5 y 2a) |

## Qué mirar siempre

Además de lo de cada uno: el saludo solo en el turno 1; nada que ya dijo el cliente se vuelve a preguntar; una sola
pregunta, al final; precios por persona; nada inventado; el idioma del cliente; y lo largo de cada respuesta frente a la
persona (119 caracteres de mediana, 1 de cada 4 con pregunta).
