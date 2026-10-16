# Informe ex-10 (15-oct-2026): examen completo con el oculto, 73 fallos por causa y plan de la fase CAL

Ronda `2026-10-15-ex10-completa` (PRE `21d4356`, 116 diálogos, ~465 turnos), juez gpt-5-mini medium con la
referencia curada. Resultado del juez: `docs/robustness/golden-set/results/2026-10-15-ex10-completa__gpt-5-mini-medium.json`.
Fallos clasificados (uno por línea, con su causa): `docs/robustness/ex10/fallos-ex10-por-causa.json`.
Herramienta para partir cualquier ronda por grupos: `python -m scripts.resumen_por_grupo <resultado.json> [otro.json]`.

## 1. Resultado frente a las referencias (mismo cálculo para todas)

| Grupo | 2-oct completa (juez de entonces) | 8-oct visible (base oficial de ex-10) | **15-oct ex-10** |
|---|---|---|---|
| Visible total (95) | 90,8 %, 55/95 | 92,8 %, 61/95 | **94,5 %, 66/95** |
| Visible reales (52, de WhatsApp) | 86,3 %, 18/52 | 88,7 %, 24/52 | **91,0 %, 26/52** |
| Visible sintéticos (43) | 96,7 %, 37/43 | 98,0 %, 37/43 | **99,0 %, 40/43** |
| **Examen oculto (21, todos reales)** | 76,5 %, 4/21 → **re-juzgado con el juez de hoy: 83,0 %, 8/21** | — | **82,7 %, 6/21** |
| Todos los reales (73) | 83,3 % | — | **88,5 %, 32/73** |

- El oculto del 2-oct se re-juzgó (`2026-10-02-oculto-rejuicio`) con el juez de hoy: el cambio de juez del 7-oct sube
  ~6,5 puntos por sí solo. La comparación justa del oculto es **83,0 → 82,7 %: plano**.
- **Lectura:** la fase EX mejoró lo visible (+1,7; reales +2,3) pero **no generalizó** a conversaciones nuevas. El oculto
  falla por las MISMAS causas que lo visible (sección 3): son causas generales sin cerrar, no casos raros.
- El oculto queda GASTADO: sus casos pasan al banco de fallos (CAL-0). Hace falta un examen oculto nuevo con
  conversaciones reales no vistas (g-4b / testers g-6).

### Metas de ex-10
| Meta | Resultado |
|---|---|
| Reales ≥ 92 % | ❌ 91,0 % visibles; 88,5 % con el oculto |
| Latencia p50/p95 no peores | ✅ p50 2,79 → 2,69 s; p95 6,53 → 6,76 s (+0,2, ruido) |
| Correcciones de redes ~0 | ✅ redes quitadas en ex-9 |

### Latencia y negocio
| | 2-oct | 8-oct (base) | **ex-10** |
|---|---|---|---|
| Latencia total p50 / p95 | 2,35 / 5,48 s | 2,79 / 6,53 s | **2,69 / 6,76 s** |
| Turnos de reserva p50 / p95 | 1,52 / 3,15 s | 1,93 / 3,82 s | **1,46 / 2,64 s** |
| Turnos de RAG p50 / p95 | 3,50 / 6,28 s | 4,13 / 7,43 s | **4,38 / 7,60 s** |
| Enrutador Jev p50 / p95 | 327 / 425 ms | 565 / 847 ms | **410 / 541 ms** |
| Llamadas LLM por turno | 3,14 | 3,02 | 3,42 |
| Conversaciones con enlace de pago | 18,1 % | 25,3 % | **32,8 %** |
| Escalados a persona | 13,8 % | 17,9 % | 15,5 % |

## 2. Decisiones de Gadea (15-oct)
- **Moneda sin nacionalidad:** si el cliente pide precio y no sabemos su nacionalidad → precio en **USD** (no las dos
  monedas). Colombianos/residentes conocidos → COP. Grupo mixto → todo en USD.
- **Teléfono / WhatsApp:** si el cliente pide un teléfono o contacto, NO se da un número: **se le pasa con una persona**.

## 3. Los 73 fallos por causa

| Causa | Visible real (38) | Oculto (32) | Sintético (3) | **Total** |
|---|---|---|---|---|
| 1. El RAG omite información que debía dar | 13 | 6 | – | **19** |
| 2. Moneda y nacionalidad | 9 | 6 | 1 | **16** |
| 3. Repregunta la actividad | 2 | 5 | 1 | **8** |
| 4. Supone algo que el cliente no dijo | 4 | 4 | – | **8** |
| 5. Repregunta otro dato ya dado | 3 | 3 | – | **6** |
| 6. No pide un dato necesario antes de cotizar | 3 | 2 | – | **5** |
| 7. Dato falso | 2 | 2 | – | **4** |
| 8. No da el contacto (decisión: pasar a persona) | – | 1 | 1 | **2** |
| Idioma | 1 | 1 | – | 2 |
| Enlaces / escalado / juez | 1 | 2 | – | 3 |

**35 de 73 son el RAG incompleto (19) y la moneda (16).** Las repreguntas, suposiciones y datos no pedidos (27) son
del entendimiento del flujo (extractor con frases nuevas, RAG sin la fecha de hoy, cotizar sin origen).

## 4. Detalle de cada fallo

### Visible real (52 diálogos): 38 fallos


**El RAG omite información que debía dar (13)**

- `confirmacion-salida-y-pago-sin-concepto` / `operamos-diario-clima` (revisar): No aclaró operación diaria ni suspensión solo por mal clima.
- `confirmacion-salida-y-pago-sin-concepto` / `confirmacion-por-pago-enlace`: No indica que reserva se confirma al pagar por el enlace online.
- `programa-fotos-y-alojamiento` / `fotos-politica`: No explicó política de fotos/videos ni su carácter voluntario.
- `paquete-5-buceos-precio-overnight-isla-grande-baru` / `geografia-rosario-vs-baru` (revisar): No aclaró que Barú no es Islas del Rosario ni dónde operan.
- `tours-diarios-isla-grande` / `pickup-islas`: No informó recogida en hotel en Islas del Rosario ni pidió nombre del hotel.
- `refresher-que-completar-antes` / `formulario-medico-refresher`: No indicó que el formulario médico se envía tras reservar
- `pareja-certificados-cop-descuento-almuerzo` / `descuentos-vigentes`: No menciona descuentos vigentes ni aclara ausencia de descuento colombiano.
- `open-water-hoteles-noche-fotos-horario` / `pernocta-obligatoria`: No confirma mínimo de noches requeridas para cursos de 2 días.
- `descuento-online-sin-codigo` / `descuento-automatico-sin-codigo`: No explicó que el 10% online se aplica automáticamente sin código.
- `recogida-ubuntu-comida-y-certificacion` / `comida-desde-islas`: No mencionó opción de comprar comida en el hotel.
- `recogida-ubuntu-comida-y-certificacion` / `minicurso-no-certifica`: No explicó requisitos ni imposibilidad de certificar en el tiempo solicitado.
- `curso-referido-pide-datos-centro` / `referido-requisito-carta`: No menciona requisito de carta de referido PADI firmada.
- `curso-open-water-principiantes-idioma-frances-anticipacion` / `anticipacion-cierre-sistema`: No informa reserva web tras cierre 4:30 p.m.

**Moneda y nacionalidad (9)**

- `open-water-precio-para-colombianos-corrige-mito` / `sin-precio-especial-colombianos`: No ofreció el valor en COP solicitado por cliente colombiano.
- `curso-open-water-precio-cop-hoteles-y-transporte` / `moneda-cop-colombianos`: No cotizó en COP a cliente colombiana que lo pidió.
- `acompanante-madre-desde-cartagena` / `precio-moneda-o-pregunta`: No preguntó nacionalidad antes de cotizar, incumpliendo regla de moneda.
- `paquete-5-buceos-precio-overnight-isla-grande-baru` / `precio-y-moneda-correctos`: No preguntó nacionalidad antes de cotizar, moneda incorrecta.
- `pareja-certificados-cop-descuento-almuerzo` / `precio-moneda-cartagena-cop`: No cotizó en COP para colombianos como indica la regla de moneda.
- `colombianos-precio-minicurso-dos-inmersiones` / `precio-minicurso-cop-o-origen`: No pregunta nacionalidad ni aplica regla de moneda antes de cotizar.
- `minicurso-precio-colombianos-origen-pendiente` / `moneda-colombianos`: No aclaró que colombianos pagan en COP y precio es igual.
- `moneda-precios-principiante-y-snorkel` / `moneda-por-nacionalidad`: No preguntó nacionalidad antes de cotizar moneda adecuada.
- `familia-mixta-precio-descuento-refresher` / `precio-mixto-cartagena-o-pregunta-faltantes`: No pidió nacionalidad antes de cotizar, omitió regla de moneda.

**Supone algo que el cliente no dijo (4)**

- `snorkel-precio-residente-y-pago-link` / `global:sin-invenciones` (revisar): Supone que ambos son residentes sin que el cliente lo diga
- `descuento-online-sin-codigo` / `global:sin-invenciones`: El bot supone un fallo técnico no mencionado por el cliente.
- `principiante-hora-lugar-y-precio` / `global:sin-invenciones`: Supone plan y punto de salida sin que cliente lo indique
- `precios-y-disponibilidad-con-negociacion` / `global:sin-invenciones`: Supone que la ventana de reserva ya cerró sin dato de hora actual.

**No pide un dato necesario antes de cotizar (3)**

- `reserva-paquete-5-buceos-solicita` / `origen-cartagena-o-islas`: Cotizó y envió enlace sin preguntar el origen del cliente.
- `refresher-que-completar-antes` / `valida-tiempo-sin-bucear`: No preguntó hace cuánto no bucea antes de reservar.
- `principiante-hora-lugar-y-precio` / `aclarar-actividad`: No pidió certificación ni preferencia por minicurso antes de cotizar.

**Repregunta otro dato ya dado (3)**

- `semana-santa-solo-avanzado-islas` / `global:sin-repreguntas`: Vuelve a preguntar fechas ya indicadas por el cliente.
- `paquete-5-buceos-islas-residente-sin-recogida` / `global:sin-repreguntas`: Vuelve a preguntar residencia ya indicada por el cliente.
- `recogida-ubuntu-comida-y-certificacion` / `global:sin-repreguntas`: Preguntó origen aunque cliente ya dijo hospedaje en las islas.

**Dato falso (2)**

- `paquete-5-buceos-islas-residente-sin-recogida` / `global:sin-invenciones`: Afirmó que el paquete es ida y vuelta el mismo día.
- `certificado-precio-dia-paquete-5-y-hoteles-base` / `precio-dia-cartagena`: Da precio incorrecto, no corresponde al plan solicitado.

**Repregunta la actividad (2)**

- `pareja-certificados-cop-descuento-almuerzo` / `global:sin-repreguntas`: Bot repregunta plan ya indicado por el cliente
- `agencia-solicita-tarifas-escalar` / `global:sin-repreguntas`: Bot preguntó actividad ya mencionada por el cliente previamente.

**Idioma (1)**

- `grupo-mixto-precio-cop-total` / `global:idioma`: Respondió en español en vez de inglés al mensaje en portugués

**Error del juez (1)**

- `agencia-solicita-tarifas-escalar` / `global:un-saludo`: El juez falla aunque el bot actuó según la base

### Examen oculto (21 diálogos reales): 32 fallos


**El RAG omite información que debía dar (6)**

- `certificado-profundidad-precio-y-base-hotel` / `profundidad-segun-nivel`: No explicó profundidad según certificación ni preguntó nivel del tío.
- `link-pago-extranjeros-sin-cedula` / `moneda-extranjeros`: No aclaró que extranjeros pagan en USD, misma tarifa, cambia moneda.
- `paquete-5-buceos-precio-fecha-y-equipaje` / `no-operamos-en-baru`: No aclara que no operan en Barú y salidas son en Rosario.
- `pareja-reactivate-y-refresh-cartagena` / `politica-refresh`: No aclara política de refresh tras 2 años ni valida Reactivate del cliente.
- `pareja-reactivate-y-refresh-cartagena` / `grupo-mixto-permitido`: No confirma que ambos pueden ir juntos en el mismo tour.
- `precio-dispo-buceo-certificado-grupo-mixto` / `mixto-moneda-usd`: No aclaró política de pago en USD para grupos mixtos.

**Moneda y nacionalidad (6)**

- `certificado-profundidad-precio-y-base-hotel` / `precio-cartagena-moneda` (revisar): Cotizó sin preguntar nacionalidad, incumpliendo regla de moneda.
- `cotiza-buceo-snorkel-y-pide-link-especial` / `pide-datos-para-cotizar`: No pidió nacionalidad antes de cotizar, incumpliendo regla de moneda.
- `grupo-mixto-cotiza-y-pide-link` / `moneda-segun-nacionalidad`: No pregunta nacionalidad ni aplica regla de moneda para grupo mixto.
- `open-water-precio-duracion-hospedaje` / `precio-moneda-origen` (revisar): Cotizó sin preguntar nacionalidad, no aplicó regla de moneda.
- `principiante-precio-y-evaluacion-medica` / `pide-datos-antes-de-precio`: No pidió nacionalidad antes de cotizar, incumpliendo regla de moneda.
- `precio-dispo-buceo-certificado-grupo-mixto` / `origen-cartagena-o-islas`: No pregunta origen antes de cotizar, da precio 'ya en islas' directo.

**Repregunta la actividad (5)**

- `certificado-profundidad-precio-y-base-hotel` / `global:sin-repreguntas`: Bot repregunta actividad ya indicada por el cliente
- `disponibilidad-hora-precio-y-pecios` / `global:sin-repreguntas`: Bot volvió a preguntar actividad ya indicada por el cliente.
- `open-water-precio-duracion-hospedaje` / `global:sin-repreguntas` (revisar): Bot repregunta curso tras cliente pedir certificación
- `paquete-5-buceos-precio-fecha-y-equipaje` / `global:sin-repreguntas`: Bot repregunta actividad ya indicada por el cliente
- `principiantes-no-certificados-minicurso` / `recomienda-minicurso`: Volvió a preguntar la actividad ya indicada por el cliente.

**Supone algo que el cliente no dijo (4)**

- `certificado-viernes-precio-cop-y-reserva` / `global:sin-invenciones` (revisar): Supone cierre de reservas sin evidencia en la base
- `cotiza-buceo-snorkel-y-pide-link-especial` / `global:sin-invenciones`: Supone punto de salida sin que el cliente lo haya indicado
- `pareja-reactivate-y-refresh-cartagena` / `global:sin-invenciones`: El bot asume el año sin que el cliente lo haya dicho.
- `precio-dispo-buceo-certificado-grupo-mixto` / `global:sin-invenciones`: El bot asumió el origen del cliente sin que lo dijera.

**Repregunta otro dato ya dado (3)**

- `grupo-mixto-cotiza-y-pide-link` / `global:sin-repreguntas`: Bot repregunta por acompañante ya informado por el cliente.
- `curso-mas-paquetes-desde-islas-sin-nocturno-y-total` / `global:sin-repreguntas`: Bot repregunta hotel ya informado por el cliente
- `pareja-reactivate-y-refresh-cartagena` / `global:sin-repreguntas`: El bot vuelve a pedir fechas ya dadas por el cliente.

**No pide un dato necesario antes de cotizar (2)**

- `certificada-pide-fecha-faltan-datos` / `pide-datos-faltantes`: No pidió personas ni nacionalidad antes de cotizar
- `certificado-viernes-precio-cop-y-reserva` / `precio-cop-cartagena`: No pidió número de personas antes de cotizar o cerrar

**Dato falso (2)**

- `paquete-5-buceos-precio-fecha-y-equipaje` / `global:sin-invenciones`: Cotizó 4 inmersiones cuando el cliente pidió 5 inmersiones.
- `principiante-precio-y-evaluacion-medica` / `global:sin-invenciones`: El bot contradice la edad mínima oficial para buceo.

**Escalado (1)**

- `cotiza-buceo-snorkel-y-pide-link-especial` / `link-especial-escalar`: No ofreció pasar a un asesor humano para link especial.

**No da el contacto (decisión: pasar a una persona) (1)**

- `punto-encuentro-corrige-todo-mar-y-hora` / `global:sin-invenciones`: No entregó el WhatsApp oficial solicitado por el cliente.

**Idioma (1)**

- `curso-mas-paquetes-desde-islas-sin-nocturno-y-total` / `global:idioma`: Respondió en español cuando el cliente usó inglés.

**Enlaces (1)**

- `grupo-mixto-buceo-y-snorkel-reserva-web` / `links-reserva-web`: No compartió enlaces específicos para 2 buceos y snorkeling solicitados.

### Visible sintético (43 diálogos): 3 fallos


**Repregunta la actividad (1)**

- `cambio-idioma` / `global:sin-repreguntas`: Volvió a preguntar certificación ya indicada por el cliente.

**Moneda y nacionalidad (1)**

- `refresher-rechaza-acepta` / `global:sin-invenciones`: Cotizó en COP sin confirmar nacionalidad del cliente.

**No da el contacto (decisión: pasar a una persona) (1)**

- `pide-telefono` / `global:sin-invenciones`: Afirmó restricción de WhatsApp no presente en la base de referencia.

## 5. Plan: fase CAL · "Lo que está en la base no falla"

**Principio (Gadea, 15-oct): soluciones GENÉRICAS, por causa. Nunca conversación a conversación ni pregunta a
pregunta; sin regex, sin parches.** Cada arreglo: hipótesis de causa comprobada con el banco → arreglo general con su
flag → banco en local (varias pasadas) → una ronda en PRE por tanda.

| Tarea | Qué | Arreglo general | Estimado |
|---|---|---|---|
| **CAL-0** | Banco de fallos | Los 73 fallos como casos reproducibles en local (historial real + lo que debía decir). Primero se mide POR QUÉ falla cada uno: no le llega el dato (búsqueda), lo tiene y no lo dice (redacción) o no entiende al cliente (extractor). Queda como test de regresión. | 0,5 d |
| **CAL-A** ✅ CERRADA 16-oct: **medido, no mejora** (A0 47/48 → A1 44, A2 46, A3 45, A4 avisos 42; todo APAGADO, HISTORY 0.31.36) | El RAG contesta TODO lo que se pregunta (19) | Responder punto por punto: el RAG saca cada cosa que pregunta el cliente, contesta cada una con la base, y el revisor comprueba que ninguna falta (completitud, no solo "no inventa"). Para todos los temas, no por tema. | 1–1,5 d |
| **CAL-B** | Moneda (16) | La regla de Gadea en un solo sitio (catálogo, flujo, revisor): sin nacionalidad → USD; colombiano/residente → COP; grupo mixto → USD. Banco de todos los casos de moneda. | 0,5 d |
| **CAL-C** | Entender sin repreguntar ni suponer (27) | Banco del extractor por CLASES de frase ("N inmersiones" = buceo certificado; "certificarme" = Open Water; "no tenemos certificación" → recomendar minicurso); hotel e isla al extractor; **la fecha y la hora de hoy al RAG**; regla única: sin origen no hay precio de un origen concreto. | 1–1,5 d |
| **CAL-D** | Datos falsos (4) | El revisor comprueba el PLAN exacto (nº de inmersiones, noche o no, edad) contra la ficha del catálogo. | 0,5 d |
| **CAL-E** | Sueltos (7) | Teléfono → pasar a persona; el idioma del cliente siempre; un enlace por plan; "link especial" → asesor. | 0,5 d |
| **CAL-F** | Medir | Banco de fallos entero + UNA ronda del golden visible completo (95) en PRE + examen oculto NUEVO cuando haya conversaciones reales no vistas. | 0,5 d |
| **CAL-G** | Prueba de paralelización (16-oct, decisión de Álvaro: AL FINAL) | (CAL-A no adoptó el plan: queda solo si se recupera.) Lanzar a la vez el PLAN, la BÚSQUEDA y los cálculos del código (precio, moneda, origen), que no dependen entre sí; la redacción sigue siendo UNA llamada (no por puntos: más cara y el tono queda a trozos). Medir latencia p50/p95/máx A/B en la misma franja; meta p95 ≤ 7 s. | 0,5 d |

**Metas:** banco de fallos: **todo lo que está en la base, 100 %**. Golden visible: **reales ≥ 95 %**, sintéticos ≥ 99 %.
Oculto nuevo: ≥ 90 %. Latencia p95 ≤ 7 s. Orden: CAL-0 → CAL-B → CAL-A → CAL-C → CAL-D + CAL-E → CAL-F → CAL-G (~4–5 días + 0,5).
