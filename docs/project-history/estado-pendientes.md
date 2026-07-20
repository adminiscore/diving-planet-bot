# Estado del bot: bugs arreglados y pendientes

> Documento vivo de estado. Última actualización: 2026-07-21 (v0.20.28).
> Consolidado a petición del owner. Para el detalle técnico de cada punto, ver
> `docs/HISTORY.md` (versión indicada) y `docs/project-history/session-handoff.md`.

## ✅ Bugs reportados y arreglados (esta racha, desplegados en PRE)

| Versión | Qué se arregló |
|---|---|
| v0.20.8 | Agujero de alucinación cerrado (respuesta desde conocimiento del mundo sin KB) + umbral RAG calibrado a 0.40 (medido, no a ojo) |
| v0.20.9 | El bot recogía datos personales en el chat para "tramitar la reserva" (PII) |
| v0.20.14 | "cojo/coja" no reconocido como movilidad reducida en DIVE TO HEAL |
| v0.20.15 | Acompañante sin actividad → recomienda minicurso; recap de contexto al "Volver" |
| v0.20.16 | Sub-flujo DIVE TO HEAL coherente (contexto persistente entre turnos) |
| v0.20.17-24 (Gadea) | **Memoria B/C/A**: resumen progresivo + notas abiertas + ventana configurable (24) |
| v0.20.18-25 (Gadea) | Bloqueo de botones en pasos sí/no; precisión de precio de buceo; falso positivo "planes"; fallback de certificación desconocida; **chunk de descuentos indexado en blanco desde hace años**; cálculo de precios derivados; preguntas bloqueadas en MIXED_LOCATION/ADD_QTY |
| v0.20.26 | **No ofrecer asesor por defecto** (solo sensible/necesario/pedido) + **nunca dar el WhatsApp** (guard determinista); botones asesor/menú fuera de respuestas normales; "Volver" en el resumen final ya no abandona el carrito; **reset de memoria por escenario nuevo** (saludo + auto-presentación con memoria previa) |
| v0.20.27 | **Certificado por texto libre → recomendar 2 inmersiones directo** (sin menú), acotado a la entrada libre y gateado por acompañante principiante (split y botón in-cart conservan menú); **snorkel a mitad de flujo ya no se ignora** (aterriza en ADD_QTY donde el split cert/actividad lo reconoce); **"Volver" fuera de todo el carrito** (`_CART_MENU_KEYS`) — cambios por lenguaje natural |
| v0.20.28 | **Inferir "1 persona" de auto-presentación singular** ("soy certificada" → group_size=1, se salta la pregunta de cantidad); conservador ante acompañante/número/plural/colectivo |

## 🟡 Pendientes abiertos (no bloqueantes)

1. **Coste/latencia de la ventana de memoria de 24** — la ventana 12→24 ~duplica los tokens de historial por llamada LLM (hay 3-4 por turno) + una llamada extra de resumen cada 24 mensajes. **Medir en vivo en PRE con conversaciones largas antes de PRO.** Palanca: `HISTORY_WINDOW_SIZE`.
2. **La generación del resumen se `await`ea antes de responder** (1 de cada 24 turnos añade ~1-2s). Evaluar fire-and-forget si la latencia molesta.
3. **Orquestador LLM no determinista** — un mensaje de reserva claro puede clasificarse distinto entre ejecuciones. Revisar si hay más combinaciones de `_should_*` sin su red de seguridad determinista (señalado por Gadea en v0.20.21).
4. **Validación de esquema en `load_embeddings.py`** — el bug del descuento en blanco (v0.20.22) pide un test general que detecte cualquier chunk que salga vacío, no solo el de descuentos.
5. **Bug hermano `MIXED_ASK_CERTIFICATION`** (v0.20.2) — "yo y mi pareja"/"2 y uno snorkel" entrando por ese paso cuenta mal. Sin arreglar.
6. **Gaps del acompañante** (v0.20.13, ver `TODO.md`): roles quién bucea/acompaña; familiares en el atajo de overview; decisión deny-list vs safe-list del atajo de precios.
7. **Hallazgos menores de baterías** (Gonzalo): nitrox "$10/tanque" (alucinación), "?" resetea a idioma, emoji/"..." → welcome en inglés.
8. **Números de teléfono embebidos en la KB** — la regla de prompt + el guard determinista los bloquean en la salida, pero siguen en los JSON. Limpieza opcional del KB (requiere reindex) si se quiere quitarlos de raíz.
9. **Switch multi-día vago por texto** (v0.20.27) — "quiero 5 inmersiones" (con conteo) cambia el plan correctamente en `MIXED_ADD_QTY`; pero "prefiero multi-día" *sin número* lo enruta el supervisor a RAG (que lista los paquetes) en vez de mostrar el menú multi-día — el cliente tiene que dar luego un conteo. Funcional pero en 2 pasos. Además, tras un split de snorkel el flujo está en `MIXED_CERT_LAST_DIVE` y el switch multi-día por texto aún no está cableado ahí (cae a RAG informativo). Cablear `_detect_multiday_switch` también en el paso de última inmersión si se quiere el switch en 1 paso.
10. **Extracción integral de información del mensaje (aspiración del owner, 2026-07-21)** — el detector determinista (`intent_detector.py`) extrae por regex campos sueltos (actividad, cert, grupo, ubicación, conteos, edades, nacionalidad…) y se ha ido ampliando caso a caso (último: group_size=1 singular en v0.20.28). El owner quiere que de CUALQUIER mensaje se extraiga bien TODA la info dada de una vez. Opciones a evaluar: (a) seguir ampliando regex por familias de casos (barato, incremental, frágil); (b) una pasada de extracción estructurada por LLM (JSON de slots) como red de seguridad cuando el regex deja huecos, reusando la infraestructura del orquestador. Decisión de diseño pendiente con el equipo — no empezada.

## 🔴 Bloqueado / dependencias externas

- **Matriz hotel→recogida** (`Dudas_V2.docx`): esperando que el equipo confirme cuáles de los 8 hoteles "posibles obsoletos" (incl. Pao Pao) siguen vivos antes de montar `hoteles.json`.
- **Booking Agent** (integración Roverd): sigue siendo un stub.
- **WhatsApp Business API**: reloj externo — pedir cuanto antes.
- **Dominio**: migrar de `pre.is-core.dev` a `pre.divingplanet.org` (acceso a HostGator).
