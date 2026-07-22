# Batería para la Fase 6 (bucle de datos reales) — lanzar por el widget de PRE

> Creado 2026-07-21. Objetivo: generar tráfico REAL (por el widget de Chatwoot en PRE, no por
> scripts) para poder correr `scripts/harvest_cutover_logs.py` contra `docker logs dp-pre-bot`
> y empezar a hacer crecer `docs/robustness/eval-set.json` con casos reales, no solo sintéticos.
> Ver `docs/robustness/plan.md` (Fase 6) y `docs/robustness/review-2026-07-21.md` (hallazgo H1).

## Cómo usar este documento

- **Lanzar cada mensaje por el widget de Chatwoot en PRE** (no por SSH/scripts — esos no dejan
  rastro en `docker logs dp-pre-bot`, que es lo que necesita el harvest de la Fase 6).
- **Espaciar los mensajes** (no en bucle rápido) — probar el widget muy seguido dispara el
  rate-limit de Rack::Attack y bloquea la IP compartida ~20 minutos (lección ya documentada en
  `docs/project-history/session-handoff.md`).
- Cada caso tiene un checkbox. Márcalo cuando lo hayas probado — no hace falta que la respuesta
  sea perfecta, el objetivo aquí es generar tráfico variado, no validar el bot (para eso ya está
  `docs/test-battery-edge-cases.md`). Si ves algo claramente mal, anótalo debajo del caso.
- **Una conversación NUEVA por cada caso de las categorías A, B, C, D y F** — cada uno prueba
  detección "de entrada" (primer mensaje o vuelta al menú); si se mandan varios seguidos en el
  mismo hilo, el estado de uno (grupo, ubicación...) contamina al siguiente.
- **Categoría E es la excepción**: cada caso necesita 2 turnos en LA MISMA conversación — primero
  una reserva normal, luego (ya a mitad de flujo) el mensaje de acompañante. No empezar en frío
  para el segundo mensaje.
- **Categoría G también es una sola conversación por caso**, de principio a fin (son reservas
  completas, no mensajes sueltos).
- Cuando haya un lote decente probado, alguien con acceso al VPS corre:
  ```
  ssh -i ~/.ssh/dp_pre_vps root@89.167.4.161 "docker logs dp-pre-bot 2>&1" | python -m scripts.harvest_cutover_logs --summary
  ```
  para ver el contador por dominio, y sin `--summary` para sacar los candidatos a revisar.

---

## Categoría A — Certificación (Fase 1)

Buscamos frases donde el regex se quede corto y el LLM tenga que rellenar `is_certified`/`activity`.

- [ ] **A1** (ES): "hola quiero probar el buceo, nunca lo he hecho, voy solo"
- [ ] **A2** (EN): "hey never been underwater before, kinda nervous, wanna give it a try"
- [ ] **A3** (ES, typo): "ola quiero vucear, ya soy sertificado, somos 2" (Los dos certificados ?)
- [ ] **A4** (EN, typo): "hi i wanna dive, im not certfied tho, just me"
- [ ] **A5** (ES, indirecto): "tengo el rescue diver, quiero seguir buceando por ahí"
- [ ] **A6** (EN, indirecto): "i already have my open water card, want to do more dives"
- [ ] **A7** (ES, negación compuesta): "no es que no estemos certificados, sí lo estamos, somos 3"
- [ ] **A8** (EN, contracción): "we arent certified yet, first time diving, just the two of us"

## Categoría B — Grupo/cantidad/edades (Fase 2)

Buscamos conteos de grupo poco habituales, edades de niños, y splits certificado/no-certificado.

- [ ] **B1** (ES): "somos mi pareja y yo, para bucear"
- [ ] **B2** (EN): "just the two of us wanna dive"
- [ ] **B3** (EN, enumeración con "plus"): "me plus 3 friends want to snorkel" *(caso conocido: el
  regex puede dar 3 en vez de 4 — anotar exactamente qué responde)*
- [ ] **B4** (ES, edad de un tercero): "mi hijo de 8 años quiere hacer snorkel con nosotros"
- [ ] **B5** (EN, edad de un tercero): "my daughter is 9 and wants to try the mini-course"
- [ ] **B6** (ES, grupo mixto explícito): "somos 6, 4 certificados y 2 quieren snorkel"
- [ ] **B7** (EN, grupo mixto explícito): "we're a group of six, four certified divers and two snorkelers"
- [ ] **B8** (ES, número en palabras): "somos nueve, queremos bucear todos"

## Categoría C — Ubicación (Fase 3)

Buscamos referencias a barrios/zonas concretas de Cartagena o de las islas, en vez del genérico "Cartagena"/"islas".

- [ ] **C1** (ES): "salimos desde bocagrande"
- [ ] **C2** (EN): "we're staying in the old town this week"
- [ ] **C3** (ES, isla + hotel): "estamos hospedados en el hotel Las Islas en Barú"
- [ ] **C4** (EN, barrio menos común): "we're staying near Getsemaní"
- [ ] **C5** (ES, ambigua): "estamos en manga, salimos desde ahí"

## Categoría D — Nacionalidad/logística (Fase 8)

Buscamos nacionalidad, duración de estancia, y última inmersión con frases naturales.

- [ ] **D1** (ES, nacionalidad indirecta): "somos paisas, queremos bucear 2 días"
- [ ] **D2** (EN, nacionalidad indirecta): "we're foreigners visiting for a week"
- [ ] **D3** (ES, duración indirecta): "estaremos toda la semana en cartagena"
- [ ] **D4** (EN, última inmersión indirecta): "i'm certified but haven't dived in like 4 years"
- [ ] **D5** (ES, última inmersión indirecta): "hace como 3 años que no buceo, seré yo solo"

## Categoría E — Acompañante a mitad de flujo (fix de hoy, ES + EN)

Ya arreglado hoy (soporte de inglés + detección de "misma actividad") — confirmar que se sostiene con tráfico real, en ambos idiomas.

- [ ] **E1** (ES): reservar 1 buceo certificado normal, y a mitad de flujo escribir "mi pareja hace lo mismo"
- [ ] **E2** (EN): reservar 1 buceo certificado normal, y a mitad de flujo escribir "my partner will do the same"
- [ ] **E3** (EN, variante de frase): "my friend is also coming, same activity as me"

## Categoría F — Grupo mixto / actividad específica mal clasificada (fix del refactor de hoy)

Mensajes ricos en info que el orquestador podría clasificar mal como pregunta — confirmar que igual entran al flujo guiado.

- [ ] **F1** (ES): "somos 5 amigos, 3 certificados y 2 sin certificar, queremos un paquete de varios días"
- [ ] **F2** (ES): "quiero hacer snorkel, somos 2"
- [ ] **F3** (EN): "we want to do the open water course, there are 3 of us"
- [ ] **F4** (ES): "quiero hacer el curso advanced"

## Categoría G — Reservas normales (tráfico base, sin buscar fallos)

Para que el eval-set y el harvest también tengan ejemplos "fáciles", no solo casos límite.

- [ ] **G1** (ES): reserva completa normal de principio a fin (buceo certificado, 2 personas, hasta confirmar)
- [ ] **G2** (EN): reserva completa normal de principio a fin (minicurso, 1 persona, hasta confirmar)
- [ ] **G3** (ES): pregunta de precio simple + reserva de snorkel
- [ ] **G4** (EN): pregunta sobre qué incluye el paquete + reserva de curso PADI

---

## Registro de hallazgos

Anotar aquí cualquier cosa rara encontrada al lanzar estos casos (bug nuevo, respuesta rara,
o simplemente "todo bien") — antes de decidir si se añade al eval-set (ver la lección de proceso
en `docs/robustness/progress-log.md`: validar SIEMPRE el "expected" contra el pipeline real antes
de fijarlo, no a ojo).

### 2026-07-22 — Corrida LOCAL de A-D+F (Gonzalo; 30 casos, pipeline real + LLM real)

Sin acceso SSH al VPS desde esta sesión, se corrió la batería **localmente** contra el
pipeline real (núcleo ON, mismo código que PRE tras `2c8e195`), capturando los logs igual
que `docker logs` y pasándolos por el harvester — el objetivo de datos se cumple (mismos
mensajes → misma extracción); lo que NO cubre es el canal Chatwoot en sí (rate-limits,
webhooks), que sigue pendiente de la corrida por widget. Resultado: 30/30 sin excepciones,
**18 records de gap-fill, 18 candidatos**, `--summary` por dominio
(group 7 / certification 6 / location 6 / logistics 3). Curación: **10 añadidos** al
eval-set (`hv-*`), 4 duplicados/casi-duplicados descartados, resto sin señal nueva.
E y G no se corrieron (multi-turno "fácil" que el regex resuelve — no generan gap-fills).

Hallazgos de bugs REALES de regex (no del LLM; candidatos a la Fase 7 de override/fix):

- 🐛 **"hace como 3 años que no buceo" → `ages=[3]`** (ídem "haven't dived in like 4
  years" → `ages=[4]`): el regex de edades captura los años de "hace X años" como si
  fueran la edad de una persona. Latente: con un minicurso en el carrito, ese fantasma
  contaminaría `kids_under_8_count` en el split del checkout. (D4/D5)
- 🐛 **"i already have my open water card, want to do more dives" → `activity=padi_open_water`**:
  el regex clasifica como CURSO a quien dice que YA lo tiene y quiere bucear (debería
  ser `certified_diving`). Como `me plus 3 friends`: el regex resuelve MAL (no deja
  hueco), así que el gap-filler no puede corregirlo por diseño. (A6)
- 🔁 **B3 confirmado otra vez**: "me plus 3 friends want to snorkel" → regex `group_size=3`
  (debería 4), ahora también en la variante snorkel.
- ℹ️ Variabilidad del mini observada en C3: en esta corrida rellenó `hotel`/`island` pero
  no `location` (el eval-set la ha dado bien otras veces). El flujo se recupera (pregunta
  la ubicación), coherente con el modo de fallo "abstención segura".
