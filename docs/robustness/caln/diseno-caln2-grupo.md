# CALN-2 · El grupo como lista de personas — diseño (27-oct)

Para Gadea y el equipo, antes de tocar código. Fase CALN (Plan Coral): calidad en conversaciones nuevas y difíciles,
sin perder la arquitectura delgada y sin parches. Gadea (27-oct): «el modelo del grupo, importante».

## 1. Qué pasa hoy

El grupo vive en **unos 19 campos** del estado, añadidos uno a uno, cada uno con su regla de cuándo se rellena y
cuándo se consume:

| Qué guarda | Campos |
|---|---|
| Cuántos son | `detected_group_size` |
| Quién hace qué | `detected_group_allocation` (`{actividad: n}`), `mixed_cart` (el carrito) |
| Edades y niños | `detected_ages`, `kids_under_8_count`, `kids_eight_to_ten_count`, `kids_count`, `kids_age_group` |
| Esperas («preguntar luego») | `pending_companion_activity`, `pending_companion_queue`, `needs_companion_activity`, `companion_activity_deferred`, `pending_undecided_qty`, `pending_companion_in_group`, `pending_split_total` |
| Banderas sueltas de otra persona | `acompanante_sin_certificar`, `acompanante_certificado_inactivo`, `solo_traveler_confirmed`, `mixed_nationality_notice` |

Son **~290 usos en 13 ficheros**, y 78 sitios más con las preguntas del acompañante, la cantidad y las edades. Los
comentarios cuentan su historia: «Auditoría 2026-07-23», «tarea 7a», «hallazgo H», «circuit-breaker»… Cada caso nuevo
trajo un campo y una regla, y **el orden en que se consumen decide qué se pregunta**: de ahí los bucles (la misma
pregunta del acompañante una y otra vez), las preguntas que se pierden y los totales que no cuadran con el reparto.

Lo que sale en las rondas: el total que no cuadra («somos 3» y el reparto suma 2); quien se suma o no al grupo («viene
mi novio»); quién está certificado y quién no, persona a persona; los niños y sus edades; «voy con una amiga que no está
certificada» = 2; el refresher de una sola persona.

**Peso:** de los 95 diálogos visibles, 14 son de grupo; pasan sin ningún fallo 7-10 (50-70 %), frente al ~73 % del
resto; son 5-9 de los 30-40 fallos visibles por ronda. En el sparring y en los 75 reales pesarán más: las familias y los
grupos de amigos son lo normal en este negocio.

## 2. Propuesta

**Una sola lista de personas en el estado**, y todo lo demás DERIVADO de ella por código:

```
personas = [
  {"quien": "cliente", "actividad": "certified_diving", "certificado": True,  "edad": None, "mas_de_2_anos": False},
  {"quien": "amiga",   "actividad": None,               "certificado": False, "edad": None, "mas_de_2_anos": None},
]
total_dicho = 3        # lo que dijo el cliente («somos 3»), aunque aún no sepamos nada de la tercera persona
```

- **El extractor** devuelve CAMBIOS sobre la lista, con su cita: añadir una persona («vengo con mi amiga»), fijar un dato
  de una persona («ella no está certificada», «el mayor tiene 10»), o el total («somos 3»). Es lo que ya hace a medias con
  `group_size`, `group_allocation` y los `acompanante_*`.
- **El código deriva** (funciones puras, sin estado propio): el total (`max(len(personas), total_dicho)`), el reparto por
  actividad, quién falta por decidir, los niños por tramo de edad, quién necesita refresher, el carrito y su precio.
- **La pregunta de la reserva sale de una sola función:** la primera persona a la que le falta un dato, en un orden
  fijo («¿y tu amiga qué le gustaría hacer?»); «¿cuántos sois?» solo si falta el total.
- **Fuera:** las siete esperas, los contadores de niños y las banderas de «otra persona» (las da la lista). El carrito se
  deriva de la lista en cada turno, en vez de mantenerse en paralelo.

Qué gana: un dato de una persona va a su sitio y ya está; no hay colas que consumir en orden; un total que no cuadra se
ve en la lista (personas sin datos) y se pregunta por ellas, sin adivinar.

## 3. Por pasos, cada uno medido

| Paso | Qué | Cómo se mide |
|---|---|---|
| 0 | Banco de grupos (~30 turnos del golden visible y del sparring de grupos, nunca del oculto) y la comprobación por código del total, el reparto y quién falta (CALN-0) | — |
| 1 | La lista como fuente; los campos viejos se derivan de ella (un adaptador): el resto del código no cambia | Suite + foto de equivalencia + banco |
| 2 | El extractor escribe los cambios por persona, con cita | Banco ex0 (inventos y perdidos) + banco de grupos ×2 |
| 3 | La pregunta desde la lista, en una función; fuera las esperas | Banco de grupos ×2 + comprobación por código |
| 4 | Limpieza: fuera los campos viejos y su código | Suite + foto de equivalencia; ronda completa al integrar |

## 4. Riesgos

- Es el cambio más grande de CALN: toca el extractor, el flujo de la reserva y el carrito. Por eso va con un adaptador
  (paso 1): hasta el paso 3 el resto del código lee lo de siempre.
- El extractor tiene que distinguir personas («mi amiga», «mi hermano», «los niños»): si se inventa personas o datos, el
  banco ex0 lo dirá (EXT-SALIDA enseñó que pequeños cambios de su salida mueven los inventos).
- Partir los módulos gigantes (Álvaro) queda detrás: este cambio reestructura justo ese código.

## 5. Lo que necesito de Gadea

1. **¿Vale el enfoque?** Una lista de personas en el estado y todo lo demás derivado por código.
2. **Personas sin decidir:** «somos 3 y uno no está certificado». Hoy se le recomienda al que no está certificado
   (minicurso o snorkel) y elige el cliente. ¿Se mantiene así, persona a persona?
3. **Orden de las preguntas:** ¿primero todas las personas (quién hace qué) y después el resto de la reserva (origen,
   seguridad, nacionalidad), o como hoy, mezclado?
