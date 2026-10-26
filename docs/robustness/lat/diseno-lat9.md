# LAT-9 · Un escritor — diseño (26-oct)

Para Gadea y el equipo. Antes de tocar código (decisión de Gadea del 26-oct). Mapa del código de hoy hecho sobre
`feature/integra-sim7-gadea`.

## 1. Qué pasa hoy

Un turno puede escribirse por **seis caminos**:

| Camino | Cuándo | Llamadas |
|---|---|---|
| Plantillas del flujo (acuse «¡Perfecto! 🙌», pregunta del dato, tarjeta, pases) | la reserva | ninguna |
| Redactor de hechos | todo lo que pide está en la tabla y se sabe la actividad | Luna (+ 2.ª redacción si sale en otro idioma) |
| RAG con hechos («al_rag») | mensaje mezclado, o el redactor dijo FALTA | reescritura + búsqueda + Luna + revisor (+ 2.º Luna y 2.º revisor si rechaza) |
| RAG puro | sin intenciones de la tabla | ídem |
| RAG «lo demás» antes de un pase | pase a un asesor | ídem |
| RAG rehecho sin precio | la tarjeta ya lleva el precio | ídem |

Además, **dos textos se pegan** en un mismo mensaje: la respuesta del RAG + la pregunta del dato que falta (o la
respuesta adelantada delante de la plantilla), y la pregunta final del turno **no tiene dueño**: la del origen del
código, la que trae la respuesta si acaba en «?», o la de la plantilla; el aviso se mete delante de la que quede.

Consecuencias que vemos en la deuda:
- textos robóticos o repetidos (el acuse en el 32 % de las respuestas; la misma pregunta dos veces);
- el escritor que no usa lo que ya sabemos (en «Ubuntu» volvió a preguntar si sale de Cartagena);
- la misma regla escrita en muchos prompts: la **moneda en 6 sitios**, el origen en 4, «sin totales» en 3, el idioma
  en 4; el RAG tiene reglas que el redactor no tiene (no adivinar, abrir con la respuesta, varios planes);
- un turno que el redactor no sabe contestar paga **redactor + RAG completo**; el camino mezclado llega a 11 s.

## 2. Qué proponemos

**Un turno, una redacción.** El código decide QUÉ se dice; un solo escritor (Luna) lo pone en palabras:

```
            ┌─ hechos de la tabla (si hay intenciones cubiertas)
mensaje ─┬─>│  búsqueda en la base (solo si trae algo que la tabla no cubre)
 Jev +   │  │  lo que ya sabemos del cliente (origen, hotel, personas, nacionalidad)
 extractor  │  la SIGUIENTE PREGUNTA que decide el código (dato pendiente u origen)
         │  └─ el AVISO del turno (avisos.json)
         │            │
         │        UN escritor (Luna) ── un texto
         │            │
         │        comprobación por código: importes del catálogo, enlaces, que estén los hechos pedidos y la
         │        pregunta decidida, idioma; revisor con modelo solo si hay datos que no vienen de los hechos (lat-5)
         │
         └─ respuesta que es SOLO un dato («somos 4», «desde Cartagena») ─> plantilla del flujo, sin modelo (como hoy)
```

- **Un prompt**: una base común (persona, seguridad, tono) y las reglas del negocio en UN sitio, generadas de
  `data/knowledge_base/decisiones.json` (moneda, origen y precio, sin totales, no adivinar, idioma...). Fuera las seis
  copias de la moneda.
- **La pregunta final la decide el código y la escribe el escritor**, dentro de su texto. Fuera las costuras
  (`_answer_question`, `_prepend_parallel_answer`, `_answer_already_asks`, la puerta del origen que recorta importes).
- **La tarjeta de la reserva y los textos fijos de seguridad siguen siendo código** (importes exactos, sin modelo).
- **Desaparecen** como caminos aparte: el redactor de hechos, el RAG con hechos, el RAG «lo demás» y el rehecho sin
  precio; el doble pago de FALTA; el camino mezclado de 11 s. Las marcas `[[incluye]]` del redactor (listas copiadas
  tal cual del dato) se conservan dentro del escritor único.

## 3. Por pasos, cada uno medido

| Paso | Qué | Cómo se mide |
|---|---|---|
| 0 | Banco fijo de lat-9: ~40 turnos del golden visible y de las tandas rotativas (nunca del oculto): pregunta de la tabla, mezclada, sin intención, dato + pregunta, despedida, corrección, post-venta | — |
| 1 | Prompt único: la base común y las reglas desde decisiones.json, compartidos por el redactor y el RAG (sin cambiar caminos) | banco ×3 |
| 2 | El escritor recibe la siguiente pregunta y el aviso y los escribe él; fuera las costuras | banco ×3 |
| 3 | Redactor y RAG en una llamada: hechos siempre, búsqueda solo si hace falta; fuera FALTA, «lo demás» y el rehecho | banco ×3 + **ronda completa** (golden + tanda) |
| 4 | Limpieza: caminos muertos fuera y partir los módulos gigantes (lat-10) | suite + foto de equivalencia |

Éxito: una sola llamada de escritura por turno (salvo los datos sueltos, que van por plantilla), p90 ≤ 7 s, y el
criterio de cierre de LAT (2 real-1 ≥ 82/116, oculto ≥ 90 % de criterios); bajan el acuse robótico y las repreguntas.

## 4. Riesgos

- Un prompt más grande para Luna: más instrucciones que cumplir y algo más de latencia por llamada (se compensa con
  menos llamadas). Si Luna no llega, se mide un modelo mayor **solo con permiso de Gadea**.
- Es el cambio más grande de LAT: por eso va por pasos, cada uno en su commit y con su banco.
- Choca con el trabajo del acuse (Gonzalo): su arreglo vale para las respuestas que son solo un dato; lo demás pasa al
  escritor en el paso 2.

## 5. Lo que necesito de Gadea

1. **Cuando el cliente no contesta con un dato** (pregunta sin «?», se despide, corrige algo), ¿escribe el escritor
   (texto natural, ~1,2 s más) o sigue la plantilla del flujo? Recomendado: el escritor; la plantilla, solo para los
   datos sueltos.
2. Visto bueno al orden por pasos (0 → 4), en 2-3 días de trabajo.
