# Fase LAT · Menos llamadas: bajar la latencia sin perder calidad

Decisión de Gadea, 24-oct-2026. Rumbo: **bajar la latencia, mantener o mejorar la calidad y reducir la complejidad.**

## Por qué

- **La calidad real no sube.** real-1 (golden completo, 116 diálogos, la mayoría de chats reales de WhatsApp) da 94,9 %
  y 82/116, frente al 95,8 % y 86/116 del 17-oct. La fase ARQ subió el G10 (examen sintético que ya hemos pasado 6
  veces), pero no las conversaciones reales. Es el mismo patrón que EX y GEN: lo visible sube, lo no visto se queda plano.
- **La latencia empeoró.** En el mismo G10 (225 turnos), antes y después de ARQ:

  | | 21-oct | 23-oct (nº 6) |
  |---|---|---|
  | Llamadas al modelo por turno | 6,4 | 7,9 (≈ 14 en los turnos lentos) |
  | Tokens de entrada por turno | 39.000 | 50.800 |
  | p90 / p95 | 8,2 / 9,0 s | 10,1 / 14,0 s |

  Entre el 87 % y el 95 % de cada turno es esperar al modelo: **la latencia es el número de llamadas en cadena.**

## Cómo es hoy un turno con pregunta

```
Mensaje del cliente
 │
 ├─ 1. ENTENDER (en paralelo, 0,5-1,5 s)
 │     Jev (señales + 10 intenciones) · extractor · extractor paso 6 · pregunta final · búsqueda
 │     + acuse / notas / reescritura, según el turno
 │     + RAG POR ADELANTADO: escribe una respuesta «por si acaso»  → se tira en el 68 %
 │     (en algunos turnos la extracción se hace dos veces)
 │
 ├─ 2. DECIDIR (código) y ESCRIBIR
 │     reserva ............ plantilla del flujo           5,0 llamadas · p50  2,0 s
 │     tabla .............. REDACTOR (Luna)               8,4 llamadas · p50  4,7 s
 │                            ├ falta un hecho → rehace (38 %)
 │                            └ dice «FALTA» → pasa al RAG
 │     tabla + otra cosa .. RAG con los hechos (Luna)    13,7 llamadas · p50 11,1 s
 │                            └ falta un hecho → rehace
 │     lo demás ........... RAG (Luna)                    9,1 llamadas · p50  6,1 s
 │
 └─ 3. DESPUÉS DE ESCRIBIR (en serie)
       revisor (DeepSeek; si falla, gpt-5.4-mini) · AVISO FINAL (Luna, ~2,3 s) · pregunta final · reescritura
```

Datos de real-1 (465 turnos):

- **El redactor no ahorra lo que debería.** En 68 de sus 79 turnos también escribió el RAG adelantado, que se tiró.
  Además rehace la respuesta en el 38 % y luego pasa por la misma cadena final. Por eso tarda 4,7 s frente a los 6,1 s
  del RAG.
- **El redactor es el camino que más falla por turno:** 19 fallos por cada 100 turnos, frente a 12 del RAG, 10 del RAG
  con hechos y 4,5 de la reserva.
- **El camino mezclado (RAG con hechos) es el más lento:** el escritor, el revisor y el aviso final salen ~2 veces por
  turno por los reintentos de completitud.
- **El RAG recibe turnos que no le tocan:** de los 112 que van al RAG sin la tabla, 36 son mensajes cortos del flujo
  («quiero bucear certificado», «cuánto cuesta», «desde Cartagena, voy solo», «me gustaría reservar»), con una p50 de
  6,3 s. Otros 23 son pases a un asesor.

## Cómo debería ser

```
Mensaje del cliente
 │
 ├─ 1. ENTENDER, una sola vez (en paralelo, ~0,7 s):  Jev  ‖  un solo extractor
 │
 ├─ 2. DECIDIR (código, 0 s) → UN solo camino, sin «por si acaso»
 │     reserva o dato del flujo ...... plantilla                         ~3 llamadas · ~2 s
 │     tabla (venga sola o mezclada) . UN escritor con los hechos         ~3-4 llamadas · ~3-3,5 s
 │     pregunta abierta .............. búsqueda + UN escritor             ~4 llamadas · ~4 s
 │
 ├─ 3. ESCRIBIR: una llamada que ya trae el aviso y la pregunta final
 │
 └─ 4. COMPROBAR POR CÓDIGO: precios, enlaces y hechos; lo que falte lo añade el código
       revisor con modelo solo en el RAG, cuando la respuesta trae datos que no vienen de los hechos
```

**Meta:** de 8-14 llamadas a **3-5 por turno**, con **p90 ≤ 7 s** y la calidad de real-1 igual o mejor.

## Vara de medir

- **Calidad:** real-1 (~45 min y ~3 $ con el juez en paralelo). Un cambio se queda solo si la calidad no baja más que el
  ruido (±3-4 diálogos). Las charlas en directo (g-3b) son la segunda medida.
- **Latencia:** p90 del cliente en las métricas de la ronda (`--metricas`), y llamadas y tokens por turno.
- **El G10 se congela:** solo como control final antes de ir a Andrés.

## Reglas

1. Un cambio cada vez, con flag y A/B: banco propio ×3 (frases nuestras) y real-1.
2. **Ningún cambio nuevo puede añadir llamadas.** Lo que se promociona baja el p90 o, como mínimo, no lo sube.
3. Al promocionar se borra el camino viejo (como sim-5): menos flags, menos caminos.
4. Sin parches ni regex; arreglar por causa. Nada más caro que gpt-5-mini sin permiso de Gadea.
5. Avisar en Coral antes de tocar ficheros compartidos; el que quede libre coge la siguiente tarea del orden.

## Orden

| # | Tarea | Qué quita o arregla | Reparto propuesto |
|---|---|---|---|
| lat-0a | «¿Cómo pago?» lleva el enlace | Fallo nuevo de real-1 (3 diálogos) | Gadea |
| lat-0b | Sin la repregunta «¿Eres buzo certificado?» | Fallo nuevo de real-1 (27 respuestas frente a 18) | Gadea |
| sim-5 | Limpieza de flags promocionados | Complejidad (~106 flags y sus caminos viejos) | Álvaro |
| lat-1 | Un solo escritor por turno | El RAG adelantado que se tira (68 %) | siguiente libre |
| lat-7 | Los mensajes cortos del flujo no van al RAG | 36 turnos cortos y 23 pases que hoy pasan por el RAG (6 s → ~2 s) | Álvaro (flujo y extractor) |
| lat-2 | El redactor escribe a la primera | Las segundas redacciones (38 %): el código completa | siguiente libre |
| lat-3 | Mensajes mezclados: una sola redacción | El camino de 13,7 llamadas y p50 de 11 s | siguiente libre |
| lat-4 | El aviso final dentro de la redacción o por código | La llamada de Luna después de escribir (~2,3 s) | Gonzalo (arq-7c) |
| lat-5 | La cadena después de escribir | Revisor, pregunta final y reescritura en serie (2-3 s) | Gonzalo |
| lat-6 | Un solo extractor | Dos llamadas a Haiku en cada turno (y a veces dos veces) | Álvaro |
| lat-8 | Ampliar la tabla con lo que se repite en los chats reales | Turnos del RAG que podrían salir del dato. Antes, contar cuántos turnos reales cubre cada tema (cambios y cancelaciones, hoteles, fotos, equipaje…) y empezar por los que más pesan | después de lat-2 |
| lat-9 | Un solo escritor: juntar el redactor y el RAG | Cuatro caminos de escritura → uno. El escritor recibe los hechos del código y, solo si hace falta, lo que encuentra la búsqueda | al final, sobre lat-1..lat-8 |

lat-8 y lat-9 van al final a propósito: antes de ampliar el redactor hay que hacerlo fiable y rápido (lat-1, lat-2,
lat-4). Hoy es el camino que más falla por turno.
