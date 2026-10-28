# CALN-2 · El lector del grupo — diseño corto (27-oct)

Para Gadea, antes de tocar código. Sigue a `diseno-caln2-grupo.md` (lista de personas, A + B, aprobado) y a dos cosas
medidas el 27-oct.

## 1. El problema, medido

- **La familia nombrada persona a persona se queda sin total ni reparto.** «Yo tengo el Open Water y quiero bucear. Mi
  esposo no bucea y vamos con los niños, de 7 y 4» (batería CALN4, b5): el extractor (Haiku) lee las edades,
  `otro_sin_certificar` y lo de quien escribe, pero no da `group_size` ni `group_allocation` (b5 10/10, g31 8/10, g30
  7/10 en llamadas directas). Luego el bot pregunta «¿cuántas personas?» a quien ya lo ha dicho (b1, b5, g30, g31, s12).
- **Tocar la regla no lo arregla y mueve otros campos.** `group_size` «o nombra a cada una» con un ejemplo nuestro,
  N=20 en los dos órdenes: total bien 1/40 → 3/40, y el origen de b5 cambia (null 10/20 → 0/20). Es la lección del 3b:
  un campo más en el esquema de Haiku le hacía dejar el reparto (g09 16/16 → 6/16).
- **La certificación de cada persona no se guarda** (decisión de Gadea, #2223): «somos 6, 4 tenemos certificación y 2
  dudan… ¿precio por ser grupo?» son 6 sin decidir, y a los 4 certificados se les recomienda la salida de buceo. Hoy
  `personas` no lo guarda y el extractor no lo da (b6: ni reparto ni `is_certified`).

## 2. Propuesta: una lectura aparte del grupo

Una llamada corta, con su propio esquema, que devuelve **la lista de personas** (la de `diseno-caln2-grupo.md`):

```
{"total_dicho": 4,
 "personas": [
   {"quien": "cliente", "cantidad": 1, "certificado": true,  "actividad": "certified_diving", "edad": null, "cita": "Yo tengo el Open Water y quiero bucear"},
   {"quien": "esposo",  "cantidad": 1, "certificado": false, "actividad": null,               "edad": null, "cita": "Mi esposo no bucea"},
   {"quien": "niños",   "cantidad": 2, "certificado": false, "actividad": null,               "edad": null, "cita": "vamos con los niños, de 7 y 4"}]}
```

- **Cuándo se llama:** solo si el mensaje habla de otras personas (ya lo dicen la lectura del turno —edades,
  `otro_sin_certificar`, un reparto con `undecided`/`companion`— o Jev, `mentions_other_person`) y lo del extractor no
  deja el grupo completo (sin total, o un reparto que no suma el total). Con la señal de Jev se lanza a la vez que la
  extracción adelantada: no suma tiempo.
- **Qué escribe:** `personas`, con la certificación de cada entrada; el total y el reparto salen de ella, como hoy. El
  extractor manda en lo que da con su cita: el lector solo rellena lo que el extractor dejó vacío y la certificación de
  cada uno. Cada persona lleva su cita comprobada en el mensaje, como los campos del extractor.
- **La recomendación** a quien no ha elegido mira su certificación: certificado → la salida de buceo; no certificado →
  las de principiante y las de su edad; sin saberlo → las dos (lo de fc6e5c4).
- **Qué sustituye:** la parte de acompañantes de `detect_special_signals` (`mentions_other_person`,
  `companion_activity`, `other_companions`). Es la «red de señales» que `diseno-caln2-grupo.md` ya quería quitar:
  relee el historial entero, crea acompañantes fantasma y va en serie cuando el turno no avanza. `recall_field` se queda.
- **El extractor no cambia:** ni su esquema ni su texto (sin efectos en sus campos, que es lo que el 3b enseñó).

## 3. Cómo se mide

| Paso | Qué | Cómo se mide |
|---|---|---|
| 1 | El lector solo, sin enchufar | Llamadas directas N=20 sobre el primer turno de g01-g31, b1/b5/b6 y l01-l10: total, reparto y certificación contra lo esperado; inventos (personas que el mensaje no nombra) |
| 2 | Enchufado tras un interruptor (apagado por defecto): rellena `personas` si el extractor no da el grupo | Suite; banco ex0 igual (el extractor no cambia); PRE A/B banco-grupo, lectura, sparring y edades ×2; latencia p50/p95 de los turnos de grupo |
| 3 | Fuera la parte de acompañantes de la red de señales | Lo mismo que el paso 2, con el interruptor encendido en A y en B |

## 4. Coste y riesgos

- **Coste:** una llamada corta solo en los turnos de grupo que el extractor deja incompletos. En esos mismos turnos se
  quita la de señales (paso 3), que iba en serie.
- **Dos lectores que no coinciden:** manda el extractor en lo que dice con cita; el lector solo rellena. Un total del
  lector que no cuadra con uno dicho por el cliente no se guarda (se pregunta, como hoy).
- **Inventar personas:** cita por persona, comprobada; el banco de llamadas directas cuenta los inventos.
- **Modelo:** el de la red (`red_extractor_model`) o Haiku; se elige en el paso 1 por aciertos, inventos y tiempo.

## 5. Paso 1, medido (28-oct; `scripts/medir_lector_grupo.py`, sin PRE)

32 casos (el primer turno de los de un turno de banco-grupo, b1/b5/b6 de la batería y l01-l10), N=20; en cada llamada el
extractor y el lector a la vez. A = lo que deja el extractor; B = el lector rellena lo que el extractor dejó vacío y da
la certificación de cada persona (el reparto del extractor manda si suma el total que dijo). Lector con Haiku
(`extractor_turno_model`), 3.ª versión del prompt (la 1.ª contaba dos veces «mi esposo y yo» y tomaba «somos Advanced» por
el curso; la 2.ª hacía acompañante a «mi esposo no bucea» 6/20). Tres disparadores:

- **T1**: el mensaje habla de otras personas y el grupo no queda completo (sin total, o un reparto que no suma).
- **T2a**: T1, o queda alguien sin elegir (su certificación decide la recomendación: b6, l06-l10).
- **T2b**: T2a, o cualquier grupo de 2 o más sin reparto (g28: «my friend… not sure»).

| De 640 | A | B con T1 | B con T2a | B con T2b |
|---|---|---|---|---|
| Total bien | 537 | 639 | 639 | 639 |
| Reparto bien | 477 | 585 | 585 | **601** |
| Certificación bien | 507 | 527 | 635 | **635** |
| Inventos (más personas o una actividad no elegida) | 60 | 54 | 54 | **36** |
| Llamadas en que salta | — | 272 | 443 | 481 |

Arregla b1, b5, b6, l01, l02, l06, l08, g02, g16, g28, g30 y g31 (de 0-6/20 a 18-20/20). Los inventos que quedan son
del extractor donde el lector no salta o su reparto ya cuadra (g12, g17, l10). El lector no lee el JSON 3 de ~690 veces
(se sigue con lo del extractor) y descarta ~0,1 entradas por llamada sin cita.

**Tiempo:** extractor p50 3,2 s / p95 4,6 s; lector p50 1,7 s / p95 2,4 s.

| Turnos que lo llamarían | T1 | T2a | T2b |
|---|---|---|---|
| Golden visible (368 turnos; sin el oculto) | 9 (2,4 %) | 18 (4,9 %) | 35 (9,5 %) |
| Sparring, 2.ª tanda (22 turnos) | 5 | 9 | 12 |
| p95 de esos turnos en el golden: hoy → a la vez que el extractor → detrás del extractor | 8,2 → 8,2 → 9,5 s | 8,2 → 8,2 → 9,5 s | 8,7 → 8,7 → 10,2 s |
| Lo mismo en el sparring | 12,1 → 12,1 → 13,9 s | igual | igual |

«A la vez» supone que el lector sale con el extractor, pero el disparador depende de lo que lee el extractor: para no
esperar habría que lanzarlo cuando Jev ya señale otras personas y tirar la lectura si luego no hace falta (más llamadas
que turnos que lo usan). «Detrás» es lo que suma si espera al extractor: +1,3-1,5 s al p95 de esos turnos.

## 6. Paso 2, medido (28-oct; interruptor `lector_grupo`, lanzado con la señal de Jev)

A/B en PRE, ×2, `--codigo-local`; A = caln-gadea (código 5ab8854), B = la rama con `--flag lector_grupo`; el mismo
`reproducir_juez_pre` en los dos (guarda el [TURN_METRICS] de cada turno).

| Banco | A | B |
|---|---|---|
| Grupos (31) | 51/62 | **56/62** (g16, g28, g30, g31) |
| Sparring (14) | 11/28 | **13/28** (s01 y s12 0 → 2/2; s03 2 → 1 y s10 2 → 1) |
| Lectura (10) | 20/20 | 20/20 |
| Precios q (5) | 10/10 | 10/10 |

Tres fallos que la medida destapó, arreglados después y comprobados en PRE ×4 (s03 4/4, g29 4/4):
- g29: un mensaje que nombra solo a una parte del grupo cambiaba el total sabido (5 → 4): `completar` ya no lo toca.
- s03: «he hasn't been diving in 3 years» leído como no certificado quitaba el buceo de sus opciones: el prompt del
  lector lo aclara y la bandera del extractor de «certificado pero inactivo» manda.
- s03: con el grupo bien leído en t2, la corrección de t3 («No wait… he wants the fun dives… only I'm doing the mini
  course») se tiraba por el veto de Jev: una corrección que solo completa a quien faltaba por elegir, completa.
s10 («¿Te animas?») es del escritor, no del grupo.

**Gasto** (192 turnos de bancos de grupo en B): el lector salió con Jev en 170 (88,5 por 100 turnos), se usó en 107 y
se tiró en 62; 1.266 tokens de entrada y 159 de salida por llamada; 0,00011 $ por llamada → **0,009 $ por 100 turnos**
(las tiradas con la media: cota alta). Lo que factura OpenRouter por 100 turnos: A 0,069 $ → B 0,082 $ (lo de OpenAI no
cambia). La red de señales de acompañantes baja sola: 17,7 → 11,5 llamadas por 100 turnos (va en serie, p50 1,4 s).

**Tiempo:** el lector sale **1,5 s después** que el extractor (espera a Jev) y, en los turnos que lo usan, el turno
espera **p50 1,07 s, p95 1,66 s** (82 de 136); p95 de esos turnos 7,8 → 9,0 s. Si saliera con el extractor, la espera
sería ~0 (5 de 136), a cambio de lanzarlo en todos los turnos (+1 llamada en paralelo, ~0,011 $ por 100 turnos); en el
golden visible se usaría en 35 de 368. Lanzarlo con el turno solo en el primer mensaje o con el grupo sabido no compensa
(66 % de los turnos del golden para cubrir 30 de 35).
