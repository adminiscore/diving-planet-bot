# Bloque 3.1: el cierre de las 4:30, con el reloj y la base (diseño, 10-nov; v2 tras la revisión)

**Ficha:**
- **Rama:** 3.1, en `feature/bloque31-gadea`, sobre `bloque4p-gadea` 550b9eae.
- **Mecanismo:** el cierre de la reserva tiene un dueño en el código; el escritor no hace la cuenta.
- **Familia:** «¿se puede mañana?» y el cierre falso.
- **Banco:** sin IA, `tests/test_bloque31.py`, con el reloj fijo.
- **Contador:** `[CORE][3.1]`.
- **Fuera:** la tarjeta (`cart_render`, del 4R de Álvaro).

**v2 (10-nov):** un agente revisó la v1 contra el código. Comprobé lo que cambiaba algo:
- los días cerrados ya tienen dueño (`domain/calendario.fechas_cerradas()`, que lee `policies.json`), así que no se crea otro;
- la línea pintada tiene tres casos, porque mañana puede ser un día cerrado;
- no se dice «por la web», porque al colombiano o al grupo de 5 o más no se les da el enlace;
- hay un solo escritor (`supervisor.rag_answer`), que lee este contexto.

## Lo que hay que cumplir (decisiones de Gadea)

- **El cierre de las 4:30 es firme** (9-nov): para reservar un día hay que hacerlo antes de las 4:30 p. m. del día anterior. Si ya
  cerró, se ofrece el primer día que se puede reservar.
- Se opera todos los días salvo los cerrados de la base (el 25-dic y el 1-ene).
- **Decidido el 10-nov:**
  - el vuelo va al 3.2;
  - el saldo del 3.1 puede salir positivo hasta el 3.2.

## Cómo está hoy (comprobado)

- **Lo que recibe el escritor:** la fecha y la hora de hoy, y qué día es mañana (`rutas/contexto_rag.py:135-145`). Le llega
  por `conversational_core.py:957`.
- **El prompt le pide hacer la cuenta él:** «COMPARA la hora actual con ese corte» (`prompts/info.py:165` en español, `:209`
  en inglés). Lo fijan `tests/test_rag_safety.py:812-823` y `tests/test_valores_de_la_base.py:72`.
- **Nadie más calcula el cierre ni lee la hora:** ni los avisos, ni la tarjeta, ni `que_preguntar`, ni el núcleo.
- **Valor medido** (por el revisor):
  - **panel:** 2 de 49 graves del bloque 1 son del cierre, los dos de visto-6914, unos 0,3-0,5 por tirada;
  - **tanda:** ninguno (b0b-08 ya cumple).
  - **Su razón son los reales:** el 17 % pide para hoy o mañana.

## El cambio

**C1. La cuenta, en `domain/calendario.py`, junto a `fechas_cerradas()`.**
- `cierre_de(dia)`: a las 4:30 p. m. del día anterior, hora de Colombia. La hora sale de `valores.hora("cierre_reservas")` y se
  pasa a 24 h.
- `primer_dia_reservable(ahora)`: el primer día D, desde mañana, que no está cerrado y con `ahora < cierre_de(D)`. Hoy nunca.
- `ahora` va siempre con zona horaria (se pasa a Bogotá; sin zona, error). Así, el reloj fijo del arnés, que sustituye
  `datetime` en `contexto_rag`, llega a la cuenta.

**C2. El código lo pinta en `contexto_rag`, junto a la fecha y la hora.** Tres casos, en español y en inglés, y sin «por la web»:
- **Mañana se puede:** «Mañana, viernes 6 de noviembre, todavía se puede reservar, hasta hoy a las 4:30 p. m.».
- **Mañana ya cerró:** «Mañana, viernes 6 de noviembre, ya no se puede reservar: el cierre fue hoy a las 4:30 p. m. El primer día
  que se puede reservar es el sábado 7 de noviembre». Va con el contador `[CORE][3.1]`.
- **Mañana no operamos** (día cerrado): «Mañana, 25 de diciembre, no operamos; el primer día que se puede reservar es el…».

**C3. Fuera la cuenta del escritor.** La regla de `info.py:165/:209` pasa a decir: para saber si se puede reservar un día, usa lo
que dice el contexto de mañana y del primer día que se puede reservar, sin hacer tú la cuenta. Se mantiene «sin urgencia inventada
ni emojis de preocupación». Se actualizan los dos tests que fijaban la regla vieja.

**El contador del parche de las 18 horas** (`rag_agent._con_la_espera_antes_de_volar`): `[CORE][3.1]` cuando actúa. Es para
el 3.2, que podrá borrarlo cuando un panel y una tanda lo vean callado. `si_vuela` no se toca: lleva la política del vuelo.

## Cómo se prueba y se mide

- **Banco sin IA:**
  - **la cuenta, con relojes fijos:**
    - el jueves a las 10:30, a las 16:29, a las 16:30 justas y a las 20:30;
    - el 24-dic a las 10:00 y a las 20:00 (el 25 está cerrado);
    - el 31-dic por la noche;
    - una hora en UTC;
    - una hora sin zona, que da error;
  - **la línea pintada:** los tres casos, en los dos idiomas, con el reloj del arnés;
  - **el prompt:** ya no pide comparar;
  - **la huella del juez:** la misma antes y después.
- **Mecanismo, ×5 con el código local y el reloj fijo,** con casos nuestros:
  - quien pide para mañana, con el reloj de después de las 4:30 y con el de antes;
  - un colombiano que pide para mañana pasadas las 4:30;
  - «el sábado» dicho un jueves por la noche;
  - del panel, visto-6914.
  - **Meta:** nunca un cierre falso, y siempre el primer día bueno.

**Saldo previsto:** unas +26 en src (C1 ~12, C2 ~14, C3 ~0). Lo que se borra llega con el 3.2.

**Riesgos:**
- Una charla que cruza las 16:30 puede contradecir lo que el bot dijo antes. Es correcto: el cierre pasó.
- «Next Friday» sigue siendo cosa del escritor.
- Con más fechas en el contexto, el revisor del lat-5 se saltará más revisiones. Se mira en el mecanismo.

**Para el 3.2** (lo apunta el revisor): el código puede decir ya, por plan y sin datos del cliente, si la última inmersión es de
día y que se vuela desde las 7:00 del día siguiente al último día. Eso quitaría el «provided your last dive is a daytime dive» de
visto-6942.
