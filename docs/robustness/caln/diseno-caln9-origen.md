# CALN-9 · Lo que depende del origen, separado por el código — diseño (30-oct)

Para Gadea y el equipo, antes de tocar código. Encargo de Gadea (#2581, #2591, #2619): «que el escritor reciba ya
separado por origen, desde el código, lo que depende del origen (lo que incluye: almuerzo, lancha, recogida; horarios).
Así no lo escribe sin rótulo ni se contradice». Es lo que bloqueó el paso 4 (2) de CALN-3 (#2553, #2558). Regla de
CALN-8: cada pieza dice qué quita.

## 1. Qué pasa hoy

- Cada plan tiene DOS servicios en `services.json`: el de Cartagena (`2_dives_1_day`) y el de las islas
  (`2_dives_1_day_already_on_island`), cada uno con su `included`, `not_included` e `itinerary`. Las fichas de la base
  (`kb_v2.ficha_servicio`) van rotuladas («— saliendo desde Cartagena» / «— ya en las islas») y llevan
  `metadata.origin`.
- Las dos fichas de un plan **no comparten casi ningún texto**: lo incluido, lo no incluido y el itinerario están
  redactados aparte (medido en 2 inmersiones, minicurso, snorkel y 4 inmersiones: 0-1 líneas comunes). Juntarlas en
  «lo común + lo que cambia» por texto no sirve.
- Con el origen sabido, la búsqueda solo BAJA la ficha del otro origen (`vector_store.penalizar_otro_origen`, rag-3):
  si pasa el umbral, llega igual al escritor.
- Sin el origen, llegan las dos y el escritor escribe lo de una sin rótulo: «incluye almuerzo» junto a los precios de
  las islas (frances-anticipacion), «lancha Cartagena-Islas incluida» estando en las islas (precio-desde-islas),
  Barú tratado como islas en el primer turno (sparring s29c).

## 2. Propuesta, en dos pasos medidos

**9a · Con el origen sabido, solo su ficha.** Después de la búsqueda (`rag_answer`, tras
`_expand_with_parent_context`), fuera las fichas de servicio (`source == "services"`) cuyo `metadata.origin` no es el
del cliente. Las FAQ y las políticas se quedan. Si el mensaje pregunta por el otro origen («¿y desde las islas qué
incluye?»), no se quita (lo dice Jev con `customer_place`, o el mensaje lo nombra).
Quita: la mezcla en los turnos con origen sabido y los tokens de la ficha que sobra.

**9b · Sin el origen, la pieza de lo que cambia.** El código arma, de `services.json`, para los planes en juego (los de
la pieza de cotizar, `cotizar.bloques_de_los_servicios`), un bloque corto rotulado por origen con solo lo que depende
de él: cómo se llega (lancha desde el Muelle de la Bodeguita a las 8:00 / recogida en el hotel 9:30-9:45 si tiene acceso
marítimo), el almuerzo (incluido / no incluido), la vuelta (Cartagena 3:00 p.m. / al hotel 12:00-13:00). Va en los
hechos del escritor como la pieza de precios, y las dos fichas completas dejan de ir juntas: va la pieza y, del plan,
lo que no depende del origen.
Quita: una ficha entera por plan cuando el origen no se sabe, y la base para quitar después la puerta del origen
(paso 4 (2) de CALN-3), que solo existía para borrar lo que el escritor escribía de un origen sin rótulo.

## 3. Cómo se mide

- 9a: bancos p/q/r y la mini-ronda de los visibles afectados (los 12 de la puerta de Gonzalo, frances-anticipacion,
  precio-desde-islas, reserva-paquete-5), una pasada frente a PRE; juez solo en los afectados, con caché.
- 9b: lo mismo más una tanda de sparring con clientes que no dicen el origen (Barú, «staying in Cartagena», hotel sin
  nombre).
- En los dos: 0 interruptores nuevos; tokens de entrada del escritor (deberían bajar); foto de prompts.

## 4. Riesgos

- Que la ficha del otro origen haga falta para comparar («¿sale más barato desde las islas?»): el precio lo da la pieza
  de cotizar con los dos orígenes; lo que incluye, 9b.
- El refresher y los cursos tienen fichas propias por origen: entran en la misma regla (mismo `metadata.origin`).
