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
