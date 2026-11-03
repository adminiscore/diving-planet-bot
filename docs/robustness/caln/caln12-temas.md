# CALN-12 · Los temas que pregunta un cliente, frente a lo que sabe la base (3-nov)

Decisión de Gadea (3-nov, laguna 2): lo que la base no sabe solo aparecía cuando el sparring lo preguntaba (embarazo,
factura, «hoy mismo», mareo, cava). Aquí, tema por tema, si la base (`data/knowledge_base`: 51 políticas, 112 FAQ
curadas, fichas de servicio, decisiones) lo contesta. Sin coste de medidas.

## Cubiertos

| Tema | Dónde |
|---|---|
| Salud: asma, embarazo, mareo, oídos y resfriado, cirugía o medicación (al equipo) | FAQ, `pregnancy`, `seasickness`, `medical_restrictions`, `medical_certified_diver` |
| No sabe nadar, miedo, nervios, tiburones, profundidad | FAQ |
| Seguro | FAQ, fichas (incluye) |
| Pago: medios, moneda, euros, anticipo, efectivo (colombianos), fallo, confirmación, factura, códigos de descuento | `payment_*`, `invoice`, FAQ |
| Cancelar, cambiar fecha o personas, reembolso por clima | `cancellation`, `reschedule`, `modify_booking`, `weather_cancellation` |
| Punto de encuentro, horarios, llegar tarde, mismo día, días cerrados | `meeting_point`, `operating_hours`, `availability_always`, `closed_days`, FAQ |
| Recogida en las islas, Barú, hoteles | `island_pickup*`, `baru_departs_from_cartagena`, FAQ |
| Equipaje, taquillas, qué llevar, comida, dietas, alcohol | `luggage_policy`, `lockers`, `what_to_bring`, `food_policy`, `no_alcohol_policy` |
| Edades mínimas, menores con un adulto responsable | `age_minimum`, fichas |
| Idiomas, fotos y propina, gafas graduadas, equipo para niños | `instruction_languages`, `photos_videos_policy`, FAQ |
| Certificaciones (PADI, SSI…), carné perdido, logbook, digital | `certification_required`, FAQ |
| Buceo adaptado, privados, grupos mixtos, mínimo de grupo | `adaptive_diving`, `private_services`, `mixed_group_boat`, `minimum_group` |
| Vida marina, temporada, visibilidad, temperatura, sitios | FAQ |

## Huecos (la base no lo dice)

| # | Tema | Ejemplo de cliente | Para quién |
|---|---|---|---|
| 1 | **Personas mayores** | «Tengo 70 años, ¿puedo bucear?» (salió en s30e) | Gadea / Andrés: ¿hay edad máxima? ¿certificado médico a partir de cierta edad? |
| 2 | **Emergencias y seguridad a bordo** | «¿Llevan oxígeno? ¿Hay cámara hiperbárica cerca?» | Andrés: oxígeno y botiquín a bordo, protocolo, cámara hiperbárica más cercana |
| 3 | **Cuántos buzos por guía o instructor** | «¿Cuántas personas van con cada instructor?» | Andrés: la proporción en el minicurso, en los cursos y en el buceo certificado |
| 4 | **Ducha, baño y dónde cambiarse** | «¿Hay baño en la lancha? ¿Dónde me cambio?» | Andrés |
| 5 | **Parqueadero cerca del muelle** | «Voy en carro, ¿dónde dejo el coche?» | Andrés |
| 6 | **Regalar o reservar para otra persona** | «Quiero regalarle el minicurso a mi novio» | Gadea / Andrés: ¿hay tarjeta regalo? ¿se reserva a nombre de otro? |
| 7 | **Fumar a bordo** | «¿Se puede fumar en la lancha?» | Andrés |
| 8 | **Mascotas** | «¿Puedo llevar a mi perro de acompañante?» | Andrés |
| 9 | **Enlace de reserva de los paquetes** | 10 servicios sin `booking_url` (paquetes de 3 y 4 inmersiones, desde las islas, Bubble Makers, Divemaster, privado) | Andrés: ¿se reservan en la web? Hoy (0.43) pasan al asesor |

Los menores (cargar el móvil, wifi a bordo) no se listan: no han salido nunca y la respuesta obvia no daña.

## Siguiente

Las respuestas, como las del 30-oct: a `policies.json` (dentro de `policies`) con sus formas de preguntarlas en
`curada/preguntas.json`, y la decisión en `decisiones.json` si es de conducta. Después, una charla por tema contra la rama
con `charla_rama --env RAG_KB_ESQUEMA=kb_v2_gadea` (la base curada cargada con `scripts.kb_v2 --esquema kb_v2_gadea`).
