# CALN-8 (6) · Inventario del detector de regex (29-oct, Gonzalo)

Encargo (Álvaro #2307, orden de Gadea #2311): contar en las rondas qué ramas del detector de regex
(`src/agents/intent_detector.py`, 1.126 líneas) deciden aún algo y borrar las muertas.

## 1. Código muerto estático: ninguno

Análisis con el árbol sintáctico (sin contar comentarios ni docstrings), sobre caln-gadea 8fc67ff:

- 92 definiciones en el módulo (funciones, clases y constantes).
- 15 se usan desde fuera del módulo en `src` (las «entradas»): `lectura_del_turno`, `detect_location`,
  `dive_counts_in`, `courses_mentioned`, `matched_activity_categories`, `course_level_is_ambiguous`,
  `_product_family_nouns`, `AGE_WORDS`, `DetectedIntent`, `_GENERIC_ISLAND_RE` y las listas de personas
  (`_PERSON_NOUN_*`, `_SINGULAR_PERSON`).
- Las 92 se alcanzan desde esas 15. Lo que parecía muerto (las cinco listas `_*_PATTERNS`) lo usa
  `_ACTIVITY_CATEGORY_PATTERNS` → `matched_activity_categories`.

Lo que se puede borrar no se ve sin datos: hay que contar qué ramas deciden en las conversaciones.

## 2. Dónde decide aún el regex (mapa)

Desde ex-9b, `lectura_del_turno` solo lee la cifra de inmersiones o días, las edades, la duración y la pista del
lugar. El extractor pisa duración y edades en `_understand` (`_poner_duracion`, `_poner_edades`), y sin extractor
no se vuelve al regex. Quedan estos sitios:

| # | Sitio | Lectura | Qué decide | Clase |
|---|---|---|---|---|
| R1 | `rutas/booking.py:459` | `cert_dives` (`detect_cert_dive_count`) | fija `detected_cert_dives` si no lo había | decide |
| R2 | `nucleo/routing.py` `_apply_short_answer` | `lectura_del_turno().duration` | la duración en la respuesta corta, si no hay extractor | respaldo |
| R3 | `nucleo/routing.py:324` `_departure_place` | `detect_location` + `place_by_role` | el origen en la respuesta a «¿desde dónde saldrías?» | decide |
| R4 | `nucleo/routing.py:491` `_word_ages` | `AGE_WORDS` | edades escritas en palabra | decide |
| R5 | `nucleo/extraction.py:931` `_number_of_something_else` | cifras, días y edades | veta un total de personas que es otra magnitud | guarda |
| R6 | `nucleo/extraction.py:556` `_flag_cert_or_course` | `course_level_is_ambiguous` | pregunta «¿lo tienes o lo quieres sacar?» si el extractor calla | decide |
| R7 | `_mentioned_product_activities` (extraction 839, routing 394/418/542) | `matched_activity_categories` + `courses_mentioned` | qué actividades nombra el mensaje (menú, deliberación) | decide |
| R8 | `nucleo/extractor.py:381` `_reparto_valido` | `matched_activity_categories` | quita del reparto lo que el mensaje no nombra | guarda |
| R9 | `nucleo/extractor.py:720` `_paquete_de_buceos_sin_curso` | `dive_counts_in` + `courses_mentioned` | un «paquete de 5 buceos» no es un curso | decide |
| R10 | `nucleo/extractor.py:244` `_paquete_de_varios_dias_nombrado` | `dive_counts_in` | varios días si nombra un paquete de varios días | decide |
| R11 | hotel del catálogo (extractor 654/995, routing 238, redactor 157) | `detect_location(nombra_un_hotel=True)` | hotel e isla de la lista cerrada | lista cerrada (se queda) |
| R12 | `_plan_nombrado` (core 1784), `_paquete_nombrado` (redactor 186), `plan_que_propone_el_bot` (routing 102) | `dive_counts_in` | el plan por su número de inmersiones | lista cerrada (se queda) |
| R13 | `_NOT_ALONE_RE`, `_MENTIONS_PERSON_RE`, `_SINGULAR_COMPANION_RE` (extraction) | listas de personas | señales de acompañantes | la red que quita el lector paso 3 (Álvaro) |

R11 y R12 leen listas cerradas del catálogo (cifra + unidad, nombres de hoteles): son la clase D del estudio ex-9 y
se quedan. R13 la retira Álvaro con el lector del grupo. Las candidatas a borrar son R1-R10.

## 3. Cómo se cuenta

Una marca por sitio, sin cambiar conducta: `observability.marca_regex("R3")` apunta en el turno qué rama decidió,
y la línea `[TURN_METRICS]` la lleva (`regex: [...]`), así que sale en el `.metricas` de cualquier ronda. Con una
ronda del golden visible (y la rotativa) se cuenta cuántos turnos decide cada rama y, en esos, si el extractor o Jev
decían lo mismo (entonces la rama sobra). Una rama con 0 decisiones en el golden y la rotativa, o que siempre
coincide con el extractor, se borra con sus tests.

Las marcas tocan seis ficheros del núcleo (routing, extraction, extractor, booking, core, redactor), los que parte
Álvaro: se ponen cuando se decida la ventana.

## 4. Primera cuenta (2-nov, rondas del 30-oct)

19 rondas del 30-oct con las marcas (0.39 y candidatas; 2.619 turnos; solo los `.metricas`, sin abrir diálogos). Turnos
en que decide cada rama: R7 446, R1 103, R3 44, R10 29, R8 9; **0**: R2, R4, R5, R6, R9. Son los mismos visibles
repetidos, sin rotativa ni sparring.

- R3 se queda: solo actúa cuando la respuesta a «¿desde dónde?» es de formato (un botón, «Cartagena» a secas) o la IA
  falla, y entonces lee la lista cerrada de lugares.
- R5 se queda aunque dé 0: es una guarda contra un error medido del resolutor LLM («2 inmersiones» o «mi hijo tiene
  9 años» como total de personas), no un respaldo.
- R6 y R9 arreglan casos concretos (gen-16, LAT-0b): se cuentan también en sparring o rotativa antes de decidir.
- **Fuera R2 y R4** (feature/caln8-regex-gonzalo): la duración del regex en la respuesta corta sin la IA y las edades
  en palabra sin la IA; con la IA las lee el extractor.
- El respaldo de ex-9b paso 6 (con el extractor caído, las edades y la duración del regex siguen valiendo; los tests
  «extractor caído como hoy» lo fijan a propósito) no tenía marca: **R11** (edades) y **R12** (duración), en
  `rutas/booking.py`. Si dan 0, se proponen fuera, y con ellos `detect_duration` entero (68 líneas del detector).
- Siguiente: si R1, R7, R8 y R10 coinciden con lo que lee el extractor.

## 5. Paso 5 (3-nov): ¿coinciden con el extractor? Leyendo los turnos (sin LLM, oculto filtrado: 21)

- **R7, mal contada.** Los 446 turnos eran «el mensaje nombra una actividad», no decisiones: la marca estaba dentro de
  `_mentioned_product_activities`. Ahora va donde decide: **R7a** (nombra otra actividad que la preguntada: se abstiene),
  **R7b** (la actividad de quien falta, por lo que nombra) y **R7c** (deliberación entre 2+ ofertas). Hay que volver a
  contarla.
- **R3 se queda:** 7 turnos distintos, todos «cartagena» o «desde cartagena» a secas.
- **R10 se queda:** 5 turnos distintos, todos «el paquete / plan de 5 buceos», bien leídos.
- **R1 no se puede comparar:** el extractor no lee el número de inmersiones (`dias_de_buceo` es otra cosa). Es la única
  lectura, de cifra + unidad. Se queda, con un falso positivo conocido, ×14 en las rondas: «vi un video de alguien que
  hizo el paquete… e hicieron dos inmersiones» fija 2 inmersiones por lo que hizo otra persona. En esa ronda, ese
  turno y el siguiente siguen con el menú de actividades (no comparado sin la lectura). No se toca hasta que dé un fallo visible.
- **R8 se queda.** Reproducida con traza en PRE 0.43: en grupo-mixto t1 ×6 no salta ninguna vez (las 3 veces del 30-oct
  fueron otra lectura del extractor); en frances-anticipacion t2 ×4 salta en 3 porque el extractor pone `padi_open_water`
  a alguien y el mensaje solo dice «nuestro curso en línea»: no se le asigna un curso que no nombra, que es su trabajo.
  De paso: grupo-mixto t1 se lee mal 3 de 6 (una 4.ª persona inventada; el buzo perdido), de la lectura del grupo y no
  de R8; pasado a Álvaro.
- **Recuento de R7 con las marcas nuevas** (mini de la 0.43, lado B, 201 turnos): R7b 1, R7a 0, R7c 0, frente a 37 con
  la marca vieja. Hay que contarla en más rondas antes de proponer nada.

## 6. Límite de este inventario

Solo cubre `intent_detector.py`. Hay regex que deciden fuera, sin marca: p. ej. `_detect_kids_mention`
(`rutas/router.py`: «since I was a baby» leído como que vienen menores, s03g). Las cifras de R1-R12 no las incluyen.
