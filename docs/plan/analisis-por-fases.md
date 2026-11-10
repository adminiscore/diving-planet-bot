# Por qué nos cuesta tanto el bot: análisis por fases

Nov 6, 2026 · @Someone

**No nos cuesta por una pieza mala, sino por cuatro cosas que se suman: reglas del negocio sin un dueño en el código, código que estropea respuestas correctas, una lectura que cambia entre vueltas y una vara que no se parece a los clientes reales y nos señala mal las prioridades.**

- **Dónde nacen los graves:** en unos 40 de los 67 del panel pesa la vara: reglas decididas después de la 0.61, guiones que no reaccionan y fricción juzgada como grave. De los limpios (de 26 a 31, según dos lecturas independientes), más de la mitad son de plan, importe y moneda, casi todos fallos deterministas del código o de la lectura. Ninguno nace en la búsqueda del RAG.
- **Por qué a veces sí y otras no:** el grueso es sistemático: 39 de los 67 son de 13 clientes que fallan en las tres vueltas. Encima hay tres azares: la lectura (Haiku y los umbrales de Jev), la redacción de Luna, que no repite ni con el prompt idéntico, y el juez, que con las mismas conversaciones cambia el veredicto de 5 de cada 40 clientes.
- **Dónde cargamos demasiado:** unos 35.000 tokens leídos por turno, 83 campos de estado y un código que cambia el texto del escritor en el 68 % de sus turnos. Estorba, pero por sí solo no explica los graves.
- **Si hemos parcheado:** sí. Son 86 commits `fix` frente a 9 `refactor`, y en una semana hemos devuelto 1.631 de las 1.858 líneas simplificadas.
- **Si la arquitectura es correcta:** la idea sí, pero el escritor recibe lo de antes del mensaje. Empieza después de leer en el 94 % de los turnos, pero su pregunta se fija antes de leer y el código la cambia en 123 de 180 cierres. Lo demás falla dentro de cada etapa. Y la línea base del 10-nov, Luna sola con toda la base y sin nuestras piezas, saca lo mismo que el bot en graves (10,7 frente a 10,3 de 40), con respuestas más cortas y una llamada por turno en vez de cuatro: hay que decidir con el equipo qué aportan las piezas.
- **Si medimos bien:** no. Los clientes reales escriben 31 caracteres de mediana y el panel 154. Un tercio de los reales ya ha reservado y el 11 % son agencias, y el panel casi no los tiene. La persona contesta en 119 caracteres y el bot en 703, y el juez no lo mide.

**Recomiendo no seguir parcheando ni rehacer el bot, sino seguir el «Plan Gadea».** Primero la vara y lo ya escrito (grupos, tercera pregunta y pase); después, los fallos deterministas de plan e importe, lo que recibe el escritor, lo que depende de leer, el momento de reservar, horas y fechas y las reglas que faltan. Lo que debes decidir, incluidas unas dudas de negocio, está en «Lo que decides tú».

## Fase 1: cuánto carga un turno

**Cada turno lee unos 35.000 tokens para escribir unos 134, y en el 68 % de sus turnos el código corrige después al escritor.** No hay una pieza dominante: el extractor es el 37 % de lo leído, el escritor el 31 % y Jev el 27 %.

Medido en 942 turnos del panel (0.59 y 0.61, tres vueltas de cada una).

| Pieza | Trabajo | Llamadas por turno | Lee por llamada (tokens) | Escribe (tokens) | Tiempo mediano |
| --- | --- | --- | --- | --- | --- |
| Jev | Responde 63 preguntas sobre el mensaje | 1,00 | 9.423 | 1.324 | 0,31 s |
| Extractor (Haiku) | Rellena hasta 20 campos | 1,40 | 9.870 | 276 | 1,42 s |
| Lector de grupo | Reparte actividades entre personas | 0,51 | 1.573 | 132 | 1,11 s |
| Escritor (Luna) | Redacta, y también decide | 0,93 | 11.533 | 134 | 2,17 s |
| Notas | Resume lo pendiente | 0,26 | 1.137 | 39 | 0,59 s |

**Dónde se acumula el peso:**

- **Prompts:** el del escritor tiene 15.861 caracteres, 47 líneas de «nunca» en `prompts/info.py` y 12.939 caracteres de hechos del catálogo. `extractor_turno.py` tiene 989 líneas.
- **Estado:** `ConversationState` tiene 83 campos. Es lo que recuerdan todas las piezas.
- **Respuesta final:** de 858 respuestas con escritor, solo 136 (16 %) salen tal cual. Otras 142 añaden texto alrededor y 580 (68 %) cambian lo que él escribió. El propio compositor documenta que la respuesta se escribe en unos 26 sitios y se le pegan trozos en unos 27.
- **Código:** 94 ficheros, 27.145 líneas y 2.935 condiciones en la 0.61. Los ficheros mayores son `conversational_core` (1.420 líneas), `jev_router` (1.395) y `nucleo/extractor` (1.334).

Esta carga estorba, pero no marca dónde están los graves. El código quita preguntas en el 46 % de los turnos, tengan grave o no, e importes en el 27 % de los turnos con grave frente al 21 % del total. Dónde falla se ve en la Fase 3.

## Fase 2: por qué a veces sí y otras no

**El mismo cliente con el mismo código no sale igual dos veces, pero el grueso de los graves es sistemático.** Cerca del 40 % de los clientes saca grave solo en algunas vueltas, y por eso un arreglo probado una vez parece bueno y luego «vuelve». Aun así, 39 de los 67 graves vienen de los 13 clientes que fallan en las tres vueltas, y esos se prueban sin IA.

&#91;embedded content: Panel de 40 clientes · 0.59 y 0.61, 3 vueltas de cada una · 314 turnos. La tarjeta y los enlaces coinciden también cuando no hay ninguno, así que esas dos barras salen infladas.\]

| Clientes, de 40 | 0.59 | 0.61 |
| --- | --- | --- |
| Grave en las 3 vueltas | 9 | 13 |
| Grave en algunas vueltas | 16 | 17 |
| Sin grave en ninguna | 15 | 10 |

La 0.59 y la 0.61 usan referencias distintas, así que esta tabla mide lo inestable que es el resultado, no si hemos mejorado.

**Dónde entra el azar, pieza a pieza:**

- **Jev es estable.** En el primer turno, con el mismo mensaje, cambió 1 señal de 1.210 comparadas. La traza solo guarda unas 15 de sus 63 respuestas, así que es una muestra. Estable no quiere decir que acierte: eso no se ha comprobado con mensajes reales.
- **La lectura no lo es.** Con el mismo primer mensaje, el estado del primer turno no sale igual en las tres vueltas en 27 de 80 casos (los 40 clientes en la 0.59 y en la 0.61), sobre todo por Haiku y a veces porque Jev cruza un umbral. Después, dos vueltas con el mismo estado se separan en 1 de cada 8 turnos, coincida o no el texto anterior del bot.
- **Luna no repite.** Con el prompt idéntico y temperatura 0 salen 4 o 5 textos distintos de 5, y `seed` apenas cambia eso. El comentario de `rag_agent.py` que da la redacción por estable no se cumple con este modelo. Además, en 19 de 428 turnos (4 %) no escribe Luna sino DeepSeek Flash, su respaldo cuando tarda, y 5 de esos 19 salen con grave (26 %, frente al 15 % con Luna). Son pocos para afirmar más, pero es otra fuente de azar.
- **La búsqueda es estable.** Con el mismo mensaje trae casi los mismos documentos (99,6 %); solo cambia el orden.
- **El juez duda.** Juzgando dos veces la misma vuelta con la misma referencia salen 20 y 23 clientes con grave, y 5 de 40 cambian de veredicto. Además, la misma conducta con otras palabras puede cambiar de veredicto. Lo detallo en «Lo que falla en nuestra vara».

**El estado decide casi todo lo que cambia la reserva:**

| Turnos que coinciden, de 157 en la 0.61 | Con el mismo estado (90) | Con distinto estado (67) |
| --- | --- | --- |
| Misma tarjeta | 90 | 55 |
| Mismos enlaces | 86 | 58 |
| Mismos importes | 75 | 36 |

El veredicto también lo nota. Si el estado se separa, cambia en el 39 % de los pares de vueltas; si no, en el 19 %, que ya es redacción y juez.

No todos los campos pesan igual. En el último turno, 19 de 40 clientes tienen distinto entre vueltas algún dato de los que usan las tablas: días 9, duración 7, actividad 4, origen 3, reparto 3 y certificado 2. Que el grupo sea de 5 o más no varía en ninguno.

**El caso de los belgas no «vuelve»: nunca se fue.** `s04i-belgas` pasa 2 y 3 de 5 en la misma versión. Probándolo una sola vez, pasar era casi tirar una moneda.

## Fase 3: dónde nace cada grave

**Con la vara de hoy, la mayoría de los graves nace en reglas que faltan o están repartidas; quitando lo que pone la vara, mandan plan, importe y moneda.** La lectura y el código que estropea respuestas vienen después. El escritor y el contexto pesan menos.

&#91;embedded content: Los mismos 67 graves en tres clasificaciones: propia, una a ciegas y una crítica. Una causa principal por grave.\]

**Qué pone la vara.** Los revisaron dos lectores por separado, con el turno y la razón del juez de cada uno, y coinciden en el 85 % de los graves (kappa 0,69). 15 existen solo por reglas decididas después de la 0.61, o 35 si la tercera pregunta se cuenta aquí y no como guion (en 3 el juez leía mal «next Friday» y solo queda la regla del grupo), de 16 a 18 dependen de un guion que no contesta lo que se le pregunta, 4 son fricción juzgada como grave y 1 es dudoso. Quedan entre 26 y 31 limpios: 26 en que coinciden las dos lecturas y 5 en que una duda. Además, 46 de los 67 son de clientes ciegos.

| Bloque del plan que lo cubre | Graves | Clientes | Limpios |
| --- | --- | --- | --- |
| 0,5. Lo ya escrito | 33 | 14 | 2 |
| 2a y 2b. Plan, importe y moneda | 17 | 8 | De 14 a 21 |
| 4. El momento de reservar | 8 | 5 | De 2 a 5 |
| 1. Lo que recibe el escritor | 7 | 5 | De 0 a 4 |
| 3. Horas y fechas | 2 | 2 | 1 |

Cada grave cuenta en su bloque principal, aunque muchos necesitan además otro. Los limpios son los 26 en que coinciden las dos lecturas, con lo que dice cada una sobre el bloque. Las familias que siguen son la clasificación anterior, con la vara de hoy.

**Decisión (de 26 a 39).** Son tres familias sencillas, y buena parte es vara:

- **Grupo de 5 o más (unos 15) y 5 % por equipo propio (3).** Se decidieron después de medir y la 0.61 no los tenía: 15 graves existen solo por eso. La regla de grupos es fácil de aplicar, porque el estado trae el grupo en 16 de 19 casos y ese dato no varía. La del equipo propio necesita además leerlo, y ni Jev, ni el extractor, ni el estado lo recogen. Con clientes reales, el grupo de 5 o más es raro: 2 de 75.
- **Tercera pregunta (22; 17 como causa principal).** El freno se apaga justo cuando el cliente pide reservar (`compositor.py:143`) y no ve las preguntas que hacen otras piezas, como en `visto-6927`. Que salga cuando no hay más que decir casi no pasa: solo con menos de 5 palabras. 18 de los 22 son de clientes ciegos: la infla el panel, como explico abajo.
- **Sin salida (1).** `visto-6899` pide un horario que no es el de siempre y termina sin que nadie le ofrezca un asesor. La base dice que un ajuste de horario lo revisa un asesor, pero ninguna regla del código lo aplica.

**Lectura (de 12 a 17).** Regex, Jev, Haiku y el lector de grupo leen el mismo mensaje, y quién manda se decide campo a campo. En `visto-6929`, una regex lee «el paquete de 5 inmersiones no es lo que le pedí» como 5 inmersiones, en las 3 vueltas. Sale la tarjeta de ese paquete, aunque el escritor daba bien los 630.000 COP. También fallan familias mixtas y el reparto por persona.

**Composición (de 7 a 10).** Son fallos deterministas del código:

- **Cifras que casan con más de un plan.** El código deduce qué plan cotiza comparando las cifras del texto con el catálogo, y 16 cifras sirven para más de un plan. El 204 es a la vez el minicurso y el paquete de 4 desde las islas, lo que apunta a por qué `visto-6941` recibe un paquete que no pidió.
- **Frases enteras fuera.** Un filtro borra la frase que lleve un importe, aunque diga algo más (`redactor_hechos.py:217`). En `visto-6941` se va el precio correcto del refresher.
- **Párrafos enteros fuera.** Otro tira el último párrafo si lleva un «?», aunque contenga la respuesta; se lleva la buena en 3 graves (`origen_precio.py:425`).

**Escritor (de 6 a 8).** Falla sobre todo cuando le dejamos hacer cuentas o concluir: horas antes de volar y fechas (`visto-6942`, `visto-6914`), o un precio que no recibió en ese turno. Con los mismos hechos, otra vuelta lo dice bien.

**Contexto (de 5 a 9).** Que el Rescue no se ofrece desde las islas está en `pricing.json`, pero ningún código lee ese campo (`visto-6916`). Y a veces un plan recibe la lista de inclusiones de otro.

**Tus tres sospechosos:**

| Sospechoso | Qué dicen los datos |
| --- | --- |
| RAG | Ninguno de los 67 graves nace en la búsqueda, y es estable. De los 21 graves que dependen de un dato, en 8 trajo el documento; en los otros 13 el dato llegaba por el código, no estaba en la base o lo había dicho el cliente antes (estudio de abajo). Ojo con el nombre: en el código y en las métricas, `rag_escritor` es Luna escribiendo y `rag_respaldo` es DeepSeek Flash cuando Luna falla. La búsqueda de documentos es la llamada `embedding`, y lo que trae se guarda en `rag_docs`. |
| Escritor | Es causa principal en 6 a 8 de 67. Sí es una fuente de azar, porque no repite ni con el prompt idéntico. |
| Lector | Jev es estable. Haiku y las regex no, y son la segunda causa de graves. |

**La causa común es que cada decisión no tiene un solo dueño.** Coincide con el análisis de Álvaro: el plan se decide en unos 12 sitios. El pase se escribe en 17 sitios de 10 ficheros. Las tablas de CALN-43 van en esa dirección.

## Lo que falla en nuestra vara

**La vara nos señala mal las prioridades: el panel no se parece a los clientes reales, parte de sus guiones no reacciona, el juez duda en la frontera y nadie mide cómo contestamos.**

|  | Clientes reales | Panel |
| --- | --- | --- |
| Largo mediano del mensaje | 31 caracteres | 154 caracteres |
| Mensajes con 2 preguntas o más | 4 % | 32 % |
| Mensajes de más de 200 caracteres | 6 % | 30 % |

Los reales son 75 episodios hablando con una persona, no con el bot, así que no sabemos cuánto falla el bot con ellos. Sí dicen qué piden y cómo les contesta la persona (lo detallo en el estudio de los clientes reales):

- **Piden cosas que el panel no tiene.** Un tercio ya ha reservado y escribe para confirmar, preguntar el punto de encuentro, pedir fotos o cambiar la fecha. El 11 % son agencias o alguien que reserva para otro, y el 15 % pregunta lo que la base no contesta. En el panel, los que ya reservaron son el 10 %.
- **El panel infla otras.** El grupo de 5 o más sale 6 veces más que en los reales (18 % frente a 3 %), y también el refresher, el origen, los menores y el vuelo.

|  | La persona, en los reales | El bot, panel 0.61 |
| --- | --- | --- |
| Largo mediano de la respuesta | 119 caracteres | 703 caracteres |
| Respuestas con pregunta | 23 % | 77 % |
| Respuestas con precio | 13 % | 52 % |
| Respuestas con enlace | 25 % | 26 % |

- **Guiones que no reaccionan.** De 16 a 18 de los 67 graves dependen de un guion que no contesta lo que se le pregunta. 18 de los 22 graves de tercera pregunta son de clientes ciegos, con mensajes escritos sin ver al bot. En las tandas con cliente que reacciona no es causa principal en ninguno de 21 graves.
- **El panel termina en la reserva.** 48 de sus 67 graves (72 %) caen en el turno de reservar, que es el 32 % de los turnos. En las tandas, el 29 %, frente al 34 % de sus turnos: allí no se concentran.
- **El juez duda entre fricción y grave.** Juzgando dos veces la misma vuelta, 5 de 40 clientes cambian de veredicto. `visto-6914`, `visto-6936` y `visto-6927` tienen la misma conducta y distinto veredicto, y 4 de los 67 son fricción juzgada como grave. Entre 3 y 8 de los 17 clientes «a veces» podrían ser esto.
- **El juez no sabe la hora.** Las tres vueltas corren seguidas la misma noche, ya pasado el cierre de las 4:30. En las fechas, «3 de 3» es una sola prueba de reloj, no tres. Y tomaba «next Friday» dicho un jueves por el de la semana siguiente: 3 graves de un mismo cliente se apoyaban en eso.
- **Todos los graves pesan igual.** Repetir una pregunta cuenta lo mismo que dar un importe equivocado.
- **Los arreglos no se ven, y la meta tampoco.** Un arreglo toca de 1 a 3 clientes, y el panel se mueve 3 o 4 por azar. La meta (2 en 60, 1,3 de 40) queda por debajo del ruido del juez. Cliente a cliente, la 0.62 frente a la 0.61 sale 6 peor, 5 mejor y 29 igual.
- **La suite no lo ve.** Tiene 2.239 tests, y `visto-6929` lleva grave en las 15 vueltas medidas.

**Con clientes que reaccionan, el reparto es otro.** De 71 clientes, 21 tienen grave (30 %). Por bloque del plan: plan, importe y moneda, 7; horas y fechas, 6; reglas que faltan, 4; el momento de reservar, 3, y lo ya escrito, 1. Las horas y fechas pesan mucho más que en el panel. Son tandas de versiones anteriores a la 0.61, con clientes que escriben 175 caracteres de mediana, aún más que el panel.

## Fase 4: qué añadimos y qué ha aguantado

**Tienes razón: de la 0.40 a la 0.61 hemos parcheado. Son 86 commits `fix` frente a 9 `refactor`, y desde la 0.59 el panel casi no se mueve.**

&#91;embedded content: Panel fijo de 40 clientes · juez Opus medium · 0.58 a 0.61, de 3 a 4 vueltas por versión.\]

El balance de la 0.40 a la 0.61 en `src` es de +3.624 y −1.993 líneas, con 226 condiciones más, 68 funciones más y 89 comentarios más que citan un caso.

&#91;embedded content: git de src: 6-oct, 0.40, 0.53 y 0.61 contadas ahora; el 20-oct, medida anterior del proyecto.\]

**Lo que vuelve:**

| Familia | Arreglos desde la 0.40 | Clientes por vuelta, 0.58 | Clientes por vuelta, 0.61 |
| --- | --- | --- | --- |
| Tercera pregunta | 24 | 6,3 | 6,7 |
| Plan o importe | 25 | 5,7 | 4,3 |
| Moneda, residente, grupo mixto | 14 | 3,3 | 3,3 |
| Vuelo, fecha, horario | 9 | 3,3 | 2,3 |

La tabla cuenta por palabras en los commits y en las razones del juez, así que es aproximada. Casi todos esos arreglos son anteriores a la 0.58, cuando aún no había panel. No dice que no sirvieran: dice que la familia sigue ahí después de ellos. La fila de la tercera pregunta está además inflada por el panel.

**Por qué vuelve:**

- **Se arregla un camino, no la decisión.** `fix(0.53b)` dice «la misma pregunta no sale una 3.ª vez», pero el freno tiene excepciones y no ve todas las preguntas.
- **Se prueba una vez algo aleatorio.** `s04i-belgas` tuvo su arreglo y pasa 2 y 3 de 5. Con una sola prueba, parecía resuelto.
- **Se apunta al síntoma.** `fix(s05d)` y CALN-39 iban a por las salidas sueltas de un día, y `visto-6929` sigue en 15 de 15 porque parte de su causa está en una regex de lectura.

**La primera tabla tampoco ha movido el total.** La 0.62, con la tabla del plan, saca 23 y 21 clientes con grave, frente a 21, 25 y 21 de la 0.61. La familia del plan baja algo, pero son dos vueltas y no se puede afirmar más.

**Lo que ha aguantado:** `visto-6939` (hora de volar) y `visto-6938` (refresher en su propio día). Tenían grave en 3 de 3 vueltas en la 0.58 y en 0 de 10 de la 0.59 a la 0.61. Coinciden con la 0.59, que metió decisiones tuyas como datos en la base. Son dos casos y no lo he aislado, pero apunta a que un dato en un solo sitio dura más que una condición nueva.

Los clientes ya leídos fallan menos de la mitad que los ciegos. Esa distancia ya existía en la 0.58 y parte viene de guiones que no contestan, así que no prueba sobreajuste.

## Fase 5: ¿la arquitectura es correcta?

**La idea es correcta, pero el escritor recibe lo de antes del mensaje.** Empieza después de acabar el extractor en el 94 % de los turnos, pero su pregunta se fija antes de leer, y el código la cambia en 123 de 180 cierres. Lo demás falla dentro de cada etapa: reglas, lectura y composición. Por lo medido, no reharía el bot.

| Capa | Lo que debería hacer | Lo que hace hoy | Veredicto |
| --- | --- | --- | --- |
| Jev | Afirmar señales del mensaje | Estable | Se queda |
| Extractor | Sacar datos | La lectura sale distinta en 1 de cada 3 primeros mensajes, sobre todo por Haiku y a veces por los umbrales de Jev; es el 37 % de lo leído | Se queda; bajar su azar en los datos que usan las tablas |
| Estado | Guardar lo sabido | 83 campos, algunos derivados | Adelgazar cuando toque |
| Decisión | Una función por decisión | Faltan reglas; plan en unos 12 sitios y pase en 17 | **El hueco principal** |
| Contexto y RAG | Dar el dato correcto | Búsqueda estable; faltan datos sueltos | Se queda; completar los datos que faltan |
| Escritor | Poner en palabras | También hace cuentas, concluye y recibe datos que no debe decir | Quitarle esos datos y las cuentas |
| Composición | Pegar lo decidido | 26 sitios escriben y 27 pegan; tiene fallos deterministas | Corregirlos y encoger |

**Por qué cuesta tanto: la meta exige más de lo que da una decisión aleatoria.** La meta es 2 graves en 60 clientes, un 3 %. Cada conversación hace unas 17 llamadas a IA, según la cuenta de Álvaro. Aunque cada una acierte el 97 %, solo el 60 % de las conversaciones saldría entera. Y Luna no repite: lo que dependa de su texto no se estabiliza con un parámetro.

**Darle al escritor lo leído en este turno es la condición para quitar los correctores.** Por sí solo apenas baja graves: en la tabla por grave es lo último que falta en solo 2 de los 67. Pero sin eso, el código tiene que cambiar la pregunta del escritor (123 de 180 cierres) y quitarle enlaces a quien no debe recibirlos. Costaría poca latencia: el escritor ya empieza 0,31 s después del lector de mediana.

**Con los enlaces basta una orden; con los importes, no.** El escritor tiene el enlace en su prompt y la orden de no dárselo a un colombiano, y no lo escribió en ninguno de 90 turnos. Quitar el dato del contexto no está probado. Los importes sí se le dan con orden de no decirlos, y el código los borra en el 21 % de los turnos.

| Alternativa | A favor | En contra | Valoración |
| --- | --- | --- | --- |
| Quitar al escritor lo que no debe decir | Permitiría quitar los borrados de importes | Sin probar: con los enlaces basta una orden, con los importes no | Probarlo antes en banco |
| Reglas en tablas, con el orden actual | Cubre la mayor causa sin tocar el centro | La lectura limita la tabla del plan | Sí |
| Salida estructurada del escritor | Permitiría contar sus preguntas y quitar filtros | Sin probar con Luna | Abierta |
| Darle al escritor lo leído en este turno | Permite quitar los correctores de la pregunta y de los enlaces | Por sí solo apenas baja graves | Sí: bloque 1 del plan |
| Cierre de reserva por código | Junta preguntas, enlace, pase y grupos en una sola decisión | En las tandas pesa menos que en el panel | Sí: bloque 4 del plan; con los reales es de lo que más pesa |
| Modelo con herramientas | Decide en una sola pieza | Otra llamada de unos 2 s y deja la decisión al modelo | Descartada |

**Las reglas no bastan por sí solas.** Si cada bloque se llevara todos sus graves, la tabla por grave deja el panel en 8 a 11 por vuelta tras lo ya escrito y la parte determinista de plan e importe, en 5 a 8 tras el resto de plan e importe, y en 0 o 1 con todos los bloques. Es un techo, no una previsión. La meta equivale a 1,3 de 40 y queda por debajo del ruido del juez. Es la cuenta del panel viejo; desde el 10-nov, la meta y la parada se miden en el panel de la vara (abajo, en «Cómo sabremos si va bien»).

**La línea base, medida el 10-nov: Luna sola saca lo mismo que el bot en graves.** Luna, con lo mismo que lee el juez y sin nuestras piezas, sobre el panel de la vara (3 tiradas, cada una juzgada dos veces, con el mismo reloj): 10,7 clientes con grave de 40 de media, frente a 10,3 del bot. La diferencia, +0,3, no llega al ruido; cliente a cliente, 5 mejoran y 5 empeoran. Luna sola escribe más corto (330 caracteres frente a 564) y pregunta menos (32 % frente a 67 %), con una llamada por turno frente a cuatro. Tarda 2,1 s de mediana frente a 3,7, aunque se midió desde este PC y no desde PRE. Ojo: Luna sola lee la misma referencia que el juez, lo que la favorece. «Solo orden» frente a «solo reglas» ya no hace falta: en la tabla por grave, el orden por sí solo es lo último que falta en 2 graves. La regla decidida para leerla:

| Si Luna sola saca, frente al bot | Lectura |
| --- | --- |
| 4 o más clientes con grave menos | Nuestras piezas estorban: se replantea la arquitectura con el equipo |
| A menos de 4 (lo que salió el 10-nov: +0,3) | Las piezas no aportan en graves: deciden el coste, la latencia y el control |
| 4 o más clientes con grave más | Las piezas aportan: se sigue con el plan |

Es una medida, no un cambio: el plan sigue mientras se habla con el equipo qué aportan las piezas, además de graves (control de lo que se dice, enlaces, pases, coste). Las tiradas y los juicios están en `feature/bloque0-gadea` (`luna-sola-*` y `vara-base-*`).

## Conclusiones de Claude Gadea

**El problema de fondo, para mí: las decisiones del negocio no tienen un dueño en el código, y los datos que las alimentan cambian entre vueltas.** Lo demás lo agrava o nos impide verlo. Las líneas citadas son de la 0.61. El orden es criterio mío, no una medida.

1. **Faltan reglas o están repartidas.** El pase se escribe en 17 sitios de 10 ficheros, incluida una función que monta el mensaje final (`cart_render.py:355`). `como_reserva` no contempla grupos (`como_reserva.py:53`). El freno de la tercera pregunta se apaga cuando el cliente pide reservar (`compositor.py:143`).
2. **La lectura cambia justo en los datos que usan las tablas.** Varios lectores leen el mismo mensaje sin una regla común. La nacionalidad se lee dos veces para protegerse del azar de Haiku (`extractor.py:1031`); los demás campos, no. 19 de 40 clientes tienen distinto entre vueltas algún dato de las tablas.
3. **El código estropea respuestas correctas.** 16 cifras del catálogo casan con más de un plan (`origen_precio.py:343`). Un filtro borra frases enteras (`redactor_hechos.py:217`) y otro, párrafos enteros (`origen_precio.py:425`). Estos fallos se pueden probar sin IA.
4. **El bot no recibe lo que se le exige.** El juez lee todas las decisiones de `decisiones.json`, y el prompt recibe 3 de 22 (`info.py:465`). Otras 8 tienen una instrucción escrita que ningún código lee. Tampoco se lee `no_se_ofrece`. Además, los datos están repetidos: «4:30» aparece en 29 líneas de 7 ficheros.
5. **Le damos al escritor lo que no debe decir y le dejamos las cuentas.** Recibe importes con orden de no decirlos, y el código los borra en el 21 % de los turnos. Hace él las cuentas de horas y fechas, y Luna no repite.
6. **La vara no distingue.** El panel está lejos de los clientes reales y casi no tiene a quien ya reservó ni a las agencias; parte de sus guiones no reacciona, el juez duda, nadie mide cómo contestamos y todos los graves pesan igual. Un arreglo no se ve entre el ruido, y los 2.239 tests tampoco lo ven.
7. **Casi nada comprueba la verdad después de escribir.** El revisor se saltó en 417 de los 428 turnos con escritor, porque solo se activa si hay cifras o días fuera del contexto (`rag_agent.py:1013`). «Es el mismo precio», en `visto-6942`, pasó sin revisar.
8. **El turno tiene dos momentos de verdad.** El escritor espera a la lectura, pero escribe antes de que se guarde, con una copia del estado que repite las reglas de la extracción (`lectura.py:80`). El venezolano con cédula «necesitó tres arreglos», uno por copia. Encarece el mantenimiento más que los graves.
9. **El estado no tiene contrato.** Son 83 campos y al menos 25 atributos que se añaden en marcha, con 147 `getattr` sobre el estado. Si falta un dato, normalmente no da error: llega `None` y la conducta cambia en silencio.
10. **Nuestra forma de trabajar lo alimenta.** Cada sesión, la mía incluida, ve un caso y añade un arreglo local sin tener el conjunto delante: de ahí los 722 comentarios que citan un caso. Además, buscar latencia nos dio segundos a cambio de perder revisión.

He leído las partes por donde pasan los graves, no todo el código, y no he mirado producción ni seguridad.

## Qué atacaría y qué no: opinión de Claude Gadea

**Atacaría cuatro cosas, por este orden: la vara, los fallos deterministas de plan e importe, las reglas que faltan y la lectura de los datos que usan las tablas.** Es una opinión; el plan la sigue.

### Lo que atacaría

**1. La vara.**

- **Por qué:** hoy nos señala mal las prioridades. Pesa en 39 de los 67 graves y no ve a un tercio de los clientes reales. Sin arreglarla no sabremos si lo demás funciona.
- **Cómo:** clientes que reaccionan y escriben corto y en ráfagas, clientes que ya reservaron y agencias, graves separados por daño, el estilo frente a la persona sin juez y el ruido del juez medido. Pruebas sin IA para las decisiones y repetidas para lo que sale a veces, con el panel solo como confirmación.
- **Qué podríamos sacar:** saber dónde fallamos con clientes parecidos a los reales, y que se acabe el «parece arreglado».

**2. Los fallos deterministas de plan e importe.**

- **Por qué:** son la mayor causa entre los graves limpios (de 14 a 21 de los 26 en que coinciden dos lecturas), se prueban sin IA y no dependen del azar.
- **Cómo:** el Rescue sin precio desde las islas, las cifras que casan con dos planes, la pieza que pega lo que incluye otro plan y los borrados de frases y párrafos enteros. Las horas y fechas, con el reloj y la base, y con pruebas repetidas: un intento anterior con el corte de las 4:30 empeoró el vuelo.
- **Qué podríamos sacar:** menos graves y menos código. `compositor`, `origen_precio` y `lectura` suman casi 1.000 líneas; no se irían todas, pero creo que varios cientos sí.

**3. Las reglas que faltan.**

- **Por qué:** con la vara de hoy son la mayor causa, aunque buena parte es vara. El dato de grupo es estable, y lo de grupos y tercera pregunta ya está escrito.
- **Cómo:** grupos en `como_reserva`, el freno sin su excepción, el horario que no es el de siempre por el asesor y un dueño claro para cada decisión. Las tablas de CALN-43 ya van por ahí.
- **Qué podríamos sacar:** cerrar las familias que más se repiten en el panel. Con clientes reales pesan poco: el grupo de 5 o más sale en 2 de 75.

**4. La lectura, solo de lo que usan las tablas.**

- **Por qué:** es la segunda causa, y puede explicar por qué la tabla del plan no ha movido el total.
- **Cómo:** días, duración, actividad, origen y reparto, no los 20 campos; una sola lectura por turno; que un rechazo no cuente como elección y que cada dato tenga un solo lector que mande.
- **Qué podríamos sacar:** menos «a veces» y tablas que decidan con datos estables. No sé cuánto: habrá que medirlo.

### Lo que no atacaría ahora

| Punto | Por qué no |
| --- | --- |
| Búsqueda del RAG | Es estable y ninguno de los 67 graves nace en ella |
| Modelos, más señales de Jev o más frases en los prompts | Es seguir como hasta ahora |
| Revisor | Sería IA vigilando a IA, y habrá menos que vigilar si el escritor dice menos |
| Contrato del estado | Entero no: cada bloque fija solo los datos que usa |
| Limpieza general de la base | Basta con corregir cada dato cuando toque |
| Rehacer el bot | No hay datos que lo justifiquen |

### Dos avisos

- **La meta:** no creo que esto nos lleve a 2 graves en 60, que equivale a 1,3 de 40, y con esta vara no se podría ver: el juez solo ya cambia el veredicto de unos 5 de cada 40. Sería una mejora grande, pero no la meta, y habrá que hablarlo.
- **Lo que me haría cambiar de opinión:** que tras lo ya escrito y la parte determinista de plan e importe el panel no baje. La línea base del 10-nov no salió mejor que el bot en graves, pero tampoco peor: eso no me hace cambiar el plan, pero sí obliga a medir qué aporta cada pieza además de graves.

## Plan Gadea

**Atacamos cada grave por el mecanismo que lo produce, y cada arreglo quita código. Antes de quitar nada, la vara se queda quieta, el escritor trabaja con lo leído en este turno y deja de escribir lo que decide el código.** Las tandas con cliente que reacciona dicen qué arreglar; el panel dice si el arreglo se repite.

### Reglas

- **Mecanismo, no caso.** Un arreglo vale si se lleva los graves que nacen en el mismo sitio. Nada de piezas por caso ni regex, y lo hecho entra solo si borra código.
- **La vara no se mueve durante una comparación.** La referencia del juez va congelada, con su huella en cada resultado. Una regla nueva entra a la vez en el juez y en el código: solo por cambiar la referencia, la misma 0.61 pasó de 52 a 67 graves.
- **Leer, decidir y escribir, por ese orden.** El escritor recibe lo leído en este turno. Hoy su pregunta se fija antes de leer y el código la cambia en 123 de 180 cierres.
- **Un solo dueño por decisión.** Plan, importe, moneda, enlace, pregunta, pase, horas y fechas los decide el código antes de escribir.
- **El código pinta lo que decide.** Importes, porcentajes, horas, fechas, enlaces y la pregunta del turno salen del código. Luna explica alrededor y no los escribe; hoy los escribe en 101 de 150 respuestas. Con los importes se prueba antes en banco si basta con quitarlos de su contexto; con los enlaces bastó una orden.
- **Breve y al grano.** Decidido el 9-nov: respuestas breves y concisas, no párrafos largos. Hoy el bot contesta en unos 700 caracteres y pregunta en 3 de cada 4 respuestas; la persona, en unos 120 y en 1 de cada 4. Cuenta todo lo que sale, también la tarjeta que pinta el código.
- **Una puerta que no edita.** Comprueba esas cifras y enlaces, y también las preguntas y las ofertas de asesor. Si Luna escribe algo que el código no le dio, se rehace una vez o va la plantilla; nunca se recorta el texto. Cada rehecho cuesta unos 2,1 s, así que antes de ponerla se mide sin juez sobre respuestas grabadas.
- **Primero cubre, luego borra, y contando.** Cada corrector sigue activo y apunta cada vez que actúa. Se borra cuando lleva un panel y una tanda sin actuar; apagarlo antes devolvería los fallos que hoy tapa.
- **Lo que pasó en la charla tiene dueño, sin campos nuevos.** Lo que dice el cliente va a su sitio del estado, que ya existe (reparto, acompañante, refresher, origen), y un plan no se fija con una cifra suelta. Las notas libres no deciden. Medido: explica 12-17 de los 67 graves, y en 11 se pierde en el código, no en Luna. Un campo de planes rechazados, solo si siguen saliendo casos.
- **Cada bloque lee bien lo que usa.** La ficha de datos del cliente se hace por partes. La variación de Haiku no se puede quitar: se quita lo que la agranda, y un dato que decide y sale distinto en dos lecturas se confirma una vez (estudio de abajo).
- **Español e inglés.** Lo que pinta el código va en los dos idiomas, en singular y para grupos. Los clientes reales escriben en esos dos: ninguno de 673 mensajes en otro.
- **Lo que es código se prueba sin saldo.** Cada decisión tiene su banco de casos, que corre sin llamar a ningún modelo.
- **PRE.** Nada sube hasta cerrar el bloque.
- **Despacio y con doble confirmación.** Decidido el 10-nov: cada decisión de rumbo, con dos lecturas independientes (agentes que no reciben la conclusión) y comprobada en las charlas o en el código antes de proponerla.

### Bloques, en orden

- **Bloque 0. La vara.**
  - Reloj fijo, con dos horas: antes y después del cierre de las 4:30. El juez recibe la hora de cada charla.
  - La referencia del juez, congelada en cada comparación y con las decisiones de negocio del 9-nov dentro; por ejemplo, que «next Friday» dicho un jueves es mañana.
  - El cliente de las tandas escribe corto (6 palabras de mediana frente a 27), en ráfagas y a veces cambia de idea. El 43 % de los bloques de mensajes reales son ráfagas, y salen en el 77 % de los episodios.
  - Clientes que ya reservaron, agencias y preguntas que la base no contesta: el 32 %, el 11 % y el 15 % de los reales, y casi ninguno en el panel.
  - Un bloque ciego nuevo: 12 de los 20 actuales ya se usaron para diseñar las reglas.
  - Graves separados por daño, contados por mecanismo y cliente a cliente.
  - El ruido del juez, medido el 9-nov: la vuelta 061a juzgada dos veces con la misma referencia da 20 y 23 clientes con grave, y 5 de 40 cambian de veredicto. Con eso, una bajada se distingue del azar si es de 4 o más clientes de media en 3 vueltas, juzgando cada vuelta dos veces.
  - El estilo, sin juez: largo y preguntas por respuesta frente a la persona (119 caracteres y 1 de cada 4 con pregunta), con una meta, porque se decidió contestar breve.
  - Con la vara nueva, una línea base nueva de la 0.61. Hecho el 10-nov, en feature/bloque0-gadea: el reloj fijo (jueves 5-nov, 10:30 y 20:30), el juez con la hora y la huella de su referencia, el marcador común, el panel de la vara (los 20 visto-\* y 20 ciegos nuevos cortos) y la tanda de la vara. La partida en ese panel: 9 a 10 clientes con grave de 40, frente a 21 a 25 en el de siempre. Con esa partida, la meta y el punto de parada, fijados con el panel viejo, se revisan. Revisados el 10-nov: están en «Cómo sabremos si va bien».
- **Bloque 0,5. Lo ya escrito.** La regla del grupo de 5 o más por el asesor (P9 y P10) en `como_reserva`, el enlace solo con el origen conocido, la regla de no preguntar una tercera vez de Álvaro (P11), sus pasos de qué preguntar y el pase en una función de Gonzalo. Va delante porque está escrito y quita código, no porque pese: cubre 2 de los graves limpios y toca a 2 de 75 clientes reales. Se juzga por su mecanismo, tercera pregunta y grupo a cero, no por el total. Orden: el pase de Gonzalo, el qué preguntar de Álvaro y la regla del grupo con la función del pase. Antes del panel, se quita del tono del escritor «cerrar con una pregunta» en la reserva y se cuenta cuándo pregunta Luna. El paso 4 de Álvaro, que quita el borrado de sus preguntas, entra cuando el contador diga que ya no pregunta. Condición: el saldo de código, negativo; juntas quitan 79 líneas netas en `src`, y 13 sin el paso 4. Medido por Álvaro el 10-nov, con 3 tiradas por lado juzgadas dos veces: los clientes con grave bajan de 24,5 a 16,7 de media y la tercera pregunta queda a cero. El grupo baja de 5, 6 y 4 a 2, 4 y 3, porque en los turnos de RAG el escritor copia el enlace. Su cierre es el enlace con un solo dueño, y solo con el origen conocido.
- **Bloque 2a. Plan e importe: lo determinista.** Lo que no depende de leer y se prueba sin IA, con un banco. El Rescue deja de tener precio desde las islas y se lee `no_se_ofrece`. El plan deducido por las cifras (`origen_precio`) deja de decidir, porque 16 cifras casan con más de un plan. Se quita la pieza que pega lo que incluye otro plan. Las comparaciones sin cifra («es el mismo precio», `visto-6942`) pasan por la puerta. La cifra del plan solo cuenta cuando Jev dice que el mensaje elige, con una señal que ya existe y es estable. Hoy entra la primera cifra, también en un rechazo: en visto-6929, «el paquete de 5 inmersiones no es lo que le pedí» fija el paquete de 5 que el bot había ofrecido en el turno 1. El extractor no lee esa cifra, y no se le añade; se prueba con las señales grabadas, sin IA. Son 13 graves del panel, todos limpios (11 según la segunda lectura). Hecho el 10-nov en feature/bloque2a-gadea, sobre el 0,5: el Rescue leído de la base, las cifras ambiguas que ya no deciden el plan (con contador) y lo que incluye cada plan con su nombre; la cifra del plan ya la resolvía la base. «Es el mismo precio» pasa al 2b, porque es lectura. En el panel de la vara, el Rescue baja de 1 de 3 a 0 de 3, pero el total no se mueve: 9,2 frente a 8,7 de 40, con el reloj del jueves 5 y 6 juicios por lado (−0,5, no cuenta). La tercera oferta del pase (visto-6940) también cae. En la tanda de la vara, 0 y 1 de 10 frente a 2 y 2: los graves del 0,5+2a son la agencia y el enlace sin hotel, del bloque 4. El saldo de src es de +38: lo que se borra llega en el 2b. Su vara ya existe: la comparación en sombra de los precios ve importes que no casan en 10 a 12 de cada 27-29 turnos que piden precio.
- **Bloque 1. Lo que recibe el escritor.** Su pregunta y sus datos salen después de leer el mensaje. Una sola lectura por turno: hoy se lanza dos veces en 23 a 29 de cada 117 turnos a partir del segundo. Los umbrales de Jev llevan una banda de duda en un solo sitio, y se prueba contestar una ráfaga como un solo turno. Se borra el corrector que tira el último párrafo con «?», que se lleva la respuesta buena en 3 graves. Los correctores de la pregunta y de los enlaces empiezan a contar cuándo actúan. El escritor contesta breve: se cambia su tono, que hoy le pide cerrar con una pregunta, y el largo se mide frente a la persona. Todo, con A/B de latencia: el escritor ya empieza 0,31 s después del lector de mediana. Se mide por la variación (clientes «a veces», estados que se separan y lecturas dobles a cero), no por los graves: por sí solo apenas los baja. Hecha el 10-nov la primera parte, en feature/bloque1-gadea, sobre el 2a: una sola lectura por turno, el escritor con lo ya guardado y un contador del corrector de la última pregunta, que ya no quita un párrafo con un importe o un enlace. El saldo de src es de −1. En el panel de la vara, con 6 juicios por lado frente al 0,5+2a, los graves pasan de 8,7 a 8,2 (no cuenta). Los clientes «a veces» pasan de 18 a 11 y las lecturas dobles, de 71 a 6 de 264; las 6 son la segunda lectura de la nacionalidad, que es deliberada. Los estados que se separan no se mueven (16 y 17 de 40). Las llamadas de IA por turno bajan de 3,93 a 3,70, y la mediana de tiempo sube de 3,52 a 3,83 s porque el escritor espera a la lectura. Lo que empeora es de los bloques 4 y 3. En visto-6901, el escritor recibe la duración bien leída, enseña un solo plan y pregunta por la reserva en vez de ofrecer el asesor, y se pierde el pase del equipo propio: hoy ese pase lo decide la pregunta del escritor. Quedan lo breve (con Álvaro), la banda de duda de Jev y las ráfagas.
- **Bloque 4. El momento de reservar y el pase.** Cuando el cliente pide reservar, una sola decisión: el enlace, las opciones con su enlace, el pase o la única pregunta que falte, una vez. Junta los callejones sin salida, las ofertas de asesor de Luna, el equipo propio, el grupo con una parte sin enlace (P10), el horario que no es el de siempre (`visto-6899`) y lo ofrecido o rechazado antes. A quien ya reservó se le contesta lo que está en la base, y lo demás pasa con una persona. Quien escribe por otros (una agencia, un instructor de otro centro) recibe el mismo trato que un cliente. De lo que la base no contesta, pasan con una persona el clima de ese día y una recogida fuera de los puntos de siempre; lo demás lo contesta la base, también la disponibilidad, que siempre hay. Lee nacionalidad, hotel y grupo mixto. Con los reales es de lo que más pesa: toca 53 de 75, y 34 escriben después de reservar o preguntan lo que la base no contesta. Jev ya reconoce a quien reservó (ya\_reservado y needs\_staff) y hoy lo pasa todo con una persona; el cambio es contestarle lo que sabe. Lo que Jev toma por una empresa también va hoy al pase, y ahí pueden caer las agencias, que ahora van como clientes. Desde el 10-nov se parte en dos, que van a la vez. El 4P es el pase y la posventa fuera de la reserva: la agencia, quien ya reservó, lo que la base no contesta y el pase médico que se come la respuesta; lo lleva el Claude de Gadea. El 4R es el momento de reservar: el enlace, las opciones, el pase o una sola pregunta, con el equipo propio, el horario que no es el de siempre y el hotel antes del enlace; lo lleva Álvaro, porque es el mismo mecanismo que el cierre de su 0,5. Con el bloque 1, en el panel de la vara pesan unos 2,8 y 2,6 de 40. La agencia falla en los 18 juicios porque la pregunta needs\_staff de Jev incluye «a travel agency».
- **Bloque 3. Horas y fechas.** En dos pasos. Primero, sin ningún dato del cliente: una función, con el reloj y la base, pinta la primera fecha que se reserva por la web y, para cada plan, desde qué hora se puede volar. La tarjeta avisa si el enlace es para una fecha ya cerrada y ofrece el primer día que se puede reservar: el cierre es firme. Se cuentan y se quitan el parche de las 18 horas, la comprobación de la espera en los hechos y la instrucción de no calcular el cierre, sin llamadas nuevas. Después, si lo decides: el lector de notas, que ya existe (corre en 129 de 471 turnos), devuelve el vuelo y las fechas como datos, y la función compara. Nada de esto toca a Haiku. Su razón son los clientes reales, no el panel: un tercio de los primeros mensajes llega entre las 16:30 y las 6:00. Se prueba con un banco con el reloj fijo. Desde el 10-nov, el primer paso (3.1, el cierre) va antes del 2b, y el segundo (3.2, el vuelo con el lector de notas) después, si lo decides.
- **Bloque 2b. Plan, importe y moneda: lo que depende de leer.** Lo decide la tabla del plan con sus datos bien leídos: actividad, días, origen, certificado y reparto, incluido lo que dice el cliente de otra persona del grupo (un refresher, un embarazo). Los planes por persona en un grupo y la moneda de un grupo, con su regla. Los importes y el plan los pinta el código. Se cuentan y, cuando ya no actúan, se quitan el borrado de frases por llevar un importe y lo que quede del plan deducido por las cifras. Desde el 10-nov va detrás del 4 y del cierre: en el panel de la vara pesa entre 0,6 y 2,5 de 40, siempre «a veces», y no sale en la tanda. Antes de empezarlo, más charlas reales (las de Andrés) o el primer mensaje de los 75 reales pasado por el bot, para ver cómo falla con los precios.
- **Bloque 5. Reglas que faltan.** Dentro de las tablas, sobre todo lo que el bot no debe decir: el refresher en su propio día, descuentos que no existen, menores. Cada regla entra como dato y con su banco, y a la vez en el juez. En las tandas pesa 4 de 21.

El 0,5 fue delante porque estaba escrito y quitaba código, y el 2a detrás porque plan e importe era lo que más pesaba entre los graves limpios del panel viejo y esa parte no necesita IA. El 1 era la condición para quitar correctores y para el 2b. El 10-nov, con los tres medidos en el panel de la vara y el rumbo revisado con dos agentes independientes, el orden cambia: el 4 va delante, partido en el 4P y el 4R, que se hacen a la vez; después, el primer paso del 3 (el cierre); luego el 2b; el segundo paso del 3 (el vuelo), si lo decides; y el 5. Con clientes como los reales, el 4 es lo que más pesa (unos 5 de 40 en el panel de la vara, y el 71 % de los reales pide algo suyo), falla siempre y sus decisiones ya están tomadas: las del 9-nov entraron en el juez, pero aún no en el bot. El 2b pesa entre 0,6 y 2,5 de 40, siempre «a veces». Si una medida dice otra cosa, se cambia.

### Cada bloque, igual

1. Leer bien sus datos, con un banco de lectura de mensajes cortos, largos y en ráfaga.
2. Decidir en código, con un banco de la decisión que corre sin saldo.
3. Pintar lo decidido y pasar la puerta.
4. Tanda con cliente que reacciona: comprobar que el mecanismo cayó, atribuyendo cada grave a su dueño en la traza y no a quien redacta la frase.
5. Los correctores del bloque cuentan cuándo actúan; se borran cuando ya no actúan.
6. Cierre: panel con 3 tiradas por lado (5 en los clientes «a veces» del bloque, si aceptas la norma de 5 de 5), la referencia congelada y la comparación cliente a cliente.

### Cómo sabremos si va bien

- **Por mecanismo:** el de cada bloque, a cero en su tanda y en las tiradas del panel, y sus correctores sin actuar. El bloque 1, por la variación: menos clientes «a veces» y ninguna lectura doble.
- **Global:** desde el 10-nov se mide en el panel de la vara (reloj del jueves 5, huella 9326257c), no en el viejo. El viejo está más lejos de los reales (16,7 puntos de distancia frente a 7,3) y solo 23 de sus 67 graves son limpios. La partida es 9,2 de 40. La meta, al acabar el plan: 5 o menos de 40 de media, con la mitad ciega en 1 o menos de 20 y ningún cliente con grave en los 6 juicios. Con el ruido de este panel, una bajada cuenta si es de 3 o más clientes de media en 3 tiradas juzgadas dos veces; por azar sale más o menos 1 de cada 100 veces, y el umbral se recalcula en cada cierre. Entre cierres manda el mecanismo, con los clientes del bloque repetidos 5 veces. La meta de 2 en 60 queda por debajo del ruido del juez.
- **Puntos de parada:** si el mecanismo de un bloque no cae en su tanda, no se pasa al siguiente sin revisarlo. Tras el bloque 4 entero y el cierre de las 4:30, el panel debe bajar al menos 3 desde 8,2; si no, se para y se escribe «qué estamos haciendo mal». La parada anterior (de 21-25 a 8-11 tras el 0,5 y el 2a, y parar si no bajaba de 16) era del panel viejo; en el de la vara, la partida ya está en 9,2.

### Lo que aún no sabemos

No cambia el rumbo del 10-nov, pero hay que acabar sabiéndolo. Cada punto tiene su momento:

- **El reparto de los graves por bloque es una sola lectura.** En la próxima medida, una segunda lectura a ciegas con otro agente.
- **La tanda de la vara es una sola tirada.** Se repite en cada cierre de bloque.
- **Los 75 reales son charlas con una persona:** dicen qué piden, no dónde falla el bot. Antes de empezar el 2b, con más charlas reales (las de Andrés) o pasando por el bot su primer mensaje.
- **Los ciegos nuevos del panel los escribió una sesión que ya conocía el diagnóstico,** y pueden inclinar la vara hacia el 4 y el 3. Al final, en el examen independiente.

### Antes de empezar

- **Saldo de OpenRouter.** El lector (Haiku) va por ahí: sin saldo no corren las tandas ni el panel, pero los bancos de código sí.
- **Ventana del juez.** Cada lado juzgado son unos 7 puntos de la ventana de 5 horas, y cada bloque pide varias tiradas.
- **Trabajo con Álvaro y Gonzalo.** Cuando el plan esté cerrado se reparte entre los tres. Sus ramas ya cubren buena parte del bloque 0,5 y un trozo del 1 (estudio de las ramas).
- **Hecho, y lo que queda con saldo.** Hecho el 9-nov, sin saldo: la referencia del juez con las decisiones del 9-nov (commit c7c7268a, en feature/caln34-gadea desde el 10-nov) y su ruido, con una vuelta juzgada dos veces (unos 5 puntos de la ventana por pasada). Con saldo: la línea base, 2 vueltas; el primer mensaje de los 75 reales pasado por el bot, con lo que leen Jev y Haiku comprobado sin juez y la respuesta juzgada; y un A/B en banco de quitar los importes del contexto del escritor.
- **Decisiones abiertas.** Las de «Lo que decides tú»; las dudas de negocio ya están decididas.

## Estudio: cómo llega a la tercera pregunta

**La tercera pregunta llega casi siempre cuando el cliente pide reservar: en 19 de los 21 graves que se pueden seguir turno a turno.** Al bot le falta un dato y, en vez de dar una salida, pregunta otra vez. Por eso la mitad de estos graves (11 de 22) llevan además un callejón sin salida: ni enlace ni pase.

Son los 22 graves con pregunta repetida de las tres vueltas de la 0.61, seguidos con los registros del compositor de cada turno. Salen por dos caminos y ninguno más.

| Camino | Graves | Qué pregunta repite | Dónde está |
| --- | --- | --- | --- |
| Pedir reservar apaga el freno | 12 | Actividad 6, personas 5, refresher 1 | El tope de 2 no se aplica si el cliente pide el enlace (`compositor.py:143`) |
| La pregunta no pasa por el contador | 10 | Pase al asesor 5, origen 4, refresher 1 | El pase lo escribe Luna y no es un dato; la confirmación del origen sale de cuatro sitios y solo uno cuenta |
| Respuesta corta | 0 | — | El freno solo falla con menos de 5 palabras; no ha pasado |

**Pedir reservar apaga el freno.** El código pregunta dos veces lo que falta. A la tercera, el cliente pregunta cómo reservar y la excepción del enlace vuelve a abrir la pregunta, porque supone que sin ese dato no hay enlace. No siempre es así: el número de personas se elige en la web, y para la actividad pueden ir las opciones con su enlace, como ya se hace con el origen.

**La pregunta no pasa por el contador.** En `visto-6940`, Luna ofrece el asesor en tres turnos seguidos, aunque la clienta ya había preguntado cómo reservar un plan sin enlace: tocaba hacer el pase. En `visto-6927`, la primera pregunta por el refresher no pasa por el contador y el código la hace dos veces más. La confirmación del origen sale de `huecos.py`, de dos sitios de `origen_precio.py` y de `redactor_hechos.py`.

**Con cliente que reacciona casi no pasa.** En las 71 charlas de las tandas, la misma pregunta llega a la tercera vez una sola vez (el pase, al pedir reservar) y el juez no la tomó como grave. Llega a la segunda en 10 casos, 6 de ellos con el pase. El panel lo infla porque sus mensajes no contestan, pero el mecanismo es real. Con clientes que escriben corto e ignoran preguntas no está probado: el de las tandas escribe 175 caracteres de mediana.

**Lo que cambia en el plan (bloque 4, el momento de reservar):**

- Si el cliente pide reservar y falta un dato, va una salida y nunca otra pregunta: el enlace si el dato no hace falta, las opciones con su enlace si hay que elegir, o el pase. Se quita la excepción del enlace; no se añade otra.
- Un solo sitio que pregunta y un contador por pregunta, no por dato. El pase y la confirmación del origen pasan por ahí, y se borran las otras tres copias de la confirmación.
- Luna no pregunta por su cuenta lo que decide la tabla, empezando por el pase.

Sale del panel 0.61 con los juicios de la referencia del 6-nov y de las charlas de las tandas, sin gastar saldo. De los clientes ciegos solo se cuenta.

## Estudio: dónde nacen los graves de horas y fechas

**Nacen en el escritor, que hace él las cuentas del reloj y del calendario: los datos están bien y el código no hace esas cuentas.** Son los 6 graves de horas y fechas de las tandas (de 21) y 5 del panel 0.61, de 3 clientes; en 3 de ellos se equivocaba el juez con «next Friday». Hay dos cuentas: desde qué hora puede volar el cliente y si ya cerró la reserva para el día que pide.

| Cuenta | Tandas | Panel 0.61 | Qué falla |
| --- | --- | --- | --- |
| Desde qué hora puede volar | 4 | 2 (`visto-6914`, `visto-6942`) | Luna hace la cuenta con la política escrita y se equivoca |
| Si ya cerró la reserva (4:30 p. m. del día anterior) | 2 | 1 cliente ciego, en sus 3 vueltas, donde Luna acertaba y se equivocó el juez | Nadie la hace bien: el enlace sale sin mirar la hora |

**Los datos están bien.** La política del vuelo de la 0.61 dice que las horas se cuentan desde la última inmersión y que las actividades acaban hacia las 12:00-13:00. También dice que se vuela desde las 7:00 del día siguiente, o desde la medianoche tras el minicurso. El cierre de las 4:30 también está.

**El vuelo: Luna hace la cuenta y falla de tres formas.**

- Toma la llegada de la lancha (4:15 p. m.) como fin de las inmersiones. En la charla 6927 acierta el sí, pero con esa hora. En la 6942 le dice a una clienta que su vuelo de las 9:00 no cumple, y sí cumple.
- Se contradice en la misma respuesta: «sí, llegas bien» y luego «no alcanza» (charla 6939). Después le niega un vuelo a las 6:00 tras el minicurso, que sí alcanza.
- Da por bueno un vuelo el mismo día, «con margen» desde las 4:15 (charla 6914, primer turno).

**El cierre: nadie hace bien la cuenta.** El código le da a Luna la fecha y la hora de hoy (`contexto_rag.py:133`). Pero la instrucción de los hechos le pide que no calcule si el cierre pasó (`info.py:528`), y la tarjeta manda el enlace sin mirarlo. A las 22:13 y a las 23:56, dos clientes recibieron el enlace para el día siguiente sin aviso (charlas 6955 y 6967). Cuando Luna sí calcula, lee «next Friday» como mañana, que es lo correcto: en el panel, a las 22:49 del jueves, dijo que el viernes ya había cerrado, y el juez lo tomó como falso.

**Por qué el código no puede hacerlo hoy.** El estado no guarda las fechas del cliente ni la hora de su vuelo, solo cuántos días quiere bucear. Lo único que hay es un parche que añade la frase de las 18 horas si Luna no la dice, buscándola por texto (`rag_agent.py:609`).

**Dos avisos sobre la vara.** Las tandas y el panel corren de noche, entre las 22:00 y las 0:00 de Colombia, ya pasado el cierre, así que este caso sale más que con clientes de día. Y los mensajes fijos con fechas relativas («next Friday», «mañana») cambian de sentido según el día en que corre el panel.

**Lo que cambia en el plan:**

- Las dos cuentas las hace el código y Luna solo las dice. Es el bloque 3 del plan, en dos pasos (estudio de cómo leer las fechas, abajo).
- Después se borran el parche de las 18 horas y la instrucción de no calcular el cierre.
- Pesa más con los clientes reales que en el panel: en el panel 0.61 quedan 2 graves de vuelo, y el paso 1 no cubre ninguno.

Sale de las charlas de las tandas, del panel 0.61 con sus registros y del código y la base de la 0.61, sin gastar saldo.

## Estudio: de dónde sale la variación de la lectura

**Sale sobre todo de Haiku, que con la misma entrada y a temperatura 0 no siempre devuelve lo mismo; el código no la origina, pero la agranda.** En el turno 1 de la 0.61, 12 de 40 clientes no salen iguales en las tres vueltas. En los turnos siguientes, con el mismo estado de partida, se separan 12 de 73.

| Fuente | Turno 1, 0.61 | Turno 1, 0.59 | Qué cambia |
| --- | --- | --- | --- |
| Haiku, al leer el mensaje | 9 | 10 | Reparto, actividad, tamaño del grupo, acompañante, origen |
| Jev cruza un umbral | 2 | 2 | Origen y pregunta pendiente |
| El código, con la misma lectura | 0 | 0 | — |
| Carrera de tiempos | 0 | 0 | Solo aparece desde el turno 2 |

Un cliente puede tener más de una fuente, y la tabla no los explica todos: queda sin fuente 1 cliente en la 0.61 y al menos 3 en la 0.59. Dos que he comprobado son la puerta de Jev sobre el origen y Haiku con el certificado.

**Haiku no repite, y eso no se puede quitar.** En 63 de 107 parejas de lecturas del mismo turno con la misma entrada, la salida tuvo distinta longitud. Lo que sí se puede quitar es lo que la agranda:

- **El lector de grupo depende de cómo salga Haiku.** Se usa o no según lo incompleta que parezca la lectura. En `visto-6898`, una vuelta reparte a las tres que tienen Open Water y se salta el lector; las otras dos lo usan y quedan con 3 sin decidir.
- **La cita se valida por el trozo citado, no por el valor.** En `visto-6899`, «we must be back on board by 5:00 pm» sale citado como lugar, se tira y el bot pide confirmar el origen.

**Jev cruza un umbral por centésimas.** Con la misma entrada, sus puntuaciones tiemblan hasta 0,02-0,05. En `visto-6936`, el extractor lee Cartagena en las tres vueltas, pero la puerta del origen (umbral de 0,6) lo bloquea en dos.

**Desde el turno 2 hay una carrera.** La lectura del turno se marca como consumida antes de publicarse (`extractor.py:1089-1104`), y si otra pieza la pide en ese hueco se lanza otra vez (`extractor.py:1219`). En el panel, 23 a 29 de cada 117 turnos a partir del segundo llaman dos veces al extractor. La segunda lectura deja vacío el lector de grupo: en `visto-6926`, una vuelta sale con el reparto y otra sin él.

**El texto anterior de Luna no explica la variación.** Jev y el extractor reciben la última respuesta del bot, que Luna redacta distinta cada vez. Pero, con el mismo estado de partida, se separan el 14 % de los pares con el mismo texto anterior y el 11 % con distinto: no se ve efecto. Hay casos sueltos: en `visto-6901`, una vuelta ofreció el asesor, el cliente dijo «Yes please» y acabó en un pase.

**Lo que cambia en el plan:**

- Bloque 1: una sola lectura por turno, publicada al lanzarla, sin relanzarla ni vaciar el lector. Quita la carrera y ahorra llamadas a Haiku.
- Bloque 1: los umbrales de Jev llevan una banda de duda en un solo sitio, con una salida fija: el origen dudoso se confirma una vez.
- Cada bloque, al leer sus datos: el lector de grupo se usa cuando el grupo lo pide, la cita se valida por el valor, y un dato que decide y sale distinto en las dos lecturas que ya se hacen en el turno 1 se confirma una vez, midiendo cuántas preguntas añade.

Sale de las trazas y llamadas guardadas del panel 0.61 y 0.59 y del código de la 0.61, sin gastar saldo. Lo de Jev es sospecha fundada: se atribuye por eliminación, porque su línea en la traza va cortada.

## Estudio: ¿trae la búsqueda el documento correcto?

**Sí, o no hacía falta: ninguno de los 67 graves del panel 0.61 nace en la búsqueda.** El RAG se queda como está y el plan no necesita un bloque para él.

**Qué recibe Luna.** Tres cosas: el catálogo entero en el prompt (precios, duración y enlaces), los hechos que pone el código sobre el plan y lo que pregunta el cliente, y los documentos que trae la búsqueda (fichas, FAQ, políticas y descuentos). Si ningún documento llega a 0,40 de similitud, se tiran todos. Eso pasa en un solo turno del panel, el mismo en las tres vueltas.

**Cómo lo medí.** El panel guardó en `rag_docs` lo que trajo cada búsqueda, los 8 primeros documentos con su nota, en los 428 turnos con escritor. En el turno de cada grave miré qué dato hacía falta, si la búsqueda trajo el documento que lo tiene y si el dato le llegó a Luna por otro camino. Sin saldo: con lo guardado y el código de la 0.61.

46 de los 67 graves no dependen de ningún documento: son decisiones (grupo con asesor, tercera pregunta, equipo propio, enlace o asesor) o plan e importe. Los otros 21:

| Qué pasó | Graves | Ejemplo y sitio en el plan |
| --- | --- | --- |
| La búsqueda trajo el documento | 8 | El vuelo en visto-6914 (1.º) y visto-6942 (3.º). Falla quien usa el dato: Luna con el vuelo y el precio (bloques 3 y 2b), la moneda (bloque 2b) y el refresher en su propio día (bloque 5). En visto-6899 trajo el horario (7.º), pero bajo el umbral, y se tiró; pasa en las 3 vueltas y solo una sale grave, y lo que faltó, ofrecer un asesor, es una decisión |
| El código dio el dato en los hechos, aunque la búsqueda no trajera el documento | 7 | El cierre de las 4:30: Luna lo tiene y cuenta mal «next Friday» (bloque 3). Lo que incluye el refresher: los hechos dicen 1 inmersión y una pieza del código pega «2 inmersiones guiadas» de otro plan (bloque 2a). El descuento de grupo en visto-6898 (bloques 0,5 y 2b) |
| El dato no está en ningún documento | 3 | visto-6916: que el Rescue no se ofrece desde las islas solo está en pricing.json; ni su ficha lo dice (bloque 2a) |
| El dato lo dijo el cliente antes en la charla | 3 | La edad de un niño y un embarazo. El mensaje del turno solo pregunta cómo reservar, así que ninguna búsqueda lo traería (el plan de cada persona, bloque 2b, y la regla «lo que pasó en la charla tiene dueño») |

**Lo que cambia en el plan.** Ningún bloque nuevo: los 21 ya tienen su sitio. Sí confirma una regla: los datos de los planes no dependen de la búsqueda. En 7 graves el documento no llegó y el dato sí, por el código. La búsqueda aporta sobre todo FAQ y políticas que el código no pide.

**Lo que no mide.** Si en turnos sin grave la búsqueda trae algo que despista: un documento equivocado que Luna ignora no se ve aquí. En octubre, con preguntas sueltas (`rag_piezas`, 20 preguntas y 104 datos), la búsqueda cubría el 96 % de los datos. No es el panel, pero va en la misma dirección.

## Estudio: lo que ya traen las ramas de Álvaro y Gonzalo

**Cubren buena parte del bloque 0,5 y un trozo del 1, y juntas quitan código: 79 líneas netas en src frente a la 0.61. No chocan entre sí. Antes de medirlas hay que arreglar un riesgo: ya no hay nada que quite ni cuente las preguntas que escriba Luna en la reserva.**

**Qué rama vale.** De Álvaro, caln43-preguntar-alvaro, con la tabla del plan de la 0.62 y los cinco pasos de qué preguntar (−110 netas frente a la 0.61), y de caln43-grupos-alvaro solo el commit de P9 y P10: el grupo de 5 o más y la parte sin enlace, por el asesor. El resto de esa rama es una copia vieja de P11. De Gonzalo, pase-gonzalo: el pase en una función y el escalado sin copias (−52). Las cifras que da cada uno (−143 y −85) se cuentan desde otra base; la tabla de la 0.62 la llevan las dos ramas. Contándola una sola vez, −79 en total; sin el paso 4, el de riesgo, quedan −13.

| Qué hace | Bloque | Líneas en src | Riesgo |
| --- | --- | --- | --- |
| Nunca una tercera pregunta, tampoco al pedir el enlace (P11) | 0,5 | +55 | Bajo |
| La tabla elige la pregunta; fuera el aplazamiento | 0,5 y 4 | −12 | Bajo |
| El escritor no pregunta en la reserva; fuera la pregunta fijada antes de leer | 1 | −130 | Medio |
| Fuera los borrados de las preguntas que redacta Luna | 1 | −66 | Alto: quita un corrector antes de cubrir su caso |
| Las preguntas del origen, en una lista que cuenta | 0,5 | +8 | Bajo; el origen sigue con dos dueños |
| El pase en una función, con un test que lo vigila | 0,5 | −25 | Nulo |
| El escalado deja de copiar los filtros de la cascada | 0,5 y 4 | −60 | Medio-bajo: cambia tres conductas sin medir (clima, búsqueda antes del pase médico, idioma) |
| Grupo de 5 o más y parte sin enlace, por el asesor (P9 y P10) | 0,5 y 4 | +118 | Bajo |

**Juntas.** Las ramas de Álvaro y Gonzalo solo comparten un fichero y se fusionan sin conflictos. Con las tres en una copia, pasan 3.580 tests y falla uno: la regla del grupo marca el pase a mano, y el test de Gonzalo pide la función nueva. Es un cambio de tres líneas. Orden: el pase de Gonzalo, el qué preguntar de Álvaro y al final la regla del grupo, ya con la función del pase.

**El riesgo antes de medir.** En la reserva, el escritor recibe «sin hacer ninguna pregunta», pero su tono le sigue pidiendo «cerrar con una pregunta útil o siguiente paso claro». Y el paso 4 quita lo que borraba las preguntas de Luna sin que nada pase a contarlas: si Luna pregunta igual, salen dos preguntas, o una tercera vez fuera del contador. Va contra una regla del plan: primero cubre la tabla, luego se borra el corrector. El propio diseño de Álvaro pedía antes del paso 4 un test con los textos reales del panel, y falta. Antes del panel: quitar esa línea del tono en los turnos de reserva y contar cuándo pregunta Luna.

**Lo que queda de cada bloque después de integrarlas.**

- 0,5: el enlace solo con el origen conocido no está en ninguna rama.
- 2a: nada.
- 1: ya está que la pregunta no se fija antes de leer. Faltan una sola lectura por turno, la banda de duda de Jev, las ráfagas, el corrector del último párrafo y los contadores de los correctores. Hay que comprobar si los datos del escritor también salen después de leer. Candidato a quitar: la segunda lectura de la nacionalidad. Un estudio de Gonzalo sobre la 0.59 dio, sin ella, 0 nacionalidades mal en 540; en la 0.61, esa segunda lectura son 0,24 llamadas por turno.
- 2b: la tabla del plan está. Faltan quitar los cálculos sueltos del plan (si está en duda, si dura varios días…), los planes por persona en un grupo y la moneda del grupo.
- 4: entra P10. El pase ya se marca en una sola función, pero cuándo pasar se sigue decidiendo en 9 ficheros, y la pregunta del origen la sigue haciendo el código del precio por su cuenta.
- 3 y 5: nada.

**Qué se mide.** Sin saldo, cinco tests nuevos, que pasan salvo el del pase. Con saldo, los bancos caln39, graves y caln35, y el panel con 3 tiradas por lado. La tabla de la 0.62 solo está medida en su primera versión.

## Estudio: cómo leer las fechas y la hora del vuelo

**El código puede hacer dos cuentas solo con el reloj y la base: el primer día que se reserva por la web y desde qué hora puede volar quien hace cada plan. Eso arregla los graves del cierre y deja quitar tres piezas. Para el vuelo hace falta además el dato del cliente. Ya lo lee una pieza que existe, el lector de notas, así que no hay que tocar a Haiku ni añadir llamadas.**

**Cuántos son.** Hay 11 graves de horas y fechas: 6 en las tandas y 5 en el panel de la 0.61. En 3 de los del panel se equivocaba el juez.

| Qué necesita | Tandas | Panel 0.61 |
| --- | --- | --- |
| Solo el reloj y la base | 4 de 6 | 0 de 5 |
| Un dato del cliente | 2 de 6 | 2 de 5; en los otros 3 se equivocaba el juez |

De los 4 primeros, dos son del vuelo: Luna contaba desde la llegada de la lancha o se contradecía. Ya no salen en ninguna de las 6 vueltas del panel de la 0.61, porque la 0.61 escribe el umbral en la política. Los otros dos piden «mañana» pasado el cierre de las 4:30, y basta con que el código sepa, con el reloj, cuál es el primer día que se reserva por la web. De los que necesitan el dato del cliente, en visto-6914 y visto-6942 Luna tenía el umbral y comparó mal 1 vez de cada 3. En un caso ciego, «next Friday» se lee como mañana en las 3 vueltas, que es lo correcto: ahí se equivocaba el juez.

**Cómo lo dicen los clientes.** En el panel, 30 de 40 nombran alguna fecha y 8 el vuelo, siempre con día y hora. En las tandas, 121 de 190 nombran una fecha y 18 el vuelo. En los reales, 44 de 75 nombran una fecha, pero el vuelo solo 2. Lo que más sale es «hoy» o «mañana» (unos 15 de 75), y al menos 2 piden reservar para mañana pasadas las 4:30. «Next» o «este» con un día de la semana sale en el 14 % de las tandas y en el 5 % de los reales.

**Lo que ya existe.** El lector de notas (DeepSeek Flash) corre en paralelo y Luna lo espera. Ya apunta el vuelo con día y hora en 17 de las 24 primeras menciones del panel, igual en las 3 vueltas. Tiene dos frenos. La puerta de Jev se lo salta: en visto-6914, las tres vueltas dan «nada que apuntar». Y su prompt le dice que no apunte fechas porque son un campo de la reserva, un campo que no existe.

| Opción | Coste | Veredicto |
| --- | --- | --- |
| Un campo nuevo en el extractor (Haiku) | El esquema va como texto en su prompt: unos 370 caracteres por campo, y para «next Friday» también la fecha de hoy | Choca con la norma de no tocar el prompt de Haiku y con lo aprendido en ex-9b |
| Una pregunta a Jev | Unas 15 líneas, en la misma llamada. Jev solo elige de una lista (hoy, mañana, otro día, no lo dice); nunca da un valor | Sirve para el cierre, no para el vuelo |
| Un analizador de fechas | De 80 a 150 líneas de patrones en dos idiomas | Es una regex sobre lo que escribe el cliente: no |
| El código pinta los umbrales y Luna compara | Es lo que ya hace la 0.61 | Para el cierre basta; con el vuelo falla 1 de cada 3 |
| Una pregunta cerrada del código | Poco código | Quien nombra el vuelo ya da día y hora: sería repreguntar |
| El lector de notas devuelve el vuelo y las fechas como datos | Unas 30-40 líneas, sin llamadas nuevas. Cambia el prompt de DeepSeek, no el de Haiku, y su puerta se abre también cuando el cliente pregunta si le alcanza (9 % de los turnos) | La recomendada para el vuelo |

**Lo que propongo.**

- Paso 1, dentro del plan. Una función, con el reloj y la base, pinta la primera fecha que se reserva por la web y, para cada plan, desde qué hora se puede volar. La tarjeta avisa si el enlace es para una fecha ya cerrada y ofrece el primer día que se puede reservar: el cierre es firme. Se quitan el parche de las 18 horas (con su regex sobre lo que escribe Luna), la comprobación de la espera en los hechos y la orden de no calcular el cierre. Saldo de código entre −10 y +10 líneas, sin llamadas nuevas. Cubre los 2 graves del cierre de las tandas y ninguno del panel: su razón son los clientes reales, porque un tercio de los primeros mensajes llega entre las 16:30 y las 6:00.
- Paso 2, lo decides tú. El lector de notas devuelve el vuelo y las fechas, y la función compara. Cubriría los 2 graves de vuelo del panel de la 0.61; los otros 3 eran un error del juez con «next Friday». La duda de «next Friday» ya está decidida: dicho un jueves, es mañana.

## Estudio: lo que el bot olvida de la charla

**Explica 12 de los 67 graves, hasta 17 con los dudosos. Luna no olvida: ve la charla entera y todo lo que sabemos del cliente. El que olvida es el código, que decide el plan, el enlace, la tarjeta y la pregunta con el estado: ahí se pierden 11 de los 12. Ninguno pide un campo nuevo.**

**Qué recibe Luna.** Los últimos 24 mensajes. El panel tiene como mucho 10, así que ve la charla entera y el resumen nunca entra. Del estado le llega todo: origen, hotel, actividad, certificación, moneda, última inmersión, refresher, grupo, reparto, duración, edades y las notas libres. Las notas solo las lee Luna: ni los hechos, ni el precio, ni el compositor, ni el plan. Además, el lector de notas solo corre en 129 de 471 turnos. No hay ningún campo de planes rechazados.

| Lo que se olvida | Dónde se pierde | Graves |
| --- | --- | --- |
| Un plan rechazado o solo preguntado vuelve | El estado guarda lo que no era | 5, en las tres vueltas |
| El embarazo de la pareja, que debe ir a snorkel | Queda en las notas, no en el reparto | 2 |
| La pareja que lleva años sin bucear | Se le apunta a quien escribe | 1 |
| Un refresher ya aceptado | No se lee | 1 |
| El origen que se deduce del hotel | No se lee | 2 |
| La edad de un niño de 7 años | Le llega a Luna y la ignora | 1 |

Los 5 dudosos: tres de moneda (el estado guarda «grupo mixto, USD» después de que Luna dijera COP), que son del bloque 2b; uno de Luna que no corrige «las dos cosas el mismo día» (visto-6941) y uno de la hora de llegada (visto-6914), que es de horas.

**Dos ejemplos.** En visto-6929, el cliente pide dormir en Cartagena y luego escribe «el paquete de 5 inmersiones no es lo que le pedí». Una regex toma la primera cifra del mensaje, el código fija el paquete de 5 como plan y la tarjeta lo enseña con su precio. Pasa en las tres vueltas. En visto-6927, el cliente dice «si hago el refresher el martes y las 2 el miércoles»: el refresher no se apunta y el código vuelve a preguntar si le interesa.

**Aparte: lo que se vuelve a preguntar.** El criterio del juez «sin repreguntas» falla en 32 de las 120 conversaciones del panel (27 %) y en 9 de 30 de las tandas, aunque casi nunca llega a grave. Se vuelve a preguntar quién hace qué o la actividad (13), el origen (11), la duración (3) y otras cosas (5). Son las preguntas que hace el código para rellenar huecos; Luna no repite por su cuenta.

**Lo que cambia en el plan.**

- La regla «lo que pasó en la charla tiene dueño» no pide campos nuevos. Lo dicho va a su sitio del estado, que ya existe (reparto, acompañante, refresher, origen), y eso es lectura: bloques 1 y 2b.
- El plan rechazado se arregla quitando código. En el bloque 2a, la cifra del plan solo cuenta cuando Jev dice que el mensaje elige; hoy entra la primera cifra, también en un rechazo. Un campo de planes rechazados, solo si después siguen saliendo casos.
- Las notas libres no deciden nada. Lo que hace falta para decidir (embarazo, edad, otra persona del grupo) tiene que estar en su campo.
- Lo que se vuelve a preguntar se mide con el qué preguntar de Álvaro (bloque 0,5), con el criterio «sin repreguntas» como vara.
- El banco de los planes rechazados sale de visto-6929 y de casos nuevos.

## Estudio: qué piden los clientes reales

**Piden sobre todo precio y reservar, como el panel, pero un tercio ya ha reservado, y la persona contesta corto y casi sin preguntar.** El panel infla las familias que más nos han ocupado y casi no tiene a quien escribe después de reservar.

**Cómo lo medí.** Leí uno a uno los 75 episodios reales y los etiqueté a mano. Para comparar con el mismo criterio, apliqué además las mismas etiquetas por palabras a los reales, al panel 0.61 y a las 190 charlas de las tandas. Donde la lectura a mano y las palabras no casan, doy las dos cifras. Solo hay cuentas: nada que identifique a un cliente.

| Necesidad | Reales (a mano / palabras) | Panel | Tandas | Bloque |
| --- | --- | --- | --- | --- |
| Precio o plan | 56 % / 47 % | 62 % | 56 % | 2a y 2b |
| Pedir reservar o pagar | 36 % / 48 % | 78 % | 62 % | 4 |
| Ya reservado: confirmar, punto de encuentro, fotos, cambios | 32 % / 28 % | 10 % | 5 % | 4 (contesta lo que sabe) |
| Colombiano, residente o moneda | 25 % / 19 % | 28 % | 29 % | 2b |
| Certificado | 24 % / 47 % | 82 % | 65 % | 1 y 2b |
| Origen o recogida | 23 % / 39 % | 75 % | 73 % | 2b y 4 |
| Hoy, mañana o este fin de semana | 16 % / 29 % | 12 % | 14 % | 3 |
| Lo que la base no contesta | 15 % | — | — | 4 (según el tema) |
| Agencia o alguien que reserva para otro | 11 % | — | — | 4 (como cualquier cliente) |
| Cambio de idea o de fecha | 7 % / 8 % | 18 % | 7 % | 1 y 4 |
| Refresher | 7 % | 25 % | 27 % | 5 |
| Salud o no saber nadar | 4 % | 12 % | 5 % | 5 |
| Menores que participan | 3 % (palabras: 15 %) | 20 % | 31 % | 5 |
| Grupo de 5 o más | 3 % | 18 % | 12 % | 0,5 |
| Vuelo tras bucear | 1-2 % (palabras: 11 %) | 20 % | 9 % | 3 |
| Ráfagas (2 o más mensajes seguidos) | 77 % | — | — | 1 |

**Cómo contesta la persona.** Cuento como una respuesta los mensajes seguidos de la persona entre dos del cliente, sin la bienvenida automática. Contesta en 119 caracteres de mediana (70 sin las fichas de producto), pregunta en 1 de cada 4 respuestas y da precio en el 13 %. El bot escribe 703, pregunta en 3 de cada 4 y da precio en el 52 %. El cliente pide reservar hacia su tercer mensaje en los reales y hacia el cuarto turno en el panel: en eso se parecen.

**Lo que hace la persona y la base ya dice.** Da precio en COP a residentes y a quien tiene cédula de extranjería (3 casos), como dice la base. Hay que comprobar en el bloque 2b que el bot también lo hace.

**Lo que cambia en el plan.** Por peso real, el momento de reservar y el pase (53 de 75) van antes que horas y fechas (18, y solo 4 con vuelo, cierre o plazo). Lo ya escrito toca a 2 de 75. La vara suma a quien ya reservó, a las agencias y lo que la base no contesta, y mide el estilo sin juez. Las dudas de negocio que salieron ya están decididas (en «Lo que decides tú»).

## Lo que decides tú

**Son ocho decisiones, con mi recomendación en cada una.** Todavía no he empezado nada de esto.

- [ ] ¿Lanzo la línea base? Decidido el 10-nov: sí. Luna sola con lo mismo que lee el juez (catálogo, enlaces, políticas, FAQ y decisiones) y la hora fija, sin nuestras piezas, sobre el panel de la vara: 3 tiradas, cada una juzgada dos veces. Se compara con la versión actual en el mismo panel. Si saca 4 o más clientes con grave menos que el bot, se replantea la arquitectura con el equipo; si se queda a menos de 4, deciden coste, latencia y control; si saca 4 o más clientes con grave más, se sigue con el plan. Es solo una medida: no cambia nada del bot.
- [x] «Solo orden» frente a «solo reglas»: ya no hace falta. En la tabla por grave, el orden por sí solo es lo último que falta en 2 de 67, y el bloque 1 mide su latencia con un A/B.
- [ ] ¿Pides a Andrés más conversaciones reales de WhatsApp? Recomiendo que sí, y que traigan también clientes que ya reservaron y agencias: son la base para arreglar la vara.
- [ ] ¿Aceptas la norma de 5 de 5 para lo que sale a veces? Recomiendo que sí, solo en los clientes «a veces» que toque cada bloque: cuesta más medir, pero evita dar por cerrado lo que no lo está.
- [x] ¿Siguen Álvaro y Gonzalo mientras tanto? Decidido el 8-nov: cuando el plan esté cerrado, se trabaja en conjunto y se reparte entre los tres.
- [ ] ¿Comparto este documento con ellos? Solo cita clientes vistos; de los ciegos solo hay cuentas.
- [ ] ¿Leemos el vuelo y las fechas con el lector de notas (paso 2 del bloque 3)? No toca a Haiku ni añade llamadas, pero cambia el prompt de DeepSeek y su puerta. Recomiendo que sí, después del paso 1: es la única forma que he encontrado de leer el vuelo dentro de las normas. No corre prisa: en los clientes reales el vuelo casi no sale (2 de 75).
- [ ] ¿Adelantamos los bloques 4 y 3, y revisamos la meta con la vara nueva? Propuesta del 10-nov, con los datos de la noche. Con clientes como los reales, lo que falla es del 4 (la agencia pasada a un asesor, quien ya reservó recibiendo ventas, el enlace sin hotel) y del 3 (el vuelo: 6 de 27 graves del panel de la vara); el 1 y el 2b casi no aparecen. Propongo que, cuando Álvaro cierre el 0,5, el orden sea 4 → 3 → 1 → 2b → 5. Mientras tanto sigo con el 1, que no choca con lo suyo. Y como la partida en el panel de la vara es de 9 a 10 de 40, la meta de 5 y el punto de parada, fijados con el panel viejo, hay que volver a fijarlos.
- [x] Las dudas de negocio: decididas el 9-nov (abajo).

### Dudas de negocio

Salen de comparar la base y el código con lo que hace la persona en los episodios reales. Lo decidido entra a la vez en la base y en el juez, en el bloque 0.

**Decidido el 9-nov:**

| Duda | Decisión | Qué cambia |
| --- | --- | --- |
| Grupo mixto: un colombiano y un extranjero sin cédula de extranjería | Paga todo el grupo en USD | Nada: ya estaba decidido (26-oct) y es lo que dice la base. La persona hizo una excepción; el bot no la hace |
| Totales de un grupo | El bot no los da | Nada: ya estaba decidido (9 y 29-oct). Precio por persona, también en la tarjeta |
| Reservar para mañana pasadas las 4:30 | El cierre es firme | Ya estaba decidido (14-oct). El bot dice que para mañana ya está cerrado y ofrece el primer día que se puede reservar por la web (bloque 3). No pasa con un asesor |
| «Next Friday» dicho un jueves | Es mañana | Va a la referencia del juez. En el panel, Luna acertaba y el juez no: 3 graves de un cliente ciego se quedan solo con la regla del grupo |
| Quien ya reservó | El bot contesta lo que sabe | Contesta lo que está en la base (punto de encuentro, hora de recogida, qué llevar) y pasa con una persona lo demás. Cambiar la fecha, cancelar o cambiar el número de personas ya estaba decidido (21-oct): da la política y pasa directamente con un asesor. Bloque 4 |
| Largo de la respuesta | Breve y concisa, no párrafos largos | Regla nueva del plan y meta en la vara, cerca de la persona: unos 120 caracteres y pocas preguntas |
| Quien escribe por otros: una agencia, un instructor de otro centro, alguien que paga por otras personas | Como cualquier cliente | Mismo trato: precio por persona y su enlace, sin precio de agencia. Bloque 4 |
| Lo que la base no contesta | Según el tema | Pasan con una persona el clima de ese día (con el texto del 20-oct) y una recogida fuera de los puntos de siempre. La disponibilidad (siempre hay, 21-oct), los hoteles, los puntos de inmersión, qué llevar y la comida los contesta la base. Bloque 4 |

## Cómo se midió y qué límites tiene

**Todo sale de lo ya medido: el panel fijo de 40 clientes, sus juicios con Opus medium, seis tandas de clientes que reaccionan, 75 episodios reales y el historial de git.** No he tocado PRE ni el código del bot, y no he juzgado nada nuevo. Hice unas 50 llamadas cortas a Luna para ver si repite. La clasificación por familias incluye dos lecturas independientes, una a ciegas y una crítica. El 9-nov lo revisé todo otra vez, sin saldo: una lectura crítica desde cero, de un agente que no conocía mis conclusiones; una tabla de los 67 graves, uno a uno, con su bloque; y los 75 episodios reales leídos uno a uno.

**Lo que puede mover estas cifras:**

- **La causa de cada grave es una lectura, no una medida.** Por eso doy rangos. La tabla por grave de la clasificación a ciegas no apareció donde dijo guardarla, así que su recuento no se puede auditar. La tabla por grave del 9-nov sí se puede auditar, y una segunda lectura independiente coincide con ella en el 85 % de los graves (kappa 0,69) y en el 84 % del bloque (0,75).
- **Las previsiones son estimaciones.** Lo que quitaría cada bloque no está medido: la tabla por grave supone que cada uno se lleva todos sus graves.
- **El juez no sabe la hora en el panel.** Algunos graves de fechas pueden estar mal juzgados: esas vueltas corrieron de noche en Colombia.
- **La referencia cambió el 6-nov.** De la 0.58 a la 0.61 se comparan con la anterior. Los 67 graves usan la nueva, que incluye reglas decididas después de medir.
- **El panel empieza en la 0.58.** Lo anterior no se puede medir igual, así que no afirmo que los arreglos de antes no sirvieran.
- **Unas cuentas son por palabras.** Familias por versión, arreglos por familia y comentarios que citan un caso son aproximadas.
- **El texto guardado del escritor no es puro.** Puede llevar preguntas de plantilla, así que parte del 68 % es código corrigiendo a código.
- **Las tandas y los episodios reales son muestras.** Son 21 graves de versiones anteriores y 75 episodios hablando con personas.

**Sin resolver:** qué hacen las otras 48 señales de Jev, si Jev acierta con mensajes reales y cuánto falla el bot con ellos. Que Haiku no repite con la misma entrada ya está medido en el estudio de la lectura.
