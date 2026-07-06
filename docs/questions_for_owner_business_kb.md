# Preguntas para el owner — negocio / KB antes de demo

> **Ronda 1 de respuestas recibida 2026-06-21** (notas crudas del owner, sin
> implementar todavía). Cada pregunta afectada tiene un bloque
> `**Respuesta (ronda 1):**` con la nota literal + estado:
> ✅ resuelto · 🟡 parcial / necesita aclaración · ⏳ sin respuesta todavía.
> Ver `## 3. Seguimiento ronda 1` al final del documento para la lista de
> aclaraciones pendientes antes de poder implementar con seguridad.

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

### 1. Fuente oficial de precios para demo 🟡 PARCIAL — acción: revisión conjunta

**Respuesta (ronda 3):** no hay una fuente clara todavía; el owner pidió
**revisar `pricing.json` y `services.json` juntos** antes de decidir cuál
manda. ⚠️ **Acción**: agendar/hacer esa revisión fila por fila para
detectar discrepancias concretas antes de poder cerrar esta pregunta.

Hoy tenemos precios en `pricing.json` y también precios en `services.json`.

Necesitamos confirmar:
- ¿Cuál debe considerarse la **fuente oficial comercial** para la demo?
- Si hay discrepancia entre ambos, ¿cuál manda?
- ¿Queremos que el bot use siempre el precio online como referencia principal y el normal como comparación?

**Impacto**: evita respuestas inconsistentes entre árbol, RAG y fichas de servicio.

---

### 2. Descuento para colombianos ⏳ SIN RESPUESTA

**Respuesta (ronda 1):** "pendiente" — el owner no lo ha cerrado todavía.

**Respuesta (ronda 3):** confirmado que **todavía no está definido**. El
bot debe seguir mencionando que existe descuento para colombianos sin
prometer cifra, y derivar el detalle a un asesor.

Sabemos que existe, pero no está suficientemente cerrado.

Necesitamos confirmar:
- ¿La tarifa para colombianos es una **tarifa cerrada** o sigue siendo un ajuste/manual en algunos casos?
- ¿Aplica a todos los servicios o solo a algunos?
- ¿Aplica también a cursos y especialidades?
- ¿Se puede mostrar directamente en chat o siempre hay que derivarlo a WhatsApp?

**Impacto**: ahora el bot sabe que existe, pero evita prometer cantidades concretas.

---

### 3. Acumulabilidad de descuentos 🟡 PARCIAL — acción: eliminar PARCEROS

**Respuesta (ronda 2):** PARCEROS es **un producto obsoleto y debe
eliminarse** de la KB y del bot (no es que dé "0% descuento", es que ya no
existe como plan). ⚠️ **Acción de implementación**: quitar todas las
referencias a PARCEROS en `discounts.json`, `policies.json`, `faqs.json` y
en cualquier flujo/mensaje del árbol o RAG que lo mencione.

Grupo + web: confirmado que se suman (10% grupo + 10% online = 20%, ver
pregunta 4). Pendiente aún: colombiano + web, segundo día + grupo.

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

### 4. Descuento de grupo ✅ RESUELTO (ronda 4 — completo en lo clave)

**Respuesta (ronda 2):** la regla de **4+ personas = 5%** queda **obsoleta
y se elimina**. Nueva regla: **5+ personas = 10% extra**, y si además
reservan online se suma el 10% online = **20% total**. Pendiente todavía
(no bloqueante): ¿aplica a cursos?, ¿aplica a grupos mixtos?, ¿automático o
requiere aprobación del staff?, ¿hay tarifa cerrada para 6+ / lancha
privada automática?

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

### 5. Precio Bubble Makers (8-10 años) ✅ RESUELTO (ronda 4)

**Respuesta (ronda 4):** $187 USD por persona. Implementado en `faqs.json`. El bot ya puede responder con precio.

El flujo ya contempla derivar a Bubble Makers para niños de 8 a 10 años, pero no tenemos precio en la KB.

Necesitamos confirmar:
- ¿Cuál es el precio de Bubble Makers?
- ¿Es el mismo precio que minicurso?
- ¿Tiene precio especial menor por ser sólo piscina / aguas poco profundas?
- ¿Cambia si el cliente sale desde Cartagena vs. si ya está en las islas?

**Impacto**: el bot ahora escala siempre cuando hay menores 8-10. Con el precio podríamos incluirlos en el cálculo del resumen y mostrar un rango orientativo.

---

### 6. Servicio privado: rangos de precio indicativos ✅ RESUELTO

**Respuesta (ronda 3):** no hay rango fijo — el bot debe **escalar siempre
sin dar ninguna cifra** (confirma que el comportamiento actual de
"contact only" es correcto, no hace falta cambiar nada).

Hoy el servicio privado (lancha exclusiva) se maneja como "contact only" sin precios en la KB.

Necesitamos confirmar:
- ¿Tenéis un rango de precios indicativo para servicio privado (por ejemplo, "para 2 personas desde U$X", "para grupos de 6+ desde U$Y")?
- ¿Depende sólo del tamaño del grupo o también de la temporada / día de la semana?

**Impacto**: el bot ahora ofrece "Cotizar lancha privada" pero sólo escala. Con un rango aproximado podría decir "desde U$X, el asesor confirma según fechas".

---

## 2.2 Reserva y pagos

### 7. Confirmación real de reserva 🟡 PARCIAL

**Respuesta (ronda 2):** al pagar online, el pago se sube automáticamente
al sistema ROVERD, pero **el equipo consolida después manualmente** todos
los pagos en un Excel con su estado. Es decir: **no es 100% automático**
— hay un paso de conciliación manual posterior. Para el bot: puede decir
que el pago se registra al instante en el sistema y que el equipo
confirma/concilia el estado poco después; evitar prometer "confirmación
instantánea sin revisión". Sigue sin responder: máximo de personas por
salida, manejo de overbooking, control de disponibilidad, lista de espera,
reservas mixtas en un solo booking de ROVERD. (Ver pregunta 40 para
recordatorios, ya resuelta: van por email.)

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


### 8. Anticipo / depósitos ✅ RESUELTO

**Respuesta (ronda 2):**
- **Colombianos**: pagan **50% online** (métodos de pago colombianos) al
  reservar, y el otro 50% presencial (tarjeta o efectivo).
- **No colombianos**: pagan el **100%** vía la URL de pago online (tarjeta)
  o presencial (tarjeta o efectivo) — no se menciona anticipo parcial para
  ellos.
- No depende de si es privado/grupo grande, depende de si es colombiano o no.

Necesitamos confirmar:
- ¿Se paga el 100% o solo un anticipo?
- Si es anticipo: ¿cuánto porcentaje o cuánto valor?
- ¿Es igual para tours, cursos, grupos, privados y colombianos?
- ¿Hay diferencia entre reservar por web y reservar por WhatsApp?

**Impacto**: sin esto, el bot no debe explicar política de pago detallada.

---

### 9. Medios de pago aceptados ✅ RESUELTO

**Respuesta (ronda 2):**
- **Colombianos**: pagan 50% online con métodos de pago colombianos
  (incluye Llave — Bancolombia/ACH), el otro 50% presencial con tarjeta o
  efectivo (ver pregunta 8, anticipo).
- **No colombianos / extranjeros**: pagan vía la URL de pago online con
  tarjeta, o presencial con tarjeta o efectivo. No se menciona PayPal — se
  entiende que tarjeta internacional (Visa/Mastercard) cubre este caso.
  Sin acción pendiente bloqueante.

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

### 10. Moneda y pago fallido ✅ RESUELTO

**Respuesta (ronda 3):**
- **Moneda**: colombianos pagan en **COP**, el resto (extranjeros) en
  **USD**.
- **Pago fallido**: el bot debe decir al cliente que **reintente en unos
  minutos** y revise que los datos introducidos sean correctos; si sigue
  fallando, ofrecer **dos botones** — escalar con un asesor / volver al
  menú principal (home). No mencionar reintento "con el mismo link"
  específicamente, solo reintentar en general.

Necesitamos confirmar:
- ¿Qué monedas aceptamos realmente?
- ¿Qué pasa si falla un pago online?
- ¿Se puede reintentar desde el mismo link?
- ¿Hay soporte manual si la tarjeta extranjera falla?

**Impacto**: punto sensible en conversación comercial real.

---

## 2.3 Cancelaciones y cambios

### 11. Cancelación por parte del cliente ✅ RESUELTO (comportamiento del bot)

**Respuesta (ronda 2):** el bot debe **informar la política de
cancelación/reembolso** usando los JSON de la KB (`policies.json` /
`faqs.json`, que ya remiten a términos y condiciones), y a continuación
mostrar **dos botones**: uno para contactar al staff (escalar) y otro para
volver al menú principal (home). Esto define el comportamiento de UX —
sigue pendiente (no bloqueante para implementar el flujo) el detalle fino
de plazos sin penalización, penalización parcial, casos sin reembolso y
no-show, que vendrán reflejados en el texto de política una vez se
redacten.

la idea es que en caso de cancelación el bot termine pasando con un agente, aunque pueda dar un resumen básico de la política.

Hoy la KB remite a términos y condiciones, pero no resume la regla.

Necesitamos confirmar:
- ¿Hasta cuándo puede cancelar sin penalización?
- ¿Hay penalización parcial? ¿cuánto?
- ¿Hay casos sin reembolso?
- ¿Qué pasa con el no-show?

**Impacto**: el bot no debería improvisar aquí bajo ningún concepto.

---

### 12. Cambio de fecha ✅ RESUELTO (comportamiento del bot)

**Respuesta (ronda 3):** mismo patrón que cancelaciones (#11): el bot debe
informar lo que diga la política/JSON de la KB sobre cambio de fecha, y
mostrar dos botones — escalar a asesor / volver al menú principal (home).
No decide ni promete plazos o costos por su cuenta.

Aquí queremos que, ante una petición concreta de cambio de fecha, el bot pase siempre con un agente en lugar de decidir solo.

Necesitamos confirmar:
- ¿Se puede cambiar fecha?
- ¿Hasta cuándo?
- ¿Tiene coste?
- ¿Depende del tipo de servicio o temporada?

**Impacto**: muy preguntado y hoy no está claro en formato resumido.

---

### 13. Clima / capitanía / reembolsos ✅ RESUELTO (ronda 4 — parcial)

**Respuesta (ronda 3):** el owner pidió dejarla **en pendiente** por ahora.
**Respuesta (ronda 4):** siempre se prefiere reprogramar antes de reembolsar. Si Capitanía cierra y no es posible reagendar → reembolso 100%. Implementado en `faqs.json` (FAQ clima actualizada). Pendiente: ¿cuánto tarda el reembolso?, ¿qué pasa si el clima no cancela oficialmente pero cambia el plan?

Aquí sí tenemos una parte cubierta: si Capitanía cierra salidas, se menciona reembolso 100%.

Necesitamos confirmar:
- ¿Siempre es reembolso 100% o a veces es reprogramación?
- ¿Qué pasa si el clima no cancela oficialmente pero se cambia el plan?
- ¿Cuánto tarda el reembolso?

**Impacto**: hoy podemos responder la regla general, pero faltan matices operativos.

---

## 2.4 Comida, alergias, fotos y extras

### 14. Comida y alergias — matiz fino ✅ RESUELTO (parcial)

**Respuesta (ronda 3):** el menú es siempre el mismo (arroz con pollo /
arroz con vegetales), **no cambia** según día/proveedor. **Sí se permite
llevar comida propia** (útil para alergias o dietas especiales). Sigue
sin responder qué alergias concretas se pueden gestionar vs. cuáles no se
pueden prometer manejar — pero con "puede traer su propia comida" ya hay
una respuesta segura por defecto.

Aunque ya tenemos una base útil, faltan detalles finos.

Necesitamos confirmar:
- ¿El almuerzo es siempre el mismo o cambia según día/proveedor?
- ¿Hay snacks o bebidas adicionales aparte de agua y dulces de coco?
- ¿Se puede llevar comida propia?
- ¿Qué alergias pueden gestionarse y cuáles no podemos prometer manejar?

**Impacto**: mejora la conversación comercial sin comprometer operación.

---

### 15. Entrega de fotos y videos ✅ RESUELTO (canal) — falta plazo/gestión

**Respuesta (ronda 1):** "si no se ve bien o no son buenas, propina al
instructor (solo buzos certificados), las mandan por WhatsApp" — confirma
canal de entrega = WhatsApp, y que el matiz de calidad/propina es
**exclusivo de buceadores certificados** (no minicursos, coherente con la
KB actual). Sigue sin responder: quién gestiona el envío (instructor
directo vs. recepción) y si hay plazo oficial distinto al "día siguiente"
para algunos planes.

La KB ya indica que las fotos y videos no se ofrecen proactivamente, que no están incluidos en el precio y que la entrega suele hacerse como máximo al día siguiente.

Necesitamos confirmar:
- ¿Cómo se entregan normalmente las fotos y videos? (Drive, enlace de descarga, WhatsApp, AirDrop en sitio, etc.)
- ¿Quién gestiona esa entrega (instructor directamente, recepción, equipo de operaciones)?
- ¿Hay algún plazo oficial distinto a "como máximo al día siguiente" para ciertos planes?

**Impacto**: el bot puede explicar hoy que no están incluidos y que se entregan al día siguiente, pero no puede detallar el canal de entrega sin riesgo de inventar.

---

### 16. Post-actividad y soporte posterior 🟡 PARCIAL

**Respuesta (ronda 1):** "preguntas de cosas perdidas: asesor" — objetos
perdidos siempre escalan a un asesor humano. Sigue sin responder: fotos
pendientes (más allá del canal ya confirmado en la 15), certificados,
incidencias durante el servicio, y si el chatbot puede seguir ayudando
post-actividad en algún caso o siempre debe escalar.

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

### 17. Matriz hotel → recogida sí/no 🟡 PARCIAL (precio resuelto, matriz pendiente)

**Respuesta (ronda 1):** "islas del rosario: mismo valor para todos / baru:
como si fueras de cartagena - les puede recoger de aquí pero el coste es lo
mismo" — esto resuelve que el **precio** no varía por hotel dentro de
Islas del Rosario, y que Barú se trata como salida desde Cartagena a
efectos de precio (con posibilidad de recogida igualmente). **No resuelve**
la matriz sí/no de recogida física por hotel (muelle propio/comunitario/
coordinación manual) — sigue pendiente la pregunta 19 (hoteles
prioritarios) para cerrarlo.

Este es probablemente el mayor hueco operativo que sigue vivo.

Necesitamos confirmar:
- Para cada hotel relevante del selector de islas, ¿la recogida está confirmada como **sí**, **no** o **depende**?
- ¿Qué hoteles usan muelle propio?
- ¿Qué hoteles usan muelle comunitario?
- ¿Qué hoteles requieren coordinación manual?

**Impacto**: la regla general “si tiene acceso marítimo” existe, pero no basta para responder con total seguridad a hoteles concretos.

---

### 18. Grupos mixtos multi-día (certificados + principiantes / snorkel) ✅ RESUELTO

**Respuesta (ronda 1):** "paquetes multidía: solo son buceos certificados,
a los que no, les ofrece el curso certificado" — confirma que no existe
combinación multi-día mixta: los paquetes 5/7/9 son solo para certificados,
y a los no certificados se les ofrece el curso Open Water en su lugar (esto
también resuelve la pregunta 21). Ya no aplican las dudas de logística de
alojamiento para principiantes/snorkelers en multi-día, porque ese
escenario mixto no existe.

Para grupos mixtos que quieren varios días en islas, la logística no está clara.

Necesitamos confirmar:
- Si en un grupo mixto (certificados + principiantes) los certificados pueden hacer un paquete 5/7/9 buceos mientras los principiantes hacen sólo minicurso de 1 día.
- Si se permite: ¿qué pasa logísticamente con los principiantes (se quedan en la isla esperando, vuelven a Cartagena, duermen en la misma isla que el resto del grupo)?
- Si en un grupo mixto multi-día con snorkelers: ¿los snorkelers se quedan en la isla todos los días?, ¿pueden hacer snorkel cada día o sólo el primero?, ¿cómo se cotiza su alojamiento?

**Impacto**: ahora el bot escala cuando hay multi-día en grupo mixto. Con esta información podríamos preguntar duración y proponer opciones de alojamiento de forma más segura.

---

### 19. Hoteles prioritarios para cerrar antes de demo ✅ RESUELTO (ronda 5 — matriz entregada)

**Respuesta (ronda 5, `Dudas_V2.docx` 2026-07-02):** el owner entregó la
**matriz completa hotel→recogida** en 5 categorías (base / muelle propio /
camina al centro / camina al muelle / isla privada). Recogida solo desde
islas del Rosario con acceso por mar (Barú NO); transfer incluido sin
importar la distancia. Aviso del owner: la lista cambia constantemente.
**Estado de implementación:** matriz documentada en `TODO.md`; pendiente
(1) verificar 8 hoteles que el bot reconoce y el owner ya no lista (incl.
Pao Pao) y (2) montar `data/knowledge_base/hoteles.json` como fuente única.
Ver el gap analysis completo en `TODO.md`.

**Respuesta (ronda 3):** varía por hotel, el owner necesita **revisarlo
con su equipo** antes de poder confirmar la matriz. ⚠️ Queda como tarea
de seguimiento (no es que falte preguntarlo, es que requiere que él lo
verifique internamente).

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

### 20. Casos especiales de logística y recogida 🟡 PARCIAL

**Respuesta (ronda 3):** "cliente que pierde la salida" → **pendiente**,
no respondida todavía (debe seguir escalando sin prometer reembolso ni
no-show). El resto de sub-preguntas (tarifas por zona, hoteles fuera del
selector, punto de encuentro alternativo, grupo con hoteles distintos,
equipaje/mochila, edad máxima) sigue sin respuesta.

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

### 21. Detección automática de nivel en paquetes 5/7/9 ✅ RESUELTO

**Respuesta (ronda 1):** ver pregunta 18 — si el cliente no es certificado,
se le ofrece directamente el curso Open Water como alternativa al paquete
5/7/9. Falta solo confirmar si existe alguna combinación válida (uno
certificado + otro haciendo curso en paralelo) pero no bloquea
implementación de la regla principal.

Hoy los paquetes 5/7/9 inmersiones son sólo para certificados (KB lo dice), pero el bot no detecta proactivamente si el cliente lo es.

Necesitamos confirmar:
- ¿El chatbot debe pedir confirmación de certificación antes de mostrar precio de estos paquetes?
- Si el cliente dice que no es certificado, ¿le ofrecemos el curso Open Water como alternativa o lo derivamos directamente a minicurso?
- ¿Hay alguna combinación válida (ej. uno del grupo certificado y otro principiante haciendo cursos en paralelo)?

**Impacto**: evita que un cliente sin certificación reciba un precio de paquete que no puede comprar.

---

### 22. Backup de instructor en servicios privados ✅ RESUELTO

**Respuesta (ronda 3):** sí hay backup, se coordina sin problema. El bot
debe presentarlo de forma genérica: "te contactamos para coordinar
instructor disponible", sin mencionar nombre ni prometer a Andrés
específicamente.

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

### 24. Cursos interrumpidos por clima ✅ RESUELTO (ronda 4 — parcial)

**Respuesta (ronda 4):** si un curso pierde un día por clima, la actividad se retoma al día siguiente. El cliente asume el coste de la noche de hotel adicional (el alojamiento no está incluido). Implementado en `faqs.json`. Pendiente: ¿hay límite de días que se puede alargar?, ¿qué pasa si el cliente ya tiene vuelo?, ¿reembolso parcial si no puede completarse?

Hoy no tenemos política clara sobre cursos multi-día cuando el clima interrumpe una jornada.

Necesitamos confirmar:
- Si un curso de 2 días pierde una inmersión por clima, ¿se reanuda al día siguiente sin coste extra?
- ¿Hay límite de días que se permite alargar el curso?
- ¿Qué pasa si el cliente ya tiene vuelo de regreso programado?
- ¿Reembolso parcial si el curso no puede completarse?

**Impacto**: muy preguntado por clientes con plan de viaje cerrado.

---

## 2.7 Cursos PADI — operativa, idiomas y combos

### 25. Idiomas del staff y materiales PADI ✅ RESUELTO (ronda 4)

**Respuesta (ronda 4):** los instructores imparten en **español e inglés únicamente**. No hay instrucción en otros idiomas. Implementado en `faqs.json`.

Hoy todo el bot trabaja en ES/EN, pero no sabemos qué soportan los instructores y el material PADI.

Necesitamos confirmar:
- ¿Qué idiomas hablan los instructores actuales (inglés, francés, alemán, portugués, italiano)?
- ¿Briefing pre-buceo se da en el idioma del cliente o sólo en ES/EN?
- ¿El material del curso PADI (libros, vídeos, eLearning) está disponible en qué idiomas?
- ¿Hay coste extra si el cliente pide instructor en un idioma específico?

**Impacto**: clientes europeos en temporada alta preguntan esto con frecuencia.

---

### 26. Bautismo vs. discovery dive vs. Open Water — diferenciación ✅ RESUELTO

**Respuesta (ronda 3):** "bautismo" = "Discover Scuba Diving" = nuestro
**minicurso** — son el mismo producto con distintos nombres (primera
experiencia de buceo sin certificación). Open Water es un producto
distinto (curso de certificación completo). El árbol del bot puede tratar
estos términos como sinónimos sin riesgo de confundir productos.

Hoy el árbol del bot mezcla "minicurso", "primer buceo", "bautismo" sin distinguirlos formalmente.

Necesitamos confirmar:
- Diferencia exacta entre: bautismo (Discover Scuba Diving), discovery dive, minicurso y Open Water.
- ¿Cuándo recomendar uno u otro según las pretensiones del cliente?
- ¿Qué preguntas debería hacer el chatbot para orientar al cliente al producto correcto (días disponibles, intención de certificarse, presupuesto, edad)?
- ¿El "bautismo" es lo mismo que nuestro minicurso o tiene formato distinto?

**Impacto**: ahorra escalaciones donde el cliente sólo quiere entender qué es cada producto.

---

### 27. Entrega de certificación PADI ✅ RESUELTO (ronda 4)

**Respuesta (ronda 4):** PADI ya **no emite tarjeta física**. La certificación es una **eCard digital** entregada via la app de PADI. Válida para bucear en cualquier parte del mundo. Implementado en `faqs.json`.

Hoy el bot menciona que el cliente recibe certificación tras el curso, pero no detalla el cómo.

Necesitamos confirmar:
- ¿La tarjeta PADI física se entrega en sitio, por correo postal o no se entrega (sólo digital)?
- ¿Plazo aproximado de llegada de la tarjeta física si aplica?
- ¿Se entrega la **PADI eCard digital automáticamente** tras el curso?
- ¿Coste de reposición si el cliente pierde la tarjeta?

**Impacto**: muy preguntado por clientes que quieren bucear en otro destino justo después.

---

### 28. Combos de cursos y especialidades ✅ RESUELTO (ronda 4 — parcial)

**Respuesta (ronda 4):** sí es posible combinar cursos y especialidades en el mismo viaje si hay tiempo suficiente. El cliente debe contactar por WhatsApp para planificar el itinerario. Implementado en `faqs.json`. Pendiente: ¿hay descuento o pack si se compran varias especialidades juntas?

Hoy cada curso/especialidad se vende como producto independiente.

Necesitamos confirmar:
- ¿Se puede hacer Advanced + una especialidad en el mismo viaje (combo)?
- ¿Hay descuento o pack si se compran varias especialidades juntas?
- ¿Combinaciones recomendadas (ej. Advanced + Nitrox + Buoyancy)?

**Impacto**: oportunidad de upsell que hoy no podemos sostener.

---

### 29. Divemaster — duración y operativa ⏳ EN PAUSA

**Respuesta (ronda 3):** "pendiente" — no respondida todavía. Sigue
escalando como contact-only sin detalles.

Hoy el flujo Divemaster es contact-only y escala directamente. Falta información mínima para guiar la conversación previa.

Necesitamos confirmar:
- ¿Cuántos días/semanas mínimo necesita el cliente para sacar Divemaster en Cartagena?
- ¿Hay prerequisitos visibles que el bot pueda mencionar (número de inmersiones, Rescue + EFR, edad mínima)?
- ¿Hay temporadas en las que no aceptan candidatos nuevos a Divemaster?

**Impacto**: el bot puede pre-cualificar al cliente antes de escalar para evitar contactos sin viabilidad.

---

## 2.8 Equipo (alquiler, propio, tallas y especiales)

### 30. Definición de "equipo propio" y aplicabilidad ✅ RESUELTO (regla principal)

**Respuesta (ronda 2):** el **5% sustituye** el monto fijo actual de
$33.000 COP/día (queda obsoleto). El 5% aplica solo si el cliente trae el
equipo **completo** (regulador, chaleco/BCD, traje, máscara, aletas, etc.
— "TODO"); traer solo parte del equipo no da descuento. Pendiente
(no bloqueante): confirmar en qué actividades aplica exactamente (cursos
PADI, minicurso, snorkel) más allá de buceo certificado.

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

### 33. Máscara graduada / corrección dioptrías ✅ RESUELTO (ronda 4)

**Respuesta (ronda 4):** disponibles en **dioptrías 2, 3 y 4**. Sin coste adicional (incluido en el equipo). Avisar al reservar. Implementado en `faqs.json`.

Hoy no hay información en la KB.

Necesitamos confirmar:
- ¿Disponemos de máscaras con corrección de dioptrías para alquiler?
- ¿Qué dioptrías cubrimos y para qué ojos?
- ¿Hay coste adicional o está incluido?

**Impacto**: preguntado por clientes con miopía / hipermetropía.

---

### 34. Equipo para niños (Bubble Makers y minicurso) ✅ RESUELTO (ronda 4)

**Respuesta (ronda 4):** disponemos de **BCD pequeño y botellas pequeñas** para niños. Cubre Bubble Makers (8-10 años) y minicurso (desde 10 años). Implementado en `faqs.json`.

Hoy el flujo deriva a Bubble Makers para 8-10 años, pero no sabemos si hay equipo dedicado.

Necesitamos confirmar:
- ¿Tenemos talla de traje, BCD, regulador específico para niños 8-10 años?
- ¿Y para niños de 10-12 que vienen al minicurso normal?
- ¿O se adapta el equipo de adulto más pequeño?

**Impacto**: padres que preguntan por seguridad y comodidad del menor.

---

### 35. Nitrox — operativa más allá del curso ✅ RESUELTO (ronda 4)

**Respuesta (ronda 4):** tanques de Nitrox disponibles **bajo pedido** (avisar al reservar). Precio: **$10 USD/tanque** ($20 USD si se hacen 2 inmersiones). Requiere certificación Nitrox. Implementado en `faqs.json`.

La KB tiene el precio del curso Nitrox, pero falta la operativa de uso post-certificación.

Necesitamos confirmar:
- ¿Hay tanques de Nitrox disponibles para buceadores ya certificados Nitrox?
- ¿Cuesta extra el llenado de Nitrox sobre el de aire estándar?
- ¿Hay que reservarlo con antelación o se solicita en sitio?

**Impacto**: cliente certificado Nitrox preguntará si puede usar su certificación con nosotros.

---

## 2.9 Upsells y extras

### 36. Catálogo actual de extras ⏳ EN PAUSA

**Respuesta (ronda 3):** todavía no está definido. El bot no debe ofrecer
ningún upsell por ahora.

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

### 40. Qué recordatorios envían hoy 🟡 PARCIAL (canal resuelto, contenido pendiente)

**Respuesta (ronda 1):** "roverd lo manda por mail" — confirma que el
canal es **email**, vía ROVERD (no WhatsApp/SMS), lo que también responde
la pregunta 42. Sigue sin responder qué contenido exacto llevan esos
emails (confirmación de datos, recordatorio pre-actividad, documentos
pendientes, recomendaciones, post-actividad) y su timing (pregunta 41).

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

### 42. Canal de envío ✅ RESUELTO

**Respuesta (ronda 1):** ver pregunta 40 — el canal es email (ROVERD), no
WhatsApp. Falta solo confirmar si hay clientes que rechazan email o algún
límite operativo, pero no bloquea implementación.

Necesitamos confirmar:
- ¿WhatsApp, email o ambos por canal?
- ¿Hay clientes que rechazan WhatsApp y sólo aceptan email (o viceversa)?
- ¿Hay límite legal/operativo de mensajes WhatsApp por día?

**Impacto**: si el bot va a tomar los recordatorios, debe usar el canal correcto.

---

### 43. Conversión de euros en el checkout real (¿DCC del gateway o del banco?) 🔴 NUEVO

Al probar en vivo el checkout de `book.divingplanet.org` (curso Open Water,
693.00 USD) con una tarjeta europea, el propio widget de pago mostró el botón
final como **"Pagar 606.89 EUR"** con un tipo de cambio visible (0.876) en la
pantalla de checkout — es decir, la conversión a euros la está haciendo el
gateway de pago en el momento del checkout (Dynamic Currency Conversion),
no "el banco o la tarjeta del cliente después", como dice hoy la FAQ del bot
(`faqs.json`, id de la pregunta "¿Puedo pagar en euros?"): *"Tu banco o
tarjeta hará la conversión de USD a euros automáticamente al momento del
pago."*

Esto puede no ser exacto: si el gateway ofrece DCC, el tipo de cambio que
aplica es el suyo (normalmente peor que el de la red de la tarjeta/banco), y
puede que el cliente tenga la opción de rechazar la conversión y pagar en USD
directamente (dejando que su propio banco convierta, que suele salir más
barato). No lo hemos confirmado todavía porque no llegamos a completar el
pago real en la prueba.

Necesitamos confirmar con el owner (o probando el flujo completo):
- ¿El checkout de Roverd siempre ofrece DCC a tarjetas no-USD, o depende del país detectado?
- ¿Existe una opción visible en esa pantalla para que el cliente elija pagar en USD en vez de en la moneda convertida?
- ¿El owner es consciente de que el checkout hace esta conversión y con qué tipo de cambio (fijo, tiempo real, con margen)?

**Impacto**: si se confirma que el cliente puede pagar en USD sin DCC, la
FAQ actual induce a error (sugiere que no hay elección) y probablemente
convenga decirle al cliente que busque la opción de pagar en USD para
evitar el margen de conversión del gateway. No tocar `faqs.json` hasta
confirmar esto con el owner — no inventar el comportamiento exacto del
checkout.

---

### 44. Cómo y con qué frecuencia le paga Roverd a Diving Planet 🔴 NUEVO — bloqueante para el diseño de pagos del proyecto de sustitución

Se confirmó (documentación oficial de Stripe, `stripe.com/global` y
`docs.stripe.com/connect/cross-border-payouts`) que **Colombia no es país
soportado por Stripe** ni para cuentas propias ni para cuentas conectadas de
Connect, ni siquiera como receptor de los "cross-border payouts"/Global
Payouts más recientes (en Latinoamérica solo Brasil y México tienen soporte
completo). Diving Planet, como empresa colombiana, **no puede tener su
propia cuenta Stripe**.

Esto, combinado con la FAQ ya existente ("tu pago se registra de inmediato
en ROVERD, pero el equipo concilia manualmente los pagos poco después"),
sugiere fuertemente que **Roverd actúa como Merchant of Record**: el dinero
del cliente entra a la cuenta de Roverd (o su procesador), y le liquida a
Diving Planet por una vía separada — probablemente no en tiempo real, de ahí
la necesidad de conciliar a mano en el Excel `RESERVAS 2026`.

Necesitamos confirmar con el owner:
- ¿Con qué frecuencia recibe Diving Planet el dinero de Roverd (diario, semanal, mensual)?
- ¿Por qué método llega (transferencia SWIFT/wire, un agregador tipo Payoneer/Wise, un partner colombiano, depósito directo)?
- ¿En qué moneda llega a su banco (USD o ya convertido a COP), y si hay alguna comisión o tasa de cambio aplicada en ese paso que hoy no esté cuantificada?
- ¿El owner tiene visibilidad de cuánto se queda Roverd en total (el 10% de comisión + cualquier coste de conversión/liquidación oculto en ese payout)?

**Impacto**: esta respuesta es la plantilla exacta a replicar (o mejorar) en
el diseño de pagos del proyecto de sustitución de Roverd — si el modelo
"Merchant of Record" es inevitable para Colombia (y probablemente para la
mayoría de futuros tenants latinoamericanos fuera de Brasil/México), esta
información nos dice qué tan buena o mala es la solución actual de Roverd
en la práctica, y qué mejorar. Ver `docs/roverd-replacement-plan.md` §1 y
§5 para el análisis técnico completo.

---

## 3. Seguimiento ronda 1 (2026-06-21)

### Listas para implementar ya (✅ resuelto, sin ambigüedad bloqueante)

- **#3** PARCEROS es un producto obsoleto → **eliminar** todas sus referencias de la KB (`discounts.json`, `policies.json`, `faqs.json`) y de cualquier mensaje del bot.
- **#4** Descuento de grupo: la regla 4+/5% queda obsoleta. Nueva regla: 5+ personas = 10%, +10% online = 20% total.
- **#7** Confirmación de reserva: el pago online sube al sistema ROVERD al instante, pero el equipo concilia manualmente los pagos en un Excel después — el bot no debe decir "confirmación instantánea sin revisión".
- **#8 / #9** Pagos: colombianos pagan 50% online (métodos colombianos, incl. Llave) + 50% presencial (tarjeta/efectivo). No colombianos pagan 100% vía URL online (tarjeta) o presencial (tarjeta/efectivo).
- **#11** Cancelación: el bot debe informar la política desde los JSON de KB y mostrar dos botones — contactar staff / volver al menú principal.
- **#15** Fotos/videos: entrega por WhatsApp, propina solo aplica a buceadores certificados.
- **#16** (parcial) Objetos perdidos → siempre escalar a asesor.
- **#17** (parcial) Precio igual para todos los hoteles de Islas del Rosario; Barú se cotiza como salida desde Cartagena (recogida posible, mismo costo).
- **#18 / #21** Paquetes multi-día (5/7/9) solo para certificados; no certificado → se ofrece Open Water en su lugar. No existen paquetes multi-día mixtos.
- **#30** Equipo propio: 5% de descuento (sustituye el monto fijo $33.000 COP/día), solo si el cliente trae el equipo completo.
- **#40 / #42** Recordatorios van por email vía ROVERD, no por WhatsApp/SMS.

### Detalles menores que quedan abiertos pero no bloquean implementar lo de arriba

- #4: ¿aplica a cursos?, ¿grupos mixtos?, ¿automático o requiere aprobación?, ¿tarifa cerrada 6+?
- #9: PayPal no mencionado explícitamente (asumimos que tarjeta internacional cubre extranjeros sin cuenta colombiana) — confirmar si hace falta.
- #11: plazos exactos sin penalización, penalización parcial, no-show (vendrá del texto de política cuando se redacte).
- #16: fotos pendientes/certificados/incidencias (más allá de objetos perdidos).
- #30: en qué actividades aplica el 5% además de buceo certificado.

### Siguen totalmente sin respuesta (⏳)

#1 (fuente oficial de precios), #2 (colombianos — descuento, no medios de pago), #5 (Bubble Makers precio), #6 (servicio privado rango), #10 (moneda/pago fallido), #12 (cambio de fecha), #13 (clima/reembolsos matiz), #14 (alergias matiz), #19 (matriz hoteles prioritarios), #20 (casos especiales logística), #22 (backup instructor privado), #23 (clima por actividad), #24 (cursos interrumpidos por clima), #25 (idiomas staff), #26 (bautismo vs discovery vs OW), #27 (entrega certificación PADI), #28 (combos cursos), #29 (Divemaster duración), #31–35 (tallas, lastres, máscara graduada, equipo niños, Nitrox), #36–39 (extras y promociones), #41 (timing recordatorios).

**Siguiente paso:** con el bloque 🟡 anterior ya resuelto, lo lógico es implementar estos cambios en la KB/bot (sobre todo: borrar PARCEROS, actualizar descuento de grupo y equipo propio, añadir botones de cancelación, matizar mensaje de confirmación de pago) antes de seguir preguntando por el bloque ⏳.

## 4. Seguimiento ronda 3 (2026-06-21)

### Nuevos ✅ resueltos esta ronda

- **#6** Servicio privado: confirmado que se escala siempre sin dar cifra (no cambia nada del comportamiento actual).
- **#10** Moneda: colombianos en COP, extranjeros en USD. Pago fallido: el bot debe pedir reintentar en unos minutos revisando los datos, y si persiste dar botones de escalar/home.
- **#12** Cambio de fecha: mismo patrón que cancelación — informar política desde KB + botones escalar/home.
- **#14** Comida/alergias: menú fijo, sí se permite comida propia.
- **#22** Backup de instructor: sí existe, el bot debe hablar en genérico ("coordinamos instructor disponible") sin nombrar a Andrés.
- **#26** Bautismo = Discover Scuba Diving = minicurso (mismo producto, distinto nombre).

### Quedan en pausa — el owner necesita verificar internamente o decidir (⏳)

- **#1** Fuente oficial de precios — pendiente revisión conjunta `pricing.json` vs `services.json`.
- **#2** Descuento colombianos — política aún no definida.
- **#5** Precio Bubble Makers — aún no definido.
- **#13** Clima/capitanía/reembolsos — puesta en pausa explícitamente por el owner.
- **#19** Matriz de hoteles prioritarios — varía por hotel, requiere que el owner lo revise con su equipo.
- **#20** (parcial) Cliente que pierde la salida — pendiente; resto de sub-casos (tarifas por zona, hoteles fuera del selector, etc.) sin responder.
- **#25** Idiomas del staff — pendiente.
- **#27** Entrega de certificación PADI — pendiente.
- **#28** Combos de cursos/especialidades — pendiente.
- **#29** Divemaster (duración/requisitos) — pendiente.
- **#36** Catálogo de extras — todavía no definido, no ofrecer upsell por ahora.

### Sin tocar todavía (no se han preguntado)

#23 (clima por actividad), #24 (cursos interrumpidos por clima), #31–35 (tallas, lastres, máscara graduada, equipo niños, Nitrox), #37–39 (pago/momento de extras, cuándo ofrecerlos, packs y promociones), #41 (timing exacto de recordatorios).

**Nota:** dado que varias preguntas técnicas/operativas (idiomas, certificación, combos, Divemaster, hoteles, extras) están volviendo como "pendiente", probablemente requieran que el owner consulte con su equipo en vez de responder sobre la marcha. Vale la pena dejarlas para una ronda posterior y priorizar mientras tanto implementar todo lo ya resuelto.

## 5. Seguimiento ronda 4 (2026-07-02)

### Nuevos ✅ resueltos esta ronda (implementados en KB v0.18.2)

- **#4** (complemento) Descuento de grupo: NO aplica a cursos PADI y NO es automático — el grupo debe contactar al equipo.
- **#5** Precio Bubble Makers: $187 USD/persona. `faqs.json`.
- **#13** (parcial) Clima: preferir reprogramar antes de reembolsar; si no es posible → 100% reembolso. `faqs.json` actualizada.
- **#24** (parcial) Curso interrumpido por clima: retoma al día siguiente, cliente paga hotel extra. `faqs.json`.
- **#25** Idiomas staff: español e inglés únicamente. `faqs.json`.
- **#27** Certificación PADI: eCard digital, no existe tarjeta física. `faqs.json`.
- **#28** (parcial) Combos cursos/especialidades: sí, si hay tiempo; contactar por WhatsApp para planificar. `faqs.json`.
- **#33** Máscara graduada: dioptrías 2, 3, 4. `faqs.json`.
- **#34** Equipo para niños: BCD pequeño + botellas pequeñas. `faqs.json`.
- **#35** Nitrox post-certificación: disponible bajo pedido, $10/tanque ($20 para 2 buceos). `faqs.json`.
- También añadido: llegada tarde con lancha ya partida → no hay reembolso (sub-caso de #20). `faqs.json`.

### Siguen pendientes (no respondidas o necesitan más info)

- **#1** Fuente oficial de precios (pricing.json vs services.json) — revisión conjunta pendiente.
- **#2** Descuento colombianos — política aún no definida.
- **#13** (matiz) ¿Cuánto tarda el reembolso? ¿Qué pasa si el clima no cancela oficialmente?
- **#19** Matriz hoteles prioritarios — el owner necesita verificar con su equipo.
- **#20** (resto) Tarifas por zona, hoteles fuera del selector, punto de encuentro alternativo, grupo con hoteles distintos, equipaje.
- **#24** (matiz) ¿Límite de días para alargar curso? ¿Cliente con vuelo fijo? ¿Reembolso parcial si no puede completarse?
- **#28** (matiz) ¿Descuento o pack por varias especialidades juntas?
- **#29** Divemaster (duración, requisitos visibles) — pendiente.
- **#31–32** Tallas extremas, lastres/tanques para biotipos — sin preguntar.
- **#36–39** Catálogo de extras, momento de pago, cuándo ofrecerlos, packs/promociones — sin definir.
- **#40–41** Contenido y timing exacto de recordatorios — canal resuelto (email ROVERD), contenido pendiente.


