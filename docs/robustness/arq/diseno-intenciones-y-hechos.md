# ARQ-1a: intenciones, hechos y redactor (diseño, 22-oct)

Plan general: `plan-hechos-por-codigo.md`. Aquí está el contrato que siguen arq-1b (interpretación), arq-1c (hechos) y
arq-1d (redactor).

## 1. Interpretación (arq-1b)

Cada parte con su herramienta, como pide la regla del 24-sep (Jev para opciones fijas; el modelo extrae valores):

- **Jev, qué intenciones trae el mensaje.** Una pregunta sí/no por intención, todas en la misma llamada que ya se hace
  (umbral 0,7, como `pide_precio`). Un mensaje puede traer varias.
- **El extractor, de qué actividad o actividades habla.** El campo `actividad_preguntada` pasa a ser una lista
  (`actividades_preguntadas`), para «¿cuánto cuestan el snorkel y el minicurso?». Si no nombra ninguna, se usa la del
  estado (la elegida o la última de la que preguntó).
- **El origen, la nacionalidad, las edades y el grupo** salen del estado, como hoy (extractor + Jev).

| Intención | Pregunta de Jev (resumen) | Ya existe |
|---|---|---|
| `precio` | cuánto cuesta una actividad nuestra | `pide_precio` |
| `incluye` | qué incluye un plan, o si incluye algo concreto | `pide_que_incluye` (ord-9) |
| `requisitos` | qué hace falta: requisitos, documentos, formularios, qué llevar, qué hacer antes | nueva |
| `horario` | horarios, punto de encuentro, recogida, regreso, duración, si se duerme en las islas | nueva |
| `disponibilidad` | si hay sitio o se opera una fecha, cómo y hasta cuándo se reserva | nueva |
| `edad` | si puede alguien de cierta edad, la edad mínima o máxima | nueva |
| `enlace` | el enlace para reservar o pagar | nueva |

Todo lo que no es ninguna de estas («¿qué se ve en los arrecifes?», «¿es seguro?») sigue en el RAG de hoy.

## 2. Hechos (arq-1c)

El código construye, para cada intención y cada actividad, un bloque de hechos con las reglas del negocio ya
aplicadas. Las fuentes son únicas: la tarifa en `pricing.json` (ord-3), las fichas en `services.json`, las políticas en
`policies.json` y el registro de actividades. **El modelo no elige ni calcula nada.**

Reglas que aplica el código, no el modelo:
- **Moneda:** COP a colombianos y residentes; USD al resto, si no se sabe o en un grupo mixto; una sola moneda.
- **Origen:** si se sabe, el plan de ese origen; si no, **las dos variantes** (Cartagena e islas), como hoy ord-7.
- **Edades:** la mínima y la máxima de la actividad, en cifra; con edades dadas, quién puede y quién no.
- **Planes con varios por origen** (las salidas de buceo y los paquetes): el plan base (2 inmersiones) si no se
  concreta, más la lista de los demás con su precio.
- **Colombianos:** el cierre lo hace un asesor, así que la intención `enlace` da el aviso de asesor en vez del enlace
  (decisión de Gadea).
- **«Aporte eco-social a DIVE TO HEAL»** va en lo que incluye (decisión de Gadea del 22-oct: se quita
  `_sanitize_includes`).

Forma de los hechos (por actividad e intención; ejemplo sin origen y sin nacionalidad):

```json
{"actividad": "minicourse", "nombre": "Minicurso de Buceo", "origen": null, "moneda": "USD",
 "precio": {"cartagena": {"online": "183 USD", "normal": "204 USD"}, "island": {"online": "134 USD", "normal": "149 USD"}},
 "incluye": {"cartagena": ["Tarifa de ingreso al Parque Nacional Natural", "Seguro obligatorio de buceo", "..."],
             "island": ["Recogida en hotel (si tiene acceso marítimo)", "..."]},
 "edad": {"minima": 10},
 "pregunta_pendiente": "origen"}
```

`pregunta_pendiente` es lo que el redactor debe preguntar al final (origen, nacionalidad o nada), y lo decide el código
(hoy lo hacen la puerta del origen y el flujo de reserva).

## 3. Redactor (arq-1d)

- **Cuándo:** si TODAS las intenciones del mensaje están en la tabla y hay actividad, contesta el redactor de hechos.
  Si hay alguna «otra», contesta el RAG de hoy, pero recibe los hechos de las intenciones cubiertas en lugar del
  catálogo entero (paso intermedio, para no perder lo que el RAG hace bien).
- **Qué recibe:** el mensaje, un resumen corto del estado, los hechos (JSON) y el estilo de Coral (el tono de siempre).
  **No** recibe el catálogo, ni las políticas enteras, ni las ~50 reglas: las que importan ya vienen aplicadas.
- **Qué se le pide:** contestar cada intención con TODOS sus hechos (las listas completas), sin añadir datos que no
  estén, en el idioma del cliente y con el tono de Coral; y, si hay `pregunta_pendiente`, terminar con esa pregunta.
- **Modelo:** Luna (decisión de Gadea). La prueba con gpt-5-mini es arq-0c, solo como contexto.
- **Flag:** `hechos_por_codigo`, apagado hasta medirlo en el banco fijo ×3 (por intención) y en su ronda core.

## 4. Validación (arq-3)

El código comprueba que la respuesta contiene cada hecho que debía (cada elemento de la lista, cada importe, la edad).
Si falta alguno, se rehace una vez diciendo cuál falta. Puede sustituir parte del juez de grounding: si solo hay
hechos del código, no hace falta preguntar a un modelo si la respuesta está respaldada.

## 5. Qué se retira después (arq-2c)

Cuando el redactor de hechos esté promocionado, sobran: la puerta del origen con sus variantes (`_origen_antes_del_precio`,
ord-7), la lista añadida de ord-9 (`listas_del_dato`), los avisos que ya cubran los hechos (días cerrados, grupo sin
cursos, edades) y las reglas equivalentes del prompt del RAG (arq-2a).
