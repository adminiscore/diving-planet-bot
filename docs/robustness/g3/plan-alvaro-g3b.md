# G3b — charlas en directo de Álvaro (cursos, certificados, refresher y colombianos)

Plan de Gadea (Coral #1579, 23-oct): los tres Claude hablan con el bot DESPLEGADO por Chatwoot
(`scripts/charla_pre.py`), un turno cada vez, adaptándose a lo que conteste como haría un cliente.
**No se empieza hasta que Gadea avise de la promoción del G10 nº 6.** Los perfiles son nuestros: no
salen de G9/G10 ni copian sus frases. Lo que falle va a `docs/robustness/g3/hallazgos.md` con su
conversación y se arregla por causa, con banco propio ×3.

Coste: el del bot en PRE (céntimos por turno). Unas 8 charlas de 4-6 turnos, unos 40 turnos.

## Perfiles

| # | Quién escribe | Qué quiere | Qué miro |
|---|---|---|---|
| 1 | Principiante, 2 personas | Sacarse el Open Water desde Cartagena | Que no pregunte si «ya tienen el curso»; 2 días y una noche en las islas (alojamiento aparte); requisitos coherentes: un solo formulario médico de curso, edad desde los 10 |
| 2 | Open Water certificado | Pasar al Advanced desde las islas | Requisito previo Open Water y edad desde los 12; precio de «ya en las islas»; no repreguntar la certificación |
| 3 | Viene a terminar un Open Water empezado en su país (Referido) | Saber cómo funciona y reservar | Que lo lea como Referido; la carta de referido; el enlace del Referido; no preguntar si ya tiene el curso |
| 4 | Certificado que lleva 3 años sin bucear | Volver a bucear el sábado | Que se le ofrezca el refresher (se reserva como el minicurso); su precio; que el refresher usa el formulario médico de curso |
| 5 | Buzo con más de 500 inmersiones y 4 años sin bucear | Salir a bucear sin refresher | La excepción: lo evalúa un asesor (no se le obliga ni se le exime de golpe) |
| 6 | Colombiana de Medellín | Precio del paquete de 5 inmersiones | COP desde el principio; el pago lo coordina un asesor (sin enlace de la web); que no hay tarifa especial, solo cambia la moneda |
| 7 | Extranjero que primero pregunta en USD y luego dice «tengo cédula de extranjería» | Snorkel para dos | Que, al decir la cédula, vuelva a dar el precio en COP |
| 8 | Grupo mixto: dos colombianos y dos franceses | Salida de 2 inmersiones | Toda la reserva en USD; sin enlace para el pago de los colombianos (lo coordina un asesor) |

## Cómo se lanza (cuando Gadea avise)

    ENV_FILE=.env.dev python -m scripts.charla_pre nueva --nombre g3b-alvaro-1-open-water
    ENV_FILE=.env.dev python -m scripts.charla_pre di --conv <conv> "<mensaje del cliente>"
    ENV_FILE=.env.dev python -m scripts.charla_pre ver --conv <conv>
