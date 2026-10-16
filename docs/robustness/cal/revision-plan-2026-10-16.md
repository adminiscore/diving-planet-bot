# Revisión del plan tras CAL-0/B/A/C (16-oct-2026, Gadea con Claude)

Para Álvaro y Gonzalo. Revisión de lo hecho del 15 al 16-oct, del estado de la fase CAL y del resto del plan, con
propuestas. Las decisiones que requieren a Gadea están al final; nada de esto cambia el código ni PRE.

## 1. Lo hecho, y cómo lo veo

| Tarea | Resultado | Valoración |
|---|---|---|
| **CAL-0** (Gonzalo) | 73 fallos reproducibles con su causa; coincide con la investigación de Gadea (búsqueda poca, azar mucho); 4 criterios de moneda desfasados | Muy bien. `banco_fallos.py medir --reps 3 --codigo-local` es el bucle rápido de la fase |
| **CAL-B** (Gonzalo + Álvaro) | `MONEDA_SIN_NACIONALIDAD_USD` promocionado: 92,7 → 95,4 %, 12 → 17/24; 7 criterios actualizados | Bien, la mejora más clara de la semana. Decisión de negocio de Álvaro (choque moneda/origen, opción a) pendiente de ratificar |
| **CAL-A** (Álvaro) | Plan → redacción → completitud, temperatura 0, revisor de avisos; banco 16×3: 47 → 44 / 46 / 45 / **42**; cerrada "no mejora" | Medida honesta, conclusión demasiado rápida (sección 2) |
| **CAL-C** (Álvaro, en curso) | C1 (sin menú si ya quiere bucear), C2 (aceptar la propuesta cuenta): 66 → 56/72; queda C3 | Bien encaminada. La lección "no tocar el prompt del extractor" es correcta |
| Plan Coral | Sin actualizar desde el 15-oct: 5 entradas en la cola | Solo la cuenta personal de Gadea puede escribir en la página (Gonzalo no tiene la herramienta; la cuenta `admin.iscore` no tiene acceso) |

Dos avisos de método: (1) **duplicación** por segunda vez en una semana (la investigación de Gadea y CAL-0 midieron lo
mismo el mismo día; antes, ex-6): reclamar la tarea antes de empezarla; (2) **gasto** ≈ 15–18 $ el 16-oct y una
mini-ronda inválida por falta de crédito, con **PRE mudo** (715 errores): ver R6.

## 2. CAL-A: por qué no cerrarla

El hallazgo de Álvaro es correcto e importante: los 16 casos no son preguntas sin contestar, son **avisos que un
asesor da sin que se los pidan** (el minicurso no certifica y el Open Water son 2 días; Barú no es Rosario; formulario
médico tras reservar; sin cédula pagas en USD; carta de referido; profundidad según nivel; tras las 4:30, siguiente
día). Pero "el diseño no funciona" no se sostiene:
1. **El plan (A2) no leía la base de conocimiento**, solo la conversación: no podía saber que el minicurso no certifica.
   Se probó una versión que no podía funcionar para estos casos.
2. **El revisor de avisos (A4) sí leía la base y fue lo único que movió la aguja (47 → 42).** Falló al ELEGIR los avisos
   con un modelo pequeño (metía relleno). El mecanismo "aviso que falta → regenerar" funciona; la elección, no.

**Propuesta: los avisos como conocimiento con condiciones** (`avisos-propuesta.json`, 18 avisos de partida):
- Un aviso es un dato de la base (como una política) con **condiciones sobre el estado**: actividad, origen,
  nacionalidad o grupo mixto, zona/hotel, fechas frente a la duración del plan, y el **tema** de la pregunta (los
  documentos que la búsqueda recuperó, no el texto del cliente). Nada de regex ni de reglas en el prompt.
- El **código** elige los que aplican en cada turno; van al RAG como **puntos obligatorios** y el **revisor de
  completitud** comprueba que estén (si falta uno, se regenera una vez con él): el mecanismo de A4 con la elección
  hecha por datos.
- Cada aviso enlaza con su política o ficha (una regla, un sitio); el texto lo redacta el RAG con esa fuente.
- **Lo puede editar el negocio** sin tocar código (es un JSON de la base, como `policies.json`). Hoy "qué diría un buen
  asesor" vive solo en los criterios del juez: en el examen, no en el producto. Por eso el oculto no mejora.
- Medida: banco CAL-0 ×3 (los 18 de CAL-A deben pasar 3/3) y, en el golden visible, que no aparezcan avisos que no
  tocan (el defecto de A4). Límite: "no te da tiempo a certificar" necesita las fechas en el estado (campo del extractor
  pendiente, CAL-C).

## 3. Correcciones al plan (contexto que faltaba, dicho por Gadea el 16-oct)

- **PRE es nuestro PRO.** No se monta infraestructura PRO. El piloto, el modo entrenamiento (g-4b) y la robustez (R6) van
  sobre PRE. R6 sube de prioridad: PRE se quedó mudo dos veces esta semana por falta de crédito, y PRE es lo que verá
  Diving Planet. R6 debe incluir: respaldo a otro proveedor cuando OpenAI falle, alerta de saldo y una respuesta fija de
  "te paso con una persona" cuando todo falle.
- **No hay clientes ni tráfico en vivo:** somos tres desarrolladores; las conversaciones reales las dio Diving Planet.
  Un **examen oculto nuevo** solo puede salir de (1) **otra tanda de conversaciones históricas de Diving Planet**
  (pedírsela; se guarda sin leer), (2) **testers** (g-6, 20–50 personas con tareas libres en PRE), (3) el simulador
  (g-3). El modo entrenamiento tiene sentido cuando Diving Planet conecte su WhatsApp a PRE: ese es el piloto.
- **Un entorno de medida local** (el banco ya corre dentro del contenedor de PRE; un contenedor local con una copia de la
  base lo haría en minutos y sin pisar a nadie): PRE es uno y ya chocan dos personas midiendo.

## 4. Lo que cambiaría del plan

| Cambio | Por qué |
|---|---|
| **CAL-A reabierta como "avisos con condiciones"** | Ataca 14–18 de los 73 fallos y generaliza (sección 2). 1,5–2 días |
| **Promocionar solo lo que pasa 3 de 3 repeticiones**; métrica "decisiones por turno tomadas por LLM" | El 23 % de los fallos no se reproduce y la temperatura 0 no lo arregló: la variación viene de 3,4 llamadas LLM por turno. Cada decisión que pueda tomar el código (moneda ya; menú con C1; origen antes del precio) sale del modelo |
| **CAL-C: experimento con Jev para la actividad** | Regla del 24-sep: Jev para opciones fijas. Una pregunta de opciones cerradas en la misma llamada del enrutador es más estable que el esquema grande del extractor. Medio día con el banco |
| **Examen oculto nuevo** de conversaciones históricas de Diving Planet o testers, antes de CAL-F | Sin examen independiente, quien escribe los criterios y los arreglos es el mismo equipo |
| **R6 antes del piloto**, con lo concreto de arriba | PRE = PRO |
| **Métrica principal: % de conversaciones sin ningún error** (hoy reales visibles 26/52, oculto 6/21), graves aparte | Es lo que siente el cliente; el % de criterios lo tapa |
| Gobierno: reclamar la tarea en Plan Coral antes de empezar; decisiones de negocio las ratifica Gadea | Dos duplicaciones en una semana |

Lo que no cambiaría: flags, bancos y rondas A/B funcionan (CAL-B lo demuestra). El problema no es el rigor; es medir
contra un examen que nos conocemos.

**Orden propuesto (~3 semanas):** (1) CAL-C hasta su A/B (Álvaro) · CAL-A como avisos (Gon o Gadea) · ratificar
decisiones y Plan Coral al día. (2) CAL-D/E, CAL-F con el golden visible · R6 · entorno de medida local.
(3) Examen oculto nuevo · piloto con Diving Planet en PRE · S4 (limpieza) cuando haya huecos.

## 5. Decisiones pendientes de Gadea
1. Plan Coral: exportar desde su cuenta (copia completa) o duplicar con lo que hay (11 tareas cerradas entre el 28-sep y el 15-oct sin su nota final).
2. Reabrir CAL-A como avisos con condiciones, y quién la lleva.
3. Ratificar la opción (a) del choque moneda/origen (Álvaro, 16-oct).
4. Pedir a Diving Planet otra tanda de conversaciones históricas para el examen oculto nuevo.
