# TODO

## Infraestructura multi-entorno

### DEV (local — Windows)
- [x] Instalar y dejar disponible **Python 3.11+** en el PATH (que funcione `python --version`).
- [x] Instalar **Docker Desktop** y verificar que funciona (`docker compose version`).
- [x] Copiar `.env.dev.example` a `.env.dev` y configurar `OPENAI_API_KEY`.
- [x] Levantar infra local: `docker compose up -d` (PostgreSQL + Redis).
- [x] (Opcional) Levantar Chatwoot local: `docker compose --profile chatwoot up -d`.
- [x] Instalar dependencias del proyecto: `pip install -e ".[dev]"`.
- [x] Crear DB de Chatwoot si aplica: `docker exec dp-dev-postgres psql -U postgres -c "CREATE DATABASE chatwoot_dev;"`.
- [x] Ejecutar carga de embeddings: `python -m scripts.load_embeddings`.
- [x] Arrancar el bot: `python -m src.main` y verificar `http://localhost:8000/health`.
- [x] **CHATWOOT INTEGRATION FUNCIONAL**: Widget local funcionando y bot respondiendo mensajes.

### PRE (staging — VPS)
- [ ] Provisionar VPS (Hetzner/DigitalOcean/OVH, mínimo 4GB RAM).
- [ ] Configurar DNS: `pre.divingplanet.org` → IP del VPS.
- [ ] Copiar repo al VPS (`git clone`).
- [ ] Copiar `.env.pre.example` a `.env.pre` y configurar API keys + contraseñas fuertes.
- [ ] Levantar VPS: `docker compose -f docker-compose.vps.yml up -d --build` (Chatwoot usa su propio Postgres/Redis dedicados, `dp-chatwoot-postgres`/`dp-chatwoot-redis`, la DB `chatwoot_production` se crea sola al arrancar).
- [ ] Cargar embeddings en pre: `docker exec dp-pre-bot python -m scripts.load_embeddings`.
- [ ] Verificar: `curl https://pre.divingplanet.org/health`.

### PRO (producción — VPS, mismo servidor)
- [ ] Configurar DNS: `api.divingplanet.org` + `chatwoot.divingplanet.org` → IP del VPS.
- [ ] Copiar `.env.pro.example` a `.env.pro` y configurar API keys + contraseñas fuertes.
- [ ] Reiniciar con variables de producción: `docker compose -f docker-compose.vps.yml up -d --build`.
- [ ] Cargar embeddings en pro: `docker exec dp-pro-bot python -m scripts.load_embeddings`.
- [ ] Configurar Chatwoot: crear cuenta admin, inbox WhatsApp, generar API token.
- [ ] Configurar webhook en Chatwoot: `https://api.divingplanet.org/webhooks/chatwoot`.
- [ ] Conectar WhatsApp Business API en Chatwoot.
- [ ] Verificar: `curl https://api.divingplanet.org/health`.

## Funcionalidad implementada (Phase 1 completada)
- [x] **Decision Tree**: Árbol de decisiones completo con flujos guiados
- [x] **Botones interactivos**: Integración con Chatwoot para menús interactivos
- [x] **Supervisor Agent**: Routing inteligente entre decision tree y RAG
- [x] **RAG Agent**: Respuestas a preguntas libres usando base de conocimiento
- [x] **Chatwoot Integration**: Webhooks, envío de mensajes, y polling de interacciones
- [x] **Multi-idioma**: Soporte ES/EN en todo el flujo
- [x] **Base de conocimiento**: Embeddings cargados en pgvector
- [x] **Tests**: Tests unitarios para botones y decision tree

## Funcionalidad pendiente (Phase 2 - LangGraph multi-agent)
- [x] Validar que `data/knowledge_base/conversations.json` está siendo indexado correctamente en `kb_documents`.
- [x] Ajustar/añadir reglas de privacidad para que el bot no pida ni repita datos sensibles (IDs, cuentas, comprobantes) y siempre derive a humano.
- [ ] Implementar **Booking Agent** (integración Roverd deep links).
- [ ] Migrar estado de conversaciones de memoria (`dict`) a Redis/PostgreSQL como último paso técnico antes de pasar a PRE (no prioritario mientras sigamos cerrando y validando en dev).
- [x] Implementar **Escalation Agent** con handoff a humano en Chatwoot.

## Mejoras (baja prioridad)
- [x] Expandir `conversations.json` con más ejemplos reales (WhatsApp) y sanitización básica.
- [x] Importador WhatsApp con chunking temático (`*_partN`) + extracción heurística de topics.
- [x] Script de limpieza para mantener solo `whatsapp_import_*_partN`.
- [x] Retrieval híbrido topic-aware: boost por topics + pesos por `source` (policies/faqs/services/conversations).
- [x] Normalizar topics legacy en conversaciones curadas al indexar (mapping a topics canónicos) para mejorar overlap en reranking.
- [x] Logging de diagnóstico de retrieval (topics detectados + preview de scores).
- [ ] Añadir un comando/shortcut (script) para re-indexar embeddings de forma segura (por ejemplo confirmación antes del `DELETE`).
- [x] Revisar el `SYSTEM_PROMPT` del `rag_agent` para reflejar el tono definido en `brand_tone.json` y las reglas de escalado.
- [x] Añadir tests para supervisor, RAG agent, escalado y webhook.
- [ ] Dashboard del dueño (analytics de conversaciones, servicios consultados, conversiones).
- [ ] Alembic migrations para esquema de DB.

## División de trabajo activa

### Estado real del árbol y del producto (junio 2026)
- [x] Entrada principal `Reservar` alineada con el flujo real **cart-first** (`MIXED_ENTRY`).
- [x] Grupo mixto funcional en reserva: mezcla tours, cursos PADI y acompañantes dentro del mismo carrito.
- [x] Flujos guiados de buceo certificado multi-día disponibles en árbol y carrito (incluidas variantes de islas).
- [x] Cursos PADI separados en submenús de **Go Pro** y **Especialidades**.
- [x] `Información > Actividades` espeja la estructura comercial actual del árbol.
- [x] Selector de isla y hotel operativo en logística (`ISLAND_MENU` / `ISLAND_HOTEL_MENU`).
- [ ] Persistencia de estado conversacional fuera de memoria (`Redis`/`PostgreSQL`).
- [ ] Política de pago definitiva y cerrada en árbol/KB (anticipo, medios locales, combinaciones y excepciones).
- [ ] Repaso manual final de recorridos E2E y pulido de copys antes de demo/piloto.

### Álvaro (`feature/dev_alvaro`) — no pisar trabajo de Gadea
- [ ] **KB: Política de cancelaciones y cambios** — confirmar reglas con el dueño (gap crítico RAG)
- [ ] **KB: Medios de pago** — documentar opciones (QR, Nequi, Bancolombia, tarjeta, efectivo) para cobertura RAG independiente del árbol
- [ ] **KB: Editorial "¿qué plan me conviene?"** — comparativa de opciones para ayudar al indeciso
- [ ] **Infraestructura PRE** — VPS + Docker + Caddy + SSL (ver checklist PRE abajo)
- [ ] **Canal WhatsApp Business API** — conexión real vía Meta Cloud API o 360dialog
- [ ] **Chatwoot operacional** — notificaciones móviles del owner, etiquetas automáticas, horario de atención + mensaje fuera de horario
- [ ] **Monitorización básica** — logs estructurados de conversaciones, alerta de latencia, tracking de escalaciones

## Próximos pasos inmediatos (Álvaro)
1. **KB cancelaciones** — reunión con dueño para definir política; redactar `policies.json` + re-indexar
2. **KB pagos RAG** — documentar medios de pago disponibles en `faqs.json` / `policies.json`
3. **PRE deployment** — provisionar VPS y hacer el primer deploy funcional
4. **Chatwoot operacional** — configurar notificaciones móviles y etiquetas antes del primer piloto real
5. **WhatsApp Business API** — solicitar acceso Meta y conectar al Chatwoot de PRE

## Pendientes (RAG)
- [x] Confirmar con cliente la info de: “¿Cuál es la profundidad máxima?” / “What is the max depth?” (minicurso/bautizo 12 m, Open Water 18 m, Advanced/paquetes 30 m, Bubble Makers 2 m).
- [x] Añadir FAQ específico de profundidad máxima (ES/EN) — añadido en `faqs.json`. Pendiente reindexar embeddings para que el RAG lo sirva.
- [ ] Confirmar / cerrar precios oficiales y reglas de descuento que siguen parciales o pendientes de validación de negocio
- [ ] Memoria en el chat?
- [ ] Almuerzo = Comida
- [ ] Info sobre la comida
- [x] Inyectar contexto de ubicación y alojamiento (`state.location`, `state.island`, `state.hotel`) en las llamadas al RAG para que pueda mencionar recogidas/logística específicas.

## Pendientes — atajo de overview de buceo / acompañante (dejados por Gadea, v0.20.13, 2026-07-16)
Documentados en `docs/HISTORY.md` v0.20.13 tras el barrido proactivo; priorizados por ella, quedan aquí para que el siguiente los retome:
- [ ] **(barato)** Si el cliente dice explícitamente que el acompañante SÍ bucea/es certificado, el bot igual añade la línea "¿tu acompañante no bucea?" — contradicción directa.
- [ ] **(barato)** El atajo de overview de buceo no reconoce familiares ("hijo", "pareja") como acompañante, solo la palabra literal "acompañante"/"companion" — inconsistente con `_detect_companion_intent` (que sí los reconoce tras el fix de v0.20.13).
- [ ] **(caro, requiere parsing de roles)** El detector de acompañante no distingue quién bucea y quién acompaña — "mi pareja es buzo, yo solo acompaño" sigue diciendo "tu acompañante no bucea" cuando es al revés.
- [ ] **(caro, requiere parsing de roles)** "no bucea/n" no exige que haya una persona antes — falso positivo con frases tipo "el snorkel no bucea".
- [ ] **Decisión de equipo pendiente:** migrar `_canonical_price_overview_answer` de lista de exclusión (deny-list) a lista de permitidos (safe-list) — comparativa completa en `docs/archive/canonical-shortcuts-safelist-decision.md`.

## Pendientes reales (árbol de opciones / intents usuarios)
- [x] Reserva principal cart-first con carrito mixto (`MIXED_ENTRY`).
- [x] Caso **grupo mixto** para reserva (certificados + principiantes + snorkel + acompañantes) dentro del mismo carrito.
- [x] Menús específicos de **precios**, **reservas/pagos** y **logística/FAQ** (`PRICING_MENU`, `BOOKING_MENU`, `LOGISTICS_MENU`).
- [x] Flujos de tours certificados y principiantes reutilizando `location` y pasando por `COLOMBIAN` / resumen cuando aplica.
- [x] Flujos de **Cursos PADI y certificaciones** alineados con el árbol actual, incluyendo Open Water, Go Pro, especialidades y referral/reactivate.
- [x] Cobertura de **edades mínimas y requisitos para niños** en minicurso / snorkel.
- [x] Selector de **isla** y **hotel** para logística de clientes ya en islas.
- [ ] Cubrir mejor preguntas de **disponibilidad de última hora** y **corte de reserva online** (hasta qué hora se puede reservar por web y qué pasa después).
- [ ] Cerrar mejor las preguntas de **precios y descuentos**: USD vs COP, Cartagena vs islas y cómo se combinan los descuentos realmente vigentes.
- [ ] Modelar mejor las dudas sobre **alojamiento en islas**: hoteles recomendados, noches extra y retorno otro día.
- [ ] Cubrir preguntas sobre **recogida en hotel en las islas**: horarios, hoteles concretos y qué pasa si no hay acceso marítimo claro.
- [ ] Cubrir preguntas sobre **punto de encuentro en Cartagena / marinas**: Muelle de la Bodeguita vs Marina Todo Mar, puerta específica, link de ubicación y maletas.
- [ ] Detallar mejor **qué incluye cada plan**: equipo, tasas, seguro, almuerzo/comida, snacks/bebidas y si se puede llevar comida propia.
- [ ] Cubrir preguntas de **equipo**: si hace falta llevar equipo propio, si se puede ver/probar antes y dónde se entrega según origen.
- [ ] Cubrir preguntas de **qué llevar y bienestar**: toalla, bloqueador, mareo y restricciones prácticas.
- [ ] Cubrir preguntas sobre **fotos y videos**: si están incluidos, cómo se solicitan y qué pasa con fotos tomadas por el guía.
- [ ] Cubrir preguntas sobre **registro de buceos / logbook**: puntos de buceo y apoyo para registrar inmersiones.
- [ ] Cubrir mejor **condiciones y políticas**: clima, cancelación, reembolsos y cambios de fecha.

#### 🔴 Matriz hotel→recogida del owner (Dudas_V2.docx, 2026-07-02) — EN INVESTIGACIÓN

El owner entregó por fin la matriz definitiva de recogida por hotel (resuelve la pregunta #19 de `docs/archive/questions_for_owner_business_kb.md`). Clasifica ~40 hoteles en 5 categorías:

- **Base (recogida directo en el hotel):** Cocoliso Island Resort, San Pedro de Majagua.
- **Muelle propio (lancha llega directo):** Isla del Pirata, Isla única, Casa Rosario, Rosario de mar, Centro Ubuntu, Coralina Island, IslaBela, Isla del Sol, Isla Lizamar, Isla Tijereto, Fragata Island House, Rosario Ecohotel, Secreto, Luxury Beach Club, El Hamaquero Hostal EcoNativo, Coral Sand, Cocotera beach, Mangata, Mulata, Orika de mar, Bora Bora, Los erizos.
- **Deben caminar al centro de buceo:** Eco Hotel Las Palmeras, Eco Hotel Bosque Encantado, Isla Grande Eco hotel, Eco hostel coco encantado.
- **Deben caminar al muelle más cercano:** Golden Frog Hostel, Eco Hotel Mar Adentro, Ecohotel Las Flores Econativo, Eco Hotel Arte y Aventura, Coral Sand, Eco hotel casitas de mar adentro, Eco camping el frugal.
- **Islas privadas (directo allá):** Isla Rosa, Isla amor, Isla Pelícano, Isla Matamba.

Notas del owner: recogida solo desde islas del Rosario con acceso por mar (**Barú NO**); transfer incluido sin importar la distancia; *"todos los días abren un nuevo hotel o cambian el nombre… esto hay que estar actualizándolo"*.

Gap analysis vs. el bot actual (25 hoteles en `intent_detector.py`, 2 FAQs de recogida en `faqs.json`):
- **Bot reconoce pero el owner NO lista (posibles obsoletos, verificar):** Pao Pao, gente de mar, Playa Libre, Isleta Beach, Isla Arena, Isla Pavitos, Gigi, San Tropel. ⚠️ **Pao Pao** es nuestro caso "especial" en la KB y no aparece en la lista del owner.
- **Owner lista pero el bot NO detecta (~21 faltantes):** Isla única, Casa Rosario, Rosario de mar, Isla Tijereto, Coral Sand, Cocotera beach, Mangata, Mulata, Orika de mar, Los erizos, Las Palmeras, Bosque Encantado, Isla Grande Eco, Coco Encantado, Golden Frog, Mar Adentro, Arte y Aventura, Casitas de mar adentro, Camping el frugal, Isla Amor, Isla Matamba.
- **Sin estructura de categorías:** el bot solo mapea hotel→isla; la KB solo distingue confirmado/incierto para 3 hoteles.

- [ ] **DECISIÓN PENDIENTE (equipo investiga):** confirmar cuáles de los 8 "posibles obsoletos" siguen vivos antes de tocar nada.
- [ ] **Propuesta:** montar `data/knowledge_base/hoteles.json` (nombre → categoría de recogida) como fuente única, mantenible por Gadea/Andrés sin tocar código; que alimente la detección (`intent_detector.py`) y las respuestas del RAG. Reemplaza las 2 FAQs sueltas + la lista de regex desincronizada. Reindexar tras crearlo.
- [ ] Retirar/actualizar el manejo especial de Pao Pao una vez confirmado su estado.

#### Islas del Rosario con muelle y hotel (notas antiguas — superadas por la matriz del owner de arriba)

- Isla Grande: la más extensa. Hoteles: San Pedro de Majagua, Pao Pao, Cocoliso. Tiene múltiples muelles.
- Isla Marina: contigua a Isla Grande. Hoteles: Coralina Island, Islabela. Tiene muelle.
- Isla del Pirata: ocupada casi totalmente por el Hotel Isla del Pirata. Tiene muelle.
- Isla del Sol: isla-resort con el Hotel Isla del Sol. Tiene muelle.
- Isleta: zona tranquila con hoteles como Hotel Isla Bela. Tiene muelle.
- Isla Arena: sede del Hotel Isla Arena. Tiene muelle.
- Isla Pavitos: donde se ubica el Bora Bora Beach Club. Tiene muelle.
- Isla Lizamar: famosa por sus pasadías y el Hotel Lizamar. Tiene muelle.
- Isla Gigi: isla privada con alojamiento de lujo. Tiene muelle.
- Isla Rosa: isla exclusiva con club de playa. Tiene muelle.
- Isla Pelícano: isla privada de alquiler íntegro (vivienda de lujo). Tiene dos muelles.
- Isla Rosario: cuenta con alojamientos como Rosario de Mar. Tiene muelle.

*Notas de contexto*: algunas islas (Gigi, Rosa, Pelícano, Pavitos) funcionan como villas privadas o clubes exclusivos, y muchos alojamientos sin muelle propio usan muelles comunitarios (como Playa Libre) o de nativos en Isla Grande.

### Próximos pasos sugeridos (árbol ES)

- [ ] Probar manualmente los principales recorridos del árbol ES (tours certificados, principiantes, grupo mixto, precios, reservas, logística y cursos) para ajustar copys y orden de mensajes.
- [x] Ajustar textos finos (copys) de menús de precios y logística (submenús de punto de encuentro/horarios, alojamiento/recogida, qué incluye y qué llevar). Pendiente afinar cursos, selector de isla y submenús de hoteles según feedback real de usuarios.
- [ ] Evaluar si conviene añadir un submenú específico para edades de niños en logística o cursos una vez validadas las políticas de Diving Planet.

## A tener en cuenta (ajustes menores opcionales)

- [ ] Q19 “alojamiento incluido”: el top-1 FAQ tiene topics raros (`meeting_point`/`schedule`/`equipment`). Indica que ese FAQ es multi-tema.
      Si la respuesta final sale bien, no tocar. Si no, revisar ese FAQ para hacerlo más atómico.

Lo que no está pasando todavía es:

No se hace una lógica muy específica tipo:
“si selected_service == "snorkeling" y el usuario dice ¿cuánto vale? => responde exactamente SERVICES['snorkeling']['price']”.
Esa parte se la dejas al LLM/RAG, que con el contexto y la base de conocimiento debe deducir de qué está hablando. 

## Notas sobre Q&A y copys concretos

- [ ] Caso mixto "open water + certificado básico" (revisar mejor respuesta / posible escalado a humano).

  Pregunta ejemplo:

  > Somos dos personas. Una persona tiene el open water y el otro el certificado básico. Que me recomiendas?

  Respuesta actual:

  > Para esta situacion especifica, prefiero transferirte con mi jefe.
  > Enseguida se pone en contacto con usted, muchas gracias :)

- [x] Pregunta: "¿Se puede mezclar con principiantes?" (respuesta validada).
- [x] Rama `Tours desde Cartagena → Solo principiantes` revisada: menú diferencia minicurso/snorkel/privado, detalles de minicurso y snorkel ampliados, privado deriva a asesor, y tests añadidos.

  Respuesta propuesta:

  > Sí, se pueden mezclar grupos con diferentes niveles. Podemos combinar buzos certificados, principiantes que deseen hacer el minicurso y snorkelers en el mismo tour.
  >
  > Mientras los buzos hacen su primera inmersión, los principiantes recibirán entrenamiento teórico y práctico en la piscina. En la segunda inmersión, si lo desean, pueden unirse a los del minicurso para bucear en aguas abiertas.
  > Si necesitas más información o tienes alguna otra pregunta, ¡aquí estoy para ayudarte!

- [ ] Pregunta: "¿El almuerzo de qué consta y dónde se realiza?" (añadir más detalle de menú).

  Respuesta actual:

  > El almuerzo está incluido en la experiencia y se realiza en una de las islas donde buceamos. Sin embargo, no tengo detalles específicos sobre el menú.
  >
  > Si tienes alguna otra pregunta o necesitas más información, ¡aquí estoy para ayudarte!

## Notas rápidas

- [x] 1. 🤿 2 Buceos - 1 dia → flujo del árbol actual OK.
- [x] 2. Solo principiantes desde Cartagena → minicurso/snorkel/privado revisado y cubierto con tests.
- [x] 3. Paquetes certificados multi-día 5/7/9 → notas de noches/alojamiento/nocturna/personalización, refresher sin perder paquete original y tests añadidos.
- [ ] Repasar todo el árbol con todas las actividades y validar copys/resúmenes.

## Guía rápida: si `chatwood-test.html` no muestra el widget o no permite escribir

- [ ] **Verificar Chatwoot corriendo**:
      - `docker compose --profile chatwoot ps` debe mostrar `dp-dev-chatwoot` y `dp-dev-chatwoot-worker` Up.
      - Abrir `http://localhost:3300` y confirmar que carga la UI.
- [ ] **Habilitar registro y preparar BD (instalación nueva o equipo nuevo)**:
      - En `docker-compose.yml` confirmar `ENABLE_ACCOUNT_SIGNUP: "true"` en `chatwoot-rails` y `chatwoot-sidekiq`.
      - Comprobar dentro del contenedor: `docker exec dp-dev-chatwoot sh -lc 'echo ENABLE_ACCOUNT_SIGNUP=$ENABLE_ACCOUNT_SIGNUP FRONTEND_URL=$FRONTEND_URL'` → debe mostrar `ENABLE_ACCOUNT_SIGNUP=true`.
      - Preparar esquema (migraciones/semillas): `docker exec dp-dev-chatwoot bundle exec rails db:chatwoot_prepare`.
- [ ] **Si no aparece el registro o hay errores de tablas — Opción B (reset TOTAL, destruye datos locales de Chatwoot)**:
      - `docker compose stop chatwoot-rails chatwoot-sidekiq`
      - `docker exec dp-dev-postgres psql -U postgres -c "DROP DATABASE chatwoot_dev;"`
      - `docker exec dp-dev-postgres psql -U postgres -c "CREATE DATABASE chatwoot_dev;"`
      - `docker compose --profile chatwoot up -d --force-recreate`
      - `docker exec dp-dev-chatwoot bundle exec rails db:chatwoot_prepare`
      - Ir directo a registro: `http://localhost:3300/app/sign_up` (o `.../app/signup`).
- [ ] **Crear admin e Inbox Website**:
      - En `http://localhost:3300/app/sign_up` crea la cuenta admin (usa ventana de incógnito si fuera necesario).
      - Crea un Inbox “Website” y copia el `websiteToken` del snippet.
      - Para DEV actual: `websiteToken = 'je14uP7MjRFcSfcmNy45AWvp'` (si reinstalas o cambias de Inbox, actualízalo).
- [ ] **Actualizar `chatwood-test.html`**:
      - `BASE_URL = "http://localhost:3300"`.
      - `websiteToken = 'je14uP7MjRFcSfcmNy45AWvp'`.
      - Hard refresh `Ctrl+F5`. Verifica que `http://localhost:3300/packs/js/sdk.js` responde 200.
- [ ] **Configurar webhook (para que el bot responda y los botones funcionen)**:
      - URL: `http://host.docker.internal:8000/webhooks/chatwoot`.
      - Eventos suscritos: `message_created`, `message_updated`, `conversation_created`, `conversation_status_changed`.
- [ ] **Configurar variables del bot en `.env.dev`**:
      - Ejemplo:
        ```dotenv
        CHATWOOT_BASE_URL=http://localhost:3300
        CHATWOOT_API_TOKEN=<TU_TOKEN_DE_PERFIL_ACTUAL>
        CHATWOOT_ACCOUNT_ID=1
        # Opcional: asignar automáticamente conversaciones nuevas a un agente
        # CHATWOOT_OWNER_AGENT_ID=<ID_AGENTE>
        ```
- [ ] **Validar tu token de Chatwoot (PowerShell)**:
      - `iwr -Uri http://localhost:3300/api/v1/profile -Headers @{api_access_token="<TU_TOKEN_DE_PERFIL_ACTUAL>"}` → debe responder 200 y mostrar tus cuentas.
- [ ] **Reiniciar el bot con el entorno correcto**:
      - `ENV_FILE=.env.dev python -m src.main` (o en WSL2 `py -m src.main`).
- [ ] **Si los botones no reaccionan**:
      - Falta `message_updated` en el webhook o Chatwoot no está enviando `message_updated`.
- [ ] **Comprobaciones rápidas**:
      - Bot salud: `http://localhost:8000/health` → 200.
      - El widget debe abrirse automáticamente; si no, ya hay un `setTimeout` de apertura forzada.

---

## Roadmap hasta producto terminado

### Núcleo funcional
| Estado | Elemento |
|--------|----------|
| ✅ | Arquitectura supervisor + árbol + RAG |
| ✅ | Integración Chatwoot (buttons, polling, escalación, handoff) |
| ✅ | Árbol de decisión: tours certificados, principiantes, cursos, precios, logística |
| ✅ | Base de conocimiento + embeddings pgvector (441 docs) |
| ✅ | Privacidad / PII + bloqueo de datos sensibles |
| ✅ | Auto-asignación conversaciones al owner en Chatwoot |
| ✅ | Flujos guiados de buceo multi-día en árbol y carrito |
| ⬜ | Persistencia de memoria (Redis/PostgreSQL) |
| ⬜ | Flujo de pago definitivo en árbol / KB |
| 🔄 | Pulido final minicurso / snorkel / principiantes con pruebas E2E |
| ⬜ Álvaro | Política de cancelaciones y cambios (KB + RAG) |
| ⬜ Álvaro | Medios de pago completos (KB + RAG) |
| ⬜ Álvaro | Editorial "¿qué plan me conviene?" (comparativa RAG) |
| ⬜ | Cobertura KB: registro de buceos / logbook / puntos de buceo |
| ⬜ | Cobertura KB: disponibilidad de última hora / corte de reserva online |

### Canal e infraestructura
| Estado | Elemento |
|--------|----------|
| ⬜ | **WhatsApp Business API** (canal real — Meta Cloud API o 360dialog) |
| ⬜ | **Despliegue PRE** (VPS + Docker + Caddy + SSL) |
| ⬜ | **Despliegue PRO** (hardening, backup, monitorización) |
| ⬜ | Estado de conversación en PostgreSQL + Redis (prep para PRE) |
| ⬜ | CI/CD básico (GitHub Actions → VPS) |
| ⬜ | Chatwoot en producción: inbox WhatsApp real, etiquetas, horarios |

### Calidad y refinamiento final
| Estado | Elemento |
|--------|----------|
| ⬜ | Tuning RAG con conversaciones reales del canal WhatsApp |
| ⬜ | Ajuste de tono/voz con feedback del dueño tras piloto |
| ⬜ | Monitorización: logs estructurados, alerta de latencia, tracking escalaciones |
| ⬜ | Optimización de coste por conversación (tokens, modelo) |
| ⬜ | Tests de carga básicos antes de PRO |
| ⬜ | Revisión legal/GDPR (tratamiento datos de clientes) |
| ⬜ | Notificaciones móviles Chatwoot configuradas para el owner |

### Funcionalidades adicionales atractivas *(post-MVP)*
| Elemento | Valor estimado |
|----------|---------------|
| Integración con sistema de reservas (Roverd / Checkfront / custom) | Alto — cierra el ciclo sin humano |
| Mensajes proactivos: recordatorio 24h antes, confirmación de salida | Alto — reduce no-shows |
| Seguimiento post-buceo: fotos, certificado PADI, reseña Google | Alto — fidelización |
| Dashboard de analítica (intents, escalaciones, conversiones) | Medio |
| Campañas por temporada (Semana Santa, diciembre, Carnaval) | Medio |
| Soporte multiidioma adicional (FR, PT para cruceristas) | Medio |
| Mensajes de media enriquecida (fotos del arrecife, vídeo del centro) | Medio |
| Integración con CRM para historial del cliente recurrente | Bajo / largo plazo |
