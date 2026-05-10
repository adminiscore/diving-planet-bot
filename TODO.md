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
- [ ] Levantar VPS: `docker compose -f docker-compose.vps.yml up -d --build`.
- [ ] Crear DB de Chatwoot: `docker exec dp-pro-postgres psql -U postgres -c "CREATE DATABASE chatwoot_production;"`.
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
- [ ] Ajustar/añadir reglas de privacidad para que el bot no pida ni repita datos sensibles (IDs, cuentas, comprobantes) y siempre derive a humano.
- [ ] Implementar **Booking Agent** (integración Roverd deep links).
- [ ] Migrar estado de conversaciones de memoria (`dict`) a Redis/PostgreSQL.
- [ ] Implementar **Escalation Agent** con handoff a humano en Chatwoot.

## Mejoras (baja prioridad)
- [x] Expandir `conversations.json` con más ejemplos reales (WhatsApp) y sanitización básica.
- [x] Importador WhatsApp con chunking temático (`*_partN`) + extracción heurística de topics.
- [x] Script de limpieza para mantener solo `whatsapp_import_*_partN`.
- [x] Retrieval híbrido topic-aware: boost por topics + pesos por `source` (policies/faqs/services/conversations).
- [x] Normalizar topics legacy en conversaciones curadas al indexar (mapping a topics canónicos) para mejorar overlap en reranking.
- [x] Logging de diagnóstico de retrieval (topics detectados + preview de scores).
- [ ] Añadir un comando/shortcut (script) para re-indexar embeddings de forma segura (por ejemplo confirmación antes del `DELETE`).
- [ ] Revisar el `SYSTEM_PROMPT` del `rag_agent` para reflejar el tono definido en `brand_tone.json` y las reglas de escalado.
- [ ] Añadir tests para supervisor, RAG agent, escalado y webhook.
- [ ] Dashboard del dueño (analytics de conversaciones, servicios consultados, conversiones).
- [ ] Alembic migrations para esquema de DB.

## Próximos pasos inmediatos
1. **Testing end-to-end**: Verificar flujo completo desde widget hasta reserva
2. **Optimización RAG**: Mejorar respuestas con más contexto de negocios
3. **Privacy rules**: Implementar filtros para datos sensibles
4. **Booking integration**: Conectar con Roverd API para reservas automáticas
5. **Deploy VPS**: Configurar entorno de pre-producción

## Pendientes (RAG)
- [ ] Confirmar con cliente la info de: “¿Cuál es la profundidad máxima?” / “What is the max depth?”
- [ ] Añadir FAQ específico de profundidad máxima (ES/EN) una vez confirmado.
- [ ] Definir los precios de servicios
- [ ] Memoria en el chat?
- [ ] Almuerzo = Comida
- [ ] Info sobre la comida
- [x] Inyectar contexto de ubicación y alojamiento (`state.location`, `state.island`, `state.hotel`) en las llamadas al RAG para que pueda mencionar recogidas/logística específicas.

## Pendientes (árbol de opciones / intents usuarios)
- [ ] Modelar caso **grupo mixto** (buzos certificados + principiantes + snorkelers / acompañantes) viajando juntos en el mismo tour, con precios diferenciados y logística de actividades/lancha.
- [ ] Cubrir preguntas de **disponibilidad de última hora** y **corte de reserva online** (hasta qué hora se puede reservar por web y qué pasa después).
- [ ] Cubrir preguntas de **precios**: valores en USD vs COP, diferencia de tarifas saliendo desde Cartagena vs ya en las islas, y paquetes de varios días (5, 7, 9 buceos) con o sin nocturna.
- [ ] Cubrir preguntas de **descuentos** para colombianos y residentes (precio local) y cómo se combina con el 10% online (si ya está aplicado o no, necesidad o no de código).
- [ ] Modelar mejor las dudas sobre **alojamiento en islas**: hoteles recomendados (Cocoliso, San Pedro de Majagua, etc.), que el alojamiento no está incluido, noches extra y posibilidad de regresar con Diving Planet otro día.
- [ ] Cubrir preguntas sobre **recogida en hotel en las islas**: horarios de pick-up y regreso, qué pasa si el hotel no tiene acceso en lancha, hoteles específicos (Isla Grande, Ubuntu, etc.).
- [ ] Cubrir preguntas sobre **punto de encuentro en Cartagena / marinas**: Muelle de la Bodeguita vs Marina Todo Mar, puerta específica, link de ubicación y opción de guardar maletas en la oficina de Cartagena.
- [ ] Detallar mejor **qué incluye cada plan**: equipo completo, tasas de parque, seguro de buceo, almuerzo/comida, si hay opciones sin almuerzo, snacks/bebidas y si se puede llevar comida propia.
- [ ] Cubrir preguntas de **equipo**: si es necesario llevar equipo propio, si se puede ver/probar el equipo antes de salir, y dónde está el equipo (Cartagena vs islas).
- [ ] Cubrir preguntas de **condiciones y políticas**: clima, cancelación y reembolsos, cambio de fecha, qué pasa si el cliente no puede viajar.
- [ ] Cubrir preguntas de **qué llevar y bienestar**: toalla, bloqueador, mareo (si ofrecen pastillas o solo recomendación), qué no está permitido llevar.
- [ ] Cubrir preguntas de **profundidad máxima, número de inmersiones y sitios**: metros máximos, diferencia entre principiantes/certificados, barcos hundidos u otros puntos “especiales” de la zona.
- [ ] Cubrir preguntas sobre **tamaño de grupos y acompañantes**: mínimo/máximo de personas por instructor, acompañantes que solo van en la lancha o hacen snorkel, posibilidad de acompañar a alguien que hace minicurso.
- [ ] Cubrir preguntas sobre el **proceso de reserva y pago**: porcentaje de anticipo (50% vs 100%), links de pago específicos por grupo/actividad, uso de pasaporte vs cédula para extranjeros, pago en pasarela local vs tarjeta extranjera vs transferencia.
- [ ] Cubrir preguntas sobre **formularios y requisitos médicos**: cuestionarios PADI, exoneraciones, Discover Scuba / DSD eLearning, cuándo se requiere certificado médico si responden “sí” en el cuestionario.
- [ ] Cubrir preguntas sobre **certificaciones y cursos**: diferencia entre minicurso y curso Open Water, upgrade de Discover/mini a Open Water, referrals desde otros centros/instructores (qué papeles deben traer).
- [ ] Cubrir preguntas sobre **fotos y videos**: si están incluidos en el plan, cómo se solicitan luego, qué pasa con fotos que tomó el guía.
- [ ] Cubrir preguntas sobre **registro de buceos / logbook**: nombres de puntos de buceo (Alex Place, Luis Guerra, etc.) y apoyo para registrar inmersiones en apps PADI/SSI.
- [ ] Cubrir preguntas sobre **frecuencia de tours**: si hay salidas todos los días, horarios típicos por tipo de plan.
- [ ] Cubrir preguntas sobre **edades mínimas y requisitos para niños** tanto en buceo como en snorkel.

- [x] Añadir paso `GROUP_TYPE` para tipo de grupo y manejar el caso de grupo mixto (buceo + snorkel / acompañantes) con explicación y escalado a humano.
- [x] Crear menús específicos de **precios**, **reservas/pagos** y **logística/FAQ** (`PRICING_MENU`, `BOOKING_MENU`, `LOGISTICS_MENU`) con mensajes ES/EN y retorno al menú principal.
- [x] Ajustar flujos de tours certificados y principiantes para reutilizar la `location` seleccionada desde el menú principal y saltar directamente a `COLOMBIAN` cuando aplica.
- [x] Actualizar el `Supervisor` para reconocer los nuevos pasos de menú y seguir ruteando correctamente al árbol de decisión.


- [x] Rediseñar el flujo de **Cursos PADI y certificaciones** para alinearlo mejor con el árbol extendido (curso básico Open Water con origen Cartagena/islas, tiempo disponible, resumen claro del curso).
- [x] Añadir granularidad en cursos: path específico para **referrals/reactivates** (cursos empezados en otro centro), explicando documentos requeridos y cómo se cobra la diferencia vs paquete de buceos.
- [x] Incorporar de forma explícita en el árbol la **edad mínima y recomendaciones para niños** en minicurso y snorkel mediante notas adicionales en los detalles de servicio.
- [x] Extender la estructura de `SERVICES` para reflejar mejor atributos de cursos y experiencias de principiantes/snorkel (edad mínima recomendada, días mínimos de práctica, notas adicionales), manteniendo compatibilidad con el resumen actual.
- [x] Modelar un selector de **isla de alojamiento** para clientes que ya están en las islas y usarlo en los flujos de logística y recogida en hotel (Step `ISLAND_MENU` con almacenamiento en `state.island`).
- [x] Cargar/configurar el listado de **hoteles por isla** (usando el detalle de alojamientos que tenemos para las 12 islas principales) y modelar submenús de hotel tras seleccionar isla (Step `ISLAND_HOTEL_MENU` con `state.hotel`).

#### Islas del Rosario con muelle y hotel (para futuros selectores)

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
- [ ] Ajustar textos finos (copys) de menús de precios, reservas, logística, cursos, selector de isla y submenús de hoteles según feedback real de usuarios.
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
- [ ] Repasar todo el árbol con todas las actividades y validar copys/resúmenes.
