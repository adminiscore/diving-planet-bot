# Preguntas para el owner

Lista de dudas que necesitamos resolver para terminar de afinar el árbol del bot. Cada respuesta puede eliminar una rama de escalación o permitir mostrar precios concretos en el chat.

> ℹ️ **Estado: junio 2026 — grupos mixtos rediseñados como carrito.** Las preguntas 1, 2 y 4 quedan ahora cubiertas por el flujo de carrito (el cliente añade actividades una a una y el bot calcula `qty × precio_individual` automáticamente). Las preguntas 3, 5, 6 y 7 siguen pendientes y bloquean otras mejoras.

## Grupos mixtos (Buceo + Snorkel, Certificados + Principiantes)

### 1. Precio mixto

¿El precio total de un grupo mixto es **simplemente la suma de los precios individuales por persona**, o hay algún **descuento por grupo** cuando hay X personas o más?

- Si hay descuento → ¿desde qué número de personas se aplica y cuánto es?
- Si no hay descuento → confirmar para mostrarlo así en el resumen del bot.

**Impacto**: el bot ahora muestra `qty × precio_individual`. Si hay descuento, hay que cambiar la fórmula.

---

### 2. Grupos grandes (6+ personas)

¿Hay alguna política especial para grupos de 6 o más personas?

- ¿Se ofrece automáticamente **lancha privada**?
- ¿Hay **precio de grupo cerrado**?
- ¿Existe un **cupo máximo** por tour (capacidad de lancha)?

**Impacto**: el bot ahora marca `grupo_grande=True` y lo nota en el resumen y en la escalación, sin cambiar el precio.

---

### 3. Certificados en grupo mixto: ¿paquetes 5/7/9 buceos?

En un grupo mixto **certificados + principiantes**, ¿los certificados pueden hacer un paquete de 5, 7 o 9 buceos (varios días) **mientras los principiantes hacen minicurso de 1 día**?

- Si sí: ¿qué pasa logísticamente? (¿los principiantes se quedan en la isla esperando? ¿vuelven a Cartagena?)
- Si no: confirmar que el subgrupo certificado queda limitado a 2 buceos / 1 día cuando es mixto.

**Impacto**: el bot ahora **escala automáticamente** cuando se elige paquete multi-día en mixto. Si se resuelve esta duda podríamos cotizar directamente.

---

### 4. Reservas mixtas online (ROVERD)

¿El sistema ROVERD acepta reservas de **grupos mixtos** (varias actividades en el mismo booking), o siempre hay que gestionarlas **manualmente por WhatsApp**?

**Impacto**: si ROVERD acepta mixto, podemos mostrar el link de reserva al final del flujo. Si no, dejar siempre escalación.

---

### 5. Precio Bubble Makers (8-10 años)

¿Cuál es el **precio de Bubble Makers** (programa para niños de 8 a 10 años)?

- ¿Mismo precio que minicurso?
- ¿Precio especial menor por ser sólo piscina / aguas poco profundas?
- ¿Distinto si va desde Cartagena vs. ya en isla?

**Impacto**: el bot ahora escala cuando hay menores 8-10. Con el precio podríamos incluirlos en el cálculo del resumen.

---

### 6. Servicio privado: rangos de precio

¿Tenéis un **rango de precios indicativo** para servicio privado (lancha exclusiva)? Por ejemplo:

- Privado para 2 personas (2 buceos / 1 día) → desde U$X
- Privado para grupo de 6+ → desde U$X

**Impacto**: el bot ahora ofrece "Cotizar lancha privada" pero sólo escala. Con un rango aproximado podría decir "desde U$X, el asesor confirma según fechas".

---

### 7. Multi-día mixto: logística snorkel

Si un grupo elige multi-día (cert hace paquete 5/7/9) **y también hay snorkelers**:

- ¿Los snorkelers se quedan en la isla todos los días?
- ¿Pueden hacer snorkel cada día o sólo el primero?
- ¿Cómo se cotiza el alojamiento para snorkelers?

**Impacto**: actualmente escalamos. Con esta info podríamos preguntar la duración en el árbol y proponer alojamiento.

---

## Otras dudas pendientes (no relacionadas con grupos mixtos)

### 8. Formulario de exoneración para snorkel

En `conversations.json` aparece "Se solicita formulario de exoneración para actividad en superficie" pero **no tenemos URL** documentada para snorkel.

Las dos URLs que sí tenemos hardcoded:
- Buzos certificados: `https://form.jotform.com/divingplanetcartagena/exoneracion-buzo-en-espanol`
- Cursos / minicurso: `https://form.jotform.com/divingplanetcartagena/exoneracion-curso-en-espanol`

Preguntas:
- ¿Existe un formulario específico de superficie/snorkel? ¿Cuál es la URL?
- ¿Se envía por email automáticamente al reservar, o lo enlazamos en el chat?
- Si no hay form específico, ¿usamos el de "curso" para snorkel también?

**Impacto**: ahora el bot muestra una nota indicando que "el asesor envía el formulario por correo" para snorkel. Si nos dan la URL podemos enlazarla directamente.

---

### 9. Política de cancelación y cambios

Texto actual en `policies.json`:
> "Al reservar aceptas nuestros terminos y condiciones, politica de cancelacion y tratamiento de datos personales. Ver: https://divingplanet.org/terminos-y-condiciones/"

Necesitamos saber:

- ¿Plazo para cancelar sin penalización?
- ¿Se puede cambiar la fecha? ¿hasta cuándo?
- ¿Qué pasa si cancela el cliente vs. si cancela Diving Planet por clima?
- ¿Hay reembolso parcial / crédito / no reembolso?

**Impacto**: el bot deriva todas las preguntas de cancelación a la URL genérica. Con un resumen claro podríamos responder directamente.

---

### 10. Programa de accesibilidad (DIVE TO HEAL)

El material de Diving Planet menciona que "parte del pago apoya la restauración de corales y el programa DIVE TO HEAL para personas con discapacidad."

Necesitamos saber:
- ¿El programa DIVE TO HEAL está disponible como servicio de reserva directo, o es solo un programa de RSC/donación?
- ¿Hay adapaciones especiales para personas con movilidad reducida u otras discapacidades en los tours?
- ¿Tiene precio especial o procedimiento de reserva distinto?

**Impacto**: el bot no contempla actualmente este perfil. Si hay un servicio activo, lo añadimos al flujo.

---

## Formato de respuesta sugerido

Por cada pregunta, basta con responder con una frase o dos. Si una pregunta requiere matices según temporada o contexto, indícalo explícitamente y armamos el árbol con esa variable.
