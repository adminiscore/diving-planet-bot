# Inventario de fuentes del negocio (lat-deuda-u) — 26-oct

Tarea pedida por Gadea: dónde vive cada dato del negocio que importa al cliente, qué huecos tiene y cómo unificarlo.

> **Estado (26-oct, tarde).** Decididas por Gadea las 11 preguntas del dueño y la moneda (D13: USD y COP).
> HECHO: Y1 (vuelo por actividad), Y2 (una regla de moneda), Y3 (tarjeta desde la ficha), Y4 (el equipo no va en todos
> los planes), Y5 (Rescue 12), Y6 (sin notas internas), Y7 (descuentos no acumulables), Y8 (políticas partidas, sin
> cortes por frases), Y10 (una lista de hoteles), Y11 a medias (fechas de cierre como dato y frase generada; falta que el
> extractor lea la fecha del cliente: decisión de Gadea), Y12 (muerto fuera, salvo lo que lee el juez), las copias de
> L9-5 en los requisitos (seguro, refresh, formulario, edad) y D1-D12. QUEDAN: Y9, Y13-Y17, L8-*, L9-1..4 y la regex de
> hoteles del detector viejo (`intent_detector.py`).
Hecho **solo leyendo** el repo (rama `integra-sim5`, HEAD 274baf9 con los cambios de avisos sin commitear), sin
llamadas a modelos. Los avisos (`avisos.json` / `avisos.py`) solo se citan como sitio donde vive un dato, sin
valorarlos.

**Huecos:** (a) REPETIDO · (b) UN IDIOMA · (c) UN CAMINO · (d) INSTRUCCIÓN al modelo en vez de dato · (e) A MANO EN EL CÓDIGO.
**Caminos:** F = flujo de reserva (textos fijos, tarjeta) · H = tabla de hechos + redactor · R-ctx = contexto fijo del
RAG (catálogo + enlaces + todas las políticas, `rag_agent.py:778-797`) · R-idx = índice `kb_v2` (fichas, FAQs
curadas, políticas, descuentos; `scripts/kb_v2.py:135-165`) · A = avisos · E = escalado (pase con texto fijo).

---

## 0. Quién lee cada fuente (mapa)

| Fuente | La leen | Partes que no lee nadie |
|---|---|---|
| `pricing.json` | `catalog.py:203-224` pone los 4 precios en cada ficha (todos los caminos) | `name_*`, `note_*`, `available`, `context_note_*`, `own_equipment_*`, `provisional`, `no_se_ofrece`: solo `scripts/load_embeddings.py:239-303` (índice v1, sin lector) y el juez |
| `services.json` | `catalog.SERVICES/RAW_SERVICES`: F (nombres, enlaces, tarjeta), H (incluye, itinerario, requisitos), R-ctx (catálogo), R-idx (fichas) | `price_note*` (29 servicios, casi todos solo en inglés), `summary_intro_*`, `itinerary_overview_*`; los campos derivados `price`, `extra_notes_*`, `extra_block_*`, `flight_rule_*` (`catalog.py:244-277`) no se usan |
| `activities.json` | `src/domain/activities.py`: edades, actividades, etiquetas (todos); `gloss`/`for_whom` a los prompts de Jev y del extractor | — |
| `policies.json` | H (~22 claves, varias cortadas por frases), R-ctx (todas, `catalog.policies_facts`), R-idx (todas), F (`closed_days` en `nucleo/availability.py:121-129`; `cancellation/reschedule/modify_booking` en `rutas/changes.py:204-222`; `no_alcohol/food` en `rutas/info.py:68-83`), A | — |
| `discounts.json` | H (`hechos.py:53-62`, `catalog.descuentos_de_la_base`), R-ctx (misma función), R-idx (`description_*`) | `combinable_with` y `discount_policies.non_cumulative` (**ningún camino**); `companion_note_*` no está en R-idx |
| `curada/faqs.json` | solo R-idx | — |
| `curada/preguntas.json` | solo R-idx (formas de preguntar) | — |
| `faqs.json` (v1) | nadie en el bot (fuente de `scripts/kb_curar.py`, juez «antigua», índice v1) | todo; tiene datos viejos (llegada 4:00 p. m., nocturno 6-8 p. m., precios) |
| `availability.json` | **nadie** | todo (temporada alta, horarios, cierre) |
| `escalation_rules.json` | **nadie** (los textos del pase viven en `escalation.py:37-100`) | todo (incluye un teléfono) |
| `brand_tone.json` | prompt del RAG (tono) | — |
| `avisos.json` | `avisos.py` | — |

Además, el CI regenera en cada deploy el índice v1 que no lee nadie (`.github/workflows/ci.yml:186`,
`load_embeddings --yes`: embeddings de pago) y ese índice dice «Descuento equipo propio: $0 COP por día de buceo»
(`scripts/load_embeddings.py:245,302-303`: lee `own_equipment_discount_cop`, que no existe).

---

## 1. Contradicciones (primero)

| # | Gravedad | Qué | Valores y sitios |
|---|---|---|---|
| C1 | **ALTA** | **Moneda cuando no se sabe la nacionalidad**: cada camino aplica una regla distinta | H: **USD y COP** (`hechos.py:72-74,176-184`; `prompts/info.py:652-661`, arq-5c, «decisión de Gadea, 23-oct»). R: **solo USD** (`catalog.py:701-702,728-729`; `rutas/contexto_rag.py:557-561`, CAL-B 15-oct). F: **solo USD** (`cart_render.py:66-69`; `state.py:69` por defecto; `conversational_core.py:2176-2179`), y la comparación del flujo da USD **siempre**, también al colombiano (`nucleo/routing.py:633-635`). Además «una sola moneda por mensaje» (G3-07a, `prompts/info.py:543-560`, `cart_render.py:66-69`) choca con «las dos monedas» de arq-5c: hay dos decisiones vigentes que se contradicen. |
| C2 | **ALTA** (seguridad) | **Espera para volar tras el refresher**: 18 h o 12 h | `policies.json:4` y FAQ #9/#49 (`curada/faqs.json:162,939`): refresher = **18 h**. Pero el refresher hereda la ficha del minicurso (`activities.json:479-497`, `sold_as: minicourse`), cuya lista de requisitos dice **12 h** (`services.json:1253,1258`): llega tal cual a H en `requisitos` (`hechos.py:210-214` vía `_plan_base`, origen Cartagena o desconocido) y a la ficha «Refresher» del índice (`scripts/kb_v2.py:92-125`, que solo cambia la descripción). |
| C3 | **ALTA** | **Tarjeta del flujo: qué incluye** el acompañante | `cart_render.py:179-189`: texto fijo «✅ Incluye: transporte…, almuerzo, **equipo** y seguro» para todo plan de día, también el acompañante (`cart_render.py:310-315`, `kind: "day"`); desde las islas «equipo… y acompañamiento de un profesional PADI». La base y H dicen que el acompañante **no** lleva equipo (`catalog.py:449-450`, FAQ #110 `curada/faqs.json:2097`). La misma línea dice «almuerzo» en los paquetes de varios días (solo el día 1: `policies.json:72`) y no avisa de la noche ni del parque. |
| C4 | MEDIA | **«El equipo va incluido en todos los planes»** | `policies.json:116` (what_to_bring) y FAQ #11 (`curada/faqs.json:201`) vs Divemaster «Tener equipo propio» / no incluye «Equipo de buceo completo» (`services.json:2434,2444`; `catalog.py:524-535`) y el acompañante. H añade `what_to_bring` a los requisitos de **toda** actividad (`hechos.py:221`), así que en el Divemaster la misma respuesta se contradice. |
| C5 | MEDIA | **Edad mínima del Rescue**: 10 o 12 | `activities.json:299` = 10 → H `edad` y la ficha del RAG («edad mínima 10», `catalog.py:352-353`). `eligibility.py:32,247-248,281-282`: «Advanced y Rescue desde los {MIN_ADVANCED}» = **12** (`activities.json:267`). El Rescue exige Advanced (12 según `policies.json:44`), así que 10 es incoherente. Docstring desfasado: `eligibility.py:12` («Advanced and Rescue from 10»). |
| C6 | MEDIA | **Curso Scuba Diver**: se ofrece o no | FAQ #33 (`curada/faqs.json:650`), #60 (`:1136`) y #107 (`:2038`, «También existe el Curso Scuba Diver PADI») vs `pricing.json:170,181` («No se ofrece», mej-2). |
| C7 | MEDIA | **Duración del Open Water** | FAQ #33/#34 (`curada/faqs.json:650,667`): «3-4 días, 5 módulos, 5 sesiones de aguas confinadas» vs 2 días y 2 sesiones de piscina (`services.json` open_water, `pricing.json:194-195`, `activities.json:230`, `conversational_core.py:385-391`). |
| C8 | MEDIA | **Hoteles con recogida**: 6 listas distintas | `policies.json:164` (base + Rosario de Mar, Secreto, Ubuntu, Mulata, Las Palmeras) · FAQ #22/#77/#106 (`curada/faqs.json:430,1443,2018`) **+ Pao Pao** · `extractor_turno.py:536-537` (sin Pao Pao) · `rag_agent.py:295-333` (~40, con Pao Pao, sin Mulata/Rosario de Mar/Las Palmeras) · `catalog.py:670-674` (solo la base) · `channels/audio.py:30`. |
| C9 | BAJA (solo respaldo) | **«¿Hay cupo mañana?»** | Palabras clave `real_time_issues` («hay cupo», «disponible mañana») → pase «depende de disponibilidad… en tiempo real» (`escalation.py:59-73`; solo si la IA calla, `supervisor.regex_decide`) vs «siempre hay disponibilidad» (`policies.json:108`, avisos, R). |
| C10 | MEDIA-BAJA | **Clima**: falta el reembolso | Pase de clima de un día concreto (vía Jev o palabras) con `escalation.py:139-147`: «se reprograma», sin el reembolso del 100 % de `policies.json:176`; FAQ #10 (`curada/faqs.json:181`) igual. |
| C11 | BAJA | Recogida en las islas | «entre 9:30 y 9:45» (`policies.json:64`, fichas) vs «hacia las 9:30» (FAQ #75, `curada/faqs.json:1409`). |
| C12 | BAJA | Divemaster | «al menos / mínimo 2 meses» (`services.json` divemaster, `activities.json:349`) vs «aproximadamente 2 meses» (FAQ #84, `curada/faqs.json:1586`). |
| C13 | BAJA | Edades en el contexto del RAG | `contexto_rag.py:621-628`: «Desde los 10 años: minicurso y **cursos PADI**» vs Advanced 12 y Divemaster 18. |
| C14 | BAJA | Planes con noche incompletos | `policies.json:84` nombra «Open Water, Curso Referido, Advanced» y no Rescue ni Mindful Diving (sus fichas sí piden 1 noche); H la da para todo plan de varios días (`hechos.py:542-550`). `policies.json:80` solo nombra los paquetes de 5/7/9 (el de 3 y el de 4 también piden certificación). |
| C15 | BAJA | Enlaces en inglés | Las fichas EN (contexto y R-idx) llevan `?language=es` (`catalog.py:365`, sin localizar) mientras `catalog_booking_links` da `language=en` (`catalog.py:792-793`): dos enlaces del mismo plan en el mismo contexto. |
| C16 | BAJA (sin lector) | Ficheros muertos que se contradicen | `availability.json:5` «Operamos todos los días del año» vs `:17` «solo se cierra el 25-dic y el 1-ene»; índice v1 «$0 COP» (sección 0). |

---

## 2. Inventario por dato (de más a menos impacto)

### Dinero

| Dato | Dónde está | Huecos | Grav. |
|---|---|---|---|
| **Precios** (plan × origen, online/normal, COP/USD) | Fuente: `pricing.json:13-554`, enlazada desde `services.json` (`tarifa`) en `catalog.py:203-224`. Copias: FAQ #94 Bubble Makers con los 8 importes **provisionales** (`curada/faqs.json:1792`). Precio del refresher armado en código (`catalog.py:651-664`). Fuera de la tarifa: Nitrox en tanque 10 USD (FAQ #102, `:1934`, sin COP). «1 inmersión no disponible desde Cartagena» y «buceo adicional»: las notas `available:false` de `pricing.json:23-29,157-163` no las lee ningún camino vivo; solo FAQ #103/#87 (`:1955,:1645`). | a (FAQ #94), c (Nitrox, no disponibles: solo R-idx), e (refresher) | MEDIA |
| **Moneda** (COP colombianos y residentes —también cédula de extranjería—; USD resto; grupo mixto → USD; sin nacionalidad → ?) | `policies.json:32,36`; `discounts.json:27-31` (sin cédula ni grupo mixto); `catalog.py:697-704/725-730` (regla + órdenes al modelo), `:750-755` (`MONEDA_SIN_NACIONALIDAD`, sin uso), `:763-772` (la del juez); `contexto_rag.py:548-561`; `hechos.py:72-81,166-184`; `prompts/info.py:169-170/216-217` (se quitan en `rag_agent.py:201-208`), `:652-661`; `cart_render.py:66-69,350-354`; `conversational_core.py:2178`; `nucleo/routing.py:633-635`; `nucleo/extractor.py:561-569`; FAQ #14, #90, #91 (`curada/faqs.json:263,1710,1731`); 3 avisos. | a (≥12 sitios, **C1**), d (catálogo, contexto, prompts), e (la regla «sin nacionalidad» y la del grupo mixto viven en código) | **ALTA** |
| **Forma de pago** (extranjero 100 % tarjeta en la web con pasaporte; colombiano 100 % online o 50/50 con asesor; transferencia solo si falla y se mantiene el 10 %; conciliación) | `policies.json:144` (dos reglas en un párrafo), `:152`, `:156`; H la corta por «El anticipo del 50 %» (`hechos.py:338-345,492-517`); a mano: `slotfill_close.py:190-203`, `contexto_rag.py:552-554`, `prompts/info.py:588-589,720-721`; FAQ #88-#93 (`curada/faqs.json:1665-1772`). Solo en FAQ #88: Llave, sin PayPal, cripto ni cuotas. FAQ #92 no dice que se mantiene el 10 %. | a (100/50 en 5 sitios), c (medios no aceptados: solo R-idx), d (prompt del redactor), e (cortes por frase, textos fijos) | **ALTA** |
| **Enlace y forma de reservar** (web, enlace por plan, cierre 4:30 p. m. del día anterior; colombiano sin enlace) | `services.json` `booking_url` (30, todos `?language=es`); idioma del enlace cambiado en 2 sitios (`catalog.py:792-793`, `cart_render.py:368-377`) y no en la ficha (`catalog.py:365`); cierre 4:30 repetido 5 veces **dentro** de `policies.json` (`:56,64,108,132,148`) + `availability.json:38` + FAQ #19, #75 + ejemplos en `prompts/info.py:149,195,439,444`; colombiano sin enlace en `hechos.py:243-245`, `contexto_rag.py:552-554`, `prompts/info.py:588,598-602`; URL de contacto de respaldo a mano (`catalog.py:282-283`); «es reserva directa» si la URL lleva `book.divingplanet.org` (`cart_render.py:208`, `conversational_core.py:2069`). | a (cierre ×9), b (**C15**), e | MEDIA |
| **Descuento online 10 %** | `discounts.json:3-9`; cabecera del catálogo a mano (`catalog.py:677-678,706-707`); `hechos.py:53-62`; `policies.json:132,156`; FAQ #14, #109 «no hay código» (`:2078`), #110; `services.json` `price_note*` (sin uso; `price_note_es` **en inglés** en `:12,:1192`). | a, b, e | BAJA |
| **Descuento de grupo** (10 % ≥5, se suma al online, pedirlo ANTES de pagar o se pierde, no en cursos PADI, el acompañante lo confirma el equipo) | Fuente completa `discounts.json:10-19`; `catalog.descuentos_de_la_base` (`catalog.py:603-616`, con la nota del acompañante) para H y R-ctx; R-idx solo `description_*` (`kb_v2.py:155`, **sin** la nota del acompañante); línea fija recortada en `catalog.py:692-696/721-724` que se sustituye siempre en `:731-735` (texto muerto); ejemplo recortado en `prompts/info.py:152,198`; avisos. | a, c (nota del acompañante fuera de R-idx), e (línea muerta) | MEDIA-BAJA |
| **Descuento equipo propio 5 %** y **acumulación** | `discounts.json:20-26`; copia en `pricing.json:4-6` (sin lector vivo); `prompts/info.py:151,197` (5 % + lista del equipo, como orden); línea fija muerta `catalog.py:695-696`; índice v1 «$0 COP» (`load_embeddings.py:302-303`). **Acumulación** (`discounts.json:8,18,25` `combinable_with`; `:33-37` `non_cumulative`: grupo + equipo **no** se suman): no la lee **ningún** camino. | a, c+ (acumulación: ningún camino), d, e | MEDIA |

### Logística

| Dato | Dónde está | Huecos | Grav. |
|---|---|---|---|
| **Horarios** (salida 8:00, vuelta 3:00 p. m. / llegada 4:15; islas 9:30-9:45, 8:00 especialidades, 7:30 día 2; nocturno 5:30-7:30 p. m.; actividades hasta 12-13 h; fijos) | `policies.json:64,104,148,172`; `availability.json:9-13` (sin lector); itinerarios de `services.json` (16 con «Bodeguita 8:00»); FAQ #2, #69, #75, #96 (`curada/faqs.json:39,1293,1409,1826`); `cart_render.py:191-192` (8:00 a mano); `faqs.json` v1 con 4:00 p. m. y nocturno 6-8 p. m. (fuente de `kb_curar.py`: si se regenera la curada, vuelven). «Llega 10-15 min antes»: solo FAQ #96. | a (≥25), c (antelación: solo R-idx), e. **C11** | MEDIA |
| **Días de cierre** (25-dic y 1-ene; festivos sí) | `policies.json:68,108`; `availability.json:5,17` (**C16**); a mano en `catalog.py:690-691,719-720`, `escalation.py:139-147`, `prompts/info.py:165,212,458-475`; regex de fechas sobre el texto del cliente `rutas/booking.py:23-35` (usado en `nucleo/availability.py:121-129`); FAQ #3, #76 (`curada/faqs.json:58,1426`); avisos. | a (≥10), d (prompt), e | MEDIA |
| **Disponibilidad** (siempre hay; fecha y personas en el enlace) | `policies.json:108`; `catalog.py:690-691`; `prompts/info.py:458-475` → `:486-495`; `hechos.py:227-229`; `escalation.py:59-73` (**C9**); avisos. | a, d, e | MEDIA |
| **Punto de encuentro** (Muelle de la Bodeguita, a 5 min del centro, **entrada 3**, «pregunta por DIVING PLANET», mapa; en Cartagena no se recoge en el hotel) | `policies.json:16` (sin entrada 3 ni mapa); FAQ #24 (`curada/faqs.json:476`, con entrada 3 y Google Maps); 16 itinerarios; a mano en `cart_render.py:191-192`, `conversational_core.py:778-785,2164-2173`, `contexto_rag.py:405-436`; `availability.json:9`. | a, c (entrada 3 y mapa: solo R-idx; H da `meeting_point` sin ellos), e | MEDIA-ALTA |
| **Recogida en las islas** (incluida si el hotel tiene acceso marítimo; base Majagua y Cocoliso en Isla Grande; punto y hora los coordina un asesor) | `policies.json:40` (tres reglas en un párrafo, cortado por frases en `hechos.py:419-452`), `:96`, `:164`; a mano `catalog.py:670-674`; listas de hoteles **C8**; FAQ #16, #77, #78, #86, #111 (`curada/faqs.json:304,1443,1467,1626,2119`); `cart_render.py:193-194`. | a, d (cortes por frase), e | MEDIA |
| **Barú / Playa Blanca / zona de operación** | `policies.json:40` (Barú dentro de `island_pickup`), `:100` (`dive_area`); FAQ #1, #79 (`curada/faqs.json:22,1489`); corte «quien se aloja en Barú» `hechos.py:404-416`; a mano en `extractor_turno.py:523,932-941`, `jev_router.py:672-690`, `prompts/booking.py:132-160`. **Playa Blanca solo existe en el código**, no en la base. | a, c (zona: solo R), e | MEDIA-BAJA |
| **Almuerzo y comida** (incluido desde Cartagena, solo el día 1 en los de varios días; no desde las islas; arroz con pollo o con vegetales; vegetarianos/celíacos; alergias; puede llevar su comida) | `policies.json:72,104`; fichas `included_*`/`not_included_*`; `catalog.py:510-516` (lo deduce buscando la palabra «almuerzo» en `includes_es`, también para inglés); a mano `conversational_core.py:2165-2172,2207`, `cart_render.py:179-182`, `catalog.py:451-456`; FAQ #11, #73, #74 (`curada/faqs.json:201,1369,1388`); aviso. | a, c (menú, dietas, alergias: solo R; H solo da «Almuerzo» de la ficha), e. **C3** | MEDIA |
| **Qué incluye / no incluye** (equipo, seguro, parque, lancha, fotos, propinas) | Fichas `included_*`/`not_included_*`; acompañante a mano `catalog.py:447-456`; «equipo incluido» deducido por palabra (`catalog.py:524-535`); tarjeta fija `cart_render.py:179-189`; `policies.json:116`; FAQ #11, #12, #15. | a, e. **C3, C4** | **ALTA** |
| **Alojamiento y planes con noche** | `policies.json:84` (lista incompleta, **C14**), `:80`, `:164`; fichas (`requirements_*`, `not_included_*` «Hotel/alojamiento», `overnight`); derivado en `catalog.py:386-399`; frases a mano `catalog.py:497-504`, `conversational_core.py:555-568`; `hechos.py:542-550`; FAQ #22, #35, #83, #106; **solo FAQ #95** (`curada/faqs.json:1809`): si un curso pierde un día por clima, la noche extra la paga el cliente. | a, c (noche extra: solo R-idx), e | MEDIA |

### Requisitos y producto

| Dato | Dónde está | Huecos | Grav. |
|---|---|---|---|
| **Requisitos y formularios** (carné; formulario médico de curso para cursos, minicurso y refresher; exoneración de buzo certificado; formato del seguro en el correo) | `policies.json:12,48` (dos formularios en un párrafo, cortado en `hechos.py:281-288` por «Si eres buzo certificado»), `:60,136`; enlace del formulario en 8 fichas de `services.json`; FAQ #18 (asma), #27, #28 (carné perdido: solo FAQ), #105 (`curada/faqs.json:347,533,554,1997`); refresher a mano en `conversational_core.py:603-616`. | a (8+ copias del enlace), b (los textos EN enlazan `exoneracion-curso-en-espanol`), c (carné perdido: solo R-idx), d (cortes por frase), e | MEDIA-ALTA |
| **Edades** (snorkel 6; Bubble Makers 8-10; minicurso/OW 10; Advanced 12; Rescue ?; Divemaster 18; menores acompañados) | Fuente `activities.json` `min_age` (`:19…:506`); `policies.json:44` (más una orden de estilo «EN CIFRA… (decisión de Gadea)»); fichas («Tener desde 10 años», «Edad mínima: 6 años», nitrox «al menos 10»); `for_whom` («Desde 10 años»); `catalog.py:317,322,352-353,689,718` («edad mínima 10» por defecto); a mano `cart_render.py:295,302`, `contexto_rag.py:621-638`; `eligibility.py:12,32,247-248,281-282`; FAQ #7, #8, #35, #37, #101. «Menores acompañados por un padre»: solo `policies.json:44` y FAQ #7 (R). | a (≥10), d (`policies.json:44`), e. **C5, C13** | MEDIA-ALTA |
| **Certificación** (el minicurso no certifica; primera certificación = Open Water; curso referido con carta; Scuba Diver no se ofrece) | `policies.json:140`; `activities.json` (`certifies`, `course_level`, `gloss`, `for_whom` `:93,:230`); `pricing.json:170,181`; ficha `referral`; a mano `conversational_core.py:385-391,405-418,466-475`; FAQ #29, #33, #34, #60, #107; avisos. H no tiene intención de certificación. `gloss` de `certified_diving` (`activities.json:23-24`): «es el valor por DEFECTO cuando se pide 'buceo'… tenga o no certificación», orden al modelo que choca con la norma de recomendar sin asumir. | a, c (solo avisos/R), d, e. **C6, C7** | MEDIA-ALTA |
| **Refresher** (>2 años sin bucear; se reserva y cobra como el minicurso; formulario de curso; vuelo 18 h; 500+ inmersiones lo revisa un asesor; ReActivate cuenta) | `policies.json:4,8,48`; `activities.json:479-497`; `pricing.json:31-40`; 9 fichas con la regla de 2 años; a mano: `kb_v2.py:78-125`, `catalog.py:651-664`, `conversational_core.py:591-595,603-616`, `slotfill_close.py:55-64`, `contexto_rag.py:563-566`, `prompts/booking.py:768-774`, `extractor_turno.py:82,570,593`; FAQ #17, #20 (`curada/faqs.json:326,387`); aviso. | a (umbral «2 años» en ≥15 sitios), e. **C2** | **ALTA** |
| **Vuelo tras bucear** | `policies.json:4`; **31** líneas de requisitos en `services.json`; `_flight_rule` (`catalog.py:115-121`, sin uso); H `tiempo` (`hechos.py:312-318`); FAQ #9, #49. | a (31 copias). **C2** | **ALTA** |
| **Cancelaciones y cambios** | `policies.json:20,24,28` (solo «ver términos» + URL), `:168,176`; `rutas/changes.py:204-255` (política + pase); FAQ #10, #30, #95, #96 («llegas tarde = sin reembolso», solo FAQ). Los términos reales (plazos, reembolsos) **no están en la base**. | c (llegar tarde, curso perdido: solo R-idx), e | MEDIA |
| **Clima** | `policies.json:68,176`; `availability.json:42` (sin lector); `escalation_rules.json` (sin lector); a mano `escalation.py:51-58,139-147`, `hechos.py:484-489` (`_PREVISION`), `prompts/info.py:673-684` (resume la política en el prompt); FAQ #10, #30, #63, #67. | a, d, e. **C10** | MEDIA |
| **Fotos y vídeos** (no incluidas; el instructor puede hacerlas; propina voluntaria; también minicurso, refresher y cursos) | `policies.json:76` (con «(Gadea, 21-oct)» en el texto ES); fichas `not_included_*`; FAQ #15, #72 (`curada/faqs.json:284,1349`). | c (H no tiene intención; solo R), nota interna en el texto | BAJA-MEDIA |
| **Profundidad** (minicurso 12 m; Bubble Makers 2 m; OW 18; Advanced 30) | `max_depth_m` solo en 4 fichas (OW y Advanced, `services.json`); `catalog.py:538-585`; `activities.json` (`pitch` «hasta 18 m», `for_whom` «hasta 30 metros»); Bubble 2 m dentro de `policies.json:44`; FAQ #6 (`curada/faqs.json:111`, **minicurso 12 m: solo aquí**), #33 (Scuba Diver 12 m), #48 (Deep 40 m), #64 (sitios 5-40 m). | a, c (minicurso: solo R-idx; H sin intención), e | MEDIA |
| **Acompañante** (precio único en los dos orígenes; incluye lancha, almuerzo, seguro, parque —en las islas sin lancha desde Cartagena ni almuerzo—; sin equipo; descuento de grupo a confirmar; puede quedarse en la base) | `pricing.json:82-91`; `activities.json:498-521`; a mano `catalog.py:438-456,680-688`; `hechos.py:520-539`; `cart_render.py:310-315` + `179-189` (**C3**); `discounts.json:15-16`; FAQ #16, #110 (`curada/faqs.json:304,2097`; «quedarse en la base»: solo aquí). | a, c, e. **C3** | MEDIA-ALTA |
| **Servicios privados / grupos grandes** | `policies.json:88`; ficha `private`; a mano `rutas/info.py:110-122` (su comentario dice que la política lleva un teléfono: ya no lo lleva); umbral de 15 personas a mano (`catalog.py:401-407`); FAQ #80. | a, e | BAJA |
| **Otros solo en FAQ (solo R-idx)** | Nitrox en tanque (`curada/faqs.json:1934`), máscaras graduadas (`:1898`), equipo infantil (`:1917`), certificación digital (`:1862`), combinar cursos (`:1879`), oficina (`:5`), temporada alta (`:77`; y `availability.json:23-29`, sin lector), condiciones del agua (`:1187`); presentación «30 años» a mano (`prompts/info.py:60,64`; FAQ #23 `:453`) frente a «Desde 1995» (`src/main.py:183`; en 2026 son 31). | c, e | BAJA |

### Patrones que se repiten (los mismos del caso de los avisos)

1. **Políticas que juntan varias reglas en un párrafo y el código las corta por frases literales**: `hechos.py:281` (formulario), `:338` (pago), `:406` (Barú), `:422-423` (recogida / lo que no incluyen las islas). Si el dueño reescribe una frase, el corte deja de encontrarla y en silencio se da la política entera o nada.
2. **Fichas que copian políticas**: el vuelo (31 líneas), el refresh (9), el formulario médico (8), el seguro, el punto de encuentro (16). Por eso el refresher hereda las 12 h (C2).
3. **El código reescribe la base con menos detalle**: tarjeta del flujo (C3), escalado del clima sin reembolso (C10), FAQ #92 sin el 10 %, `policies.meeting_point` sin la entrada 3 de la FAQ, índice sin la nota del acompañante del descuento de grupo.
4. **Notas internas dentro del texto que ve el cliente**: `services.json:446-447,459-460` (Bubble Makers «decisión de Gadea… confirmar con Andrés», va a la ficha del RAG), `policies.json:44,76` («decisión de Gadea», «(Gadea, 21-oct)», van al contexto fijo del RAG).
5. **Órdenes al modelo escritas como dato**: `policies.json:44` («se dice la edad EN CIFRA»), `activities.json` `gloss`/`for_whom` (además repiten edades, días y metros que ya son campos), la regla de moneda del catálogo (`catalog.py:697-704`).
6. **Datos sin lector**: `availability.json`, `escalation_rules.json`, notas de `pricing.json`, `price_note*`, `combinable_with`/`non_cumulative`, `faqs.json` v1.

---

## 3. Arreglos propuestos

Etiquetas: **[YA]** sin llamadas, se puede ya (no hace falta llamar a modelos para hacerlo; si cambia lo que ve el cliente, va con su test y entra en la próxima medida; tocar la base regenera `kb_v2` en el deploy, céntimos de embeddings) · **[LAT-8]** ampliar la tabla de hechos · **[LAT-9]** un solo escritor · **[DUEÑO]** revisión de la base con el dueño.

### Sin llamadas, se pueden ya — 17

| # | Arreglo | Fuente única propuesta |
|---|---|---|
| Y1 | **Vuelo del refresher (C2)**. Sacar la regla del vuelo de los `requirements_*` de las fichas y darla como dato de cada actividad; H y la ficha la ponen desde ahí. Regla general: lo que una actividad hereda de la ficha con la que se vende (`sold_as`) no incluye las reglas que son de la actividad. | `activities.json`: campo `horas_antes_de_volar` (18 por defecto; 12 minicurso y Bubble Makers; 18 refresher), con el texto de `policies.flight_after_diving` |
| Y2 | **Moneda (C1)**, en cuanto Gadea elija UNA regla para «sin nacionalidad» (ver D13): la regla como dato y **una** función (`hechos._moneda`) que usen el catálogo, el contexto del RAG, la tarjeta, `_dos_variantes` y la comparación (`routing.py:633-635`, que hoy da USD también al colombiano). | `policies.json`: `colombian_pricing` + `mixed_nationality_group` + clave nueva para nacionalidad desconocida |
| Y3 | **Tarjeta del flujo (C3)**: la línea «✅ Incluye…» sale de `included_*` del plan (y del acompañante, Y9), no de un texto fijo; la salida («8:00, Muelle de la Bodeguita») del dato del punto de encuentro. | `services.json` `included_*` + `policies.meeting_point` |
| Y4 | **«Equipo incluido en todos los planes» (C4)**: `what_to_bring` solo dice qué llevar; si el equipo va incluido lo dice cada plan (ya está en `included_*`); H no añade lo del equipo si el plan no lo incluye. | `services.json` `included_*`/`not_included_*` |
| Y5 | **Edad del Rescue (C5)**: tras D1, una sola fuente; `eligibility.py` usa `dom.by_id("padi_rescue").min_age` y no `MIN_ADVANCED`; se corrige el docstring; `contexto_rag.py:621-638` y `cart_render.py:295,302` generan las edades del registro. | `activities.json` `min_age` |
| Y6 | **Notas internas fuera del texto del cliente**: `services.json:446-447,459-460`, `policies.json:44,76` → a un campo `_nota`; la orden «edad EN CIFRA» ya está en el prompt del redactor (`prompts/info.py:581-582`): quitarla de la política. | el campo `_nota` de cada entrada |
| Y7 | **Acumulación de descuentos**: `descuentos_de_la_base` añade `non_cumulative` (o lo deriva de `combinable_with`); así llega a H `descuento`, al catálogo del RAG y al índice. | `discounts.json` |
| Y8 | **Partir las políticas que se cortan por frases**: `medical_restrictions` → `medical_form_course` / `waiver_certified_diver`; `foreign_card_payment` → `payment_international` / `payment_colombian`; `island_pickup` → `island_pickup_how` / `island_plans_exclude` / `baru_departs_from_cartagena`. Se borran los `_CORTE_*` de `hechos.py`. | `policies.json` (claves nuevas) |
| Y9 | **Acompañante**: lo que incluye por origen (`catalog.py:447-456`) a la base. | `pricing.json` `acompanante` (o una ficha `companion` en `services.json` con `included_*` por origen) |
| Y10 | **Hoteles (C8)**: una lista estructurada que lean `extractor_turno.HOTELES_DE_LA_BASE`, `jev_router`, el catálogo (`catalog.py:670-674`) y `channels/audio.py`; que el detector de lugares (`rag_agent.py:295-333`) incluya al menos esa lista (hoy le faltan Mulata, Rosario de Mar y Las Palmeras). Pao Pao, según D5. | `policies.json`: `island_hotels: [{nombre, base, recogida: confirmada \| a confirmar}]` |
| Y11 | **Días de cierre**: fechas estructuradas; los textos del catálogo, del escalado y del prompt se generan; el cierre se comprueba comparando la **fecha que ya da el extractor** con esas fechas (arreglo por causa), en lugar de la regex de `rutas/booking.py:30-35` sobre el texto del cliente. | `policies.json`: `closed_dates: ["12-25","01-01"]` + `closed_days` como texto |
| Y12 | **Borrar datos y código muertos**: `availability.json` (la temporada alta, si se quiere, a una política), `escalation_rules.json`; en `pricing.json`, `own_equipment_*`, `context_note_*`, `note_*`/`available` (lo que valga, a las políticas, D7); en `services.json`, `price_note*` (`price_note_es` está en inglés), `summary_intro_*`, `itinerary_overview_*`; en `catalog.py`, `_format_price`, `_extra_notes*`, `_flight_rule` y los campos `price`, `extra_*`, `flight_rule_*`, `MONEDA_SIN_NACIONALIDAD` y la línea fija de descuentos (`:692-696/721-724`); en el CI, el paso `load_embeddings --yes` (`ci.yml:186`) y `load_knowledge_base` (se quedan los helpers que importa `kb_v2`). Ahorra embeddings en cada deploy y quita el «$0 COP». | — |
| Y13 | **Enlaces por idioma (C15)**: una función de enlace por idioma compartida por `service_fact_sheet`, `catalog_booking_links` y `cart_render`. | `services.json` `booking_url` + la función |
| Y14 | **Textos fijos del flujo que llevan datos** (`conversational_core.py:385-391,412-418`: «2 días… 4 inmersiones»; `slotfill_close.py:190-203`: 100 %/50 %; `contexto_rag.py:548-554`; `rutas/info.py:110-122`): que lean el dato. | ficha (`duration_days`, `num_dives` de la tarifa), `policies.payment_colombian` (Y8), `policies.private_services` |
| Y15 | **Cabeceras del catálogo con datos a mano** (`catalog.py:677-678` «online = 10 %», `:689` «edad mínima 10», `:690-691` cierre, `:697-704` moneda): generarlas de la base o quitarlas si se hace L9-1. | `discounts.json`, `activities.json`, `policies.json` |
| Y16 | **Umbral «2 años» del refresher** como dato usado en sus ~15 textos (y el umbral de 15 personas para grupos grandes, si el dueño lo confirma como regla). | `activities.json` `refresher.inactividad_anos` |
| Y17 | **Punto de encuentro completo**: «entrada 3», «pregunta por DIVING PLANET» y el mapa (hoy solo FAQ #24) a la política; H `recogida` ya lo daría. | `policies.meeting_point` |

### Para lat-8 (ampliar la tabla) — 8

| # | Arreglo | Fuente única |
|---|---|---|
| L8-1 | Fotos y vídeos: intención propia o dentro de `incluye`/`no_incluye`. | `policies.photos_videos_policy` |
| L8-2 | Profundidad por actividad (minicurso 12, Bubble 2, OW 18, Advanced 30; salida certificada = la de su certificación) e intención `profundidad`. | `activities.json` `max_depth_m` |
| L8-3 | Comida (menú, vegetarianos, alergias, llevar comida) con `incluye` cuando se pregunta por el almuerzo, o intención `comida`. | `policies.food_policy` |
| L8-4 | Certificación: si el plan certifica, qué curso es el primero, el referido. | `activities.json` (`certifies`, `course_level`) + `policies.minicourse_scope` |
| L8-5 | Alojamiento: los hoteles (Y10) y la noche extra si se pierde un día de curso (hoy solo FAQ #95) en `alojamiento`. | `policies.json` (`island_hotels`, regla nueva del día perdido) |
| L8-6 | Cancelaciones y cambios en general (sin reserva hecha): términos, llegar tarde, clima. Después de D4. | `policies.json` |
| L8-7 | Zona de operación y Barú/Playa Blanca. | `policies.dive_area` + `baru_departs_from_cartagena` (Y8) |
| L8-8 | Lo que hoy solo está en FAQs (Nitrox en tanque, máscaras graduadas, medios de pago no aceptados, Llave) en `pago`/`incluye`. Después de D7. | `pricing.json` / `policies.json` |

### Para lat-9 (un solo escritor) — 5

| # | Arreglo | Fuente única |
|---|---|---|
| L9-1 | Precio y moneda los escribe solo la tabla (el RAG ya recibe hechos para esa parte, arq-1g); fuera la regla de moneda del catálogo y del contexto del RAG. Resuelve C1 de raíz. | `pricing.json` + regla de Y2 |
| L9-2 | «Qué incluye»: una sola función (la de H) para la tarjeta, el catálogo del RAG y `_dos_variantes`. | `services.json` |
| L9-3 | Disponibilidad, cierre y clima: un escritor (H); el pase de clima y el de «tiempo real» reutilizan el texto del hecho (`escalation.py:59-73,139-147`). | `policies.json` |
| L9-4 | Las ~30 FAQs curadas que repiten políticas o precios (#2, #3, #7, #9, #11, #12, #14-#17, #19, #20, #22, #24, #30, #49, #72, #73, #75-#77, #86, #88-#94, #105, #106) fuera del índice, o solo como formas de preguntar que apuntan a su política (como `curada/preguntas.json`): termina el «una regla, un sitio» de rag-2. | `policies.json`, `pricing.json` |
| L9-5 | Las fichas no copian políticas (vuelo ×31, refresh ×9, formulario ×8, seguro, punto de encuentro ×16): las pone la ficha o la tabla desde la política. | `policies.json` + Y1 |

### Revisión de la base con el dueño — 13

| # | Pregunta | Dónde se corrige |
|---|---|---|
| D1 | Edad mínima del Rescue (10 o 12) y de las especialidades (Nitrox «al menos 10»). | `activities.json:299,387-469` |
| D2 | Scuba Diver: no se ofrece → reescribir FAQ #33, #60, #107 o que digan «no lo ofrecemos». | `curada/faqs.json:650,1136,2038` |
| D3 | Open Water: «3-4 días, 5 sesiones» (FAQ #33/#34) frente a 2 días y 2 sesiones de piscina. | `curada/faqs.json:650,667` |
| D4 | Términos de cancelación y cambio: qué puede decir el bot (plazos, reembolsos). Hoy la base solo tiene el enlace. | `policies.json:20-29` |
| D5 | Hoteles: ¿entra Pao Pao? ¿En cuáles está confirmada la recogida? | Y10 |
| D6 | Precios provisionales de Bubble Makers: confirmarlos y quitar la copia de la FAQ #94. | `pricing.json:73-81,359-367`; `curada/faqs.json:1792` |
| D7 | Nitrox en tanque (10 USD, ¿y en COP?), máscaras graduadas, Llave / sin PayPal ni cuotas: confirmar y pasarlo a la tarifa o a las políticas. | `pricing.json`, `policies.json` |
| D8 | ¿Hay formulario médico y de exoneración en inglés? Los textos EN enlazan el de «en-espanol». | `policies.json:48-49,136-137`, `services.json` |
| D9 | Divemaster: «al menos 2 meses» o «aprox. 2 meses». | `curada/faqs.json:1586` |
| D10 | ¿Se suman el descuento de grupo y el de equipo propio? (`combinable_with` dice que no) | `discounts.json:18,25,33-37` |
| D11 | Playa Blanca en la política (hoy solo en código); «30 años» frente a «desde 1995» → un dato `fundado: 1995`. | `policies.json:40`; `prompts/info.py:60,64`; `src/main.py:183` |
| D12 | Planes con noche: Rescue y Mindful Diving en `courses_overnight_requirement`; paquetes de 3 y 4 en `packages_certification_requirement`; el paquete de 3 inmersiones desde Cartagena: ¿cuándo se vuelve? (el itinerario acaba en la noche del día 1). | `policies.json:80,84`; `services.json` `3_dives_1_day` |
| D13 | (Gadea) Moneda sin nacionalidad: ¿USD (CAL-B, 15-oct) o USD y COP (arq-5c, 23-oct)? ¿Y «una sola moneda por mensaje» (G3-07a, 18-oct)? Hoy están vigentes las tres. | Y2 / L9-1 |

**Recuento:** 17 [YA] · 8 [LAT-8] · 5 [LAT-9] · 13 [DUEÑO]. Y2 y Y5 esperan a una decisión (D13, D1). Orden
propuesto: Y1, Y3, Y6, Y7 y Y12 primero (seguridad, lo que ve todo cliente que cierra, y borrar); después D13 → Y2
y luego Y8 + L9-5 (son el mismo movimiento: políticas partidas y fichas sin copias).
