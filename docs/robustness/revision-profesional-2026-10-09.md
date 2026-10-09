# Repaso: ¿qué nos separa de un chatbot profesional? (9-oct-2026, Gadea con Claude)

Sin contar el regex (fase EX, `docs/robustness/regex/plan-ex-entender-con-ia.md`). Todo comprobado en el repo y en el
servidor de PRE el 9-oct.

## Lo que ya está a nivel profesional

- **Medición de calidad:** golden-set de 116 diálogos (73 reales), juez automático calibrado, examen oculto, mini-rondas
  A/B con flag por cambio. Pocos equipos pequeños tienen esto.
- **Tests:** ~2990 en local; lint; migraciones.
- **Seguridad del texto:** revisor de grounding, guardas de importes/links/teléfonos, privacidad (datos personales
  tapados), timeouts del LLM (30 s) y conexiones reutilizadas.
- **Canal:** WhatsApp por Chatwoot, notas de voz transcritas, paso a humano con resumen del cliente.
- **Latencia:** turno p50 ~3 s, p95 ~5-6 s; respaldo de modelo para la cola.

## Diferencias, por área

### A. Producto (lo que nota el cliente)

| # | Hoy | Profesional | Prioridad |
|---|---|---|---|
| A1 | No ve cupos ni reserva: manda un link ("no puedo confirmar cupos") | Consulta disponibilidad y deja la reserva/pago preparados (plan, fecha, personas) por API | Alta (depende de Roverd o del plan `docs/future/roverd-replacement-plan.md`) |
| A2 | Nada proactivo: si el cliente no termina, se pierde | Seguimiento a quien no reserva, recordatorio antes de la salida (formularios, punto de encuentro), pedir reseña después (plantillas de WhatsApp) | Alta (conversión) |
| A3 | Solo español e inglés (idioma detectado con lista de palabras) | Contesta en el idioma del cliente (portugués, francés…: turistas de Cartagena) | Media (decisión de negocio) |
| A4 | El paso a humano asigna siempre a una persona; sin horario de atención ni mensaje fuera de horario | Horario, mensaje de espera con tiempo estimado, reparto entre el equipo | Media |
| A5 | Imágenes (foto del carné, captura de pago) no se leen | El modelo las lee (los de ahora son multimodales) | Baja-media |

### B. Fiabilidad e infraestructura

| # | Hoy | Profesional | Prioridad |
|---|---|---|---|
| B1 | **Un solo servidor pequeño** (2 CPU, 3,7 GB; 2,3 GB usados, carga 1,5/2) con PRE + Chatwoot, y PRO previsto en el mismo compose | PRO en su propio servidor (o uno mayor), PRE aparte | **Alta antes de PRO** |
| B2 | **Sin copias de seguridad** de las bases de datos en el servidor (Chatwoot = historial con clientes) | Copia diaria automática fuera del servidor y prueba de restauración (confirmar si Hetzner hace snapshots) | **Alta** |
| B3 | Métricas solo en los logs del contenedor (se pierden en cada deploy); Langfuse agotado; **sin alertas** | Trazas y métricas persistentes; alertas de caída, errores, latencia y **saldo de OpenAI** (si se acaba, el bot no contesta) | **Alta** |
| B4 | Un solo proveedor para casi todo (OpenAI); R6 pendiente | Proveedor de reserva para el camino crítico y mensaje amable + humano si todo cae | Media-alta |
| B5 | Estado de la conversación en Redis con TTL y política `allkeys-lru` (hoy 20 MB de 256) | `volatile-lru`/`noeviction` + persistencia, o el estado en Postgres | Media |
| B6 | Mensajes de clientes a Jev por OpenRouter (privacidad para PRO pendiente); sin aviso de tratamiento de datos | Aviso de privacidad (Ley 1581, Colombia), retención definida, proveedores con acuerdo de datos | **Alta antes de PRO** (legal) |

### C. Código y proceso

| # | Hoy | Profesional | Prioridad |
|---|---|---|---|
| C1 | **La CI corre 21 de 139 ficheros de tests**; la suite completa solo en local | Suite completa en cada push (en paralelo, ~3-4 min) | **Alta y barata** |
| C2 | 58 interruptores; `conversational_core` 5.500 líneas, `supervisor` 3.400; capas superpuestas | Flags retirados al promocionar; módulos por nodo; un solo camino | Media (S4: s4-1, s4-2, s4-25; EX ex-9) |
| C3 | La calidad se mide a mano (rondas) | Puertas automáticas (golden core antes de promocionar), muestreo diario de conversaciones reales con el juez, modo entrenamiento | Media-alta (Q5, g-4, g-4b) |
| C4 | El mismo dato del negocio en varios ficheros (la propina estaba en 3) | Una sola fuente del negocio y el resto generado | Media |
| C5 | Textos fijos del flujo de reserva (17 fallos; "¿Sois buzos certificados?" en bucle) | Flujo conversacional: el modelo redacta, el código decide qué falta | Media-alta (después de EX) |

### D. Modelos

Los modelos **no son hoy el cuello de botella**; lo son la arquitectura, los datos y el proceso.

| Pieza | Hoy | Comentario |
|---|---|---|
| Respuesta (RAG) | GPT-6 Luna + respaldo gpt-4.1-mini | Al día |
| Revisor | gpt-4.1 | La pieza más cara (~3,5 $/1.000 turnos) y +2-3 s cuando rechaza; se queda (s4-33) hasta otro modelo |
| Extracción | gpt-4o-mini | Generación anterior: en EX probar Luna/gpt-4.1-mini con la llamada única (s4-32) |
| Enrutador | Jev (OpenRouter) | Rápido; falta la privacidad para PRO |
| Embeddings | text-embedding-3-small | Suficiente para una base pequeña |

## Orden propuesto

1. **Bloqueantes antes de PRO:** B2 copias, B3 observabilidad y alertas (incluido el saldo de OpenAI), B1 servidor de
   PRO, B6 privacidad/legal, C1 CI completa, B4 respaldo de proveedor (R6).
2. **En curso:** fase EX (entender con IA) y, detrás, C5 (flujo conversacional) y C2 (limpieza S4).
3. **Producto, para vender más:** A2 proactivo, A1 disponibilidad/reserva, A3 idiomas, A4 horario del paso a humano.
4. **Continuo:** C3 calidad automática y C4 fuente única del negocio.
