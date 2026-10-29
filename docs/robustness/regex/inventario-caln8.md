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
