# Simplificar: Luna con la base del bot, en una sola llamada (diseño, 10-nov)

**Por qué.** Decidido por Gadea el 10-nov, tras la re-medida con el arnés arreglado.
- Cinco bloques del plan bajan el panel solo de 8,2 a 7,5. Los ciegos y los 75 reales salen peor. El código crece unas +440 líneas.
  El estilo no cambia: 600 caracteres y pregunta en el 96 % de las primeras respuestas a reales.
- Luna sola, sin nuestras piezas, empata con el bot: 10,7 frente a 10,3, con la mitad de largo y 1 llamada.
- Por familias, Luna sola falla en lo exacto (precio, horas) y el bot en lo que decide nuestro código (plan, pase).

**Qué se prueba.** Si una arquitectura simple iguala o mejora al bot de ahora con clientes como los reales.
- **V1 (Claude de Gadea):** Luna en una sola llamada, con la base del bot.
- **V2 (Claude de Álvaro, `diseno-simple-puerta.md`):** V1 más una puerta del código sobre lo que Luna entendió.

Es un prototipo fuera del bot (`scripts/simple_v1.py`), sin tocar src. Mientras dura, se congelan las piezas nuevas en src
(4R-1b, 2b, 3.2). Se acordó con el Claude de Álvaro (#3756-#3758).

## V1

- **Una llamada por turno a Luna** (`gpt-6-luna`, el escritor del bot), como `linea_base_luna`: temperatura 0, sin razonamiento,
  con todo el historial.
- **Lo que lee, solo lo que el bot puede tener en producción:** el catálogo y sus fichas con los enlaces de reserva, `pricing`,
  `policies`, `discounts`, `availability`, las FAQ curadas y las decisiones de Gadea como reglas (`instruccion_*` si la tienen;
  si no, su texto).
  - **No lee** `escalation_rules.json`, que solo lee el juez y está desfasado, ni el marco del juez.
  - Se arma con las mismas piezas de `judge_golden_set.load_reference`, sin `escalation_rules`. El banco comprueba que no entra.
- **La hora y el cierre:** la línea de `contexto_rag._el_cierre` (3.1), con el reloj fijo del arnés.
- **Breve:** contesta como una persona por WhatsApp (la persona: 119 caracteres; 1 de cada 4 respuestas con pregunta). Corto y
  al grano, una pregunta como mucho y solo si hace falta para avanzar. Sin repetir el saludo.
- **Salida estructurada en la misma llamada** (JSON):
  ```
  {"texto": str,
   "entendido": {"origen": "cartagena"|"islas"|null, "hotel": str|null,
                 "nacionalidad": "colombiana"|"residente"|"extranjera"|null, "personas": int|null,
                 "actividad": str|null, "plan": id del catálogo|null, "certificado": bool|null,
                 "quiere_reservar": bool, "ya_reservo": bool},
   "pasar": {"si": bool, "motivo": str|null}}
  ```
  - `entendido` se guarda entre turnos y se le vuelve a dar, como estado. Sustituye a Jev y al extractor.
  - En V1, el pase va en el texto («te paso con un asesor del equipo»). En V2, el código lo marca de verdad.
- **Salida del guion:** el formato del panel (`dialogo`, `turn`, `msg`, `reply`, `estado` = `entendido` y `pasar`, `metricas`
  con las llamadas, los tokens y los segundos), para juzgarla con `juez_claude --panel` y compararla con `marcador`.
  Las instrucciones se escriben una vez, sin mirar el panel, y no se ajustan con lo que salga.

## Cómo se mide

- **Panel de la vara:** 3 tiradas con el reloj alterno, cada una juzgada dos veces, con la huella 9326257c y desde el mismo
  árbol que A y B.
- **Los 75 primeros mensajes reales:** 3 tiradas, cada una juzgada dos veces. Al bot de ahora (B) se le pasan 2 tiradas más,
  para tener también 3 (unos 0,3 $ de OpenRouter). Los reales y sus juicios se quedan fuera del repo.
- **Estilo frente a la persona,** y **llamadas, p50, p90 y coste por turno.**
- **Coste:** Luna por OpenAI, sin OpenRouter, ~0,1 $ por tirada (Luna sola tuvo un 99 % de caché); el juez gasta ventana de Claude.

## Cuándo se adopta (fijado antes de medir; v2 tras la revisión independiente)

V1 o V2 pasa a ser la base nueva, y el plan se dedica a quitar piezas, si frente a B (el bot de ahora) cumple todo esto:

| | Condición |
|---|---|
| Panel, graves de 40 | V1 − B ≤ +1,5. Con el ruido medido (desviación de la diferencia, 0,76): si son iguales, pasa el 98 %; si V1 es 3 peor, el 2 % |
| Ciegos del panel | V1 − B ≤ +1,5. **Es el que más pesa**, con los reales: V1 lee el 99 % de lo que lee el juez y las decisiones salen de los vistos |
| Reales, graves de 75 | **V1 − B ≤ +2,5.** Fijado el 10-nov a las 16:30, antes de juzgar V1: B en 3 tiradas, 5,5 · 8,5 · 2,5 (media 5,5; desviación entre tiradas 3,0; la de la diferencia con 3+3 tiradas, ~2,45). Si son iguales, pasa ~84 %; si V1 es 5 peor, ~16 % |
| Clientes que pasan con una persona | V1 ≤ B (en V1 el pase es texto, y pasar de más casi nunca es grave para el juez). Y «pasar.si» coincide con el texto |
| Importes que no están en el catálogo | Contados por código: V1 ≤ B |
| Estilo en los reales | Caracteres de mediana ≤ 300 y con pregunta ≤ 50 % |
| Latencia | p90 ≤ 7,5 s. B tiene un respaldo a los 3 s; si V1 gana en todo lo demás, el respaldo se añade en producción |

Además, **control:** Luna sola (`linea_base_luna`), 3 tiradas con el mismo reloj. Su 10,7 se midió con el reloj del jueves
12 y no se puede comparar con el 7,5 de B: con ese reloj y el arnés viejo, el mismo bot daba 10,3 frente a 8,2.

Si sale peor en graves, las piezas sí aportan algo y se mira cuáles con V2. Si empata en graves y gana en estilo, coste y
código, se adopta: eso es lo que pide el objetivo del plan.

**Cambios de V1 tras la revisión:**
- añadido `lugares.json`: la base traía 2 de los 37 sitios de las islas;
- en el JSON, «entendido» y «pasar» van antes que «texto»;
- campos nuevos: edades, refresher, fecha y días;
- tope de 1.200 tokens;
- «unos 300 caracteres como mucho» en vez de 119, porque algunas reglas piden dar varios datos.

## Riesgos

- **Que Luna invente importes, como en la línea base** (precio 35). Es lo que cubre la puerta de V2.
- **El contexto es largo** (~50.000 tokens por llamada). Con la caché de OpenAI sale barato, pero hay que medir la latencia.
- **La salida en JSON puede romperse.** Si no se lee, cuenta como fallo del turno y se registra.
- **Los reales ya se usaron para esta comparación.** No se diseña nada mirándolos, y su texto no entra en ningún banco ni documento.
