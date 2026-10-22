# G10 de control con el redactor (arq-4, 22-oct): fallos por quién escribió el turno

Ronda `2026-10-22-g10-arq1` (redactor + arq-3 + arq-1f, código local): 87,7 % 25/72 sin desfasados. SOLO DIAGNÓSTICO: los bancos de arreglo se escriben con frases nuestras, nunca con las del examen.

Clasificación con `clasifica_g10.py` (el turno que cita el juez y las llamadas de ese turno en las métricas). «redactor->RAG» = el redactor contestó y la respuesta adelantada del RAG también se calculó (casi siempre contesta el redactor).

```
74 fallos: {'RAG': 37, 'redactor->RAG': 20, 'sin RAG (booking)': 6, 'redactor': 5, 'sin RAG (safety)': 5, 'sin RAG (info)': 1}

== redactor->RAG (20)
  - g10-010 global:idioma: El cliente escribió en portugués; la regla exige responder en inglés cuando el cliente usa un idioma distinto a español o inglés, pero la última respu
  - g10-010 edad-minima-minicurso-buceo: El bot dijo que el niño de 7 está por debajo de la edad mínima pero no aclaró explícitamente que el Minicurso de Buceo es desde los 10 años (ni que el
  - g10-058 global:sin-invenciones: El bot asume que la reserva es "desde Cartagena" y da un punto de encuentro horario específico sin que el cliente haya dicho su lugar de salida (Carta
  - g10-058 hora-y-punto-encuentro-cartagena: El bot preguntó el origen y dio el punto y la hora para Cartagena, pero al indicar el punto de encuentro no añadió la aclaración obligatoria «a 5 minu
  - g10-001 recogida-hotel-islas: El bot confirma la recogida en el hotel si tiene acceso marítimo pero no menciona el regreso ni que la recogida/regreso estén incluidos sin cargo adic
  - g10-047 precio-y-que-incluye-fun-dives-o-minicurso: El cliente declaró tener cédula de extranjería (residente), por lo que el bot debía dar el precio solo en COP; en su respuesta mostró tanto USD como C
  - g10-016 que-incluye-minicurso-islas: El bot mencionó piscina, inmersión, instructor y equipo y aludió a la recogida, pero no declaró que el seguro está incluido, no mencionó la clase teór
  - g10-025 hora-recogida-especialidad-islas: Aunque el bot dio la hora (8:00) y dijo que recoge en el hotel si tiene acceso por lancha, no indicó que el punto y la hora exactos para recogidas en 
  - g10-015 hotel-no-incluido-grupo: El cliente indicó su hotel en las islas (Ubuntu) y el bot no aclaró en ningún momento que el alojamiento no está incluido en el precio del paquete y q
  - g10-055 global:sin-invenciones: La referencia indica 'edad mínima 10 años' (desde los 10 años). Decir 'tener más de 10 años' excluye a los que tienen exactamente 10 años y contradice
  - g10-055 no-incluye-fotos-minicurso: El criterio exige dejar claro que en el minicurso no se incluyen ni se realizan fotos/videos; el bot solo dijo que no están incluidas pero afirmó que 
  - g10-002 global:sin-repreguntas: El bot vuelve a preguntar si el hotel tiene acceso por lancha ('Is your hotel accessible by boat?') aunque el cliente ya dijo explícitamente que se ho
  - g10-030 global:idioma: El bot respondió extensamente en portugués aunque la política exige responder en inglés cuando el cliente escribe en portugués.
  - g10-005 no-recogen-hotel-cartagena: El cliente preguntó si hay recogida en el hotel; el bot respondió solo que sí para quienes ya están en las islas pero no aclaró específicamente que de
  - g10-069 confirma-disponibilidad-cursos-islas: El bot confirmó la disponibilidad (con las excepciones correctas) pero no limitó la reserva a la fecha seleccionable en el enlace específico del «Curs
  - g10-069 comparte-link-curso-open-water-islas: El criterio exigía que el bot compartiera el enlace de reserva del Curso Open Water 'ya en las islas', pero el bot no incluyó ningún enlace en su resp
  - g10-014 global:sin-invenciones: El bot presenta información específica para "buceo certificado" (requisitos y horario) aunque el cliente no dijo que la reserva fuera para un plan de 
  - g10-014 hora-y-punto-recogida-en-hotel-islas: El bot dio correctamente la ventana de recogida (9:30–9:45) pero no indicó que la hora exacta y el punto serán confirmados por un asesor ni ofreció pa
  - g10-003 recomienda-minicurso-principiante: Aunque el bot recomendó correctamente el Minicurso y lo explicó brevemente, no cumplió la parte obligatoria de enviar el link de reserva; prometió pas
  - g10-033 que-incluye-snorkel: El bot solo mencionó lancha, equipo y almuerzo, pero omitió incluir otros elementos obligatorios de la ficha (tarifa de entrada al Parque Nacional, se

== sin RAG (booking) (6)
  - g10-004 precio-open-water-isla-cop: El cliente pidió reservar el Curso Open Water ya en las islas, pero el bot no dio el precio en COP del catálogo; en su lugar pidió el número de person
  - g10-015 salida-antes-de-fin-plan: El cliente informó que se van mañana al mediodía pero el bot no avisó que los paquetes de varios días requieren disponibilidad los días completos (act
  - g10-069 explica-curso-open-water-islas: El cliente indicó que está en Ecohotel Las Palmeras (en las islas) pero el bot no explicó el Curso Open Water 'ya en las islas' (duración, precio en U
  - g10-059 sin-certificacion-snorkel: El bot no aclara explícitamente que no se requiere certificación para hacer snorkeling; solo reconoce que el cliente no está certificado pero no afirm
  - g10-003 precio-minicurso-cop-cartagena-corto: El criterio exige dar el precio en COP del Minicurso saliendo desde Cartagena para un cliente colombiano; el bot no proporcionó el precio en COP despu
  - g10-020 global:sin-repreguntas: El bot preguntó por el hotel cuando el cliente ya había indicado claramente que está alojado en el hotel base en las Islas del Rosario, por lo que es 

== RAG (37)
  - g10-050 precio-minicurso-o-pregunta: El criterio exige dar el precio del Minicurso en USD por persona (o preguntar si ya están en las islas o salen desde Cartagena antes de cotizar). El b
  - g10-050 limitacion-tiempo: El criterio pedía advertir que, por salir mañana al mediodía, probablemente no alcancen la actividad porque ésta termina hacia las 12:00–13:00 si ya e
  - g10-036 global:sin-invenciones: El bot afirma que son las 5:54 p.m. y que ya no se puede reservar para mañana, pero la conversación está fechada a las 05:54 (hora de Colombia) — adem
  - g10-036 ofrece-plan-familia-ninos-edad-minima: El bot informó las edades mínimas generales (minicurso desde 10 años, Advanced desde 12) pero no validó explícitamente que los niños del cliente cumpl
  - g10-036 envia-enlace-online-plan-correcto: El cliente pidió el enlace de reserva; el bot no entregó ningún link oficial (ni del plan apropiado) y en su lugar solo anunció el cierre del sistema 
  - g10-045 no-confirma-al-pagar: El bot no aclaró que el pago se registra inmediatamente pero que la reserva solo queda confirmada cuando el equipo concilia manualmente los pagos; esa
  - g10-048 global:sin-invenciones: El bot proporcionó el enlace al formulario médico de CURSO (exoneracion-curso) sin que el cliente haya indicado si la persona con asma hará un curso/m
  - g10-048 asthma-escalado: El bot escaló correctamente y dio el enlace del formulario médico, pero no continuó respondiendo las demás preguntas del cliente (por ejemplo, no prop
  - g10-035 precio-moneda-cop-ambos-planes: El cliente pidió información/seguimiento y el bot no dio los precios en COP solicitados (630.000 COP para buzo certificado y 288.000 COP para acompaña
  - g10-035 ofrece-enlace-online: El criterio pide que el bot comparta el enlace de reserva online para las 2 inmersiones desde Cartagena y explique que la reserva/pago se hacen por la
  - g10-023 no-operan-en-baru: El bot dijo correctamente que no operan en Barú y que operan en las Islas del Rosario, pero no aclaró explícitamente que los clientes alojados en Barú
  - g10-065 recogida-en-hotel-islas: El bot explicó que la recogida está incluida si el hotel tiene acceso marítimo y que a veces se indica el muelle, pero no mencionó que cuando el hotel
  - g10-029 requisitos-y-que-llevar-minicurso: Menciona la teoría online y el formulario médico y qué llevar, pero no indica la edad mínima requerida (10 años) para el minicurso, por lo que incumpl
  - g10-047 global:sin-repreguntas: El bot vuelve a preguntar el punto de salida (Cartagena o islas) cuando el cliente ya indicó claramente que vive en Cartagena, dato del que se deduce 
  - g10-061 inclusiones-todos-los-planes-islas: El bot no enumeró todas las inclusiones obligatorias del plan 'Salidas de Buceo - 2 inmersiones (ya en las islas)' — faltaron 'recogida en el hotel (s
  - g10-021 logistica-tiempo-limitado-no-es-ida-y-vuelta-buceo-mismo-dia: El bot no aclaró la regla del cierre del sistema de reservas a las 4:30 p. m. del día anterior (condición exigida por el criterio) aunque el cliente c
  - g10-031 global:sin-invenciones: El bot afirma que el cliente "ya estás en las islas" sin que el cliente lo hubiera dicho explícitamente (solo mencionó el nombre del hotel).
  - g10-031 precio-referral-already-on-island: El cliente indicó que está en Eco Hotel Las Palmeras (ya en las islas) pero el bot no cotizó en COP el Curso Referido (Open Water) - ya en las islas; 
  - g10-008 explica-refresh-y-pregunta-experiencia: El bot explica correctamente la regla del refresher y las excepciones (500+ inmersiones/Divemaster y PADI ReActivate), pero no pregunta ni valida si a
  - g10-008 da-precio-cop-y-explica-descuento-grupo: El bot no dio los precios en COP por persona para las Salidas de Buceo (2 inmersiones) ni para el refresher/minicurso saliendo desde Cartagena; en vez
  - g10-006 no-confirma-al-pagar: El cliente preguntó si el pago asegura la reserva, pero el bot no aclaró que la reserva no queda confirmada al instante de pagar y que el equipo revis
  - g10-009 no-da-lista-llevar: El bot proporcionó una lista explícita de 'qué llevar' ("Bring a swimsuit, towel, sunscreen, sunglasses, and comfortable clothes."), mientras que el c
  - g10-032 incluye-equipo-y-que-incluye: El bot sí explicó duración, teoría previa, número de inmersiones, requisito de certificación, la necesidad de quedarse una noche y los precios en COP,
  - g10-032 requiere-noche-en-islas: El bot sí explica que se debe quedar al menos una noche y que no se puede volver el mismo día, pero no aclara explícitamente que el alojamiento no est
  - g10-026 global:sin-invenciones: Recomienda el enlace del Minicurso saliendo desde Cartagena en vez del enlace 'Minicurso (ya en las islas)' que corresponde a clientes que ya están en
  - g10-026 explica-como-reservar-online-menciona-link: El bot indicó reservar online y dio enlaces, pero compartió los links para salidas desde Cartagena en lugar de los enlaces 'ya en las islas' requerido
  - g10-068 anticipo-colombianos-explica: El bot menciona solo la opción del anticipo del 50% pero no explica que los colombianos también pueden pagar el 100% online, como exige la política.
  - g10-067 descuento-equipo-propio-explica-politica: El bot mencionó el 5% por traer equipo completo para "recreational diving packages" pero no indicó que el descuento también aplica a cursos PADI, ni d
  - g10-067 alojamiento-no-incluido-explica: El bot dice que el alojamiento no está incluido y que el cliente debe 'arrange accommodation', pero no aclara explícitamente que debe reservarse direc
  - g10-034 comida-no-incluida-islas-explica: El cliente ya está en las islas (Ubuntu) y el refresher/minicurso 'ya en las islas' no incluye almuerzo; el bot afirmó que el almuerzo está incluido, 
  - g10-013 precio-minicurso-cop-cartagena: El bot no dio el precio en COP del Minicurso saliendo desde Cartagena ni detalló las inclusiones (lancha, almuerzo, equipo, seguro, etc.); en lugar de
  - g10-024 precio-buceo-already-on-island-usd: El criterio exige que el bot dé el precio por persona en USD para la modalidad 'ya en las islas' o, al menos, pregunte qué tipo de buceo busca el grup
  - g10-024 acompanante-paga-igual: El cliente preguntó explícitamente si el acompañante paga igual; el bot solo dijo que el precio debe cotizarlo el equipo (no dio el precio de 80 USD o
  - g10-024 proceso-reserva-grupo: No explicó que la reserva se hace por el enlace online; en su respuesta solo indicó que el equipo debe cotizar y ofreció pasar a un asesor, sin inform
  - g10-012 incluye-almuerzo-especialidad-cartagena: El bot confirma que el almuerzo está incluido para salidas desde Cartagena pero no aclara explícitamente que el almuerzo NO se incluye cuando el clien
  - g10-060 global:sin-repreguntas: El cliente ya dijo claramente que necesita refresher y que hace tiempo que no bucea; preguntar si han pasado más de 2 años es una repregunta.
  - g10-028 global:sin-repreguntas: El bot vuelve a preguntar por la duración (3 o 4 días) cuando el cliente ya indicó claramente '3 days' en su primer mensaje.

== sin RAG (info) (1)
  - g10-049 pueden-combinar-buceo-snorkel-misma-lancha: El bot no confirma explícitamente que se puede combinar snorkel y buceo en la misma lancha ni explica que el snorkel se realiza en una zona distinta (

== redactor (5)
  - g10-070 global:idioma: El cliente escribió en portugués, y la política exige responder en inglés cuando el cliente usa portugués; el bot respondió esa vez en portugués en lu
  - g10-064 incluye-nitrox-cartagena: El bot listó los elementos incluidos pero no especificó explícitamente que la especialidad Nitrox saliendo desde Cartagena incluye 2 inmersiones (menc
  - g10-020 global:idioma: El cliente escribió en portugués, por lo que el bot debía responder en inglés; en cambio el bot respondió en portugués («Claro! Aqui está...», «O link
  - g10-020 enlace-snorkel-already-on-island: El cliente pidió el link; el bot lo dio pero con language=en (inglés). El criterio exige ofrecer el enlace en español (language=es), por lo que no cum
  - g10-033 global:sin-repreguntas: El bot vuelve a preguntar por el número de personas pese a que el cliente ya indicó claramente que es para una persona.

== sin RAG (safety) (5)
  - g10-037 cambio-cancelacion-escalado: El bot no explicó que los cambios o cancelaciones de reservas ya hechas los gestiona una persona del equipo, y en vez de pasar directamente con un ase
  - g10-037 acompanante-precio-cartagena-cop: El bot no ofreció el plan de acompañante ni dio el precio por persona saliendo desde Cartagena en COP, ni preguntó desde dónde sale antes de cotizar, 
  - g10-024 confirma-buceo-adaptado: El bot mencionó el programa DIVE TO HEAL pero no confirmó explícitamente que atienden discapacidad motora y auditiva ni que "todos los instructores es
  - g10-063 descuento-grupo-mixto: El cliente indicó explícitamente que el grupo es mixto (colombianos + extranjero) pero el bot no aclaró que en grupos mixtos toda la reserva se paga e
  - g10-063 precio-snorkel-cartagena-grupo: El cliente preguntó si cambia el precio al hacer snorkel y el bot no dio el precio por persona en USD del Tour de Snorkeling desde Cartagena ni aclaró
```
