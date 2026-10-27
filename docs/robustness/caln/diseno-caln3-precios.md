# CALN-3 · El resolvedor de precios — diseño (27-oct)

Para Gadea y el equipo, antes de tocar código. Fase CALN (Plan Coral): calidad en conversaciones nuevas y difíciles,
sin perder la arquitectura delgada y sin parches. Encaja con CALN-2 (el grupo como lista de personas) y CALN-6 (un
compositor al final del turno: los precios serían una pieza más).

## 1. Qué pasa hoy

**Quién decide qué precio sale** está repartido en tres sitios, y después lo corrigen tres más:

| Dónde | Qué hace | Quién decide |
|---|---|---|
| La tarjeta (`slotfill_close`, `cart_render`) | Al cerrar la reserva: `N × precio = total`, en su moneda | El código (fiable) |
| Los hechos del escritor (`flows/hechos.py`, 180 líneas) | El precio de UNA actividad, con lo guardado ANTES del turno | El código elige qué; el escritor lo redacta |
| El catálogo entero en el prompt del escritor | 12.700 caracteres y **156 importes** | El modelo elige cuál dice |
| La puerta del origen (`_origen_antes_del_precio` y compañía, **158 líneas** en `conversational_core`) | Si no se sabe el origen, quita los importes y pregunta, o deja las dos variantes | El código, DESPUÉS de escribir |
| `sin_precio` | Si va la tarjeta, el texto no da precios | El código |
| La guarda de importes (`currency_amounts_grounded`) | Rechaza un importe que no está en el contexto | El código, después |

El precio sale en **84 de los 465 turnos** del golden (caln1-B). Como lo elige el modelo y lo arreglan las puertas a
posteriori, los fallos son de muchas formas, pero de una sola causa: **nadie calcula ANTES qué precios tocan en este
turno**.

**Peso**, en el golden visible de caln1-B: **~16 de los 41 fallos** (en 15 diálogos) son de precio:

| Tipo | Fallos | Ejemplos |
|---|---|---|
| Sin origen → ningún precio (contra «dos precios y pregunta») | 5-6 | certificado-fecha-precio-cop, acompanante-madre, minicurso-precio-colombianos (×2), precio-paquetes-5-o-3; sparring s2-pareja t1 |
| Plan equivocado o a medias | 3 | colombianos-precio-minicurso (pide minicurso, cotiza la salida de 2 inmersiones); grupo-mixto (solo una actividad); grupo-con-refresher (solo el refresher) |
| Origen o moneda que no toca | 3 | paquete-5-islas (1.429.000 de Cartagena a quien está en las islas); semana-santa (precio de las islas sin corregir); cédula de extranjería → USD |
| Cantidad de la cotización | 1 diálogo, 3 criterios | grupo-cambia-dos-veces (2 × 126 con 3, y no se actualiza a 4) |
| Descuentos | 1 | sin-descuento-por-residente |

Más el sparring CALN2: «no tengo aquí el precio para Isla Grande» (hechos con el origen de antes, arreglado en 95a860a)
y «I don't have its island price here» (el refresher no entra en los hechos).

## 2. Propuesta

**Una función pura, `cotizar(lectura del turno) → pieza de precios`**, que decide ANTES de escribir qué importes tocan,
y **solo el código escribe importes** (como ya hace la tarjeta):

```
entrada: personas y su actividad (CALN-2), días/plan, origen (dicho en ESTE turno, confirmado o desconocido),
         moneda (nacionalidad: colombiano / no / mixta / desconocida), si pide precio (Jev), si va la tarjeta
salida:  lineas = [{quien, actividad, servicio, origen, moneda, por_persona, cantidad, total}, …]
         falta = ["origen"] | ["moneda"] | ["plan"] | []
         descuentos que aplican (online, grupo) y los que NO (residente, efectivo) si los pregunta
```

- **Sin origen:** los dos orígenes y la pregunta (decisión «origen-y-precio»), siempre, también sin actividad elegida
  si el plan se deduce (s2-pareja t1).
- **Sin moneda:** las dos monedas (como hoy en los hechos), o la del grupo si es mixto (USD).
- **Sin plan** (actividad sin decidir): los 2-3 planes candidatos de esa persona (los de CALN-2 por edad y días), sin
  inventar uno.
- **El escritor** recibe la pieza como hechos y escribe el texto ALREDEDOR, sin importes (los pone el compositor de
  CALN-6). Fuera del prompt la tabla de 156 importes del catálogo: le basta con qué incluye cada plan.
- **Fuera:** la puerta del origen y sus 158 líneas (`_origen_antes_del_precio`, `_sin_importes`, `_dos_variantes`,
  `_cotiza_los_dos_origenes`…), `sin_precio` y la guarda de importes del RAG (sin importes del modelo, no hay nada que
  vigilar).

Qué gana: un importe es siempre del catálogo y del estado de ESTE turno; los fallos de arriba se ven en la pieza
(comprobable por código, sin juez); la tarjeta y la cotización salen de la misma función, así que no se contradicen.

## 3. Por pasos, cada uno medido

| Paso | Qué | Cómo se mide |
|---|---|---|
| 0 | Banco de precios (~30 turnos: los 15 diálogos de arriba y el sparring, nunca del oculto) y una comprobación por código en `caln0_comprobaciones`: cada importe de la respuesta es el de la actividad, el origen y la moneda que tocan (o los dos orígenes si no se sabe) | — |
| 1 | `cotizar()` en sombra: se calcula y se registra en la traza, sin cambiar nada; se compara con lo que dijo el escritor | Banco ×2: % de turnos en que coinciden; los que no, a mano |
| 2 | La pieza va al escritor como sus hechos de precio (en vez de los de `hechos.py`); el escritor aún escribe importes; la guarda exige que estén en la pieza | Banco ×2 + CALN-0 + ex0 no aplica (no toca el extractor) |
| 3 | El compositor (CALN-6 paso 2) pone la pieza; el escritor ya no escribe importes; fuera la tabla de importes del prompt | Banco ×2 + ronda completa (latencia: prompt más corto) |
| 4 | Limpieza: fuera la puerta del origen, `sin_precio`, la guarda de importes del RAG y sus tests | Suite + foto de prompts; ronda al integrar |

El paso 1 no cambia nada visible y ya dice cuánto se equivoca hoy el escritor frente al código.

## 4. Riesgos

- **La prosa sin importes puede sonar a plantilla** («el precio va abajo»). El escritor sigue explicando qué incluye y
  por qué; el compositor pone las líneas donde van. Se ve en el sparring y en el banco.
- **Depende de CALN-6 paso 2** (piezas). Hasta entonces, el paso 2 da casi todo lo bueno con el escritor redactando los
  importes de la pieza.
- **Planes sin precio fijo** (Open Water referido, especialidades): la pieza dice «a consultar» y no se inventa.
- **Preguntas raras de precio** («¿y si pago en efectivo?», «¿cuánto la noche de hotel?»): la pieza solo cubre NUESTROS
  planes y descuentos (Jev ya dice si pide precio de nuestras actividades); lo demás, el escritor como hoy.

## 5. Otras formas de hacerlo

| Opción | A favor | En contra |
|---|---|---|
| A. `cotizar()` y solo el código escribe importes (la propuesta) | Determinista, comprobable sin juez; fuera la puerta y la guarda (~190 líneas); prompt más corto | Depende de CALN-6; la prosa puede sonar más rígida |
| B. `cotizar()` da los hechos y el escritor redacta los importes, con guarda exacta | Cambio menor; texto natural | El modelo aún puede callar u omitir un precio («no tengo aquí…»); siguen la puerta y las reescrituras |
| C. Arreglar caso a caso (origen del mensaje, refresher en los hechos, los dos orígenes…) | Rápido | Es lo que se ha hecho hasta ahora: cada arreglo, un caso; la puerta crece |
| D. El catálogo y que el modelo decida, con mejores reglas en el prompt | Poco código | Lo de hoy: no determinista, se equivoca de plan y de origen |

**Propuesta: A, pasando por B** (el paso 2 es B y ya vale solo; el paso 3 llega a A cuando el compositor esté).

## 6. Decisiones (27-oct, Gadea delegó en su Claude, #2154)

1. **A pasando por B: sí.** Primero B (paso 2: la pieza como hechos del escritor); A cuando el compositor de CALN-6
   ponga piezas.
2. **Sin plan elegido:** se cotizan los 2-3 candidatos que deja el contexto (edad, días, certificación; los de CALN-2) y
   elige el cliente; nunca el catálogo entero.
3. **Total del grupo:** ya decidido el 9-oct (A1): en el texto, precio por persona; solo la tarjeta multiplica.
4. **Descuentos:** el online siempre (va en «online / normal»); el de grupo solo cuando aplica (5+, se pide antes de
   pagar); los demás solo si los pregunta.

## 7. Hecho

- Paso 0 (f304b40): banco de precios y comprobaciones por código en `caln0_comprobaciones`.
- Paso 1 (Gadea, 53b6082): `cotizar()` en sombra (`src/flows/cotizar.py`), solo traza.
- Paso 2a (4036ad5): sin actividad elegida, el precio con los hechos de los candidatos (CALN3-P01): el escritor recibe
  el plan base de cada uno en los dos orígenes, sin la carta de paquetes, y el código pregunta el origen detrás.
