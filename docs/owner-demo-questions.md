# Set de preguntas para demo en vivo al owner

Este documento contiene preguntas en lenguaje natural ordenadas por categoría, seleccionadas porque:

1. Están **cubiertas por la base de conocimiento** (FAQs, policies, services, conversations) — el bot tiene material para responder.
2. Están **validadas por tests** o usan tópicos detectados por el clasificador.
3. **Demuestran variedad** de capacidades: comprensión, contexto, multi-idioma, guardarraíles.

Pensado para usarse después de mostrar el árbol guiado: *"y además de los botones, le puedes preguntar lo que quieras directamente"*.

---

## Cómo usarlo en vivo

- **No leerlas en orden mecánico**. Mezcla. Empieza por una de "Logística básica" para construir confianza, luego salta de categoría.
- **Después de cada respuesta**, hacer una pausa: *"Fíjate que no se inventa el precio, lo trae de nuestra ficha de servicio"*.
- **Reserva un caso de "guardarraíl" hacia el final** (médico o link roto) para mostrar cuándo deriva a humano. Es el momento que más tranquiliza al owner.
- **Termina con una pregunta en inglés** (multi-idioma) para cerrar con efecto.

Tiempo estimado: 8-10 minutos de demo de texto libre, eligiendo ~10-12 preguntas de las 50+ disponibles.

---

## 1. Logística básica — *empezar aquí, alta confianza*

> *Estas las responde leyendo de FAQs y policies. Las uso para abrir.*

- ¿A qué hora es la salida?
- ¿Dónde están ubicados?
- ¿Cuál es el punto de encuentro?
- ¿Salen todos los días?
- ¿Qué días no operan?
- ¿Cuáles son los horarios de operación?
- ¿Cuál es la temporada alta?
- ¿Hasta qué hora puedo reservar para mañana?

---

## 2. Precios y descuentos — *muestra que NO inventa*

> *Aquí el bot va a `services.json` y `pricing.json`. Si el cliente es colombiano, baja precio. Si no, USD.*

- ¿Cuánto cuesta el minicurso de buceo?
- ¿Cuánto cuesta el plan de 2 buceos desde Cartagena?
- ¿Cuál es el precio del snorkel?
- ¿Cuánto es el paquete de 5 buceos?
- ¿Tienen descuento para colombianos?
- ¿Hay descuento si reservo por la web?
- ¿Hay precio para grupos?

**Truco para demo**: pregunta primero "¿cuánto cuesta el plan de 2 buceos?" sin contexto. Después di al bot "soy colombiano" y vuelve a preguntar. Verás cómo cambia la moneda. (Esto requiere que el `extra_context` esté seteado — si estás probando texto libre puro, igual responde sensatamente.)

---

## 3. Cursos y certificaciones PADI — *amplia cobertura, demuestra profundidad*

- ¿Cuál es la diferencia entre Scuba Diver y Open Water Diver?
- ¿Qué es Advanced Open Water?
- ¿Qué es Rescue Diver y por qué es importante?
- ¿Qué es el curso Divemaster?
- ¿Qué es Nitrox y para quién sirve?
- ¿Cómo elegir entre Open Water, especialidades y Rescue?
- ¿Qué es buceo autónomo o scuba diving?
- ¿Cómo es el curso Open Water desde Cartagena?

---

## 4. Casos especiales del cliente — *contexto que el bot maneja bien*

- Hace años no buceo, ¿necesito refresher?
- Tengo mi carnet pero hace mucho no buceo, ¿qué hago?
- Perdí mi carnet de buceo, ¿puedo bucear igual?
- Es mi primera vez buceando, ¿qué recomiendan?
- ¿Necesito saber nadar para bucear?
- ¿Cuál es la edad mínima para bucear?
- ¿Puedo volar después de bucear?

---

## 5. Grupos mixtos y familias — *muestra inteligencia conversacional*

> *Estas activan detección de "grupos con varias personas". El bot describe opciones de forma neutra y deriva — no se inventa roles "para ti / para él".*

- ¿Pueden venir grupos con diferentes niveles (certificados, principiantes y snorkel) en el mismo tour?
- Somos 4 amigos, unos buzos certificados y otros nunca han buceado, ¿qué nos recomiendan?
- Quiero ir con mi pareja, ella quiere snorkel y yo buceo, ¿se puede?
- Voy con mis hijos pequeños, ¿pueden hacer algo en el agua?

---

## 6. Logística de hoteles e islas — *muestra el contexto enriquecido*

> *El bot sabe que los Rosario tienen acceso marítimo y que se recoge a clientes ya en islas.*

- Si ya estoy en las islas, ¿me recogen?
- ¿A qué hoteles de las islas pueden recogerme?
- Si ya estoy en las islas, ¿hay algún cargo extra por la recogida?
- ¿Tienen opciones de alojamiento en las Islas del Rosario?
- ¿Los cursos de 2 días requieren pernoctar en las islas?
- ¿Barú es lo mismo que las Islas del Rosario?

---

## 7. Qué incluye / no incluye — *guarda contra el "y la comida?"*

- ¿Qué incluye el tour?
- ¿Qué no está incluido?
- ¿Qué comida incluye el tour?
- Soy vegetariano, ¿pueden atenderme?
- ¿Tengo alergia alimentaria, qué pasa?
- ¿Hacen fotos o videos durante la actividad?

---

## 8. Equipo y aspectos técnicos — *demuestra conocimiento de dominio*

- ¿Qué equipo básico se usa para bucear?
- ¿Qué debo llevar (toalla, bloqueador, etc.)?
- ¿Para qué sirven el BCD, regulador, botella y ordenador de buceo?
- ¿Cómo se compensan los oídos?
- ¿Puedo bucear resfriado?
- ¿Qué profundidad máxima se bucea normalmente?
- ¿Por qué consumo tanto aire al bucear?

---

## 9. Vida marina e Islas del Rosario — *para clientes curiosos*

- ¿Qué vida marina se ve en las Islas del Rosario?
- ¿Qué arrecifes y corales hay?
- ¿Por qué elegir las Islas del Rosario para bucear?
- ¿Cómo son las condiciones de buceo?
- ¿Cuál es la mejor temporada para bucear allí?
- ¿Es buen destino para principiantes?
- ¿Es bueno para fotografía submarina?
- ¿Los tiburones, peces o erizos son peligrosos?

---

## 10. Aspectos emocionales del principiante — *muestra el tono cercano*

> *Esta categoría es oro para demo: muestra que el bot es empático sin ser robot.*

- Me da miedo respirar bajo el agua, ¿es normal?
- Tengo ansiedad bajo el agua, ¿qué hago?
- ¿Qué se siente estar bajo el agua?
- Soy principiante y me da pánico, ¿pueden ayudarme?
- ¿El buceo es seguro?
- ¿Qué pasa si me entra agua en la máscara?
- ¿Qué pasa si me quedo sin aire?

---

## 11. Servicios especiales — *cobertura adicional*

- ¿Ofrecen servicios privados o grupos cerrados?
- ¿Qué es DIVE TO HEAL? *(programa de buceo adaptado — info pública)*
- ¿Qué es el buceo adaptado?
- ¿Personas con discapacidad pueden bucear con ustedes?
- ¿Los paquetes de 5, 7 o 9 buceos requieren certificación?
- ¿Qué pasa si no quiero hacer el buceo nocturno incluido?

---

## 12. **Guardarraíles** — *el momento crítico de la demo*

> *Estas son las preguntas que el bot **NO debe responder solo**. Demuestran que sabe cuándo callarse y pasar al equipo. Es lo que más tranquiliza al owner.*

### Médico (el bot escala SIEMPRE — excepto DIVE TO HEAL)

- Tengo asma, ¿puedo bucear?
- Tengo problemas de corazón, ¿es seguro?
- Estoy embarazada, ¿puedo bucear?
- Tomo medicación para la tensión, ¿hay problema?

### Clima en tiempo real (escala — el bot no sabe el clima de mañana)

- ¿Mañana va a llover? ¿podré bucear?
- ¿Cómo está el mar hoy?
- ¿Hay viento previsto este fin de semana?

### Disponibilidad real (escala — el bot no tiene calendario)

- ¿Hay cupos para mañana a las 8?
- ¿Está disponible Andrés para el sábado?

### Quejas o problemas (escala con prioridad)

- El link de reserva no me funciona
- El formulario de exoneración no abre
- Pagué y no recibí confirmación

### PII (el bot **bloquea** y no procesa)

- Mi cédula es 1234567890, ¿puedo reservar?
- Mi tarjeta es XXXX-XXXX-XXXX-XXXX, ¿pueden cobrar?

> *Después de mostrar estos, comenta: "fíjate que ni siquiera procesa el dato sensible — el cliente está protegido y el equipo se entera con todo el contexto."*

---

## 13. Cancelaciones y políticas — *el bot da la regla general y deriva*

- ¿Qué pasa si se cancela por mal clima?
- ¿Hay reembolso si cancelo?
- ¿Puedo mover la fecha?
- ¿Cuál es la política de cancelación?

---

## 14. Multi-idioma (inglés) — *cierre con efecto*

> *Pregunta lo mismo en inglés para mostrar que TODO el bot funciona bilingüe sin esfuerzo extra.*

- What time is the departure?
- How much does the mini-course cost?
- I'm a certified diver, do you have plans for me?
- I haven't dived in years, do I need a refresher?
- What's the difference between Open Water and Advanced?
- Can you pick me up if I'm already on the islands?
- I have asthma, can I dive? *(escala igual que en español)*
- Where is the meeting point?

---

## Set recomendado de **10 preguntas** para una demo de 8 minutos

Si solo tienes tiempo para 10, esta es la selección con mejor mezcla:

| # | Pregunta | Qué muestra |
|---|---|---|
| 1 | ¿A qué hora es la salida? | Logística básica, respuesta corta |
| 2 | ¿Cuánto cuesta el plan de 2 buceos desde Cartagena? | Precio real desde la KB |
| 3 | ¿Cuál es la diferencia entre Open Water y Advanced? | Conocimiento técnico PADI |
| 4 | Hace 5 años no buceo, ¿qué hago? | Caso especial, ofrece refresher |
| 5 | Somos 3 amigos: 1 certificado, 2 principiantes — ¿podemos ir juntos? | Grupo mixto, sin asignar roles |
| 6 | Si ya estoy en Isla Grande, ¿me recogen? | Logística con contexto isla |
| 7 | ¿Qué vida marina se ve en los Rosario? | Sales pitch, info del destino |
| 8 | Tengo asma, ¿puedo bucear? | **Guardarraíl médico — escala** |
| 9 | El link de reserva no me funciona | **Guardarraíl link roto — escala con prioridad** |
| 10 | What time is the departure? | **Multi-idioma — cierre** |

---

## Lo que NO te recomiendo preguntar en vivo

Estas preguntas el bot las maneja peor hoy (sin las fases pendientes del plan RAG):

- **Follow-ups muy cortos sin contexto**: "¿y los niños?", "¿y el precio?", "¿y los lunes?" — el query rewriting (Fase 1.3) está pendiente, hoy puede fallar.
- **Nombres de hotel muy específicos**: "¿Pao Pao tiene recogida?", "¿Coralina tiene muelle?" — el hybrid search (Fase 1.1) está pendiente, el embedding puro a veces no coincide.
- **Preguntas sobre disponibilidad concreta**: "¿hay cupos para el 15?" — escala correctamente pero parece "se rinde".
- **Precios exactos en pesos colombianos sin contexto**: el bot prefiere USD si no sabe que es colombiano.
- **Procesos de pago detallados**: "¿cómo es el pago paso a paso?" — escala correctamente pero el cliente puede esperar una respuesta directa.

Si Andrés pregunta alguna de estas en vivo, está bien — la escalación o el "te paso con un asesor" es el comportamiento esperado y demuestra el guardarraíl.

---

## Apuntes finales para el demo

- Ten **abierto el inspector de Chatwoot** con la nota interna del lead a un lado. Cuando una pregunta escale, enseña en vivo la nota auto-generada con todo el contexto.
- Si el bot tarda más de lo normal en responder, di: *"está consultando la base de conocimiento — son alrededor de 450 documentos curados"*. Convierte un bug en feature.
- Si el bot responde algo que no es perfecto, di: *"ese es exactamente el caso que estamos puliendo en las próximas iteraciones — por eso documentamos las preguntas pendientes con el owner"*. Conecta al doc de 42 preguntas.
- Termina enseñando el `brand_tone.json`: *"si quieres que sea más formal o más cercano, lo cambias aquí en JSON, sin tocar código. Andrés/Gadea pueden editarlo".*
