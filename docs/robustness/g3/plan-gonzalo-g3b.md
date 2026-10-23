# G3b · guion de Gonzalo (islas y hoteles, clima, buceo adaptado, inglés y portugués)

Cada charla: 4-8 turnos, adaptándose a lo que conteste el bot como un cliente real. Apuntar cada fallo con el turno,
la zona (flujo/extractor = Álvaro; RAG/datos/redactor = Gadea) y si se reproduce en banco ×3.

1. **Hotel en las islas (Majagua).** «Hola, estamos en el hotel San Pedro de Majagua del 3 al 6 de noviembre, somos
   dos, uno certificado y otra sin experiencia». Comprobar: origen islas, recogida 9:30-9:45, precios de islas, sin
   almuerzo, minicurso y buceo en la misma salida, enlaces de islas.
2. **Hotel de la zona que no es base (Rosario de Mar).** Recogida si hay acceso marítimo, precio de islas, sin repetir
   el origen.
3. **Barú / Playa Blanca.** «Nos quedamos en Barú, ¿nos recogen?» → no; sale de Cartagena (Bodeguita 8:00); no repregunta.
4. **Clima general, luego concreto.** «¿Qué pasa si hace mal tiempo?» (política, sin pase) → «¿y el sábado que viene,
   cómo pinta?» (pase). Después «ok, quiero reservar el snorkel» (el flujo sigue tras el pase).
5. **Buceo adaptado (DIVE TO HEAL).** Persona en silla de ruedas que quiere bucear; pregunta también el precio y el
   horario. Comprobar: programa, asesor, y que lo demás se contesta (arq-1l).
6. **Inglés de principio a fin.** Pareja de EE. UU., fun dives + snorkel, «how do I pay?», «is the booking confirmed
   right away?».
7. **Portugués.** «Olá, somos do Brasil, queremos fazer mergulho de batismo, quanto custa?» → idioma (se contesta en
   inglés o español según la regla), moneda USD, sin «null».
8. **Cambio de idioma a mitad.** Empieza en español y pide «can you write in English?».
