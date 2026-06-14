# Preguntas para el owner — negocio / KB antes de demo

Este documento recoge los huecos de negocio que siguen siendo sensibles para la demo.

Objetivo:
- separar lo que **ya podemos responder con seguridad** usando la KB actual,
- de lo que **todavía requiere confirmación del cliente/owner** antes de que el bot lo responda con confianza.

## 1. Lo que ya podemos sostener hoy con la KB actual

### Precios base

La KB actual ya tiene bastante cobertura de tarifas en:
- `data/knowledge_base/pricing.json`
- `data/knowledge_base/services.json`

Hoy podemos sostener con bastante seguridad:
- precios normales vs online para salidas desde Cartagena,
- precios normales vs online para clientes ya en islas,
- precios de paquetes 3/4/5/7/9,
- precios de Open Water, Advanced, Rescue, referral y especialidades,
- nota de descuento por equipo propio (`$33.000 COP / día`).

### Descuentos generales

La KB actual ya permite sostener estas reglas generales:
- existe precio online / descuento web,
- existe descuento para grupos de 4+,
- existe plan PARCEROS,
- existe descuento / tarifa especial para colombianos,
- la política por defecto dice que **los descuentos no son acumulables** salvo autorización del staff.

Fuentes:
- `data/knowledge_base/discounts.json`
- `data/knowledge_base/pricing.json`
- `data/knowledge_base/policies.json`
- `data/knowledge_base/faqs.json`

### Última hora / cierre de reservas online

Esto sí está bastante claro hoy:
- el sistema ROVERD cierra a las **4:30 p.m. del día anterior**,
- para reservas de última hora hay que pasar a WhatsApp.

Fuentes:
- `data/knowledge_base/policies.json`
- `data/knowledge_base/faqs.json`

### Comida y alergias

Esto está mejor cubierto de lo que parecía inicialmente.

Hoy la KB ya sostiene que:
- el tour incluye agua durante todo el día,
- incluye dulces de coco entre inmersiones,
- incluye almuerzo,
- el almuerzo es arroz con pollo o arroz con vegetales,
- vegetarianos, veganos y celíacos reciben arroz con vegetales,
- si el cliente tiene alergias, debe avisar antes del tour,
- el bot **no debe preguntar proactivamente** por alergias.

Fuentes:
- `data/knowledge_base/policies.json`
- `data/knowledge_base/faqs.json`

### Fotos y videos

También hay más base de la que parecía.

Hoy la KB ya sostiene que:
- fotos y videos **no están incluidos**,
- no se ofrecen proactivamente,
- el instructor puede hacerlos voluntariamente,
- la entrega suele hacerse como máximo al día siguiente,
- la propina orientativa es `50.000 COP / 14 USD`, pagada directamente al instructor,
- no se hacen fotos/videos en minicursos ni primeras experiencias.

Fuentes:
- `data/knowledge_base/policies.json`
- `data/knowledge_base/faqs.json`

### Recogidas en islas

Hoy sí podemos sostener la regla general:
- si el cliente ya está en Islas del Rosario y su hotel tiene **acceso marítimo / muelle**, la recogida y regreso en lancha están incluidos.

Además, la KB ya contiene:
- la regla general de recogida,
- horarios orientativos de recogida en varios FAQs de planes desde islas,
- y el árbol ya tiene selector de isla y hotel.

Fuentes:
- `data/knowledge_base/policies.json`
- `data/knowledge_base/faqs.json`
- `src/flows/decision_tree.py`

## 2. Lo que sigue necesitando confirmación del owner

## 2.1 Precios y descuentos

### 1. Fuente oficial de precios para demo

Hoy tenemos precios en `pricing.json` y también precios en `services.json`.

Necesitamos confirmar:
- ¿Cuál debe considerarse la **fuente oficial comercial** para la demo?
- Si hay discrepancia entre ambos, ¿cuál manda?
- ¿Queremos que el bot use siempre el precio online como referencia principal y el normal como comparación?

**Impacto**: evita respuestas inconsistentes entre árbol, RAG y fichas de servicio.

---

### 2. Descuento para colombianos

Sabemos que existe, pero no está suficientemente cerrado.

Necesitamos confirmar:
- ¿La tarifa para colombianos es una **tarifa cerrada** o sigue siendo un ajuste/manual en algunos casos?
- ¿Aplica a todos los servicios o solo a algunos?
- ¿Aplica también a cursos y especialidades?
- ¿Se puede mostrar directamente en chat o siempre hay que derivarlo a WhatsApp?

**Impacto**: ahora el bot sabe que existe, pero evita prometer cantidades concretas.

---

### 3. Acumulabilidad de descuentos

La KB dice que los descuentos no son acumulables salvo autorización del staff, pero falta bajarlo a casos concretos.

Necesitamos confirmar:
- Confirmamos que `online/web` y `direct booking` se están usando como el mismo concepto: **10% de descuento**.
- ¿Cuáles son exactamente **todos los descuentos vigentes** que el bot puede mencionar?
- ¿Se puede combinar colombiano + web?
- ¿Se puede combinar grupo + web?
- ¿Se puede combinar segundo día + grupo?
- ¿PARCEROS excluye todos los demás descuentos?


**Impacto**: este es uno de los puntos más fáciles para que el bot se contradiga en demo.

---

### 4. Descuento de grupo

Sabemos que existe 5% para grupos de 4+, pero faltan detalles.

Necesitamos confirmar:
- ¿Aplica a todos los servicios sin excepción?
- ¿Aplica también a cursos?
- ¿Aplica a grupos mixtos?
- ¿Se aplica automáticamente o solo previa aprobación del staff?
- En grupos mixtos (buceo + snorkel / certificados + principiantes), ¿el precio total es simplemente la suma de `cantidad × precio_individual` (aplicando los descuentos que correspondan) o existen tarifas cerradas/especiales de grupo?
- Para grupos grandes (6+ personas), ¿hay política específica (lancha privada automática, precio de grupo cerrado, cupo máximo por tour)?

**Impacto**: el bot podría calcular mal totales si esto no queda cerrado.

---

### 5. Precio Bubble Makers (8-10 años)

El flujo ya contempla derivar a Bubble Makers para niños de 8 a 10 años, pero no tenemos precio en la KB.

Necesitamos confirmar:
- ¿Cuál es el precio de Bubble Makers?
- ¿Es el mismo precio que minicurso?
- ¿Tiene precio especial menor por ser sólo piscina / aguas poco profundas?
- ¿Cambia si el cliente sale desde Cartagena vs. si ya está en las islas?

**Impacto**: el bot ahora escala siempre cuando hay menores 8-10. Con el precio podríamos incluirlos en el cálculo del resumen y mostrar un rango orientativo.

---

### 6. Servicio privado: rangos de precio indicativos

Hoy el servicio privado (lancha exclusiva) se maneja como "contact only" sin precios en la KB.

Necesitamos confirmar:
- ¿Tenéis un rango de precios indicativo para servicio privado (por ejemplo, "para 2 personas desde U$X", "para grupos de 6+ desde U$Y")?
- ¿Depende sólo del tamaño del grupo o también de la temporada / día de la semana?

**Impacto**: el bot ahora ofrece "Cotizar lancha privada" pero sólo escala. Con un rango aproximado podría decir "desde U$X, el asesor confirma según fechas".

---

## 2.2 Reserva y pagos

### 7. Confirmación real de reserva

Hoy sabemos que existe ROVERD y que el sistema cierra a las 4:30 p.m. del día anterior.

Necesitamos confirmar:
- ¿Cuándo queda una reserva **realmente confirmada**?
- ¿Al pagar online queda confirmada automáticamente?
- ¿Hay revisión manual posterior?
- ¿Qué datos mínimos se necesitan para considerar una reserva cerrada?
- ¿Cuando entra una reserva, el Excel se rellena automáticamente o lo actualiza alguien manualmente?
- En reservas mixtas (varias actividades en el mismo día), ¿ROVERD permite hacer la reserva online en un solo booking o siempre hay que gestionarlas manualmente por WhatsApp?
- ¿Envían recordatorios automáticos antes de la actividad (email, WhatsApp, SMS)? ¿Con cuánta antelación?
- ¿Existe un máximo de personas por salida / tour?
- ¿Qué ocurre operativamente cuando un tour está lleno (overbooking, cierre automático, bloqueo manual, etc.)?
- ¿Cómo controlan hoy la disponibilidad (sistema, Excel, calendario manual, ROVERD, mezcla de varios)?
- ¿Quieren que el chatbot tenga acceso a disponibilidad en tiempo real, o siempre mostrará información genérica y derivará dudas de cupos a un asesor?
- ¿Existe lista de espera cuando no hay cupos, y cómo se gestiona?

**Impacto**: el bot hoy puede explicar el canal, pero no la confirmación real exacta.

---


### 8. Anticipo / depósitos

Necesitamos confirmar:
- ¿Se paga el 100% o solo un anticipo?
- Si es anticipo: ¿cuánto porcentaje o cuánto valor?
- ¿Es igual para tours, cursos, grupos, privados y colombianos?
- ¿Hay diferencia entre reservar por web y reservar por WhatsApp?

**Impacto**: sin esto, el bot no debe explicar política de pago detallada.

---

### 9. Medios de pago aceptados

Necesitamos confirmar:
- ¿Qué medios aceptamos exactamente?
- ¿Tarjeta?
- ¿Transferencia?
- ¿Nequi?
- ¿Bancolombia?
- ¿Efectivo?
- ¿PayPal / enlace internacional?

**Impacto**: hoy el bot puede hablar de reserva, pero no de medios exactos con seguridad.

---

### 10. Moneda y pago fallido

Necesitamos confirmar:
- ¿Qué monedas aceptamos realmente?
- ¿Qué pasa si falla un pago online?
- ¿Se puede reintentar desde el mismo link?
- ¿Hay soporte manual si la tarjeta extranjera falla?

**Impacto**: punto sensible en conversación comercial real.

---

## 2.3 Cancelaciones y cambios

### 11. Cancelación por parte del cliente

la idea es que en caso de cancelación el bot termine pasando con un agente, aunque pueda dar un resumen básico de la política.

Hoy la KB remite a términos y condiciones, pero no resume la regla.

Necesitamos confirmar:
- ¿Hasta cuándo puede cancelar sin penalización?
- ¿Hay penalización parcial? ¿cuánto?
- ¿Hay casos sin reembolso?
- ¿Qué pasa con el no-show?

**Impacto**: el bot no debería improvisar aquí bajo ningún concepto.

---

### 12. Cambio de fecha

Aquí queremos que, ante una petición concreta de cambio de fecha, el bot pase siempre con un agente en lugar de decidir solo.

Necesitamos confirmar:
- ¿Se puede cambiar fecha?
- ¿Hasta cuándo?
- ¿Tiene coste?
- ¿Depende del tipo de servicio o temporada?

**Impacto**: muy preguntado y hoy no está claro en formato resumido.

---

### 13. Clima / capitanía / reembolsos

Aquí sí tenemos una parte cubierta: si Capitanía cierra salidas, se menciona reembolso 100%.

Necesitamos confirmar:
- ¿Siempre es reembolso 100% o a veces es reprogramación?
- ¿Qué pasa si el clima no cancela oficialmente pero se cambia el plan?
- ¿Cuánto tarda el reembolso?

**Impacto**: hoy podemos responder la regla general, pero faltan matices operativos.

---

## 2.4 Comida, alergias, fotos y extras

### 14. Comida y alergias — matiz fino

Aunque ya tenemos una base útil, faltan detalles finos.

Necesitamos confirmar:
- ¿El almuerzo es siempre el mismo o cambia según día/proveedor?
- ¿Hay snacks o bebidas adicionales aparte de agua y dulces de coco?
- ¿Se puede llevar comida propia?
- ¿Qué alergias pueden gestionarse y cuáles no podemos prometer manejar?

**Impacto**: mejora la conversación comercial sin comprometer operación.

---

### 15. Entrega de fotos y videos

La KB ya indica que las fotos y videos no se ofrecen proactivamente, que no están incluidos en el precio y que la entrega suele hacerse como máximo al día siguiente.

Necesitamos confirmar:
- ¿Cómo se entregan normalmente las fotos y videos? (Drive, enlace de descarga, WhatsApp, AirDrop en sitio, etc.)
- ¿Quién gestiona esa entrega (instructor directamente, recepción, equipo de operaciones)?
- ¿Hay algún plazo oficial distinto a "como máximo al día siguiente" para ciertos planes?

**Impacto**: el bot puede explicar hoy que no están incluidos y que se entregan al día siguiente, pero no puede detallar el canal de entrega sin riesgo de inventar.

---

### 16. Post-actividad y soporte posterior

No tenemos documentado cómo se gestionan las consultas después de la actividad.

Necesitamos confirmar:
- ¿Cómo gestionan consultas posteriores al tour, por ejemplo:
  - fotos pendientes,
  - objetos perdidos,
  - detalles de una inmersión concreta,
  - certificados,
  - incidencias durante el servicio?
- ¿Quién responde estas consultas (instructores, recepción, un área específica de servicio al cliente)?
- ¿En qué canal deberían entrar estas consultas si las inicia el chatbot (seguir en chat, pasar a WhatsApp, correo, etc.)?
- ¿Quieren que el chatbot pueda seguir ayudando después de la actividad, o siempre debe derivar a un humano en estos casos?

**Impacto**: estas situaciones son muy frecuentes; si no están claras, el bot debería limitarse a escalar siempre y no intentar resolver nada post-actividad.

---

## 2.5 Hoteles y recogidas

### 17. Matriz hotel → recogida sí/no

Este es probablemente el mayor hueco operativo que sigue vivo.

Necesitamos confirmar:
- Para cada hotel relevante del selector de islas, ¿la recogida está confirmada como **sí**, **no** o **depende**?
- ¿Qué hoteles usan muelle propio?
- ¿Qué hoteles usan muelle comunitario?
- ¿Qué hoteles requieren coordinación manual?

**Impacto**: la regla general “si tiene acceso marítimo” existe, pero no basta para responder con total seguridad a hoteles concretos.

---

### 18. Grupos mixtos multi-día (certificados + principiantes / snorkel)

Para grupos mixtos que quieren varios días en islas, la logística no está clara.

Necesitamos confirmar:
- Si en un grupo mixto (certificados + principiantes) los certificados pueden hacer un paquete 5/7/9 buceos mientras los principiantes hacen sólo minicurso de 1 día.
- Si se permite: ¿qué pasa logísticamente con los principiantes (se quedan en la isla esperando, vuelven a Cartagena, duermen en la misma isla que el resto del grupo)?
- Si en un grupo mixto multi-día con snorkelers: ¿los snorkelers se quedan en la isla todos los días?, ¿pueden hacer snorkel cada día o sólo el primero?, ¿cómo se cotiza su alojamiento?

**Impacto**: ahora el bot escala cuando hay multi-día en grupo mixto. Con esta información podríamos preguntar duración y proponer opciones de alojamiento de forma más segura.

---

### 19. Hoteles prioritarios para cerrar antes de demo

Si no podemos cerrar la matriz completa, al menos deberíamos validar primero los hoteles que más salen en conversación.

Propuesta de validación mínima:
- San Pedro de Majagua
- Cocoliso
- Bora Bora Beach Club
- Pao Pao
- Islabela
- Centro Ubuntu
- Hotel Isla del Pirata
- Hotel Isla del Sol
- Coralina Island
- Hotel Lizamar
- Rosario EcoHotel
- Hotel San Tropel

Necesitamos confirmar por cada uno:
- ¿recogida sí/no?
- ¿horario orientativo?
- ¿alguna restricción especial?

**Impacto**: con esto ya tendríamos una demo mucho más segura.

---

### 20. Casos especiales de logística y recogida

Aparte de la matriz hotel sí/no (pregunta 17), faltan los matices operativos que más generan preguntas reales.

Necesitamos confirmar:
- **Tarifas de transporte por isla/zona**: ¿hay tarifas distintas según la zona dentro del archipiélago? ¿qué zonas tienen coste adicional sobre el precio base?
- **Hoteles fuera del selector**: si el hotel del cliente no está en nuestra lista oficial, ¿lo recogen igualmente coordinando manualmente, o se le pide trasladarse a un punto de encuentro común?
- **Punto de encuentro alternativo en islas**: si el hotel no tiene acceso marítimo, ¿existe un muelle/punto común al que el cliente deba acercarse? ¿cuál?
- **Grupo con hoteles distintos**: parejas/amigos que se hospedan en hoteles diferentes — ¿se hacen múltiples paradas de recogida o se cita en un punto único?
- **Cliente que pierde la salida**: si llega tarde y la lancha ya salió, ¿hay alternativa (incorporarse en isla por su cuenta, reembolso parcial, reprogramación)?
- **Equipaje y mochila**: confirmado preliminarmente que **sí** se puede dejar mochila/equipaje de ciudad en el muelle o en la base de las islas — falta confirmar formato (taquilla, depósito vigilado, bajo responsabilidad del cliente).
- **Edad máxima y requisitos médicos por edad**: ¿hay edad máxima de facto para bucear? ¿a partir de qué edad pedimos formulario médico extra o aval médico?

**Impacto**: hoy el bot remite a la regla general "si hay acceso marítimo te recogemos" pero no puede responder ninguno de estos casos específicos sin riesgo de inventar.

---

## 2.6 Operativa de entrada al servicio

### 21. Detección automática de nivel en paquetes 5/7/9

Hoy los paquetes 5/7/9 inmersiones son sólo para certificados (KB lo dice), pero el bot no detecta proactivamente si el cliente lo es.

Necesitamos confirmar:
- ¿El chatbot debe pedir confirmación de certificación antes de mostrar precio de estos paquetes?
- Si el cliente dice que no es certificado, ¿le ofrecemos el curso Open Water como alternativa o lo derivamos directamente a minicurso?
- ¿Hay alguna combinación válida (ej. uno del grupo certificado y otro principiante haciendo cursos en paralelo)?

**Impacto**: evita que un cliente sin certificación reciba un precio de paquete que no puede comprar.

---

### 22. Backup de instructor en servicios privados

Hoy el servicio privado se asocia mucho a Andrés, pero no está claro qué ocurre cuando no está disponible.

Necesitamos confirmar:
- Si Andrés no está disponible, ¿hay otros instructores que cubran servicio privado?
- ¿Cambia el precio o la experiencia (instructor con menos antigüedad, sin idioma X)?
- ¿Cómo debe presentarlo el bot: "te contactamos para coordinar instructor disponible" o "te confirmamos disponibilidad de Andrés"?

**Impacto**: evita comprometer una experiencia personalizada que no podamos sostener.

---

### 23. Actividades dependientes del clima o estado del mar

Hoy sabemos que el clima puede suspender salidas, pero no qué actividades son más sensibles.

Necesitamos confirmar:
- ¿Qué actividades son las primeras en cancelarse por mar picado / lluvia / viento (snorkel nocturno, buceo nocturno, salidas largas a islas más lejanas, etc.)?
- ¿Quién toma la decisión y a qué hora se confirma cada día?
- ¿Hay rutas/sitios de buceo alternativos cuando el plan original no se puede ejecutar (reef más protegido, base en isla)?

**Impacto**: el bot puede dar una respuesta más precisa que "depende del clima" cuando el cliente pregunta por una actividad específica.

---

### 24. Cursos interrumpidos por clima

Hoy no tenemos política clara sobre cursos multi-día cuando el clima interrumpe una jornada.

Necesitamos confirmar:
- Si un curso de 2 días pierde una inmersión por clima, ¿se reanuda al día siguiente sin coste extra?
- ¿Hay límite de días que se permite alargar el curso?
- ¿Qué pasa si el cliente ya tiene vuelo de regreso programado?
- ¿Reembolso parcial si el curso no puede completarse?

**Impacto**: muy preguntado por clientes con plan de viaje cerrado.

---

## 2.7 Cursos PADI — operativa, idiomas y combos

### 25. Idiomas del staff y materiales PADI

Hoy todo el bot trabaja en ES/EN, pero no sabemos qué soportan los instructores y el material PADI.

Necesitamos confirmar:
- ¿Qué idiomas hablan los instructores actuales (inglés, francés, alemán, portugués, italiano)?
- ¿Briefing pre-buceo se da en el idioma del cliente o sólo en ES/EN?
- ¿El material del curso PADI (libros, vídeos, eLearning) está disponible en qué idiomas?
- ¿Hay coste extra si el cliente pide instructor en un idioma específico?

**Impacto**: clientes europeos en temporada alta preguntan esto con frecuencia.

---

### 26. Bautismo vs. discovery dive vs. Open Water — diferenciación

Hoy el árbol del bot mezcla "minicurso", "primer buceo", "bautismo" sin distinguirlos formalmente.

Necesitamos confirmar:
- Diferencia exacta entre: bautismo (Discover Scuba Diving), discovery dive, minicurso y Open Water.
- ¿Cuándo recomendar uno u otro según las pretensiones del cliente?
- ¿Qué preguntas debería hacer el chatbot para orientar al cliente al producto correcto (días disponibles, intención de certificarse, presupuesto, edad)?
- ¿El "bautismo" es lo mismo que nuestro minicurso o tiene formato distinto?

**Impacto**: ahorra escalaciones donde el cliente sólo quiere entender qué es cada producto.

---

### 27. Entrega de certificación PADI

Hoy el bot menciona que el cliente recibe certificación tras el curso, pero no detalla el cómo.

Necesitamos confirmar:
- ¿La tarjeta PADI física se entrega en sitio, por correo postal o no se entrega (sólo digital)?
- ¿Plazo aproximado de llegada de la tarjeta física si aplica?
- ¿Se entrega la **PADI eCard digital automáticamente** tras el curso?
- ¿Coste de reposición si el cliente pierde la tarjeta?

**Impacto**: muy preguntado por clientes que quieren bucear en otro destino justo después.

---

### 28. Combos de cursos y especialidades

Hoy cada curso/especialidad se vende como producto independiente.

Necesitamos confirmar:
- ¿Se puede hacer Advanced + una especialidad en el mismo viaje (combo)?
- ¿Hay descuento o pack si se compran varias especialidades juntas?
- ¿Combinaciones recomendadas (ej. Advanced + Nitrox + Buoyancy)?

**Impacto**: oportunidad de upsell que hoy no podemos sostener.

---

### 29. Divemaster — duración y operativa

Hoy el flujo Divemaster es contact-only y escala directamente. Falta información mínima para guiar la conversación previa.

Necesitamos confirmar:
- ¿Cuántos días/semanas mínimo necesita el cliente para sacar Divemaster en Cartagena?
- ¿Hay prerequisitos visibles que el bot pueda mencionar (número de inmersiones, Rescue + EFR, edad mínima)?
- ¿Hay temporadas en las que no aceptan candidatos nuevos a Divemaster?

**Impacto**: el bot puede pre-cualificar al cliente antes de escalar para evitar contactos sin viabilidad.

---

## 2.8 Equipo (alquiler, propio, tallas y especiales)

### 30. Definición de "equipo propio" y aplicabilidad

Hoy la KB sabe que hay un descuento de $33.000 COP/día por equipo propio, pero no qué cuenta como "equipo propio" ni en qué actividades aplica.

Necesitamos confirmar:
- ¿Qué partes cuentan como equipo propio (BCD, regulador, traje, máscara, aletas, ordenador)?
- ¿Aplica el descuento si el cliente sólo trae parte del equipo (ej. sólo máscara y aletas)?
- ¿En qué actividades aplica: buzo certificado, paquetes, cursos PADI, minicurso, snorkel?

**Impacto**: el bot puede aplicar el descuento correctamente o pedir aclaración con seguridad.

---

### 31. Tallas extremas y disponibilidad

Hoy asumimos que tenemos talla estándar pero no hemos validado los bordes.

Necesitamos confirmar:
- ¿Tenemos traje, BCD y botines en tallas XS y XXL+? ¿hasta qué peso/altura?
- ¿Qué pasa si el cliente está fuera del rango disponible?
- ¿Hay aviso recomendado con antelación?

**Impacto**: evita que un cliente reserve y al llegar descubra que no hay equipo en su talla.

---

### 32. Lastres y tanques para clientes muy pesados o muy ligeros

Aspectos técnicos del equipo según peso del cliente.

Necesitamos confirmar:
- ¿Tenemos lastres adicionales para clientes pesados o con traje seco?
- ¿Tanques de aluminio disponibles para clientes muy ligeros (que flotarían demasiado con tanque de acero)?
- ¿Es información que el bot deba sondear o que se ajusta directamente en sitio?

**Impacto**: técnico pero importante en cursos y buceadores con biotipos extremos.

---

### 33. Máscara graduada / corrección dioptrías

Hoy no hay información en la KB.

Necesitamos confirmar:
- ¿Disponemos de máscaras con corrección de dioptrías para alquiler?
- ¿Qué dioptrías cubrimos y para qué ojos?
- ¿Hay coste adicional o está incluido?

**Impacto**: preguntado por clientes con miopía / hipermetropía.

---

### 34. Equipo para niños (Bubble Makers y minicurso)

Hoy el flujo deriva a Bubble Makers para 8-10 años, pero no sabemos si hay equipo dedicado.

Necesitamos confirmar:
- ¿Tenemos talla de traje, BCD, regulador específico para niños 8-10 años?
- ¿Y para niños de 10-12 que vienen al minicurso normal?
- ¿O se adapta el equipo de adulto más pequeño?

**Impacto**: padres que preguntan por seguridad y comodidad del menor.

---

### 35. Nitrox — operativa más allá del curso

La KB tiene el precio del curso Nitrox, pero falta la operativa de uso post-certificación.

Necesitamos confirmar:
- ¿Hay tanques de Nitrox disponibles para buceadores ya certificados Nitrox?
- ¿Cuesta extra el llenado de Nitrox sobre el de aire estándar?
- ¿Hay que reservarlo con antelación o se solicita en sitio?

**Impacto**: cliente certificado Nitrox preguntará si puede usar su certificación con nosotros.

---

## 2.9 Upsells y extras

### 36. Catálogo actual de extras

Hoy el bot no ofrece nada que esté fuera del paquete contratado.

Necesitamos confirmar:
- ¿Qué extras se ofrecen hoy realmente y a qué precio?
  - equipo premium (regulador top, ordenador de buceo, traje seco)
  - transporte privado (taxi/lancha exclusiva al muelle)
  - cursos o inmersiones adicionales al plan
  - almuerzo o bebidas extra (cerveza, refrescos)
  - libro de buceo / logbook / souvenirs
- ¿Hay otros extras que el bot debería conocer?

**Impacto**: oportunidad de upsell perdida hoy.

---

### 37. Pago y momento de los extras

Necesitamos confirmar:
- ¿Dónde se pagan los extras (online al reservar, en sitio antes del tour, post-tour por WhatsApp)?
- ¿Se pueden añadir extras después de confirmar la reserva principal?

**Impacto**: el bot puede explicar el momento adecuado para añadirlos.

---

### 38. Cuándo debe ofrecerlos el chatbot

Necesitamos confirmar:
- ¿Durante el flujo de reserva (justo antes de confirmar el carrito)?
- ¿En el chat informativo (cuando el cliente pregunta "qué incluye")?
- ¿Post-actividad (recordatorio para próximas visitas)?

**Impacto**: política comercial — el equipo decide la agresividad del upsell.

---

### 39. Packs y promociones puntuales

Necesitamos confirmar:
- ¿Hay packs vigentes que el bot pueda mencionar (combo curso + estancia, descuento por reservar X días antes, etc.)?
- ¿Hay promociones de temporada que aparecen y desaparecen (Black Friday, semana del buceador, etc.)?
- ¿Cómo se sincronizan estas promos con el bot — manualmente o desde un canal automatizado?

**Impacto**: evita que el bot ignore promociones activas o las invente.

---

## 2.10 Recordatorios automáticos

### 40. Qué recordatorios envían hoy

Necesitamos confirmar:
- ¿Recordatorio post-reserva confirmando datos (fecha, hora, punto de encuentro, qué llevar)?
- ¿Recordatorio antes de la actividad (24h, 12h, 2h antes)?
- ¿Recordatorio de documentos pendientes (formulario médico, foto de certificación, exoneración firmada)?
- ¿Recordatorio de recomendaciones (no alcohol, llevar protector solar, llegar 15 min antes)?
- ¿Recordatorio post-actividad (pedir reseña, ofrecer próximo curso)?

**Impacto**: el bot puede sustituir o complementar estos envíos.

---

### 41. Timing exacto de los recordatorios

Necesitamos confirmar:
- ¿Con cuánta antelación se envía cada uno (24h, 12h, 2h, 30min)?
- ¿Hay un horario fijo (ej. siempre a las 6 PM del día anterior)?
- ¿Qué pasa si el cliente reserva el mismo día — se envía algún recordatorio o sólo confirmación?

**Impacto**: define el calendario de comunicación.

---

### 42. Canal de envío

Necesitamos confirmar:
- ¿WhatsApp, email o ambos por canal?
- ¿Hay clientes que rechazan WhatsApp y sólo aceptan email (o viceversa)?
- ¿Hay límite legal/operativo de mensajes WhatsApp por día?

**Impacto**: si el bot va a tomar los recordatorios, debe usar el canal correcto.


